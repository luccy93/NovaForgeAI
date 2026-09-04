"""C1 tests — Governed FinOps foundation (Volume 69 Commit 1).

Pricing versions, deterministic AI cost accounting, unknown pricing,
allocation idempotency, aggregation retry safety, tenant/workspace
isolation, authorization, budgets/events, API, SDK, CLI, audit and
secret redaction.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.database import Base, async_session
from app.core.events import EventType
from app.finops.governed_models import (
    FinOpsAuditLog,
    FinOpsBudget,
    FinOpsBudgetEvent,
    FinOpsCostAggregation,
    FinOpsCostAllocation,
    FinOpsCostRecord,
    FinOpsPricingVersion,
)
from app.finops.pricing import (
    create_pricing_version,
    deprecate_pricing_version,
    get_effective_pricing,
    list_pricing_versions,
)
from app.finops.costing import (
    compute_cost_cents,
    list_costs,
    record_ai_usage_cost,
    record_usage_cost,
    usage_summary,
)
from app.finops.allocation import allocate_cost, list_allocations
from app.finops.aggregation import list_aggregations, run_aggregation
from app.finops.budgets import create_budget, evaluate_budget, get_budget, list_budgets, update_budget
from app.finops.governed_common import ValidationError, dimensions_hash, idempotency_key


NOW = datetime.now(timezone.utc)


def _usage(**over):
    base = {
        "provider": "openai", "model": "gpt-4o",
        "input_tokens": 1000, "output_tokens": 500, "requests": 1,
        "occurred_at": NOW.isoformat(),
        "source_type": "ai_execution", "source_id": f"req-{uuid.uuid4().hex[:8]}",
        "dimensions": {"workspace": "ws1", "project": "p1", "operation": "chat"},
    }
    base.update(over)
    return base


async def _price(db, org_id, **over):
    kw = {"model": "gpt-4o", "input_price_cents_per_m": 500.0,
          "output_price_cents_per_m": 1500.0, "request_price_cents": 0.0,
          "operator": "tester", "reason": "test",
          "effective_from": (NOW - timedelta(days=1)).isoformat()}
    kw.update(over)
    return await create_pricing_version(db, org_id, "openai", **kw)


# ─── Models & migrations ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_governed_tables_registered():
    for table in ("finops_pricing_versions", "finops_cost_records", "finops_cost_allocations",
                  "finops_budgets", "finops_budget_events", "finops_cost_aggregations", "finops_audit_log"):
        assert table in Base.metadata.tables


@pytest.mark.asyncio
async def test_pricing_version_increments(db, org_id):
    v1 = await _price(db, org_id)
    v2 = await _price(db, org_id)
    assert v1["version"] == 1
    assert v2["version"] == 2


@pytest.mark.asyncio
async def test_effective_pricing_selection(db, org_id):
    v1 = await _price(db, org_id, effective_from=(NOW - timedelta(days=30)).isoformat())
    v2 = await _price(db, org_id, effective_from=(NOW - timedelta(days=1)).isoformat())
    eff = await get_effective_pricing(db, org_id, "openai", model="gpt-4o", at=NOW.isoformat())
    assert eff["id"] == v2["id"]
    old = await get_effective_pricing(db, org_id, "openai", model="gpt-4o",
                                      at=(NOW - timedelta(days=10)).isoformat())
    assert old["id"] == v1["id"]


@pytest.mark.asyncio
async def test_historical_pricing_immutable(db, org_id):
    v1 = await _price(db, org_id, input_price_cents_per_m=500.0)
    rec = await record_usage_cost(db, org_id, _usage())
    assert rec["pricing_version_id"] == v1["id"]
    assert rec["amount_cents"] == int(round((1000 * 500.0 + 500 * 1500.0) / 1_000_000))
    v2 = await _price(db, org_id, input_price_cents_per_m=5000.0)
    # Historical record keeps v1 snapshot, not v2 prices
    row = (await db.execute(select(FinOpsCostRecord).where(FinOpsCostRecord.id == uuid.UUID(rec["id"])))).scalar_one()
    assert row.pricing_snapshot["input_price_cents_per_m"] == 500.0
    assert row.amount_cents == rec["amount_cents"]
    # Deprecation changes status only, never prices
    dep = await deprecate_pricing_version(db, org_id, v1["id"], operator="tester")
    assert dep["status"] == "DEPRECATED"
    row2 = (await db.execute(select(FinOpsPricingVersion).where(FinOpsPricingVersion.id == uuid.UUID(v1["id"])))).scalar_one()
    assert row2.input_price_cents_per_m == 500.0


# ─── Cost calculation ────────────────────────────────────────────────────────


def test_compute_cost_deterministic():
    pricing = {"id": "x", "version": 1, "input_price_cents_per_m": 500.0,
               "output_price_cents_per_m": 1500.0, "request_price_cents": 2.0, "currency": "USD"}
    first = compute_cost_cents(input_tokens=1000, output_tokens=500, requests=3, pricing=pricing)
    second = compute_cost_cents(input_tokens=1000, output_tokens=500, requests=3, pricing=pricing)
    assert first == second
    assert first[0] == int(round((1000 * 500.0 + 500 * 1500.0) / 1_000_000 + 3 * 2.0))
    assert first[1] == "actual"


def test_compute_cost_unpriced_never_fabricated():
    amount, basis, snapshot = compute_cost_cents(input_tokens=10**9, output_tokens=10**9, pricing=None)
    assert amount == 0
    assert basis == "unpriced"
    assert snapshot == {}


@pytest.mark.asyncio
async def test_record_ai_usage_cost(db, org_id):
    await _price(db, org_id)
    rec = await record_ai_usage_cost(db, org_id, {
        "provider": "openai", "model": "gpt-4o", "prompt_tokens": 2000,
        "completion_tokens": 1000, "request_id": "r-1", "workspace": "ws1",
    })
    assert rec["input_tokens"] == 2000
    assert rec["output_tokens"] == 1000
    assert rec["cost_basis"] == "actual"
    assert rec["amount_cents"] > 0


@pytest.mark.asyncio
async def test_unknown_provider_marked_unpriced(db, org_id):
    rec = await record_usage_cost(db, org_id, _usage(provider="no-such-provider", model="zzz"))
    assert rec["cost_basis"] == "unpriced"
    assert rec["amount_cents"] == 0


@pytest.mark.asyncio
async def test_record_retry_idempotent(db, org_id):
    await _price(db, org_id)
    usage = _usage(source_id="replay-1")
    first = await record_usage_cost(db, org_id, usage)
    second = await record_usage_cost(db, org_id, usage)
    assert first["id"] == second["id"]
    assert second.get("deduplicated") is True
    rows = (await db.execute(select(FinOpsCostRecord).where(FinOpsCostRecord.tenant == org_id))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_secret_metadata_redacted(db, org_id):
    rec = await record_usage_cost(db, org_id, _usage(metadata={"api_key": "sk-live", "note": "ok"}))
    row = (await db.execute(select(FinOpsCostRecord).where(FinOpsCostRecord.id == uuid.UUID(rec["id"])))).scalar_one()
    assert row.metadata_["api_key"] == "[REDACTED]"
    assert row.metadata_["note"] == "ok"
    assert "sk-live" not in str(row.metadata_)


# ─── Allocation ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_allocation_and_no_double_count(db, org_id):
    await _price(db, org_id)
    rec = await record_usage_cost(db, org_id, _usage())
    splits = [
        {"allocation_key": "ws-a", "target_workspace": "ws-a", "share": 0.6},
        {"allocation_key": "ws-b", "target_workspace": "ws-b", "share": 0.4},
    ]
    first = await allocate_cost(db, org_id, rec["id"], splits)
    assert sum(a["amount_cents"] for a in first) <= rec["amount_cents"] + 1
    second = await allocate_cost(db, org_id, rec["id"], splits)
    assert all(a.get("deduplicated") for a in second)
    rows = (await db.execute(select(FinOpsCostAllocation).where(FinOpsCostAllocation.tenant == org_id))).scalars().all()
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_allocation_rejects_bad_shares(db, org_id):
    await _price(db, org_id)
    rec = await record_usage_cost(db, org_id, _usage())
    with pytest.raises(ValidationError):
        await allocate_cost(db, org_id, rec["id"], [{"allocation_key": "x", "share": 0.5}])


# ─── Aggregation ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_aggregation_retry_safe(db, org_id):
    await _price(db, org_id)
    await record_usage_cost(db, org_id, _usage(source_id="a1"))
    await record_usage_cost(db, org_id, _usage(source_id="a2"))
    start = (NOW - timedelta(days=1)).isoformat()
    end = (NOW + timedelta(days=1)).isoformat()
    first = await run_aggregation(db, org_id, "day", start, end)
    second = await run_aggregation(db, org_id, "day", start, end)
    assert first["records_scanned"] == 2
    assert second["buckets"] == first["buckets"]
    rows = (await db.execute(select(FinOpsCostAggregation).where(FinOpsCostAggregation.tenant == org_id))).scalars().all()
    assert len(rows) == first["buckets"]
    listed = await list_aggregations(db, org_id, granularity="day")
    assert listed["total"] == len(rows)


# ─── Isolation ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tenant_isolation(db, org_id):
    other = str(uuid.uuid4())
    await _price(db, org_id)
    await record_usage_cost(db, org_id, _usage(source_id="t1"))
    mine = await list_costs(db, org_id)
    theirs = await list_costs(db, other)
    assert mine["total"] == 1
    assert theirs["total"] == 0


@pytest.mark.asyncio
async def test_workspace_isolation(db, org_id):
    await _price(db, org_id)
    await record_usage_cost(db, org_id, _usage(source_id="w1", dimensions={"workspace": "ws-a"}))
    await record_usage_cost(db, org_id, _usage(source_id="w2", dimensions={"workspace": "ws-b"}))
    filtered = await list_costs(db, org_id, filters={"workspace": "ws-a"})
    assert filtered["total"] == 1


# ─── Budgets ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_budget_lifecycle_and_events(db, org_id):
    await _price(db, org_id)
    budget = await create_budget(db, org_id, "ai-cap", 100, warning_threshold=0.5, hard_limit_threshold=1.0)
    assert budget["status"] == "ACTIVE"
    # Spend ~62% of budget (62.5c -> 62c): crosses warning at 0.5
    usage = _usage(source_id="b1", input_tokens=100_000, output_tokens=0)
    await record_usage_cost(db, org_id, usage)
    evaluated = await evaluate_budget(db, org_id, budget["id"])
    assert evaluated["status"] == "WARNING"
    assert evaluated["spend_cents"] > 0
    events = (await db.execute(select(FinOpsBudgetEvent).where(FinOpsBudgetEvent.tenant == org_id))).scalars().all()
    assert any(e.event_type == "warning" for e in events)
    # Re-evaluation must not duplicate the warning event for the same period
    await evaluate_budget(db, org_id, budget["id"])
    events2 = (await db.execute(select(FinOpsBudgetEvent).where(FinOpsBudgetEvent.tenant == org_id))).scalars().all()
    assert len(events2) == len(events)


@pytest.mark.asyncio
async def test_budget_exceeded(db, org_id):
    await _price(db, org_id)
    budget = await create_budget(db, org_id, "tiny", 10)
    await record_usage_cost(db, org_id, _usage(source_id="e1", input_tokens=100_000, output_tokens=100_000))
    evaluated = await evaluate_budget(db, org_id, budget["id"])
    assert evaluated["status"] == "EXCEEDED"


@pytest.mark.asyncio
async def test_budget_crud(db, org_id):
    created = await create_budget(db, org_id, "ops", 5000, owner="finops-team")
    fetched = await get_budget(db, org_id, created["id"])
    assert fetched["owner"] == "finops-team"
    updated = await update_budget(db, org_id, created["id"], {"status": "SUSPENDED"}, actor="tester")
    assert updated["status"] == "SUSPENDED"
    skipped = await evaluate_budget(db, org_id, created["id"])
    assert skipped["evaluation"] == "skipped"
    listed = await list_budgets(db, org_id)
    assert listed["total"] == 1


# ─── Events, audit, SDK, CLI ─────────────────────────────────────────────────


def test_finops_event_types_registered():
    assert EventType.finops_usage_recorded.value == "finops.usage.recorded"
    assert EventType.finops_cost_calculated.value == "finops.cost.calculated"
    assert EventType.finops_budget_warning.value == "finops.budget.warning"
    assert EventType.finops_budget_exceeded.value == "finops.budget.exceeded"
    assert EventType.finops_allocation_completed.value == "finops.allocation.completed"


@pytest.mark.asyncio
async def test_audit_log_written(db, org_id):
    await _price(db, org_id, operator="auditor")
    rows = (await db.execute(select(FinOpsAuditLog).where(
        FinOpsAuditLog.tenant == org_id, FinOpsAuditLog.action == "pricing.create"))).scalars().all()
    assert len(rows) == 1
    assert rows[0].actor == "auditor"


def test_sdk_mixins_registered():
    from backend.sdk.finops import FinOpsMixin, AsyncFinOpsMixin
    from backend.sdk import FinOpsMixin as R1, AsyncFinOpsMixin as R2
    assert R1 is FinOpsMixin and R2 is AsyncFinOpsMixin
    for method in ("finops_usage_summary", "finops_list_costs", "finops_record_cost",
                   "finops_list_pricing", "finops_create_pricing", "finops_list_budgets",
                   "finops_create_budget", "finops_budget_status", "finops_evaluate_budget",
                   "finops_run_aggregation", "finops_list_aggregations"):
        assert callable(getattr(FinOpsMixin, method))
        assert callable(getattr(AsyncFinOpsMixin, method))


def test_cli_helpers():
    from app.cli.finops_commands import _base, _key, handle_finops_command
    assert _base(None) == "http://localhost:8000"
    assert callable(handle_finops_command)


# ─── API ─────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def api_client(db, org_id, fake_user):
    from httpx import AsyncClient, ASGITransport
    from app.api import create_app
    import app.finops.api as finops_api

    app = create_app()

    async def _override_db():
        yield db

    async def _override_user():
        return fake_user

    app.dependency_overrides[finops_api._get_db] = _override_db
    app.dependency_overrides[finops_api._resolve_user] = _override_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_api_usage_summary(api_client):
    resp = await api_client.get("/api/v1/finops/usage/summary")
    assert resp.status_code == 200
    assert "spend_cents" in resp.json()


@pytest.mark.asyncio
async def test_api_cost_record_and_list(api_client):
    payload = {"usage": _usage()}
    resp = await api_client.post("/api/v1/finops/costs/record", json=payload)
    assert resp.status_code == 201
    assert resp.json()["cost_basis"] in ("actual", "estimated", "unpriced")
    listed = await api_client.get("/api/v1/finops/costs")
    assert listed.status_code == 200
    assert listed.json()["total"] >= 1


@pytest.mark.asyncio
async def test_api_pricing_crud(api_client):
    created = await api_client.post("/api/v1/finops/pricing", json={
        "provider": "anthropic", "model": "claude-x",
        "input_price_cents_per_m": 300.0, "output_price_cents_per_m": 1500.0,
        "operator": "tester", "reason": "seed",
    })
    assert created.status_code == 201
    assert created.json()["version"] == 1
    listed = await api_client.get("/api/v1/finops/pricing", params={"provider": "anthropic"})
    assert listed.status_code == 200
    assert listed.json()["items"][0]["provider"] == "anthropic"


@pytest.mark.asyncio
async def test_api_budgets(api_client):
    created = await api_client.post("/api/v1/finops/budgets", json={"name": "api-cap", "amount_cents": 1000})
    assert created.status_code == 201
    budget_id = created.json()["id"]
    status = await api_client.get(f"/api/v1/finops/budgets/{budget_id}")
    assert status.status_code == 200
    assert status.json()["status"] in ("ACTIVE", "WARNING", "EXCEEDED")
    evaluated = await api_client.post(f"/api/v1/finops/budgets/{budget_id}/evaluate")
    assert evaluated.status_code == 200


@pytest.mark.asyncio
async def test_api_aggregations(api_client):
    start = (NOW - timedelta(days=1)).isoformat()
    end = (NOW + timedelta(days=1)).isoformat()
    ran = await api_client.post("/api/v1/finops/aggregations/run", json={
        "granularity": "day", "start": start, "end": end, "dimensions": {}})
    assert ran.status_code == 200
    listed = await api_client.get("/api/v1/finops/aggregations", params={"granularity": "day"})
    assert listed.status_code == 200


@pytest.mark.asyncio
async def test_api_deny_override_enforced(api_client, org_id):
    from app.iam.policy_authorizer import policy_authorizer
    policy_authorizer.set_deny_override(org_id, "billing:read")
    try:
        resp = await api_client.get("/api/v1/finops/costs")
        assert resp.status_code == 403
    finally:
        policy_authorizer.clear_deny_override(org_id, "billing:read")


@pytest.mark.asyncio
async def test_api_missing_tenant_rejected(db):
    from httpx import AsyncClient, ASGITransport
    from app.api import create_app
    import app.finops.api as finops_api

    app = create_app()

    async def _override_db():
        yield db

    async def _override_user():
        class _Anon:
            id = ""
            organization_id = ""
            role = "anonymous"
        return _Anon()

    app.dependency_overrides[finops_api._get_db] = _override_db
    app.dependency_overrides[finops_api._resolve_user] = _override_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/finops/costs")
        assert resp.status_code == 403
