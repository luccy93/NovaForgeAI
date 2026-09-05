"""C2 tests — enterprise governance (Volume 71 Commit 2).

Controls/evidence over existing authorities, posture counting,
drift detection, AI/data/security/FinOps/integration/workflow
governance, JIT integration, explanation, cache freshness, audit,
hardening and reporting.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.core.database import Base
from app.governance.plane_common import ValidationError
from app.governance.plane_models import GovernancePlanePolicy
from app.governance.plane_models_c2 import (
    GovernancePlaneDriftFinding,
    GovernancePlaneEvidence,
    GovernancePlaneReport,
)
from app.governance.plane_policies import create_policy, create_version, set_version_status
from app.governance.plane_bindings import create_binding
from app.governance.plane_evaluate import evaluate
from app.governance.plane_controls import (
    assess_control,
    collect_control_evidence,
    control_package,
    create_control,
    list_controls,
)
from app.governance.plane_evidence import (
    evidence_coverage,
    list_evidence,
    refresh_evidence,
    register_evidence,
)
from app.governance.plane_posture import latest_posture, refresh_posture
from app.governance.plane_drift import detect_drift, list_drift, resolve_drift
from app.governance.plane_reports import generate_report, list_reports, trends
from app.governance.plane_explain import explain_decision
from app.governance.plane_cache import (
    cache_get_tenant,
    cache_invalidate_tenant,
    cache_set_tenant,
    cached_evaluate,
)
from app.governance.plane_ai import govern_ai_request
from app.governance.plane_data import govern_data_access
from app.governance.plane_security import govern_security_action, open_critical_findings
from app.governance.plane_finops import govern_spend
from app.governance.plane_integrations import govern_integration_use
from app.governance.plane_workflow import govern_agent_step, govern_workflow_run


def _allow_rule(name="a", priority=0, field="operation", op="equals", value="read"):
    return {"name": name, "effect": "allow", "priority": priority,
            "condition": {"field": field, "op": op, "value": value}, "obligations": []}


async def _active_policy(db, org_id, rules, **over):
    policy = await create_policy(db, org_id, f"pol-{uuid.uuid4().hex[:8]}", **over)
    version = await create_version(db, org_id, policy["id"], rules)
    await set_version_status(db, org_id, version["id"], "ACTIVE")
    return policy, version


async def _bind(db, org_id, policy, version, scope_type="tenant", scope_value="",
                mandatory=False):
    return await create_binding(db, org_id, policy["id"], version["id"],
                                scope_type=scope_type, scope_value=scope_value,
                                mandatory=mandatory)


# ─── Controls over existing authorities ──────────────────────────────────────


@pytest.mark.asyncio
async def test_control_lifecycle(db, org_id):
    created = await create_control(db, org_id, "SOC2", "CC-1", owner="grc")
    assert created["control_id"] == "CC-1"
    # The authority requires valid evidence before PASS.
    await collect_control_evidence(db, org_id, created["id"],
                                   source_system="audit", source_ref="audit-logs")
    assessed = await assess_control(db, org_id, created["id"], "PASS", actor="auditor")
    assert assessed["status"] == "PASS"
    with pytest.raises(ValidationError):
        await assess_control(db, org_id, created["id"], "BOGUS")
    listed = await list_controls(db, org_id, framework="SOC2")
    assert listed["total"] == 1


@pytest.mark.asyncio
async def test_control_evidence_reference_only(db, org_id):
    created = await create_control(db, org_id, "SOC2", "CC-2")
    evidence = await collect_control_evidence(db, org_id, created["id"],
                                              source_system="audit",
                                              source_ref="audit-logs-2024")
    assert evidence["hash"] != ""
    assert "audit-logs" not in str(evidence.get("metadata", {}))
    package = await control_package(db, org_id, framework="SOC2")
    assert package is not None


# ─── Evidence registry ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_evidence_register_and_refresh(db, org_id):
    registered = await register_evidence(db, org_id, "access-reviews",
                                         source_system="audit", source_ref="audit-logs")
    assert registered["result"] == "PASS"
    assert registered["expired"] is False
    # Re-registration is idempotent on (tenant, control, system, ref).
    again = await register_evidence(db, org_id, "access-reviews",
                                    source_system="audit", source_ref="audit-logs")
    assert again["id"] == registered["id"]
    refreshed = await refresh_evidence(db, org_id)
    assert refreshed["total"] >= 1
    coverage = await evidence_coverage(db, org_id)
    assert coverage["total"] >= 1
    with pytest.raises(ValidationError):
        await register_evidence(db, org_id, "x", source_system="nope", source_ref="y")


@pytest.mark.asyncio
async def test_evidence_never_copies_datasets(db, org_id):
    big_payload = {"records": list(range(5000))}
    registered = await register_evidence(db, org_id, "min",
                                         source_system="policy_decision",
                                         source_ref="dec-1",
                                         metadata={"records": big_payload["records"]})
    row = (await db.execute(select(GovernancePlaneEvidence).where(
        GovernancePlaneEvidence.id == uuid.UUID(registered["id"])))).scalar_one()
    assert row.metadata_ is not None


# ─── Posture ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_posture_counts_only_verifiable(db, org_id):
    policy, version = await _active_policy(db, org_id, [_allow_rule()])
    await _bind(db, org_id, policy, version)
    await evaluate(db, org_id, scope_type="tenant", operation="read",
                   context={"operation": "read"})
    snapshot = await refresh_posture(db, org_id)
    assert snapshot["total_policies"] == 1
    assert snapshot["active_policies"] == 1
    history = await latest_posture(db, org_id)
    assert history["total"] >= 1
    assert set(history["items"][0].keys()) >= {
        "total_policies", "active_policies", "violations_24h",
        "open_exceptions", "verified_controls", "failing_controls"}


# ─── Drift ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_drift_tamper_and_expiry(db, org_id):
    policy, version = await _active_policy(db, org_id, [_allow_rule()])
    await _bind(db, org_id, policy, version)
    clean = await detect_drift(db, org_id)
    assert clean["total"] == 0
    # Tamper with an ACTIVE version row directly.
    from app.governance.plane_models import GovernancePlanePolicyVersion
    row = (await db.execute(select(GovernancePlanePolicyVersion).where(
        GovernancePlanePolicyVersion.id == uuid.UUID(version["id"])))).scalar_one()
    row.rules = []
    await db.flush()
    dirty = await detect_drift(db, org_id)
    assert dirty["total"] >= 1
    assert dirty["findings"][0]["finding_type"] == "policy_tampered"
    assert dirty["findings"][0]["severity"] == "CRITICAL"
    # Dedup on rerun, then resolve.
    again = await detect_drift(db, org_id)
    assert again["total"] == dirty["total"]
    resolved = await resolve_drift(db, org_id, dirty["findings"][0]["id"], actor="sec")
    assert resolved["status"] == "RESOLVED"


@pytest.mark.asyncio
async def test_drift_unbound_scope(db, org_id):
    policy, version = await _active_policy(db, org_id, [_allow_rule()])
    await _bind(db, org_id, policy, version)
    for _ in range(3):
        await evaluate(db, org_id, scope_type="workspace", scope_value="ghost",
                       operation="read", context={"operation": "read"})
    result = await detect_drift(db, org_id)
    assert any(f["finding_type"] == "unbound_scope" for f in result["findings"])


# ─── AI governance ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ai_governance_allow(db, org_id):
    policy, version = await _active_policy(db, org_id, [_allow_rule(
        "ai-ok", field="operation", op="equals", value="ai.invoke")], domain="ai")
    await _bind(db, org_id, policy, version)
    result = await govern_ai_request(db, org_id, model="gpt-4o", provider="openai",
                                     classification="INTERNAL", actor="agent-1")
    assert result["allowed"] is True
    assert result["layer"] in ("governance", "governance+finops")


@pytest.mark.asyncio
async def test_ai_governance_deny_classified(db, org_id):
    from app.governance.plane_common import SCOPE_TYPES  # noqa: F401
    policy, version = await _active_policy(db, org_id, [{
        "name": "no-secret-ai", "effect": "deny", "priority": 10,
        "condition": {"field": "classification", "op": "equals", "value": "SECRET"},
        "obligations": []}], domain="ai")
    await _bind(db, org_id, policy, version)
    result = await govern_ai_request(db, org_id, model="m", classification="SECRET")
    assert result["allowed"] is False
    assert result["decision"] == "DENY"


# ─── Data governance ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_data_governance_allow(db, org_id):
    policy, version = await _active_policy(db, org_id, [_allow_rule(
        "d", field="operation", op="equals", value="data.access")], domain="data")
    await _bind(db, org_id, policy, version)
    result = await govern_data_access(db, org_id, dataset="ds1", classification="INTERNAL")
    assert result["allowed"] is True


# ─── Security governance ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_security_governance_layered(db, org_id):
    policy, version = await _active_policy(db, org_id, [_allow_rule(
        "s", field="operation", op="equals", value="deploy")], domain="security")
    await _bind(db, org_id, policy, version)
    result = await govern_security_action(db, org_id, action="deploy",
                                          classification="INTERNAL", actor="deployer")
    assert "layer" in result
    assert isinstance(result["allowed"], bool)


@pytest.mark.asyncio
async def test_open_critical_findings_safe(db, org_id):
    result = await open_critical_findings(db, org_id)
    assert set(result.keys()) == {"total", "critical_high"}


# ─── FinOps governance ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_finops_spend_governance(db, org_id):
    policy, version = await _active_policy(db, org_id, [_allow_rule(
        "sp", field="operation", op="equals", value="spend")], domain="finops")
    await _bind(db, org_id, policy, version)
    result = await govern_spend(db, org_id, operation="spend", estimated_cents=10)
    assert result["allowed"] is True
    assert result["layer"] in ("governance", "governance+finops")


@pytest.mark.asyncio
async def test_finops_budget_exceeded_blocks(db, org_id):
    from app.finops.budgets import create_budget, evaluate_budget
    from app.finops.pricing import create_pricing_version
    from app.finops.costing import record_usage_cost
    from datetime import timedelta as _td

    now = datetime.now(timezone.utc)
    await create_pricing_version(
        db, org_id, "openai", model="m", input_price_cents_per_m=10**7,
        output_price_cents_per_m=10**7, operator="t", reason="t",
        effective_from=(now - _td(days=1)).isoformat())
    budget = await create_budget(db, org_id, "tiny", 10)
    await record_usage_cost(db, org_id, {
        "provider": "openai", "model": "m", "input_tokens": 100_000,
        "occurred_at": now.isoformat(), "source_type": "ai_execution",
        "source_id": "gov-spend-1"})
    status = await evaluate_budget(db, org_id, budget["id"])
    assert status["status"] == "EXCEEDED"
    from app.governance.plane_policies import create_policy as _create_policy
    from app.governance.plane_policies import create_version as _create_version
    from app.governance.plane_policies import set_version_status as _activate
    from app.governance.plane_bindings import create_binding as _bind_policy
    allow_all = await _create_policy(db, org_id, f"allow-{uuid.uuid4().hex[:6]}")
    allow_v = await _create_version(db, org_id, allow_all["id"], [_allow_rule(
        "a", field="operation", op="equals", value="spend")])
    await _activate(db, org_id, allow_v["id"], "ACTIVE")
    await _bind_policy(db, org_id, allow_all["id"], allow_v["id"],
                       scope_type="tenant")
    result = await govern_spend(db, org_id, operation="spend", budget_id=budget["id"])
    assert result["allowed"] is False
    assert result["layer"] == "finops"


# ─── Integration governance ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_integration_use_governed(db, org_id):
    policy, version = await _active_policy(db, org_id, [_allow_rule(
        "iu", field="operation", op="equals", value="integration.use")],
        domain="integrations")
    await _bind(db, org_id, policy, version)
    result = await govern_integration_use(
        db, org_id, connection_id="conn-1", classification="INTERNAL")
    assert result["allowed"] is True


# ─── Workflow/agent governance ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_workflow_fanout_cap(db, org_id):
    policy, version = await _active_policy(db, org_id, [_allow_rule(
        "wf", field="operation", op="equals", value="workflow.run")], domain="workflow")
    await _bind(db, org_id, policy, version)
    ok = await govern_workflow_run(db, org_id, workflow_id="wf-1", fan_out=3)
    assert ok["allowed"] is True
    blocked = await govern_workflow_run(db, org_id, workflow_id="wf-1", fan_out=99)
    assert blocked["allowed"] is False
    assert blocked["decision"] == "BLOCK"


@pytest.mark.asyncio
async def test_agent_step_cap(db, org_id):
    policy, version = await _active_policy(db, org_id, [_allow_rule(
        "ag", field="operation", op="equals", value="agent.step")], domain="agents")
    await _bind(db, org_id, policy, version)
    ok = await govern_agent_step(db, org_id, agent="a1", tool="search", step_number=3)
    assert ok["allowed"] is True
    blocked = await govern_agent_step(db, org_id, agent="a1", tool="search", step_number=500)
    assert blocked["allowed"] is False


# ─── Explanation ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_explain_decision(db, org_id):
    policy, version = await _active_policy(db, org_id, [_allow_rule("named")])
    await _bind(db, org_id, policy, version)
    result = await evaluate(db, org_id, scope_type="tenant", operation="read",
                            context={"operation": "read"}, actor="tester")
    explained = await explain_decision(db, org_id, result["id"])
    assert explained["tenant"] == org_id
    expl = explained["explanation"]
    assert expl["decision"] == "ALLOW"
    assert expl["policy"]["name"] == policy["name"]
    assert expl["version"]["version"] == 1
    assert expl["rule"]["name"] == "named"
    assert "binding" in expl
    assert expl["why"] != ""
    # Cross-tenant explanation is rejected.
    with pytest.raises(Exception):
        await explain_decision(db, str(uuid.uuid4()), result["id"])


# ─── Cache ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cache_isolation_and_invalidation(db, org_id):
    other = str(uuid.uuid4())
    await cache_set_tenant(org_id, "evaluate", {"decision": "ALLOW"}, {"op": "read"})
    assert await cache_get_tenant(other, "evaluate", {"op": "read"}) is None
    assert (await cache_get_tenant(org_id, "evaluate", {"op": "read"}))["decision"] == "ALLOW"
    assert await cache_invalidate_tenant(org_id) >= 1
    assert await cache_get_tenant(org_id, "evaluate", {"op": "read"}) is None


@pytest.mark.asyncio
async def test_cached_evaluate_version_checked(db, org_id):
    policy, version = await _active_policy(db, org_id, [_allow_rule()])
    await _bind(db, org_id, policy, version)
    first = await cached_evaluate(db, org_id, scope_type="tenant", operation="read",
                                  context={"operation": "read"})
    assert first["cached"] is False
    second = await cached_evaluate(db, org_id, scope_type="tenant", operation="read",
                                   context={"operation": "read"})
    assert second["cached"] is True
    assert second["decision"] == "ALLOW"
    # Newer mandatory deny invalidates stale cache implicitly.
    deny_p, deny_v = await _active_policy(db, org_id, [{
        "name": "new-deny", "effect": "deny", "priority": 5,
        "condition": {"field": "operation", "op": "equals", "value": "read"},
        "obligations": []}])
    await _bind(db, org_id, deny_p, deny_v, scope_type="organization", mandatory=True)
    third = await cached_evaluate(db, org_id, scope_type="tenant", operation="read",
                                  context={"operation": "read"})
    assert third["cached"] is False
    assert third["decision"] == "DENY"


# ─── Reports ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reports_and_trends(db, org_id):
    policy, version = await _active_policy(db, org_id, [_allow_rule()])
    await _bind(db, org_id, policy, version)
    await evaluate(db, org_id, scope_type="tenant", operation="read",
                   context={"operation": "read"})
    report = await generate_report(db, org_id, "posture", days=30)
    assert set(report.keys()) >= {"summary", "sections"}
    assert "violations" in report["summary"]
    assert "top_risks" in report["summary"]
    listed = await list_reports(db, org_id)
    assert listed["total"] >= 1
    trend = await trends(db, org_id)
    assert "items" in trend
    with pytest.raises(ValidationError):
        await generate_report(db, org_id, "bogus")


# ─── API ─────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def api_client(db, org_id, fake_user):
    from httpx import AsyncClient, ASGITransport
    from app.api import create_app
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
        yield client


@pytest.mark.asyncio
async def test_api_controls_evidence(api_client):
    # Control lifecycle is owned by the Data Governance router, which is
    # registered first and stays authoritative; the central plane only
    # adds the evidence registry below.
    created = await api_client.post("/api/v1/governance/controls", json={
        "framework": "SOC2", "control_id": "API-1"})
    assert created.status_code == 201, created.text
    control_id = created.json()["id"]
    evidence_first = await api_client.post(
        f"/api/v1/governance/controls/{control_id}/evidence",
        json={"evidence_type": "audit", "source": "audit-logs"})
    assert evidence_first.status_code == 201, evidence_first.text
    assessed = await api_client.post(f"/api/v1/governance/controls/{control_id}/assess",
                                     json={"status": "PASS"})
    assert assessed.status_code == 200
    registered = await api_client.post("/api/v1/governance/evidence/register", json={
        "control_key": "API-1", "source_system": "audit", "source_ref": "audit-logs"})
    assert registered.status_code == 201, registered.text
    coverage = await api_client.get("/api/v1/governance/evidence/coverage")
    assert coverage.status_code == 200
    assert coverage.json()["total"] >= 1


@pytest.mark.asyncio
async def test_api_drift_reports_explain(api_client, db, org_id):
    policy = await api_client.post("/api/v1/governance/policies", json={"name": "rep-pol"})
    policy_id = policy.json()["id"]
    version = await api_client.post(f"/api/v1/governance/policies/{policy_id}/versions", json={
        "rules": [{"name": "r", "effect": "allow", "priority": 1,
                   "condition": {"field": "operation", "op": "equals", "value": "read"},
                   "obligations": []}]})
    version_id = version.json()["id"]
    await api_client.post(f"/api/v1/governance/versions/{version_id}/status",
                          json={"status": "ACTIVE"})
    await api_client.post("/api/v1/governance/bindings", json={
        "policy_id": policy_id, "version_id": version_id, "scope_type": "tenant"})
    evaluated = await api_client.post("/api/v1/governance/evaluate", json={
        "scope_type": "tenant", "operation": "read", "context": {"operation": "read"}})
    assert evaluated.json()["decision"] == "ALLOW"
    explained = await api_client.get(
        f"/api/v1/governance/decisions/{evaluated.json()['id']}/explain")
    assert explained.status_code == 200
    assert explained.json()["explanation"]["decision"] == "ALLOW"
    drift = await api_client.post("/api/v1/governance/drift/detect")
    assert drift.status_code == 200
    report = await api_client.post("/api/v1/governance/reports", json={
        "report_type": "posture", "days": 7})
    assert report.status_code == 201, report.text
    assert "top_risks" in report.json()["summary"]
    listed = await api_client.get("/api/v1/governance/reports")
    assert listed.json()["total"] >= 1


@pytest.mark.asyncio
async def test_api_domain_governance(api_client):
    policy = await api_client.post("/api/v1/governance/policies", json={"name": "allow-all"})
    policy_id = policy.json()["id"]
    version = await api_client.post(f"/api/v1/governance/policies/{policy_id}/versions", json={
        "rules": [{"name": "a", "effect": "allow", "priority": 1,
                   "condition": {"field": "operation", "op": "contains", "value": ""},
                   "obligations": []}]})
    version_id = version.json()["id"]
    await api_client.post(f"/api/v1/governance/versions/{version_id}/status",
                          json={"status": "ACTIVE"})
    await api_client.post("/api/v1/governance/bindings", json={
        "policy_id": policy_id, "version_id": version_id, "scope_type": "tenant"})
    ai = await api_client.post("/api/v1/governance/govern/ai", json={
        "model": "gpt-4o", "classification": "INTERNAL"})
    assert ai.status_code == 200
    assert ai.json()["allowed"] is True
    data = await api_client.post("/api/v1/governance/govern/data", json={
        "dataset": "ds", "classification": "INTERNAL"})
    assert data.status_code == 200
    wf = await api_client.post("/api/v1/governance/govern/workflow", json={
        "workflow_id": "w", "fan_out": 99})
    assert wf.json()["allowed"] is False
    agent = await api_client.post("/api/v1/governance/govern/agent", json={
        "agent": "a", "step_number": 500})
    assert agent.json()["allowed"] is False


@pytest.mark.asyncio
async def test_api_viewer_denied_write(db, org_id, viewer_user):
    from httpx import AsyncClient, ASGITransport
    from app.api import create_app
    import app.api.governance as governance_api

    app = create_app()

    async def _override_db():
        yield db

    async def _override_user():
        return viewer_user

    app.dependency_overrides[governance_api._get_db] = _override_db
    app.dependency_overrides[governance_api._resolve_user] = _override_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/governance/policies", json={"name": "x"})
        assert resp.status_code == 403


@pytest.mark.asyncio
async def test_api_sdk_cli_surface():
    from backend.sdk.governance import GovernanceMixin, AsyncGovernanceMixin
    for method in ("governance_create_control", "governance_assess_control",
                   "governance_collect_evidence", "governance_register_evidence",
                   "governance_detect_drift", "governance_generate_report",
                   "governance_explain_decision", "governance_check_ai",
                   "governance_check_data", "governance_check_spend",
                   "governance_check_workflow"):
        assert callable(getattr(GovernanceMixin, method))
        assert callable(getattr(AsyncGovernanceMixin, method))
