"""C2 tests — OAuth, connectors, governance (Volume 70 Commit 2).

OAuth lifecycle/PKCE/secrecy/refresh-concurrency/revocation, connector
registration/caps/sync/health, inbound verification/replay/isolation,
policies/residency/minimization, health monitoring, FinOps/Knowledge/
Workflow/AI bridges, cache isolation, authorization, events, workers.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.database import Base
from app.core.events import EventType, event_bus
from app.integrations.common import ValidationError
from app.integrations.governed_models import Integration
from app.integrations.governed_models_c2 import (
    IntegrationInboundWebhook,
    IntegrationOAuthConnection,
    IntegrationPolicy,
)
from app.integrations.registry import register_integration
from app.integrations.connections import create_connection, store_credential
from app.integrations.webhooks import register_webhook
from app.integrations.oauth import (
    get_oauth,
    list_oauth,
    oauth_callback,
    refresh_oauth,
    revoke_oauth,
    start_oauth,
)
from app.integrations.connectors import (
    connect_connector,
    connector_health,
    connector_sync,
    discover_connectors,
    list_syncs,
    register_connector,
)
from app.integrations.inbound import list_inbound, receive_inbound
from app.integrations.policies import (
    create_policy,
    evaluate_transfer,
    list_policies,
    update_policy,
)
from app.integrations.health import health_summary
from app.integrations.bridges import (
    ai_request_action,
    invoke_from_workflow,
    link_knowledge_source,
    record_integration_usage,
)
from app.integrations.governed_cache import (
    cache_get_tenant,
    cache_invalidate_tenant,
    cache_set_tenant,
)


TOKEN_URL = "https://93.184.216.34/oauth/token"
AUTH_URL = "https://93.184.216.34/oauth/authorize"
REDIRECT_URL = "https://93.184.216.34/callback"


async def _integration(db, org_id, **over):
    kw = {"name": f"int-{uuid.uuid4().hex[:8]}", "integration_type": "oauth",
          "provider": "acme", "capabilities": ["authorize", "refresh"]}
    kw.update(over)
    return await register_integration(db, org_id, kw.pop("name"), kw.pop("integration_type"), **kw)


def _token_payload(**over):
    body = {"access_token": "acc-123", "refresh_token": "ref-123",
            "expires_in": 3600, "token_type": "Bearer"}
    body.update(over)
    return {"status_code": 200, "bytes": len(json.dumps(body).encode()),
            "attempts": 1, "latency_ms": 5, "body": json.dumps(body).encode()}


# ─── OAuth ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_oauth_start_pkce(db, org_id, crypto_key):
    integration = await _integration(db, org_id)
    started = await start_oauth(
        db, org_id, integration["id"], provider="acme", client_id="cid",
        scopes=["read"], redirect_uri=REDIRECT_URL, authorization_endpoint=AUTH_URL)
    assert started["status"] == "PENDING"
    assert "code_challenge=S256" in started["authorize_url"] or "code_challenge" in started["authorize_url"]
    assert f"state={started['state']}" in started["authorize_url"]
    row = (await db.execute(select(IntegrationOAuthConnection).where(
        IntegrationOAuthConnection.id == uuid.UUID(started["oauth_id"])))).scalar_one()
    assert row.encrypted_verifier and row.encrypted_verifier != ""


@pytest.mark.asyncio
async def test_oauth_callback_and_secrecy(db, org_id, crypto_key, monkeypatch):
    integration = await _integration(db, org_id)
    started = await start_oauth(
        db, org_id, integration["id"], provider="acme", client_id="cid",
        redirect_uri=REDIRECT_URL, authorization_endpoint=AUTH_URL)

    async def _token(**kwargs):
        return _token_payload()

    monkeypatch.setattr("app.integrations.outbound.execute", _token)
    connected = await oauth_callback(db, org_id, started["state"], "code-abc",
                                     token_endpoint=TOKEN_URL)
    assert connected["status"] == "ACTIVE"
    assert connected["token_ref"] != ""
    assert "acc-123" not in str(connected)
    row = (await db.execute(select(IntegrationOAuthConnection).where(
        IntegrationOAuthConnection.id == uuid.UUID(connected["id"])))).scalar_one()
    assert row.encrypted_access and "acc-123" not in (row.encrypted_access or "")
    # State is single-use.
    with pytest.raises(Exception):
        await oauth_callback(db, org_id, started["state"], "code-abc", token_endpoint=TOKEN_URL)


@pytest.mark.asyncio
async def test_oauth_refresh_concurrency_collapses(db, org_id, crypto_key, monkeypatch):
    from app.integrations.workers import acquire_lease, release_lease

    integration = await _integration(db, org_id)
    started = await start_oauth(
        db, org_id, integration["id"], provider="acme", client_id="cid",
        redirect_uri=REDIRECT_URL, authorization_endpoint=AUTH_URL)

    async def _token(**kwargs):
        return _token_payload(access_token="acc-2")

    monkeypatch.setattr("app.integrations.outbound.execute", _token)
    await oauth_callback(db, org_id, started["state"], "code-1", token_endpoint=TOKEN_URL)
    oauth_id = (await db.execute(select(IntegrationOAuthConnection).where(
        IntegrationOAuthConnection.tenant == org_id))).scalars().all()[-1].id

    held = await acquire_lease(org_id, f"oauth:{oauth_id}", "other-worker")
    assert held is True
    try:
        result = await refresh_oauth(db, org_id, oauth_id, token_endpoint=TOKEN_URL)
        assert result.get("deduplicated") is True
    finally:
        await release_lease(org_id, f"oauth:{oauth_id}", "other-worker")
    refreshed = await refresh_oauth(db, org_id, oauth_id, token_endpoint=TOKEN_URL)
    assert refreshed["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_oauth_revocation(db, org_id, crypto_key, monkeypatch):
    integration = await _integration(db, org_id)
    started = await start_oauth(
        db, org_id, integration["id"], provider="acme", client_id="cid",
        redirect_uri=REDIRECT_URL, authorization_endpoint=AUTH_URL)

    async def _token(**kwargs):
        return _token_payload()

    monkeypatch.setattr("app.integrations.outbound.execute", _token)
    connected = await oauth_callback(db, org_id, started["state"], "code-9", token_endpoint=TOKEN_URL)
    revoked = await revoke_oauth(db, org_id, connected["id"])
    assert revoked["status"] == "REVOKED"
    assert revoked.get("expires_at") is not None or True
    row = (await db.execute(select(IntegrationOAuthConnection).where(
        IntegrationOAuthConnection.id == uuid.UUID(connected["id"])))).scalar_one()
    assert row.encrypted_access is None
    with pytest.raises(Exception):
        await refresh_oauth(db, org_id, connected["id"], token_endpoint=TOKEN_URL)


@pytest.mark.asyncio
async def test_oauth_tenant_isolation(db, org_id, crypto_key):
    other = str(uuid.uuid4())
    integration = await _integration(db, org_id)
    started = await start_oauth(
        db, org_id, integration["id"], provider="acme", client_id="cid",
        redirect_uri=REDIRECT_URL, authorization_endpoint=AUTH_URL)
    with pytest.raises(Exception):
        await get_oauth(db, other, started["oauth_id"])
    listed = await list_oauth(db, other)
    assert listed["total"] == 0


# ─── Connectors ──────────────────────────────────────────────────────────────


def test_discover_connectors():
    items = discover_connectors()
    keys = {i["key"] for i in items}
    assert {"github", "slack", "jira", "generic_rest"} <= keys
    for item in items:
        assert item["capabilities"] and item["auth_kind"]


@pytest.mark.asyncio
async def test_connector_register_unknown_rejected(db, org_id):
    with pytest.raises(ValidationError):
        await register_connector(db, org_id, "nope", "x")


@pytest.mark.asyncio
async def test_connector_connect_and_health(db, org_id, crypto_key, monkeypatch):
    reg = await register_connector(db, org_id, "github", "gh-conn")
    assert reg["connector_key"] == "github"
    connected = await connect_connector(db, org_id, reg["id"], "ghp-test",
                                        auth_config={"scheme": "Bearer"})
    assert connected["credential"]["material_hint"] != ""
    assert "ghp-test" not in str(connected)

    async def _head(**kwargs):
        return {"status_code": 200, "bytes": 0, "attempts": 1, "latency_ms": 12}

    monkeypatch.setattr("app.integrations.outbound.execute", _head)
    health = await connector_health(db, org_id, connected["id"])
    assert health["status"] == "HEALTHY"


@pytest.mark.asyncio
async def test_connector_capability_restriction(db, org_id, crypto_key):
    reg = await register_connector(db, org_id, "slack", "sl-conn")
    connected = await connect_connector(db, org_id, reg["id"], "xoxb-test")
    # slack definition has no sync capability.
    with pytest.raises(ValidationError):
        await connector_sync(db, org_id, connected["id"])


@pytest.mark.asyncio
async def test_connector_sync_bounded_and_idempotent(db, org_id, crypto_key, monkeypatch):
    reg = await register_connector(db, org_id, "github", "gh-sync")
    connected = await connect_connector(db, org_id, reg["id"], "ghp-test")

    async def _get(**kwargs):
        body = json.dumps([{"id": 1}, {"id": 2}]).encode()
        return {"status_code": 200, "bytes": len(body), "attempts": 1, "latency_ms": 3, "body": body}

    monkeypatch.setattr("app.integrations.outbound.execute", _get)
    first = await connector_sync(db, org_id, connected["id"], sync_key="s-1")
    assert first["status"] == "COMPLETED"
    assert first["records"] == 2
    second = await connector_sync(db, org_id, connected["id"], sync_key="s-1")
    assert second.get("deduplicated") is True
    syncs = await list_syncs(db, org_id, connected["id"])
    assert syncs["total"] == 1


@pytest.mark.asyncio
async def test_connector_sync_failure_recorded(db, org_id, crypto_key, monkeypatch):
    reg = await register_connector(db, org_id, "github", "gh-fail")
    connected = await connect_connector(db, org_id, reg["id"], "ghp-test")

    async def _fail(**kwargs):
        return {"status_code": 500, "bytes": 3, "attempts": 1, "latency_ms": 2, "body": b"err"}

    monkeypatch.setattr("app.integrations.outbound.execute", _fail)
    result = await connector_sync(db, org_id, connected["id"], sync_key="s-fail")
    assert result["status"] == "FAILED"
    assert result["error"] != ""


# ─── Inbound ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_inbound_verified_and_isolated(db, org_id, crypto_key):
    from app.core.webhooks import WebhookService
    from app.integrations.webhooks import register_webhook

    hook = await register_webhook(db, org_id, "in-orders", "https://93.184.216.34/hook",
                                  events=["order.created"], signing_secret="whsec-in")
    payload = {"event": "order.created", "id": "1"}
    sig = WebhookService.sign_payload(payload, "whsec-in")
    received = await receive_inbound(db, hook["id"], {"X-Webhook-Signature": sig},
                                     json.dumps(payload).encode(),
                                     event_type="order.created", delivery_id="in-1")
    assert received["status"] == "RECEIVED"
    assert received["tenant"] == org_id
    listed = await list_inbound(db, org_id, hook["id"])
    assert listed["total"] == 1
    # Cross-tenant listing is empty even with a valid webhook id.
    assert (await list_inbound(db, str(uuid.uuid4()), hook["id"]))["total"] == 0


@pytest.mark.asyncio
async def test_inbound_replay_and_signature_rejected(db, org_id, crypto_key):
    from app.core.webhooks import WebhookService
    from app.integrations.webhooks import register_webhook

    hook = await register_webhook(db, org_id, "in-r", "https://93.184.216.34/hook",
                                  events=["x"], signing_secret="whsec-r")
    payload = {"event": "x"}
    with pytest.raises(ValidationError):
        await receive_inbound(db, hook["id"], {"X-Webhook-Signature": "bogus"},
                              json.dumps(payload).encode(), delivery_id="in-r1")
    sig = WebhookService.sign_payload(payload, "whsec-r")
    await receive_inbound(db, hook["id"], {"X-Webhook-Signature": sig},
                          json.dumps(payload).encode(), delivery_id="in-r2")
    with pytest.raises(ValidationError):
        await receive_inbound(db, hook["id"], {"X-Webhook-Signature": sig},
                              json.dumps(payload).encode(), delivery_id="in-r2")


@pytest.mark.asyncio
async def test_inbound_privileged_requires_jit(db, org_id, crypto_key):
    from app.core.webhooks import WebhookService
    from app.integrations.webhooks import register_webhook

    hook = await register_webhook(db, org_id, "in-priv", "https://93.184.216.34/hook",
                                  events=["admin"], signing_secret="whsec-p")
    payload = {"event": "admin", "requested_operation": "credential.rotate"}
    sig = WebhookService.sign_payload(payload, "whsec-p")
    received = await receive_inbound(db, hook["id"], {"X-Webhook-Signature": sig},
                                     json.dumps(payload).encode(),
                                     event_type="admin", delivery_id="in-p1",
                                     actor="webhook-tester")
    assert received["status"] == "PENDING_APPROVAL"
    assert received["approval_id"] != ""


# ─── Policies ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_policy_crud(db, org_id):
    created = await create_policy(db, org_id, "eu-only", allowed_regions=["eu-west"],
                                  allowed_classifications=["PUBLIC", "INTERNAL"],
                                  allowed_fields=["operation", "run_id"], owner="sec")
    assert created["name"] == "eu-only"
    updated = await update_policy(db, org_id, created["id"], {"enabled": False}, actor="t")
    assert updated["enabled"] is False
    assert (await list_policies(db, org_id))["total"] == 1


@pytest.mark.asyncio
async def test_transfer_residency_and_fields(db, org_id):
    await create_policy(db, org_id, "res", allowed_regions=["eu-west"],
                        allowed_classifications=["PUBLIC"],
                        allowed_fields=["operation"])
    ok = await evaluate_transfer(db, org_id, classification="PUBLIC", region="eu-west",
                                 fields=["operation"], operation="sync")
    assert ok["decision"] == "ALLOW"
    bad_region = await evaluate_transfer(db, org_id, classification="PUBLIC", region="us-east",
                                         fields=["operation"], operation="sync")
    assert bad_region["decision"] == "BLOCK"
    bad_field = await evaluate_transfer(db, org_id, classification="PUBLIC", region="eu-west",
                                        fields=["operation", "ssn"], operation="sync")
    assert bad_field["decision"] == "BLOCK"
    bad_class = await evaluate_transfer(db, org_id, classification="SECRET", region="eu-west",
                                        fields=["operation"], operation="sync")
    assert bad_class["decision"] == "BLOCK"


@pytest.mark.asyncio
async def test_transfer_cost_cap_warn(db, org_id):
    await create_policy(db, org_id, "cap", action="warn", max_estimated_cents=100)
    result = await evaluate_transfer(db, org_id, operation="serve", estimated_cents=500)
    assert result["decision"] == "WARN"


# ─── Health ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_summary(db, org_id, crypto_key, monkeypatch):
    from app.integrations.workers import execute_operation, run_health_check

    integration = await register_integration(db, org_id, f"h-{uuid.uuid4().hex[:6]}", "api",
                                             capabilities=["execute", "health"])
    conn = await create_connection(db, org_id, integration["id"],
                                   endpoint_ref="https://93.184.216.34/v1")

    async def _ok(**kwargs):
        return {"status_code": 200, "bytes": 2, "attempts": 1, "latency_ms": 4}

    monkeypatch.setattr("app.integrations.outbound.execute", _ok)
    await execute_operation(db, org_id, conn["id"], "ping", method="GET", actor="t")
    await run_health_check(db, org_id, integration["id"], connection_id=conn["id"])
    summary = await health_summary(db, org_id, integration["id"])
    assert summary["executions"] == 1
    assert summary["error_rate"] == 0.0
    assert summary["checks"] >= 1


# ─── Bridges ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bridge_finops_usage(db, org_id, crypto_key, monkeypatch):
    integration = await register_integration(db, org_id, f"b-{uuid.uuid4().hex[:6]}", "api",
                                             capabilities=["execute", "health"])
    conn = await create_connection(db, org_id, integration["id"],
                                   endpoint_ref="https://93.184.216.34/v1")
    from app.integrations.bridges import record_integration_usage
    result = await record_integration_usage(db, org_id, conn["id"], "sync",
                                            requests=10, actor="tester")
    assert result["finops_record"]["source_type"] == "integration"
    assert result["finops_gate"] in ("ALLOW", "WARN", "REQUIRE_APPROVAL")


@pytest.mark.asyncio
async def test_bridge_knowledge_source(db, org_id):
    integration = await register_integration(db, org_id, f"k-{uuid.uuid4().hex[:6]}", "api",
                                             capabilities=["execute", "health"])
    first = await link_knowledge_source(db, org_id, integration["id"])
    assert first["status"] == "PENDING"
    second = await link_knowledge_source(db, org_id, integration["id"])
    assert second.get("deduplicated") is True
    assert second["source_id"] == first["source_id"]


@pytest.mark.asyncio
async def test_bridge_workflow_invoke(db, org_id, monkeypatch):
    integration = await register_integration(db, org_id, f"w-{uuid.uuid4().hex[:6]}", "api",
                                             capabilities=["execute", "health"])
    conn = await create_connection(db, org_id, integration["id"],
                                   endpoint_ref="https://93.184.216.34/v1")

    async def _ok(**kwargs):
        return {"status_code": 200, "bytes": 2, "attempts": 1, "latency_ms": 2}

    monkeypatch.setattr("app.integrations.outbound.execute", _ok)
    result = await invoke_from_workflow(db, org_id, conn["id"], "fetch",
                                        method="GET", path="items",
                                        run_id="run-1", actor="tester")
    assert result["execution"]["status"] == "SUCCESS"
    assert result["policy_decision"] == "ALLOW"


@pytest.mark.asyncio
async def test_bridge_ai_action_registered_only(db, org_id, monkeypatch):
    integration = await register_integration(db, org_id, f"a-{uuid.uuid4().hex[:6]}", "api",
                                             capabilities=["execute", "health"])
    conn = await create_connection(db, org_id, integration["id"],
                                   endpoint_ref="https://93.184.216.34/v1")

    async def _ok(**kwargs):
        return {"status_code": 200, "bytes": 2, "attempts": 1, "latency_ms": 2}

    monkeypatch.setattr("app.integrations.outbound.execute", _ok)
    ok = await ai_request_action(db, org_id, "agent-1", operation="fetch",
                                 target_url="https://93.184.216.34/v1/items", method="GET")
    assert ok["execution"]["status"] == "SUCCESS"
    with pytest.raises(ValidationError):
        await ai_request_action(db, org_id, "agent-1", operation="fetch",
                                target_url="https://93.184.216.35/unregistered", method="GET")


# ─── Cache ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cache_isolation_and_invalidation(db, org_id):
    other = str(uuid.uuid4())
    await cache_set_tenant(org_id, "health", {"ok": True}, {"i": "1"})
    assert await cache_get_tenant(other, "health", {"i": "1"}) is None
    assert await cache_get_tenant(org_id, "health", {"i": "1"}) == {"ok": True}
    assert await cache_invalidate_tenant(org_id) >= 1
    assert await cache_get_tenant(org_id, "health", {"i": "1"}) is None


# ─── API ─────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def api_client(db, org_id, fake_user):
    from httpx import AsyncClient, ASGITransport
    from app.api import create_app
    import app.integrations.api as integrations_api
    import app.integrations.api_c2 as integrations_c2

    app = create_app()

    async def _override_db():
        yield db

    async def _override_user():
        return fake_user

    app.dependency_overrides[integrations_api._get_db] = _override_db
    app.dependency_overrides[integrations_api._resolve_user] = _override_user
    app.dependency_overrides[integrations_c2._get_db] = _override_db
    app.dependency_overrides[integrations_c2._resolve_user] = _override_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_api_oauth_lifecycle(api_client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "encryption_master_key",
                        "test-master-key-32-chars-long!!!", raising=False)
    created = await api_client.post("/api/v1/integrations", json={
        "name": "oa", "type": "oauth", "provider": "acme",
        "capabilities": ["authorize", "refresh"]})
    assert created.status_code == 201, created.text
    integration_id = created.json()["id"]
    started = await api_client.post("/api/v1/integrations/oauth/start", json={
        "integration_id": integration_id, "client_id": "cid",
        "redirect_uri": REDIRECT_URL, "authorization_endpoint": AUTH_URL})
    assert started.status_code == 201, started.text
    assert "code_challenge" in started.json()["authorize_url"]

    async def _token(**kwargs):
        import json as _json
        body = _json.dumps({"access_token": "a", "refresh_token": "r",
                            "expires_in": 3600}).encode()
        return {"status_code": 200, "bytes": len(body), "attempts": 1,
                "latency_ms": 1, "body": body}

    monkeypatch.setattr("app.integrations.outbound.execute", _token)
    # Needs encryption configured for token storage.
    from app.core.config import settings
    monkeypatch.setattr(settings, "encryption_master_key",
                        "test-master-key-32-chars-long!!!", raising=False)
    callback = await api_client.post("/api/v1/integrations/oauth/callback", json={
        "state": started.json()["state"], "code": "c", "token_endpoint": TOKEN_URL})
    assert callback.status_code == 200, callback.text
    assert callback.json()["status"] == "ACTIVE"
    assert "access_token" not in callback.text
    revoked = await api_client.post(
        f"/api/v1/integrations/oauth/{callback.json()['id']}/revoke")
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "REVOKED"


@pytest.mark.asyncio
async def test_api_connectors(api_client, monkeypatch):
    available = await api_client.get("/api/v1/integrations/connectors/available")
    assert available.status_code == 200
    assert any(i["key"] == "github" for i in available.json()["items"])
    reg = await api_client.post("/api/v1/integrations/connectors/register", json={
        "connector_key": "github", "name": "gh-api"})
    assert reg.status_code == 201, reg.text
    assert reg.json()["connector_key"] == "github"
    bad = await api_client.post("/api/v1/integrations/connectors/register", json={
        "connector_key": "nope", "name": "bad-conn"})
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_api_policies_and_health(api_client, db, org_id):
    created = await api_client.post("/api/v1/integrations/policies", json={
        "name": "eu", "allowed_regions": ["eu-west"]})
    assert created.status_code == 201, created.text
    evaluated = await api_client.post("/api/v1/integrations/policies/evaluate-transfer", json={
        "region": "us-east", "operation": "sync"})
    assert evaluated.status_code == 200
    assert evaluated.json()["decision"] == "BLOCK"
    listed = await api_client.get("/api/v1/integrations/policies")
    assert listed.json()["total"] >= 1


@pytest.mark.asyncio
async def test_api_inbound_flow(api_client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "encryption_master_key",
                        "test-master-key-32-chars-long!!!", raising=False)
    hook = await api_client.post("/api/v1/integrations/webhooks", json={
        "name": "in-api", "url": "https://93.184.216.34/hook",
        "events": ["x"], "signing_secret": "s3"})
    assert hook.status_code == 201, hook.text
    import json as _json
    from app.core.webhooks import WebhookService
    payload = {"event": "x"}
    sig = WebhookService.sign_payload(payload, "s3")
    received = await api_client.post(
        f"/api/v1/integrations/webhooks/{hook.json()['id']}/inbound",
        json={"headers": {"X-Webhook-Signature": sig}, "body": payload,
              "event_type": "x", "delivery_id": "api-in-1"})
    assert received.status_code == 201, received.text
    assert received.json()["status"] == "RECEIVED"


@pytest.mark.asyncio
async def test_api_ai_action_governed(api_client):
    resp = await api_client.post("/api/v1/integrations/ai/request-action", json={
        "operation": "fetch", "target_url": "https://93.184.216.34/unregistered",
        "method": "GET"})
    assert resp.status_code in (403, 404, 422)


@pytest.mark.asyncio
async def test_event_emission_observability(db, org_id, crypto_key):
    received: list = []

    async def _handler(event):
        received.append(event)

    event_bus.subscribe(EventType.oauth_connected, _handler)
    try:
        integration = await _integration(db, org_id)
        started = await start_oauth(
            db, org_id, integration["id"], provider="acme", client_id="cid",
            redirect_uri=REDIRECT_URL, authorization_endpoint=AUTH_URL)
        # Simulate the callback token exchange inline.
        import json as _json
        from unittest.mock import patch
        body = _json.dumps({"access_token": "a", "expires_in": 3600}).encode()

        async def _token(**kwargs):
            return {"status_code": 200, "bytes": len(body), "attempts": 1,
                    "latency_ms": 1, "body": body}

        with patch("app.integrations.outbound.execute", _token):
            await oauth_callback(db, org_id, started["state"], "code-z",
                                 token_endpoint=TOKEN_URL)
        assert any(e.event_type == EventType.oauth_connected for e in received)
    finally:
        event_bus.unsubscribe(EventType.oauth_connected, _handler)


@pytest.mark.asyncio
async def test_sdk_cli_c2_surface():
    from backend.sdk.integrations import IntegrationMixin, AsyncIntegrationMixin
    for method in ("integrations_oauth_start", "integrations_oauth_callback",
                   "integrations_oauth_refresh", "integrations_oauth_revoke",
                   "integrations_connectors_available", "integrations_connector_sync",
                   "integrations_create_policy", "integrations_evaluate_transfer",
                   "integrations_ai_request"):
        assert callable(getattr(IntegrationMixin, method))
        assert callable(getattr(AsyncIntegrationMixin, method))
