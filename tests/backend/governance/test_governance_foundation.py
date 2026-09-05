"""C1 tests — central governance plane foundation (Volume 71 Commit 1).

Policy lifecycle, immutable versions, binding inheritance, deny
precedence, priority resolution, isolation, side-effect-free
simulation, exception expiry, mandatory-deny unbypassability,
authorization integration, auditability, determinism, pagination,
workers and migration integrity.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.core.database import Base
from app.core.events import EventType
from app.governance.plane_common import ValidationError, canonical_checksum
from app.governance.plane_models import (
    GovernancePlaneBinding,
    GovernancePlaneDecision,
    GovernancePlaneEvaluation,
    GovernancePlaneException,
    GovernancePlanePolicy,
    GovernancePlanePolicyVersion,
    GovernancePlanePostureSnapshot,
)
from app.governance.plane_policies import (
    create_policy,
    create_version,
    get_active_version,
    get_policy,
    list_policies,
    list_versions,
    set_version_status,
)
from app.governance.plane_bindings import (
    create_binding,
    delete_binding,
    list_bindings,
    resolve_chain,
    set_binding_enabled,
)
from app.governance.plane_evaluate import decide, evaluate, get_decision, list_decisions
from app.governance.plane_simulate import compare_versions, simulate_batch, simulate_one
from app.governance.plane_exceptions import (
    approve_exception,
    deny_exception,
    expire_due_exceptions,
    get_exception,
    list_exceptions,
    request_exception,
    revoke_exception,
)
from app.governance.plane_workers import (
    run_drift_detection,
    run_evaluation_sweep,
    run_evidence_refresh,
    run_exception_cleanup,
    run_posture_refresh,
)


def _allow_rule(name="allow-all", priority=0, field="operation", op="equals", value="read"):
    return {"name": name, "effect": "allow", "priority": priority,
            "condition": {"field": field, "op": op, "value": value}, "obligations": []}


def _deny_rule(name="deny-all", priority=0, field="operation", op="equals", value="write"):
    return {"name": name, "effect": "deny", "priority": priority,
            "condition": {"field": field, "op": op, "value": value}, "obligations": []}


async def _active_policy(db, org_id, rules, **over):
    policy = await create_policy(db, org_id, f"pol-{uuid.uuid4().hex[:8]}", **over)
    version = await create_version(db, org_id, policy["id"], rules)
    await set_version_status(db, org_id, version["id"], "ACTIVE")
    return policy, version


async def _bind(db, org_id, policy, version, scope_type="tenant", scope_value="", mandatory=False):
    return await create_binding(db, org_id, policy["id"], version["id"],
                                scope_type=scope_type, scope_value=scope_value,
                                mandatory=mandatory)


# ─── Models & migrations ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_governed_tables_registered():
    for table in ("governance_plane_policies", "governance_plane_policy_versions",
                  "governance_plane_bindings", "governance_plane_evaluations",
                  "governance_plane_decisions", "governance_plane_exceptions",
                  "governance_plane_exception_approvals",
                  "governance_plane_posture_snapshots"):
        assert table in Base.metadata.tables


@pytest.mark.asyncio
async def test_migration_chain():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "m0042", "backend/alembic/versions/0042_governance_foundation.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "0042_governance_foundation"
    assert module.down_revision == "0041_integrations_advanced"
    assert "governance_plane_policies" in module.GOVERNANCE_TABLES


# ─── Lifecycle & immutability ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_policy_lifecycle(db, org_id):
    policy = await create_policy(db, org_id, "access-ctl", domain="security")
    assert policy["status"] == "DRAFT"
    v1 = await create_version(db, org_id, policy["id"], [_allow_rule()])
    assert v1["version"] == 1
    assert v1["status"] == "DRAFT"
    assert v1["checksum"] == canonical_checksum({"rules": v1["rules"], "default_effect": "deny"})
    active = await set_version_status(db, org_id, v1["id"], "ACTIVE")
    assert active["status"] == "ACTIVE"
    policy = await get_policy(db, org_id, policy["id"])
    assert policy["status"] == "ACTIVE"
    assert policy["active_version_id"] == v1["id"]
    # New version supersedes the old on activation.
    v2 = await create_version(db, org_id, policy["id"], [_allow_rule("a2")])
    assert v2["version"] == 2
    await set_version_status(db, org_id, v2["id"], "ACTIVE")
    old = (await db.execute(select(GovernancePlanePolicyVersion).where(
        GovernancePlanePolicyVersion.id == uuid.UUID(v1["id"])))).scalar_one()
    assert old.status == "SUPERSEDED"
    # Terminal states are immutable.
    await set_version_status(db, org_id, v1["id"], "RETIRED")
    with pytest.raises(ValidationError):
        await set_version_status(db, org_id, v1["id"], "ACTIVE")
    # Duplicate names rejected.
    with pytest.raises(ValidationError):
        await create_policy(db, org_id, policy["name"])


@pytest.mark.asyncio
async def test_checksum_tamper_detected(db, org_id):
    policy, version = await _active_policy(db, org_id, [_allow_rule()])
    row = (await db.execute(select(GovernancePlanePolicyVersion).where(
        GovernancePlanePolicyVersion.id == uuid.UUID(version["id"])))).scalar_one()
    row.rules = [{"name": "evil", "effect": "allow", "priority": 999,
                  "condition": {"field": "operation", "op": "equals", "value": "x"},
                  "obligations": []}]
    await db.flush()
    v2 = await create_version(db, org_id, policy["id"], [_allow_rule("ok")])
    # Tampered v1 cannot be reactivated; v2 activates normally.
    with pytest.raises(ValidationError):
        await set_version_status(db, org_id, version["id"], "ACTIVE")
    activated = await set_version_status(db, org_id, v2["id"], "ACTIVE")
    assert activated["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_effective_time_window(db, org_id):
    from datetime import timezone as _tz
    policy = await create_policy(db, org_id, "timed")
    future = (datetime.now(_tz.utc) + timedelta(days=30)).isoformat()
    version = await create_version(db, org_id, policy["id"], [_allow_rule()],
                                   effective_from=future)
    await set_version_status(db, org_id, version["id"], "ACTIVE")
    assert await get_active_version(db, org_id, policy["id"]) is None
    past = (datetime.now(_tz.utc) - timedelta(days=30)).isoformat()
    version2 = await create_version(db, org_id, policy["id"], [_allow_rule("now")],
                                    effective_from=past)
    await set_version_status(db, org_id, version2["id"], "ACTIVE")
    assert (await get_active_version(db, org_id, policy["id"]))["id"] == version2["id"]


# ─── Bindings & inheritance ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_binding_inheritance_chain(db, org_id):
    policy, version = await _active_policy(db, org_id, [_allow_rule()])
    await _bind(db, org_id, policy, version, scope_type="organization")
    await _bind(db, org_id, policy, version, scope_type="tenant")
    await _bind(db, org_id, policy, version, scope_type="workspace", scope_value="ws1")
    chain = await resolve_chain(db, org_id, "workspace", "ws1")
    assert [b["scope_type"] for b in chain] == ["workspace", "tenant", "organization"]
    narrow = await resolve_chain(db, org_id, "workspace", "ws2")
    assert {b["scope_type"] for b in narrow} == {"tenant", "organization"}
    # Non-mandatory bindings can be disabled and deleted.
    ws_binding = [b for b in chain if b["scope_type"] == "workspace"][0]
    disabled = await set_binding_enabled(db, org_id, ws_binding["id"], False)
    assert disabled["enabled"] is False
    deleted = await delete_binding(db, org_id, ws_binding["id"])
    assert deleted["deleted"] is True


@pytest.mark.asyncio
async def test_mandatory_binding_protected(db, org_id):
    policy, version = await _active_policy(db, org_id, [_deny_rule()])
    binding = await _bind(db, org_id, policy, version, scope_type="organization", mandatory=True)
    assert binding["mandatory"] is True
    with pytest.raises(ValidationError):
        await set_binding_enabled(db, org_id, binding["id"], False)
    with pytest.raises(ValidationError):
        await delete_binding(db, org_id, binding["id"])
    with pytest.raises(ValidationError):
        await create_binding(db, org_id, policy["id"], version["id"],
                             scope_type="tenant", mandatory=True)


# ─── Evaluation semantics ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deny_precedence_over_allow(db, org_id):
    allow_p, allow_v = await _active_policy(db, org_id, [_allow_rule("a", priority=100)])
    deny_p, deny_v = await _active_policy(db, org_id, [_deny_rule("d", priority=1,
                                                                  field="operation",
                                                                  op="equals", value="read")])
    await _bind(db, org_id, allow_p, allow_v)
    await _bind(db, org_id, deny_p, deny_v)
    result = await evaluate(db, org_id, scope_type="tenant", operation="read",
                            context={"operation": "read"})
    assert result["decision"] == "DENY"
    assert result["policy_id"] == deny_p["id"]


@pytest.mark.asyncio
async def test_priority_and_specificity(db, org_id):
    low_p, low_v = await _active_policy(db, org_id, [_allow_rule("low", priority=1)])
    high_p, high_v = await _active_policy(db, org_id, [_deny_rule(
        "high", priority=50, field="operation", op="equals", value="read")])
    await _bind(db, org_id, low_p, low_v, scope_type="tenant")
    await _bind(db, org_id, high_p, high_v, scope_type="workspace", scope_value="ws1")
    result = await evaluate(db, org_id, scope_type="workspace", scope_value="ws1",
                            operation="read", context={"operation": "read"})
    assert result["decision"] == "DENY"
    assert result["priority"] == 50


@pytest.mark.asyncio
async def test_default_deny_without_match(db, org_id):
    policy, version = await _active_policy(db, org_id, [_allow_rule(value="other-op")])
    await _bind(db, org_id, policy, version)
    result = await evaluate(db, org_id, scope_type="tenant", operation="read",
                            context={"operation": "read"})
    assert result["decision"] == "DENY"


@pytest.mark.asyncio
async def test_deterministic_decisions(db, org_id):
    policy, version = await _active_policy(db, org_id, [_allow_rule()])
    await _bind(db, org_id, policy, version)
    first = await evaluate(db, org_id, scope_type="tenant", operation="read",
                           context={"operation": "read"})
    second = await evaluate(db, org_id, scope_type="tenant", operation="read",
                            context={"operation": "read"})
    assert first["decision"] == second["decision"] == "ALLOW"
    assert first["reason"] == second["reason"]
    assert first["policy_id"] == second["policy_id"]


@pytest.mark.asyncio
async def test_malicious_conditions_rejected(db, org_id):
    policy = await create_policy(db, org_id, "evil")
    bad_rules = [
        [{"effect": "allow", "condition": {"field": "__class__", "op": "equals", "value": 1}}],
        [{"effect": "allow", "condition": {"field": "operation", "op": "regex", "value": ".*"}}],
        [{"effect": "allow", "condition": {"field": "operation", "op": "equals"}}],
        [{"effect": "allow", "condition": {"all": [{"field": "operation", "op": "equals", "value": "x"}]}}],
    ]
    for rules in bad_rules[:3]:
        with pytest.raises(ValidationError):
            await create_version(db, org_id, policy["id"], rules)
    with pytest.raises(ValidationError):
        await create_version(db, org_id, policy["id"], [{"effect": "allow"}] * 60)
    with pytest.raises(ValidationError):
        await create_version(db, org_id, policy["id"], "not-a-list")


@pytest.mark.asyncio
async def test_context_sanitized(db, org_id):
    policy, version = await _active_policy(db, org_id, [_allow_rule()])
    await _bind(db, org_id, policy, version)
    result = await evaluate(db, org_id, scope_type="tenant", operation="read",
                            context={"operation": "read", "api_key": "sk-live",
                                     "nested": {"a": 1}})
    assert result["decision"] == "ALLOW"
    row = (await db.execute(select(GovernancePlaneEvaluation).where(
        GovernancePlaneEvaluation.tenant == org_id))).scalars().all()
    assert row, "evaluation metadata persisted (auditability)"
    assert "sk-live" not in str(row[0].metadata_ or {})


# ─── Mandatory deny unbypassable ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mandatory_deny_cannot_be_bypassed(db, org_id):
    deny_p, deny_v = await _active_policy(db, org_id, [_deny_rule(
        "org-deny", priority=1, field="classification", op="equals", value="SECRET")])
    await _bind(db, org_id, deny_p, deny_v, scope_type="organization", mandatory=True)
    allow_p, allow_v = await _active_policy(db, org_id, [{
        "name": "child-allow", "effect": "allow", "priority": 999,
        "condition": {"field": "classification", "op": "equals", "value": "SECRET"},
        "obligations": []}])
    await _bind(db, org_id, allow_p, allow_v, scope_type="workspace", scope_value="ws1")
    result = await evaluate(db, org_id, scope_type="workspace", scope_value="ws1",
                            operation="read", context={"classification": "SECRET"})
    assert result["decision"] == "DENY"
    assert "mandatory" in result["reason"]
    # Even an approved exception cannot soften a mandatory deny.
    from app.governance.plane_exceptions import request_exception
    exc = await request_exception(db, org_id, deny_p["id"], scope_type="workspace",
                                  scope_value="ws1", justification="business need",
                                  requester="u", duration_hours=1)
    from app.governance.plane_exceptions import approve_exception
    await approve_exception(db, org_id, exc["id"], approver="boss")
    again = await evaluate(db, org_id, scope_type="workspace", scope_value="ws1",
                           operation="read", context={"classification": "SECRET"})
    assert again["decision"] == "DENY"


# ─── Exceptions ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_exception_lifecycle_and_expiry(db, org_id):
    deny_p, deny_v = await _active_policy(db, org_id, [_deny_rule(
        "d", field="operation", op="equals", value="deploy")])
    await _bind(db, org_id, deny_p, deny_v)
    exc = await request_exception(db, org_id, deny_p["id"], justification="hotfix",
                                  requester="dev", duration_hours=2)
    assert exc["status"] == "PENDING"
    approved = await approve_exception(db, org_id, exc["id"], approver="lead")
    assert approved["status"] == "APPROVED"
    allowed = await evaluate(db, org_id, scope_type="tenant", operation="deploy",
                             context={"operation": "deploy"})
    assert allowed["decision"] == "ALLOW"
    assert allowed["exception_id"] == exc["id"]
    # Expired exceptions stop applying and are swept.
    row = (await db.execute(select(GovernancePlaneException).where(
        GovernancePlaneException.id == uuid.UUID(exc["id"])))).scalar_one()
    row.end_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db.flush()
    denied = await evaluate(db, org_id, scope_type="tenant", operation="deploy",
                            context={"operation": "deploy"})
    assert denied["decision"] == "DENY"
    from app.governance.plane_exceptions import expire_due_exceptions
    swept = await expire_due_exceptions(db, org_id)
    assert swept["expired"] == 1
    assert (await get_exception(db, org_id, exc["id"]))["status"] == "EXPIRED"
    # No permanent bypass: over-long windows rejected.
    with pytest.raises(ValidationError):
        await request_exception(db, org_id, deny_p["id"], justification="forever",
                                requester="dev", duration_hours=24 * 365)


@pytest.mark.asyncio
async def test_high_risk_exception_requires_approval(db, org_id):
    deny_p, deny_v = await _active_policy(db, org_id, [_deny_rule("d")])
    exc = await request_exception(db, org_id, deny_p["id"], justification="risky",
                                  requester="dev", high_risk=True)
    with pytest.raises(ValidationError):
        await approve_exception(db, org_id, exc["id"], approver="boss")
    denied = await deny_exception(db, org_id, exc["id"], approver="boss")
    assert denied["status"] == "DENIED"
    revoked = await request_exception(db, org_id, deny_p["id"], justification="x",
                                      requester="dev")
    from app.governance.plane_exceptions import revoke_exception
    assert (await revoke_exception(db, org_id, revoked["id"], actor="boss"))["status"] == "REVOKED"


# ─── Simulation ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_simulation_has_no_side_effects(db, org_id):
    policy, version = await _active_policy(db, org_id, [_deny_rule(
        "d", field="operation", op="equals", value="delete")])
    await _bind(db, org_id, policy, version)

    async def _counts():
        evals = (await db.execute(select(func.count()).select_from(
            GovernancePlaneEvaluation).where(
            GovernancePlaneEvaluation.tenant == org_id))).scalar() or 0
        decisions = (await db.execute(select(func.count()).select_from(
            GovernancePlaneDecision).where(
            GovernancePlaneDecision.tenant == org_id))).scalar() or 0
        return evals, decisions

    before = await _counts()
    single = await simulate_one(db, org_id, scope_type="tenant", operation="delete",
                                context={"operation": "delete"})
    assert single["decision"] == "DENY"
    assert single["side_effects"] is False
    batch = await simulate_batch(db, org_id, [
        {"scope_type": "tenant", "operation": "delete", "context": {"operation": "delete"}},
        {"scope_type": "tenant", "operation": "read", "context": {"operation": "read"}},
    ])
    assert batch["summary"] == {"DENY": 2}
    with pytest.raises(ValidationError):
        await simulate_batch(db, org_id, [{"scope_type": "tenant"}] * 101)
    assert await _counts() == before


@pytest.mark.asyncio
async def test_simulate_before_after(db, org_id):
    policy, version = await _active_policy(db, org_id, [_deny_rule(
        "d", field="operation", op="equals", value="delete")])
    await _bind(db, org_id, policy, version)
    requests = [{"scope_type": "tenant", "operation": "delete",
                 "context": {"operation": "delete"}}]
    proposed = {"policy_id": policy["id"], "version": 99,
                "rules": [_allow_rule("prop", field="operation", op="equals", value="delete")]}
    compared = await compare_versions(db, org_id, requests, proposed=proposed)
    assert compared["changed_count"] == 1
    assert compared["changes"][0]["before"] == "DENY"
    assert compared["changes"][0]["after"] == "ALLOW"
    assert compared["affected_resources"] == [{"scope_type": "tenant", "scope_value": ""}]


# ─── Isolation ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tenant_isolation(db, org_id):
    other = str(uuid.uuid4())
    policy, version = await _active_policy(db, org_id, [_allow_rule()])
    await _bind(db, org_id, policy, version)
    assert (await list_policies(db, org_id))["total"] == 1
    assert (await list_policies(db, other))["total"] == 0
    with pytest.raises(Exception):
        await get_policy(db, other, policy["id"])
    result = await evaluate(db, other, scope_type="tenant", operation="read",
                            context={"operation": "read"})
    assert result["decision"] == "DENY"


@pytest.mark.asyncio
async def test_workspace_isolation(db, org_id):
    policy, version = await _active_policy(db, org_id, [_allow_rule()])
    await _bind(db, org_id, policy, version, scope_type="workspace", scope_value="ws-a")
    assert await resolve_chain(db, org_id, "workspace", "ws-a") != []
    assert await resolve_chain(db, org_id, "workspace", "ws-b") == []
    from app.governance.plane_bindings import resolve_chain as _chain
    assert len(await _chain(db, org_id, "workspace", "ws-a")) == 1


# ─── Authorization integration ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_decide_additional_layer(db, org_id):
    policy, version = await _active_policy(db, org_id, [_allow_rule()])
    await _bind(db, org_id, policy, version)
    result = await decide(db, org_id, scope_type="tenant", operation="read",
                          context={"operation": "read"}, actor="tester")
    assert set(result.keys()) >= {"decision", "allowed", "reason"}
    assert isinstance(result["allowed"], bool)
    assert result["allowed"] == (result["decision"] == "ALLOW")
    assert "zero_trust" in result


@pytest.mark.asyncio
async def test_decisions_auditable(db, org_id):
    policy, version = await _active_policy(db, org_id, [_allow_rule()])
    await _bind(db, org_id, policy, version)
    result = await evaluate(db, org_id, scope_type="tenant", operation="read",
                            context={"operation": "read"}, actor="tester")
    assert "id" in result
    fetched = await get_decision(db, org_id, result["id"])
    assert fetched["reason"] == result["reason"]
    assert fetched["actor"] == "tester"
    listed = await list_decisions(db, org_id)
    assert listed["total"] >= 1


# ─── Events, SDK, CLI ────────────────────────────────────────────────────────


def test_governance_event_types_registered():
    assert EventType.governance_policy_created.value == "governance.policy.created"
    assert EventType.governance_policy_activated.value == "governance.policy.activated"
    assert EventType.governance_violation.value == "governance.violation"
    assert EventType.governance_exception_granted.value == "governance.exception.granted"
    assert EventType.governance_drift_detected.value == "governance.drift.detected"


def test_sdk_mixins_registered():
    from backend.sdk.governance import GovernanceMixin, AsyncGovernanceMixin
    from backend.sdk import GovernanceMixin as R1, AsyncGovernanceMixin as R2
    assert R1 is GovernanceMixin and R2 is AsyncGovernanceMixin
    for method in ("governance_list_policies", "governance_create_policy",
                   "governance_create_version", "governance_set_version_status",
                   "governance_create_binding", "governance_evaluate",
                   "governance_simulate", "governance_list_decisions",
                   "governance_create_exception", "governance_approve_exception",
                   "governance_posture"):
        assert callable(getattr(GovernanceMixin, method))
        assert callable(getattr(AsyncGovernanceMixin, method))


def test_cli_helpers():
    from app.cli.governance_commands import _base, _key, handle_governance_command
    assert _base(None) == "http://localhost:8000"
    assert callable(handle_governance_command)


# ─── Workers ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_workers_recovery(db, org_id):
    policy, version = await _active_policy(db, org_id, [_allow_rule()])
    await _bind(db, org_id, policy, version)
    sweep = await run_evaluation_sweep(db, org_id)
    assert sweep["status"] == "completed"
    assert sweep["evaluated"] >= 1
    cleanup = await run_exception_cleanup(db, org_id)
    assert cleanup["status"] == "completed"
    posture = await run_posture_refresh(db, org_id)
    assert posture["status"] == "completed"
    assert posture["total_policies"] >= 1
    evidence = await run_evidence_refresh(db, org_id)
    assert evidence["status"] == "completed"
    drift = await run_drift_detection(db, org_id)
    assert drift["status"] == "completed"
    assert drift["total"] == 0
    assert drift["findings"] == []
    from app.governance.plane_workers import run_evaluation_sweep as _sweep
    bad = await _sweep(db, org_id, limit="NaN")
    assert bad["status"] in ("completed", "failed")


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
async def test_api_policy_flow(api_client):
    created = await api_client.post("/api/v1/governance/policies", json={
        "name": "api-pol", "domain": "security", "owner": "sec"})
    assert created.status_code == 201, created.text
    policy_id = created.json()["id"]
    version = await api_client.post(f"/api/v1/governance/policies/{policy_id}/versions", json={
        "rules": [{"name": "r", "effect": "allow", "priority": 1,
                   "condition": {"field": "operation", "op": "equals", "value": "read"},
                   "obligations": []}],
        "reason": "initial"})
    assert version.status_code == 201, version.text
    version_id = version.json()["id"]
    activated = await api_client.post(f"/api/v1/governance/versions/{version_id}/status",
                                      json={"status": "ACTIVE"})
    assert activated.status_code == 200
    binding = await api_client.post("/api/v1/governance/bindings", json={
        "policy_id": policy_id, "version_id": version_id, "scope_type": "tenant"})
    assert binding.status_code == 201, binding.text
    evaluated = await api_client.post("/api/v1/governance/evaluate", json={
        "scope_type": "tenant", "operation": "read", "context": {"operation": "read"}})
    assert evaluated.status_code == 200
    assert evaluated.json()["decision"] == "ALLOW"
    decisions = await api_client.get("/api/v1/governance/decisions")
    assert decisions.status_code == 200
    assert decisions.json()["total"] >= 1


@pytest.mark.asyncio
async def test_api_simulate_and_posture(api_client):
    simulated = await api_client.post("/api/v1/governance/simulate", json={
        "scope_type": "tenant", "operation": "read", "context": {"operation": "read"}})
    assert simulated.status_code == 200
    assert simulated.json()["side_effects"] is False
    posture = await api_client.get("/api/v1/governance/posture")
    assert posture.status_code == 200
    assert posture.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_api_exceptions(api_client):
    policy = await api_client.post("/api/v1/governance/policies", json={"name": "exc-pol"})
    policy_id = policy.json()["id"]
    created = await api_client.post("/api/v1/governance/policy-exceptions", json={
        "policy_id": policy_id, "justification": "hotfix", "requester": "dev",
        "duration_hours": 2})
    assert created.status_code == 201, created.text
    exception_id = created.json()["id"]
    approved = await api_client.post(
        f"/api/v1/governance/policy-exceptions/{exception_id}/approve",
        json={"approver": "lead"})
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"
    listed = await api_client.get("/api/v1/governance/policy-exceptions",
                                  params={"status": "APPROVED"})
    assert listed.json()["total"] >= 1


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
async def test_api_deny_override_enforced(api_client, org_id):
    from app.iam.policy_authorizer import policy_authorizer
    policy_authorizer.set_deny_override(org_id, "organization:read")
    try:
        resp = await api_client.get("/api/v1/governance/policies")
        assert resp.status_code == 403
    finally:
        policy_authorizer.clear_deny_override(org_id, "organization:read")


@pytest.mark.asyncio
async def test_api_missing_tenant_rejected(db):
    from httpx import AsyncClient, ASGITransport
    from app.api import create_app
    import app.api.governance as governance_api

    app = create_app()

    async def _override_db():
        yield db

    async def _override_user():
        class _Anon:
            id = ""
            organization_id = ""
            role = "anonymous"
        return _Anon()

    app.dependency_overrides[governance_api._get_db] = _override_db
    app.dependency_overrides[governance_api._resolve_user] = _override_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/governance/policies")
        assert resp.status_code == 403
