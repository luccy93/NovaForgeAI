"""C1 tests — Governed integrations foundation (Volume 70 Commit 1).

Models, tenant/workspace isolation, authorization, credential secrecy,
connection lifecycle, bounded API execution, SSRF/private-IP/redirect
protection, timeouts/size limits, rate limiting, webhook registration /
signatures / replay / idempotency / retry / dead-letter, events, API,
SDK, CLI, audit and observability hooks.
"""

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.database import Base
from app.core.events import EventType
from app.integrations.common import ValidationError, idempotency_key
from app.integrations.governed_models import (
    Integration,
    IntegrationAuditLog,
    IntegrationConnection,
    IntegrationCredential,
    IntegrationExecution,
    IntegrationWebhook,
    IntegrationWebhookDelivery,
)
from app.integrations.network_policy import NetworkPolicyError, scrub, validate_url
from app.integrations.registry import (
    create_version,
    get_integration,
    list_integrations,
    list_versions,
    register_integration,
    set_integration_status,
    update_integration,
)
from app.integrations.connections import (
    create_connection,
    get_connection,
    list_connections,
    resolve_credential_material,
    rotate_credential,
    set_connection_status,
    store_credential,
)
from app.integrations.webhooks import (
    deliver_attempt,
    delivery_history,
    enqueue_delivery,
    get_webhook,
    list_webhooks,
    register_webhook,
    set_webhook_status,
    verify_inbound,
)
from app.integrations.workers import execute_operation, process_pending_deliveries, run_health_check


async def _integration(db, org_id, **over):
    kw = {"name": f"int-{uuid.uuid4().hex[:8]}", "integration_type": "api",
          "provider": "acme", "capabilities": ["execute", "health"]}
    kw.update(over)
    return await register_integration(db, org_id, kw.pop("name"), kw.pop("integration_type"), **kw)


# ─── Models & migrations ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_governed_tables_registered():
    for table in ("integrations", "integration_versions", "integration_connections",
                  "integration_credentials", "integration_executions",
                  "integration_health_checks", "integration_webhooks",
                  "integration_webhook_deliveries", "integration_api_subscriptions",
                  "integration_audit_log"):
        assert table in Base.metadata.tables


@pytest.mark.asyncio
async def test_migration_chain():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "m0040", "backend/alembic/versions/0040_integrations_foundation.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "0040_integrations_foundation"
    assert module.down_revision == "0039_finops_intelligence"
    assert "integrations" in module.INTEGRATIONS_TABLES


# ─── Registry ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_and_lifecycle(db, org_id):
    created = await _integration(db, org_id)
    assert created["status"] == "ACTIVE"
    assert created["capabilities"] == ["execute", "health"]
    fetched = await get_integration(db, org_id, created["id"])
    assert fetched["name"] == created["name"]
    # Duplicate name rejected.
    with pytest.raises(ValidationError):
        await register_integration(db, org_id, created["name"], "api")
    # Undeclared capability rejected.
    with pytest.raises(ValidationError):
        await register_integration(db, org_id, f"x-{uuid.uuid4().hex[:6]}", "api",
                                   capabilities=["mind_read"])
    disabled = await set_integration_status(db, org_id, created["id"], "DISABLED")
    assert disabled["status"] == "DISABLED"
    with pytest.raises(ValidationError):
        await set_integration_status(db, org_id, created["id"], "BOGUS")


@pytest.mark.asyncio
async def test_version_history_immutable(db, org_id):
    created = await _integration(db, org_id)
    v2 = await create_version(db, org_id, created["id"], "2.0.0",
                              contract={"endpoints": ["/v2"]}, compatibility="breaking")
    assert v2["version"] == "2.0.0"
    versions = await list_versions(db, org_id, created["id"])
    assert versions["total"] == 2  # 1.0.0 seeded at registration + 2.0.0
    with pytest.raises(ValidationError):
        await create_version(db, org_id, created["id"], "2.0.0")


@pytest.mark.asyncio
async def test_tenant_and_workspace_isolation(db, org_id):
    other = str(uuid.uuid4())
    await _integration(db, org_id, workspace="ws-a")
    mine = await list_integrations(db, org_id)
    theirs = await list_integrations(db, other)
    assert mine["total"] == 1
    assert theirs["total"] == 0
    with pytest.raises(Exception):
        await get_integration(db, other, mine["items"][0]["id"])


# ─── Network policy ──────────────────────────────────────────────────────────


def test_ssrf_localhost_blocked():
    with pytest.raises(NetworkPolicyError):
        validate_url("http://localhost:8000/api")
    with pytest.raises(NetworkPolicyError):
        validate_url("http://127.0.0.1:9000/x")


