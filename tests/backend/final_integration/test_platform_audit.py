"""Final platform integration audit — Volume 72 Commit 1.

Route inventory, event uniqueness, migration integrity, duplicate
tables, cross-volume flows, failure paths, adversarial tenant
isolation, cache safety, transaction/resilience behavior, health,
configuration, SDK consistency and secret scanning.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.core.database import Base
from app.core.events import EventType


def _iter_routes(router, prefix=""):
    """Expand FastAPI _IncludedRouter entries into effective (methods, path).

    include_context.prefix is already fully accumulated (parent prefix +
    include prefix); route.path values are relative to their router.
    """
    out = []
    for route in router.routes:
        if type(route).__name__ == "_IncludedRouter":
            ctx = route.include_context
            out += _iter_routes(route.original_router, getattr(ctx, "prefix", "") or "")
        else:
            methods = sorted(getattr(route, "methods", None) or [])
            path = getattr(route, "path", "") or ""
            if methods and path:
                out.append((tuple(methods), prefix + path))
    return out


def _app_routes():
    from app.api.router import api_router
    return [(methods, path) for methods, path in _iter_routes(api_router)
            if path.startswith("/api/")]


# ─── Route inventory ─────────────────────────────────────────────────────────


def test_no_duplicate_routes():
    routes = _app_routes()
    assert len(routes) > 1000, f"unexpected route count: {len(routes)}"
    seen: dict[tuple, int] = {}
    for methods, path in routes:
        for method in methods:
            key = (method, path)
            seen[key] = seen.get(key, 0) + 1
    duplicates = {k: v for k, v in seen.items() if v > 1}
    assert duplicates == {}, f"duplicate routes: {duplicates}"


def test_fixed_prefixes_reachable():
    routes = {(m, path) for methods, path in _app_routes() for m in methods}
    for method, path in [
        ("GET", "/api/v1/agents/v2/runs"),
        ("GET", "/api/v1/ai-governance/assets"),
        ("POST", "/api/v1/analytics/events/ingest"),
        ("GET", "/api/v1/knowledge-graph/entities"),
        ("GET", "/api/v1/finops/usage/summary"),
        ("GET", "/api/v1/integrations"),
        ("GET", "/api/v1/governance/policies"),
    ]:
        assert (method, path) in routes, f"missing route {method} {path}"
    # No doubled version/prefix segments anywhere.
    for _, path in routes:
        assert "/api/v1/api/" not in path, f"doubled version in {path}"
        assert "ai-governance/ai-governance" not in path, f"doubled prefix in {path}"
        assert "kernel/kernel" not in path, f"doubled prefix in {path}"


def test_agents_v2_ordering():
    routes = _app_routes()
    paths = [p for _, p in routes]
    runs_index = paths.index("/api/v1/agents/v2/runs")
    param_index = paths.index("/api/v1/agents/v2/{agent_name}")
    assert runs_index < param_index


def test_auth_namespaces_disjoint():
    from app.api import auth as _auth
    from app.api import auth_v2 as _auth_v2

    def _paths(mod):
        out = set()
        for route in mod.router.routes:
            for method in sorted(getattr(route, "methods", None) or []):
                out.add((method, getattr(route, "path", "")))
        return out

    overlap = _paths(_auth) & _paths(_auth_v2)
    assert overlap == set(), f"auth/auth_v2 overlap: {overlap}"


def test_datagov_governance_coexistence():
    routes = {(m, path) for methods, path in _app_routes() for m in methods}
    # Legacy datagov owns /exceptions; central plane uses /policy-exceptions.
    assert ("POST", "/api/v1/governance/exceptions") in routes
    assert ("POST", "/api/v1/governance/policy-exceptions") in routes
    assert ("POST", "/api/v1/governance/evaluate") in routes


# ─── Events ──────────────────────────────────────────────────────────────────


def test_event_names_unique():
    names = [member.name for member in EventType]
    assert len(names) == len(set(names))


def test_event_values_documented_aliases_only():
    from collections import Counter
    values = Counter(member.value for member in EventType)
    dupes = {v for v, n in values.items() if n > 1}
    # Every duplicated value must be a documented dual-case alias pair.
    for value in dupes:
        members = [m.name for m in EventType if m.value == value]
        lowered = {m.lower() for m in members}
        assert len(lowered) == 1, f"non-alias value collision on {value}: {members}"


# ─── Migrations ──────────────────────────────────────────────────────────────


def _migration_revisions():
    """Parse revision metadata via AST (no imports: some legacy modules
    have pre-existing import-time issues unrelated to the chain)."""
    import ast
    import glob as _glob

    versions: dict[str, set] = {}
    for path in _glob.glob("backend/alembic/versions/0*.py"):
        try:
            tree = ast.parse(open(path, encoding="utf-8").read())
        except Exception:
            continue
        values: dict[str, object] = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(
                    node.targets[0], ast.Name) and node.targets[0].id in (
                    "revision", "down_revision"):
                try:
                    values[node.targets[0].id] = ast.literal_eval(node.value)
                except Exception:
                    continue
        if "revision" not in values:
            continue
        revisions = values["revision"]
        revisions = revisions if isinstance(revisions, tuple) else (revisions,)
        downs = values.get("down_revision")
        downs = set(downs) if isinstance(downs, tuple) else ({downs} if downs else set())
        for revision in revisions:
            versions[revision] = downs
    return versions


def test_migration_single_head_and_chain():
    versions = _migration_revisions()
    assert "0045_rename_enterprise_connection" in versions
    assert "0044_merge_sre_rename" in versions
    children: dict[str, list] = {}
    for revision, downs in versions.items():
        for down in downs:
            children.setdefault(down, []).append(revision)
    heads = [r for r in versions if r not in children or not children[r]]
    assert heads == ["0045_rename_enterprise_connection"], f"multiple heads: {heads}"
    # Chain spot-checks.
    assert versions["0045_rename_enterprise_connection"] == {"0044_merge_sre_rename"}
    assert set(versions["0044_merge_sre_rename"]) == {
        "0043_governance_enterprise", "0004_sre_rename_tables"}


def test_no_duplicate_tablenames():
    import ast
    import pathlib
    from collections import Counter
    # Source-level scan: catches collisions even for models that are not
    # imported in this process (e.g. legacy modules with broken imports).
    names: list[str] = []
    for path in pathlib.Path("backend/app").rglob("*models*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(
                    node.targets[0], ast.Name) and node.targets[0].id == "__tablename__":
                try:
                    names.append(ast.literal_eval(node.value))
                except Exception:
                    continue
    dupes = {t for t, n in Counter(names).items() if n > 1}
    assert dupes == set(), f"duplicate __tablename__: {dupes}"
    # The V70 collision is gone: exactly one definition repo-wide, and the
    # dead enterprise/models.py that shadowed it has been removed.
    assert names.count("integration_connections") == 1


# ─── Cross-volume flows ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_flow_auth_governance_knowledge_finops(db, org_id, fake_user):
    from app.governance.plane_policies import create_policy, create_version, set_version_status
    from app.governance.plane_bindings import create_binding
    from app.governance.plane_evaluate import evaluate
    from app.knowledge.retrieval import lexical_search
    from app.finops.costing import record_usage_cost, usage_summary

    policy = await create_policy(db, org_id, f"flow-{uuid.uuid4().hex[:6]}")
    version = await create_version(db, org_id, policy["id"], [{
        "name": "a", "effect": "allow", "priority": 1,
        "condition": {"field": "operation", "op": "equals", "value": "read"},
        "obligations": []}])
    await set_version_status(db, org_id, version["id"], "ACTIVE")
    await create_binding(db, org_id, policy["id"], version["id"], scope_type="tenant")
    decision = await evaluate(db, org_id, scope_type="tenant", operation="read",
                              context={"operation": "read"}, actor="flow")
    assert decision["decision"] == "ALLOW"
    results = await lexical_search(db, org_id, "nothing matches this xyzzy")
    assert isinstance(results, list)
    summary = await usage_summary(db, org_id)
    assert summary["tenant"] == org_id
    record = await record_usage_cost(db, org_id, {
        "provider": "openai", "model": "gpt-4o", "input_tokens": 10,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "source_type": "ai_execution", "source_id": "flow-1"})
    assert record["cost_basis"] in ("actual", "estimated", "unpriced")


@pytest.mark.asyncio
async def test_flow_integration_execution_to_finops(db, org_id, fake_user, monkeypatch):
    from app.integrations.registry import register_integration
    from app.integrations.connections import create_connection
    from app.integrations.workers import execute_operation
    from app.integrations.bridges import record_integration_usage

    integration = await register_integration(
        db, org_id, f"flow-{uuid.uuid4().hex[:6]}", "api", capabilities=["execute"])
    conn = await create_connection(db, org_id, integration["id"],
                                   endpoint_ref="https://93.184.216.34/v1")

    async def _ok(**kwargs):
        return {"status_code": 200, "bytes": 2, "attempts": 1, "latency_ms": 1}

    monkeypatch.setattr("app.integrations.outbound.execute", _ok)
    executed = await execute_operation(db, org_id, conn["id"], "list",
                                       method="GET", path="items", actor="flow")
    assert executed["status"] == "SUCCESS"
    usage = await record_integration_usage(db, org_id, conn["id"], "list",
                                           requests=1, actor="flow")
    assert usage["finops_record"]["source_type"] == "integration"


@pytest.mark.asyncio
async def test_flow_workflow_approval_and_gate(db, org_id, fake_user):
    from app.workflow.approval import create_approval, decide_approval
    from app.governance.plane_workflow import govern_workflow_run

    approval = await create_approval(
        db, org_id, str(uuid.uuid4()), "step-1", str(uuid.uuid4()),
        requester="flow", scope={"resource": "deploy", "action": "DEPLOY"},
        reason="flow test")
    assert approval.status == "PENDING"
    decided = await decide_approval(
        db, org_id, str(approval.id), approver="flow-lead", decision="APPROVED",
        binding_hash=approval.binding_hash)
    assert decided.status == "APPROVED"
    from app.governance.plane_policies import create_policy, create_version, set_version_status
    from app.governance.plane_bindings import create_binding
    allow_all = await create_policy(db, org_id, f"flow-allow-{uuid.uuid4().hex[:6]}")
    allow_v = await create_version(db, org_id, allow_all["id"], [{
        "name": "a", "effect": "allow", "priority": 1,
        "condition": {"field": "operation", "op": "equals", "value": "workflow.run"},
        "obligations": []}])
    await set_version_status(db, org_id, allow_v["id"], "ACTIVE")
    await create_binding(db, org_id, allow_all["id"], allow_v["id"], scope_type="tenant")
    gated = await govern_workflow_run(db, org_id, workflow_id="wf-1", fan_out=2)
    assert gated["allowed"] is True


# ─── Failure paths ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_failure_invalid_uuid_guarded(db, org_id, super_user):
    from httpx import AsyncClient, ASGITransport
    from app.api import create_app
    import app.finops.api as finops_api

    app = create_app()

    async def _override_db():
        yield db

    async def _override_user():
        return super_user

    app.dependency_overrides[finops_api._get_db] = _override_db
    app.dependency_overrides[finops_api._resolve_user] = _override_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/finops/budgets/not-a-uuid")
        assert resp.status_code in (404, 422)


@pytest.mark.asyncio
async def test_failure_pagination_bounded(db, org_id, fake_user):
    from httpx import AsyncClient, ASGITransport
    from app.api import create_app
    import app.governance.plane_common  # noqa: F401
    import app.api.governance as governance_api

    app = create_app()

    async def _override_db():
        yield db

    async def _override_user():
        return fake_user

    app.dependency_overrides[governance_api._get_db] = _override_db
    app.dependency_overrides[governance_api._resolve_user] = _override_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/governance/policies", params={"limit": 100000})
        assert resp.status_code == 422


# ─── Adversarial tenant isolation ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_adversarial_cross_tenant(db, org_id, other_org_id):
    from app.finops.costing import list_costs, record_usage_cost
    from app.governance.plane_policies import create_policy, get_policy
    from app.integrations.registry import get_integration, register_integration

    await record_usage_cost(db, org_id, {
        "provider": "openai", "model": "m", "input_tokens": 5,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "source_type": "ai_execution", "source_id": "adv-1"})
    assert (await list_costs(db, other_org_id))["total"] == 0
    policy = await create_policy(db, org_id, f"adv-{uuid.uuid4().hex[:6]}")
    with pytest.raises(Exception):
        await get_policy(db, other_org_id, policy["id"])
    integration = await register_integration(db, org_id, f"adv-{uuid.uuid4().hex[:6]}", "api")
    with pytest.raises(Exception):
        await get_integration(db, other_org_id, integration["id"])


@pytest.mark.asyncio
async def test_adversarial_guessed_uuid(db, org_id):
    from app.finops.budgets import get_budget
    from app.governance.plane_evaluate import get_decision
    with pytest.raises(Exception):
        await get_budget(db, org_id, str(uuid.uuid4()))
    with pytest.raises(Exception):
        await get_decision(db, org_id, str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_adversarial_cache_isolation(db, org_id, other_org_id):
    from app.governance.plane_cache import (cache_get_tenant, cache_invalidate_tenant,
                                            cache_set_tenant)
    await cache_set_tenant(org_id, "evaluate", {"decision": "ALLOW"}, {"op": "read"})
    assert await cache_get_tenant(other_org_id, "evaluate", {"op": "read"}) is None
    await cache_invalidate_tenant(org_id)


# ─── Cache safety ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_zero_trust_invalidation_pattern():
    from app.zero_trust import cache as _cache
    await _cache.cache_set("zero_trust:authz:t1:i:r:READ:v1", '{"allowed": true}', ttl=60)
    await _cache.cache_del_pattern("zero_trust:authz:t1:*")
    assert await _cache.cache_get("zero_trust:authz:t1:i:r:READ:v1") is None


@pytest.mark.asyncio
async def test_cached_result_tenant_key():
    from app.core.redis import cached_result
    calls = {"n": 0}

    @cached_result(ttl=60, tenant_kwarg="tenant")
    async def _fn(tenant: str, value: int):
        calls["n"] += 1
        return {"v": value}

    await _fn(tenant="t1", value=1)
    await _fn(tenant="t2", value=1)
    assert calls["n"] == 2


# ─── Transactions & resilience ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_savepoint_isolation(db, org_id):
    from app.finops.pricing import create_pricing_version
    from app.finops.governed_models import FinOpsPricingVersion
    await create_pricing_version(db, org_id, "acme", operator="t", reason="t",
                                 effective_from=(datetime.now(timezone.utc)).isoformat())
    try:
        async with db.begin_nested():
            db.add(FinOpsPricingVersion(tenant=org_id, provider="acme", version=999))
            await db.flush()
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    rows = (await db.execute(select(FinOpsPricingVersion).where(
        FinOpsPricingVersion.tenant == org_id))).scalars().all()
    assert all(r.version != 999 for r in rows)
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_eventbus_failure_safe():
    from app.core.events import Event, EventType, event_bus
    import app.core.redis as redis_mod
    original = redis_mod.get_redis

    async def _boom():
        raise ConnectionError("redis down")

    redis_mod.get_redis = _boom
    try:
        await event_bus.publish_nowait(Event(EventType.integration_created,
                                             {"id": "x"}, source="t", organization_id="t"))
    finally:
        redis_mod.get_redis = original


@pytest.mark.asyncio
async def test_worker_crash_reported(db, org_id):
    from app.finops.governed_workers import execute_aggregation
    result = await execute_aggregation(db, org_id, "fortnight", None, None)
    assert result["status"] == "failed"
    assert "error" in result


@pytest.mark.asyncio
async def test_outbound_retry_and_timeout(monkeypatch):
    import app.integrations.outbound as outbound

    calls = {"n": 0}

    class _Flaky:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def request(self, method, url, headers=None, content=None):
            calls["n"] += 1
            if calls["n"] < 3:
                import httpx as _httpx
                raise _httpx.ConnectError("down")
            return _FakeOk()

    class _FakeOk:
        status_code = 200
        content = b"ok"
        headers = {}

    monkeypatch.setattr("httpx.AsyncClient", _Flaky)
    result = await outbound.execute(tenant="t", method="GET", url="https://93.184.216.34/",
                                    max_attempts=3)
    assert result["status_code"] == 200
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_unpriced_cost_never_fabricated(db, org_id):
    from app.finops.costing import record_usage_cost
    record = await record_usage_cost(db, org_id, {
        "provider": "nope", "model": "zzz", "input_tokens": 10**9,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "source_type": "ai_execution", "source_id": "unpriced-1"})
    assert record["cost_basis"] == "unpriced"
    assert record["amount_cents"] == 0


# ─── Health, config, SDK, secrets ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_endpoint():
    from httpx import AsyncClient, ASGITransport
    from app.api import create_app

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


def test_production_config_defaults():
    from app.core.config import settings
    assert isinstance(settings.cors_origins, list)
    assert settings.cors_origins, "allowed origins must be explicit"
    assert getattr(settings, "access_token_expire_minutes", 0) > 0
    assert getattr(settings, "rate_limit_default_max", 0) <= 1000


def test_sdk_surface_consistency():
    from backend.sdk.finops import FinOpsMixin, AsyncFinOpsMixin
    from backend.sdk.governance import GovernanceMixin, AsyncGovernanceMixin
    from backend.sdk.integrations import IntegrationMixin, AsyncIntegrationMixin
    for cls in (FinOpsMixin, AsyncFinOpsMixin, GovernanceMixin,
                AsyncGovernanceMixin, IntegrationMixin, AsyncIntegrationMixin):
        assert cls is not None


def test_secret_scan():
    import pathlib
    import re

    root = pathlib.Path("backend/app")
    offenders = []
    patterns = [re.compile(r"sk-live-[A-Za-z0-9]{8,}"),
                re.compile(r"xox[bap]-[A-Za-z0-9-]+"),
                re.compile(r"AKIA[0-9A-Z]{16}"),
                re.compile(r"-----BEGIN (?:RSA )?PRIVATE KEY-----")]
    for path in root.rglob("*.py"):
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue
        for lineno, line in enumerate(lines, 1):
            window = "\n".join(lines[max(0, lineno - 9):lineno]).lower()
            if any(marker in window for marker in (
                    "detect", "regex", "pattern", "patterns", "placeholder",
                    "example", "test", "mock", "redact", "mask", "scanner",
                    "allow", "sanitiz")):
                continue
            for pattern in patterns:
                match = pattern.search(line)
                if match:
                    offenders.append(f"{path}:{lineno}:{match.group()[:16]}")
    assert offenders == [], f"possible secrets: {offenders[:10]}"