def test_ssrf_private_ranges_blocked():
    for url in ("http://10.0.0.5/", "http://192.168.1.1/", "http://172.16.0.9/",
                "http://169.254.169.254/latest/", "http://[::1]/", "http://0.0.0.0/"):
        with pytest.raises(NetworkPolicyError):
            validate_url(url)


def test_ssrf_metadata_host_blocked():
    with pytest.raises(NetworkPolicyError):
        validate_url("http://metadata.google.internal/computeMetadata/v1/")


def test_ssrf_schemes_and_userinfo_blocked():
    for url in ("file:///etc/passwd", "ftp://example.com/x", "gopher://x/",
                "http://user:pass@93.184.216.34/", "not-a-url", "http:///"):
        with pytest.raises(NetworkPolicyError):
            validate_url(url)


def test_ssrf_unresolvable_denied():
    with pytest.raises(NetworkPolicyError):
        validate_url("http://nonexistent.invalid/")


def test_allowlist_enforced():
    with pytest.raises(NetworkPolicyError):
        validate_url("http://93.184.216.34/", allowlist=["api.github.com"])
    assert validate_url("http://93.184.216.34/", allowlist=["93.184.216.34"])


def test_scrub_hides_query():
    assert "secret" not in scrub("https://api.example.com/x?token=secret")


# ─── Credentials ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_credential_lifecycle_and_secrecy(db, org_id, crypto_key):
    integration = await _integration(db, org_id)
    conn = await create_connection(db, org_id, integration["id"], endpoint_ref="https://93.184.216.34/v1")
    cred = await store_credential(db, org_id, "api_key", "sk-live-123",
                                  connection_id=conn["id"],
                                  auth_config={"header": "X-Api-Key"})
    assert cred["secret_ref"].startswith("enc:v1:")
    assert "sk-live-123" not in str(cred)
    # Ciphertext at rest, plaintext nowhere in the serialized form.
    row = (await db.execute(select(IntegrationCredential).where(
        IntegrationCredential.id == uuid.UUID(cred["id"])))).scalar_one()
    assert row.encrypted_material != "sk-live-123"
    assert cred["material_hint"].startswith("sk-l")
    # Server-side resolution works for execution use.
    material = await resolve_credential_material(db, org_id, cred["id"], purpose="test", actor="t")
    assert material == "sk-live-123"
    # Rotation revokes the old row.
    rotated = await rotate_credential(db, org_id, cred["id"], "sk-live-456", actor="t")
    assert rotated["id"] != cred["id"]
    old = (await db.execute(select(IntegrationCredential).where(
        IntegrationCredential.id == uuid.UUID(cred["id"])))).scalar_one()
    assert old.status == "REVOKED"


@pytest.mark.asyncio
async def test_credential_requires_encryption(db, org_id, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "encryption_master_key", None, raising=False)
    with pytest.raises(ValidationError):
        await store_credential(db, org_id, "api_key", "sk-x")


@pytest.mark.asyncio
async def test_connection_lifecycle(db, org_id):
    integration = await _integration(db, org_id)
    conn = await create_connection(db, org_id, integration["id"], workspace="ws1",
                                   endpoint_ref="https://93.184.216.34/v1")
    assert conn["status"] == "ACTIVE"
    assert conn["credential_id"] is None
    fetched = await get_connection(db, org_id, conn["id"])
    assert fetched["workspace"] == "ws1"
    # SSRF-checked endpoint.
    with pytest.raises(NetworkPolicyError):
        await create_connection(db, org_id, integration["id"], endpoint_ref="http://169.254.169.254/")
    # Disabled integration refuses new connections.
    await set_integration_status(db, org_id, integration["id"], "DISABLED")
    with pytest.raises(ValidationError):
        await create_connection(db, org_id, integration["id"])
    listed = await list_connections(db, org_id)
    assert listed["total"] == 1


# ─── Bounded execution ───────────────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, status_code=200, content=b'{"ok": true}'):
        self.status_code = status_code
        self.content = content
        self.headers = {"Content-Type": "application/json"}


class _FakeClient:
    seen_auth: list = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def request(self, method, url, headers=None, content=None):
        _FakeClient.seen_auth.append((headers or {}).get("Authorization"))
        return _FakeResponse()


@pytest.mark.asyncio
async def test_execute_operation_managed_auth(db, org_id, crypto_key, monkeypatch):
    import app.integrations.outbound as outbound

    integration = await _integration(db, org_id)
    conn = await create_connection(db, org_id, integration["id"], endpoint_ref="https://93.184.216.34/v1")
    await store_credential(db, org_id, "bearer", "tok-abc", connection_id=conn["id"],
                           auth_config={"scheme": "Bearer"})
    monkeypatch.setattr("httpx.AsyncClient", _FakeClient)
    result = await execute_operation(db, org_id, conn["id"], "list",
                                     method="GET", path="items",
                                     idempotency_key="exec-1", actor="tester")
    assert result["status"] == "SUCCESS"
    assert _FakeClient.seen_auth[-1] == "Bearer tok-abc"
    # Idempotent retry returns the same row.
    again = await execute_operation(db, org_id, conn["id"], "list",
                                    method="GET", path="items",
                                    idempotency_key="exec-1", actor="tester")
    assert again["id"] == result["id"]
    assert again.get("deduplicated") is True
    rows = (await db.execute(select(IntegrationExecution).where(
        IntegrationExecution.tenant == org_id))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_execute_rejects_destructive_by_default(db, org_id, crypto_key):
    integration = await _integration(db, org_id)
    conn = await create_connection(db, org_id, integration["id"], endpoint_ref="https://93.184.216.34/v1")
    with pytest.raises(ValidationError):
        await execute_operation(db, org_id, conn["id"], "wipe", method="DELETE", actor="t")


@pytest.mark.asyncio
async def test_execute_rejects_bad_timeout(db, org_id):
    integration = await _integration(db, org_id)
    conn = await create_connection(db, org_id, integration["id"], endpoint_ref="https://93.184.216.34/v1")
    with pytest.raises(ValidationError):
        await execute_operation(db, org_id, conn["id"], "x", method="GET", timeout=500.0, actor="t")


@pytest.mark.asyncio
async def test_outbound_rate_limit_enforced(monkeypatch):
    import app.integrations.outbound as outbound

    async def _deny(key, max_requests, window_seconds=60):
        return False, 0

    monkeypatch.setattr("app.core.redis.rate_limit_check", _deny)
    with pytest.raises(ValidationError):
        await outbound.execute(tenant="t", method="GET", url="https://93.184.216.34/")


@pytest.mark.asyncio
async def test_outbound_strips_caller_auth(monkeypatch):
    import app.integrations.outbound as outbound

    seen = {}

    class _Cap(_FakeClient):
        async def request(self, method, url, headers=None, content=None):
            seen.update(headers or {})
            return _FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient", _Cap)
    result = await outbound.execute(tenant="t", method="GET", url="https://93.184.216.34/",
                                    headers={"Authorization": "Bearer caller-smuggled"})
    assert result["status_code"] == 200
    assert "Authorization" not in seen


@pytest.mark.asyncio
async def test_outbound_response_cap(monkeypatch):
    import app.integrations.outbound as outbound

    class _Big(_FakeClient):
        async def request(self, method, url, headers=None, content=None):
            return _FakeResponse(content=b"x" * 100)

    monkeypatch.setattr("httpx.AsyncClient", _Big)
    with pytest.raises(ValidationError):
        await outbound.execute(tenant="t", method="GET", url="https://93.184.216.34/",
                               max_response_bytes=10)


# ─── Webhooks ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_webhook_register_and_status(db, org_id, crypto_key):
    hook = await register_webhook(db, org_id, "orders", "https://93.184.216.34/hook",
                                  events=["order.created"], signing_secret="whsec-1")
    assert hook["status"] == "ACTIVE"
    assert hook["credential_id"] is not None
    # Secret material never serialized.
    assert "whsec-1" not in str(hook)
    fetched = await get_webhook(db, org_id, hook["id"])
    assert fetched["url"] == "https://93.184.216.34/hook"
    with pytest.raises(ValidationError):
        await register_webhook(db, org_id, "bad", "http://127.0.0.1/hook")
    disabled = await set_webhook_status(db, org_id, hook["id"], "DISABLED")
    assert disabled["status"] == "DISABLED"


def test_webhook_signature_and_replay():
    payload = {"order": 1}
    assert verify_inbound(payload, "bogus", "whsec-1") is False
    assert verify_inbound(payload, "", "whsec-1") is False
    from app.core.webhooks import WebhookService
    sig = WebhookService.sign_payload(payload, "whsec-1")
    assert verify_inbound(payload, sig, "whsec-1", delivery_id=f"dl-{uuid.uuid4().hex}") is True
    # Replay of the same delivery id is rejected.
    assert verify_inbound(payload, sig, "whsec-1", delivery_id="dl-replay-x") is True
    assert verify_inbound(payload, sig, "whsec-1", delivery_id="dl-replay-x") is False


@pytest.mark.asyncio
async def test_delivery_retry_and_idempotency(db, org_id, monkeypatch):
    import app.integrations.webhooks as webhooks_mod

    hook = await register_webhook(db, org_id, "orders2", "https://93.184.216.34/hook",
                                  events=["order.created"])
    first = await enqueue_delivery(db, org_id, hook["id"], "order.created", {"order": 1},
                                   delivery_id="dl-1")
    assert first["status"] == "PENDING"
    again = await enqueue_delivery(db, org_id, hook["id"], "order.created", {"order": 1},
                                   delivery_id="dl-1")
    assert again.get("deduplicated") is True

    calls = {"n": 0}

    class _Fail(_FakeClient):
        async def request(self, method, url, headers=None, content=None):
            calls["n"] += 1
            return _FakeResponse(status_code=500, content=b"err")

    async def _fake_execute(**kwargs):
        resp = await _Fail().request(kwargs.get("method"), kwargs.get("url"),
                                     headers=kwargs.get("headers"), content=kwargs.get("body"))
        return {"status_code": resp.status_code, "bytes": len(resp.content),
                "attempts": 1, "latency_ms": 1}

    monkeypatch.setattr("app.integrations.outbound.execute", _fake_execute)
    for _ in range(5):
        await deliver_attempt(db, org_id, "dl-1", {"order": 1})
    final = (await db.execute(select(IntegrationWebhookDelivery).where(
        IntegrationWebhookDelivery.tenant == org_id,
        IntegrationWebhookDelivery.delivery_id == "dl-1"))).scalar_one()
    assert final.status == "DEAD_LETTER"
    assert final.attempts == 5
    history = await delivery_history(db, org_id, hook["id"])
    assert history["total"] == 1


@pytest.mark.asyncio
async def test_delivery_worker_processes_due(db, org_id, monkeypatch):
    import app.integrations.webhooks as webhooks_mod

    hook = await register_webhook(db, org_id, "orders3", "https://93.184.216.34/hook",
                                  events=["order.created"])
    await enqueue_delivery(db, org_id, hook["id"], "order.created", {"order": 2},
                           delivery_id="dl-2")

    async def _ok(**kwargs):
        return {"status_code": 200, "bytes": 2, "attempts": 1, "latency_ms": 1}

    monkeypatch.setattr("app.integrations.outbound.execute", _ok)
    from app.integrations.workers import process_pending_deliveries
    results = await process_pending_deliveries(db, org_id, payloads={"dl-2": {"order": 2}})
    assert results and results[0]["status"] == "DELIVERED"


# ─── Health ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_check_unknown_without_target(db, org_id):
    integration = await _integration(db, org_id)
    result = await run_health_check(db, org_id, integration["id"])
    assert result["status"] == "UNKNOWN"


# ─── Events, audit, SDK, CLI ─────────────────────────────────────────────────


def test_integration_event_types_registered():
    assert EventType.integration_created.value == "integration.created"
    assert EventType.integration_revoked.value == "integration.revoked"
    assert EventType.webhook_delivery_succeeded.value == "webhook.delivery.succeeded"
    assert EventType.webhook_delivery_failed.value == "webhook.delivery.failed"


@pytest.mark.asyncio
async def test_audit_log_written(db, org_id):
    created = await _integration(db, org_id)
    rows = (await db.execute(select(IntegrationAuditLog).where(
        IntegrationAuditLog.tenant == org_id,
        IntegrationAuditLog.action == "integration.create"))).scalars().all()
    assert len(rows) == 1
    assert rows[0].resource_id == created["id"]


def test_sdk_mixins_registered():
    from backend.sdk.integrations import IntegrationMixin, AsyncIntegrationMixin
    from backend.sdk import IntegrationMixin as R1, AsyncIntegrationMixin as R2
    assert R1 is IntegrationMixin and R2 is AsyncIntegrationMixin
    for method in ("integrations_list", "integrations_create", "integrations_get",
                   "integrations_update", "integrations_set_status",
                   "integrations_create_connection", "integrations_connection_status",
                   "integrations_execute", "integrations_create_webhook",
                   "integrations_webhook_status", "integrations_delivery_history",
                   "integrations_health"):
        assert callable(getattr(IntegrationMixin, method))
        assert callable(getattr(AsyncIntegrationMixin, method))


def test_cli_helpers():
    from app.cli.integrations_commands import _base, _key, handle_integrations_command
    assert _base(None) == "http://localhost:8000"
    assert callable(handle_integrations_command)


# ─── API ─────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def api_client(db, org_id, fake_user):
    from httpx import AsyncClient, ASGITransport
    from app.api import create_app
    import app.integrations.api as integrations_api

    app = create_app()

    async def _override_db():
        yield db

    async def _override_user():
        return fake_user

    app.dependency_overrides[integrations_api._get_db] = _override_db
    app.dependency_overrides[integrations_api._resolve_user] = _override_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_api_registry_crud(api_client):
    created = await api_client.post("/api/v1/integrations", json={
        "name": "gh", "type": "connector", "provider": "github",
        "capabilities": ["execute", "sync", "health"]})
    assert created.status_code == 201, created.text
    integration_id = created.json()["id"]
    fetched = await api_client.get(f"/api/v1/integrations/{integration_id}")
    assert fetched.status_code == 200
    listed = await api_client.get("/api/v1/integrations")
    assert listed.json()["total"] >= 1
    updated = await api_client.patch(f"/api/v1/integrations/{integration_id}", json={"owner": "team-a"})
    assert updated.status_code == 200
    disabled = await api_client.post(f"/api/v1/integrations/{integration_id}/status", json={"status": "DISABLED"})
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "DISABLED"


@pytest.mark.asyncio
async def test_api_connections_and_execute(api_client, monkeypatch):
    created = await api_client.post("/api/v1/integrations", json={
        "name": "rest", "type": "api", "capabilities": ["execute"]})
    integration_id = created.json()["id"]
    conn = await api_client.post("/api/v1/integrations/connections", json={
        "integration_id": integration_id, "endpoint_ref": "https://93.184.216.34/v1"})
    assert conn.status_code == 201, conn.text
    connection_id = conn.json()["id"]
    status = await api_client.get(f"/api/v1/integrations/connections/{connection_id}")
    assert status.status_code == 200

    async def _ok(**kwargs):
        return {"status_code": 200, "bytes": 2, "attempts": 1, "latency_ms": 1}

    monkeypatch.setattr("app.integrations.outbound.execute", _ok)
    import httpx as _httpx
    monkeypatch.setattr("httpx.AsyncClient", _FakeClient)
    executed = await api_client.post(
        f"/api/v1/integrations/connections/{connection_id}/execute",
        json={"operation": "list", "method": "GET", "path": "items"})
    assert executed.status_code == 200, executed.text
    assert executed.json()["status"] == "SUCCESS"


@pytest.mark.asyncio
async def test_api_webhooks(api_client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "encryption_master_key",
                        "test-master-key-32-chars-long!!!", raising=False)
    hook = await api_client.post("/api/v1/integrations/webhooks", json={
        "name": "wh1", "url": "https://93.184.216.34/hook",
        "events": ["order.created"], "signing_secret": "s3cr3t"})
    assert hook.status_code == 201, hook.text
    assert "s3cr3t" not in hook.text
    webhook_id = hook.json()["id"]
    queued = await api_client.post(f"/api/v1/integrations/webhooks/{webhook_id}/deliver", json={
        "event_type": "order.created", "payload": {"order": 1}})
    assert queued.status_code == 201
    history = await api_client.get(f"/api/v1/integrations/webhooks/{webhook_id}/deliveries")
    assert history.status_code == 200
    assert history.json()["total"] == 1


@pytest.mark.asyncio
async def test_api_viewer_denied_write(db, org_id, viewer_user):
    from httpx import AsyncClient, ASGITransport
    from app.api import create_app
    import app.integrations.api as integrations_api

    app = create_app()

    async def _override_db():
        yield db

    async def _override_user():
        return viewer_user

    app.dependency_overrides[integrations_api._get_db] = _override_db
    app.dependency_overrides[integrations_api._resolve_user] = _override_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/integrations", json={"name": "x", "type": "api"})
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_api_deny_override_enforced(api_client, org_id):
    from app.iam.policy_authorizer import policy_authorizer
    policy_authorizer.set_deny_override(org_id, "organization:read")
    try:
        resp = await api_client.get("/api/v1/integrations")
        assert resp.status_code == 403
    finally:
        policy_authorizer.clear_deny_override(org_id, "organization:read")


@pytest.mark.asyncio
async def test_api_missing_tenant_rejected(db):
    from httpx import AsyncClient, ASGITransport
    from app.api import create_app
    import app.integrations.api as integrations_api

    app = create_app()

    async def _override_db():
        yield db

    async def _override_user():
        class _Anon:
            id = ""
            organization_id = ""
            role = "anonymous"
        return _Anon()

    app.dependency_overrides[integrations_api._get_db] = _override_db
    app.dependency_overrides[integrations_api._resolve_user] = _override_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/integrations")
        assert resp.status_code == 403
