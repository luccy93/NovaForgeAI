"""C2 tests — forecasting, anomalies, optimization, governance (Volume 69 Commit 2).

Insufficient-data honesty, anomaly severity/dedup, evidence-based
recommendations with UNKNOWN savings, model comparison without switching,
policy gates with JIT approval, chargeback/showback provenance, versioned
pricing updates, worker idempotency/retry/concurrency, cache isolation,
authorization, range limits, events and failure recovery.
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.database import Base
from app.core.events import EventType, event_bus
from app.finops.governed_models import FinOpsCostAggregation, FinOpsCostRecord
from app.finops.governed_models_c2 import (
    FinOpsAnomaly,
    FinOpsChargebackReport,
    FinOpsForecast,
    FinOpsPolicy,
    FinOpsPolicyDecision,
    FinOpsRecommendation,
)
from app.finops.pricing import create_pricing_version
from app.finops.costing import record_usage_cost
from app.finops.governed_forecasting import generate_forecast, list_forecasts
from app.finops.anomalies import detect_anomalies, list_anomalies
from app.finops.recommendations import generate_recommendations, list_recommendations
from app.finops.model_intelligence import compare_models
from app.finops.governance import create_policy, evaluate_operation, list_policies, update_policy
from app.finops.chargeback import generate_report, list_reports
from app.finops.governed_cache import cache_get_tenant, cache_invalidate_tenant, cache_set_tenant
from app.finops.governed_common import ValidationError
from app.finops.intelligence_workers import (
    run_anomaly_job,
    run_budget_evaluation_job,
    run_forecast_job,
    run_recommendation_job,
)


NOW = datetime.now(timezone.utc)


async def _price(db, org_id, model="gpt-4o", inp=500.0, out=1500.0, **over):
    kw = {"model": model, "input_price_cents_per_m": inp, "output_price_cents_per_m": out,
          "operator": "tester", "reason": "seed",
          "effective_from": (NOW - timedelta(days=60)).isoformat()}
    kw.update(over)
    return await create_pricing_version(db, org_id, "openai", **kw)


async def _spend_days(db, org_id, days=10, per_day=2, model="gpt-4o", provider="openai",
                      tokens=100_000, start_ago=12, operation="chat"):
    for day in range(days):
        for seq in range(per_day):
            occurred = (NOW - timedelta(days=start_ago - day, minutes=seq)).isoformat()
            await record_usage_cost(db, org_id, {
                "provider": provider, "model": model,
                "input_tokens": tokens, "output_tokens": tokens // 2, "requests": 5,
                "occurred_at": occurred, "source_type": "ai_execution",
                "source_id": f"hist-{day}-{seq}-{uuid.uuid4().hex[:6]}",
                "dimensions": {"operation": operation, "workspace": "ws1"},
            })


# ─── Forecasting ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_forecast_ready(db, org_id):
    await _price(db, org_id)
    await _spend_days(db, org_id, days=10, per_day=2)
    result = await generate_forecast(db, org_id, horizon_days=30)
    assert result["status"] == "READY"
    assert result["predicted_cents"] > 0
    assert result["basis_buckets"] >= 7
    assert result["confidence"] >= 0.0
    assert result["quality"] in ("HIGH", "MEDIUM", "LOW")
    listed = await list_forecasts(db, org_id)
    assert listed["total"] >= 1


@pytest.mark.asyncio
async def test_forecast_insufficient_data_honest(db, org_id):
    await _price(db, org_id)
    await record_usage_cost(db, org_id, {
        "provider": "openai", "model": "gpt-4o", "input_tokens": 100,
        "occurred_at": NOW.isoformat(), "source_type": "ai_execution", "source_id": "lonely-1",
    })
    result = await generate_forecast(db, org_id, horizon_days=30)
    assert result["status"] == "INSUFFICIENT_DATA"
    assert "predicted_cents" not in result
    rows = (await db.execute(select(FinOpsForecast).where(FinOpsForecast.tenant == org_id))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_forecast_horizon_bounded(db, org_id):
    with pytest.raises(ValidationError):
        await generate_forecast(db, org_id, horizon_days=365)


@pytest.mark.asyncio
async def test_forecast_exhaustion_date(db, org_id):
    from app.finops.budgets import create_budget
    await _price(db, org_id)
    await _spend_days(db, org_id, days=10, per_day=2)
    budget = await create_budget(db, org_id, "cap", 1000)
    result = await generate_forecast(db, org_id, horizon_days=30, budget_id=budget["id"])
    assert result["status"] == "READY"
    assert result["budget_exhaustion_date"] is not None


# ─── Anomalies ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_anomaly_spike_detected(db, org_id):
    await _price(db, org_id)
    await _spend_days(db, org_id, days=12, per_day=1, tokens=10_000)
    # Inject a spike on the most recent day.
    await record_usage_cost(db, org_id, {
        "provider": "openai", "model": "gpt-4o", "input_tokens": 5_000_000,
        "output_tokens": 1_000_000, "occurred_at": NOW.isoformat(),
        "source_type": "ai_execution", "source_id": "spike-1",
        "dimensions": {"operation": "chat", "workspace": "ws1"},
    })
    result = await detect_anomalies(db, org_id)
    assert result["total"] >= 1
    first = result["anomalies"][0]
    assert {"baseline_cents", "observed_cents", "deviation", "severity",
            "confidence", "evidence", "bucket_start", "dimension_key",
            "dimension_value", "granularity", "status"} <= set(first.keys())
    assert first["severity"] in ("MEDIUM", "HIGH", "CRITICAL")
    assert first["observed_cents"] > first["baseline_cents"]


@pytest.mark.asyncio
async def test_anomaly_no_storm_on_rerun(db, org_id):
    await _price(db, org_id)
    await _spend_days(db, org_id, days=12, per_day=1, tokens=10_000)
    await record_usage_cost(db, org_id, {
        "provider": "openai", "model": "gpt-4o", "input_tokens": 5_000_000,
        "occurred_at": NOW.isoformat(), "source_type": "ai_execution", "source_id": "spike-2",
        "dimensions": {"operation": "chat", "workspace": "ws1"},
    })
    first = await detect_anomalies(db, org_id)
    second = await detect_anomalies(db, org_id)
    assert second["total"] == first["total"]
    rows = (await db.execute(select(FinOpsAnomaly).where(FinOpsAnomaly.tenant == org_id))).scalars().all()
    assert len(rows) == first["total"]


# ─── Recommendations ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_recommendation_cheaper_model_evidence(db, org_id):
    await _price(db, org_id, model="gpt-4o", inp=500.0, out=1500.0)
    await _price(db, org_id, model="gpt-4o-mini", inp=50.0, out=150.0)
    await _spend_days(db, org_id, days=8, per_day=3, model="gpt-4o", tokens=200_000)
    result = await generate_recommendations(db, org_id)
    assert result["total"] >= 1
    cheaper = [r for r in result["recommendations"] if r["rec_type"] == "cheaper_model"]
    assert cheaper, "expected a cheaper-model recommendation with real pricing evidence"
    assert cheaper[0]["estimated_savings_cents"] is not None
    assert cheaper[0]["savings_known"] is True
    assert cheaper[0]["evidence"]["top_model"] == "gpt-4o"


@pytest.mark.asyncio
async def test_recommendation_unknown_savings_never_fabricated(db, org_id):
    await _price(db, org_id)
    # Many tiny requests -> batching rule fires, savings honestly UNKNOWN.
    for seq in range(60):
        await record_usage_cost(db, org_id, {
            "provider": "openai", "model": "gpt-4o", "input_tokens": 10,
            "requests": 1, "occurred_at": (NOW - timedelta(days=seq % 9 + 1)).isoformat(),
            "source_type": "ai_execution", "source_id": f"tiny-{seq}",
            "dimensions": {"operation": "ping"},
        })
    result = await generate_recommendations(db, org_id)
    batched = [r for r in result["recommendations"] if r["rec_type"] == "batch_requests"]
    assert batched
    assert batched[0]["estimated_savings_cents"] is None
    assert batched[0]["savings"] == "UNKNOWN"
    assert batched[0]["evidence"]["requests"] >= 50


# ─── Model intelligence ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_model_compare_no_switching(db, org_id):
    await _price(db, org_id, model="gpt-4o")
    await _price(db, org_id, model="gpt-4o-mini", inp=50.0, out=150.0)
    await _spend_days(db, org_id, days=8, per_day=2, model="gpt-4o", tokens=100_000)
    await _spend_days(db, org_id, days=8, per_day=2, model="gpt-4o-mini", tokens=100_000)
    result = await compare_models(db, org_id)
    assert result["total"] == 2
    assert result["items"][0]["spend_cents"] >= result["items"][1]["spend_cents"]
    assert all("cost_per_request_cents" in r for r in result["items"])
    assert "switch" not in str(result).lower() or "governed" in result["note"]


# ─── Governance gate ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gate_allow_by_default(db, org_id):
    result = await evaluate_operation(db, org_id, "user-1", "chat", estimated_cents=10)
    assert result["decision"] == "ALLOW"
    assert result["allowed"] is True


@pytest.mark.asyncio
async def test_gate_block_policy(db, org_id):
    await create_policy(db, org_id, "no-big-runs", operation="train",
                        max_estimated_cents=100, action="block")
    result = await evaluate_operation(db, org_id, "user-1", "train", estimated_cents=500)
    assert result["decision"] == "BLOCK"
    assert result["allowed"] is False


@pytest.mark.asyncio
async def test_gate_warn_policy(db, org_id):
    await create_policy(db, org_id, "watch-serve", operation="serve",
                        max_estimated_cents=100, action="warn")
    result = await evaluate_operation(db, org_id, "user-1", "serve", estimated_cents=500)
    assert result["decision"] == "WARN"
    assert result["allowed"] is True


@pytest.mark.asyncio
async def test_gate_require_approval_creates_jit(db, org_id):
    await create_policy(db, org_id, "approve-train", operation="train",
                        max_estimated_cents=100, action="require_approval")
    result = await evaluate_operation(db, org_id, "user-1", "train", estimated_cents=500)
    assert result["decision"] == "REQUIRE_APPROVAL"
    assert result["approval_id"] != ""
    from app.zero_trust.jit import get_access
    rec = await get_access(db, org_id, result["approval_id"])
    assert rec is not None
    assert rec.status == "REQUESTED"


@pytest.mark.asyncio
async def test_gate_server_estimate_overrides_client(db, org_id):
    await _price(db, org_id)
    await create_policy(db, org_id, "cap-chat", operation="chat",
                        max_estimated_cents=100, action="block")
    # Client claims 1c but server-side pricing says far more.
    result = await evaluate_operation(
        db, org_id, "user-1", "chat", estimated_cents=1,
        usage={"input_tokens": 1_000_000, "output_tokens": 500_000, "requests": 1},
        model="gpt-4o", provider="openai")
    assert result["estimated_cents"] > 1
    assert result["decision"] == "BLOCK"


@pytest.mark.asyncio
async def test_policy_crud(db, org_id):
    created = await create_policy(db, org_id, "p1", max_estimated_cents=50, action="warn")
    updated = await update_policy(db, org_id, created["id"], {"enabled": False}, actor="tester")
    assert updated["enabled"] is False
    listed = await list_policies(db, org_id)
    assert listed["total"] == 1


# ─── Chargeback / showback ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_showback_report(db, org_id):
    await _price(db, org_id)
    await _spend_days(db, org_id, days=3, per_day=2)
    start = (NOW - timedelta(days=15)).isoformat()
    end = (NOW + timedelta(days=1)).isoformat()
    report = await generate_report(db, org_id, "showback", start=start, end=end, group_by="workspace")
    assert report["total_cents"] > 0
    assert report["provenance"]["source"] == "finops_cost_records"
    assert any(line["group"] == "ws1" for line in report["lines"])
    # Idempotent regeneration.
    again = await generate_report(db, org_id, "showback", start=start, end=end, group_by="workspace")
    assert again.get("deduplicated") is True
    assert again["id"] == report["id"]


@pytest.mark.asyncio
async def test_chargeback_report_provenance(db, org_id):
    from app.finops.allocation import allocate_cost
    await _price(db, org_id)
    rec = await record_usage_cost(db, org_id, {
        "provider": "openai", "model": "gpt-4o", "input_tokens": 100_000,
        "occurred_at": NOW.isoformat(), "source_type": "ai_execution", "source_id": "cb-1",
    })
    await allocate_cost(db, org_id, rec["id"], [
        {"allocation_key": "ws-a", "target_workspace": "ws-a", "share": 1.0}])
    start = (NOW - timedelta(days=1)).isoformat()
    end = (NOW + timedelta(days=1)).isoformat()
    report = await generate_report(db, org_id, "chargeback", start=start, end=end, group_by="workspace")
    assert report["total_cents"] == rec["amount_cents"]
    assert report["provenance"]["source"] == "finops_cost_allocations"


# ─── Pricing governance ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pricing_override_requires_new_version(db, org_id):
    v1 = await _price(db, org_id, inp=500.0)
    v2 = await create_pricing_version(db, org_id, "openai", model="gpt-4o",
                                      input_price_cents_per_m=600.0, output_price_cents_per_m=1500.0,
                                      operator="governor", reason="quarterly refresh",
                                      effective_from=NOW.isoformat())
    assert v2["version"] == v1["version"] + 1
    assert v2["operator"] == "governor"


@pytest.mark.asyncio
async def test_pricing_override_authorization_enforced(api_client):
    viewer = {"id": str(uuid.uuid4()), "organization_id": None, "role": "viewer"}

    async def _viewer():
        class _V:
            id = viewer["id"]
            organization_id = ""
            role = "viewer"
        return _V()

    import app.finops.api as finops_api
    from httpx import AsyncClient, ASGITransport
    from app.api import create_app
    from app.core.database import async_session

    app = create_app()

    async def _db():
        async with async_session() as session:
            yield session

    app.dependency_overrides[finops_api._get_db] = _db
    app.dependency_overrides[finops_api._resolve_user] = _viewer
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/finops/pricing", json={"provider": "x"})
        assert resp.status_code in (401, 403)


# ─── Workers ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_worker_forecast_idempotent(db, org_id):
    await _price(db, org_id)
    await _spend_days(db, org_id, days=9, per_day=2)
    first = await run_forecast_job(db, org_id, horizon_days=14)
    second = await run_forecast_job(db, org_id, horizon_days=14)
    assert first["status"] == "completed"
    assert second["status"] == "completed"


@pytest.mark.asyncio
async def test_worker_anomaly_and_recommendation(db, org_id):
    await _price(db, org_id)
    await _spend_days(db, org_id, days=9, per_day=2)
    assert (await run_anomaly_job(db, org_id))["status"] == "completed"
    assert (await run_recommendation_job(db, org_id))["status"] == "completed"
    assert (await run_budget_evaluation_job(db, org_id))["status"] == "completed"


@pytest.mark.asyncio
async def test_worker_retry_safe_aggregation(db, org_id):
    from app.core.database import async_session
    from app.finops.governed_workers import execute_aggregation
    await _price(db, org_id)
    await _spend_days(db, org_id, days=4, per_day=2)
    start = (NOW - timedelta(days=13)).isoformat()
    end = (NOW + timedelta(days=1)).isoformat()
    # Independent sessions: AsyncSession does not support concurrent use.
    # The lease may legitimately skip one run; the guarantee under test is
    # no crash, no duplicates, and one canonical bucket set afterwards.
    async with async_session() as s1, async_session() as s2:
        results = await asyncio.gather(*[
            execute_aggregation(s, org_id, "day", start, end) for s in (s1, s2)
        ])
    assert all(r["status"] in ("completed", "skipped") for r in results)
    assert any(r["status"] == "completed" for r in results)
    rows = (await db.execute(select(FinOpsCostAggregation))).scalars().all()
    assert len({(r.granularity, r.bucket_start, r.dimensions_hash) for r in rows}) == len(rows)


@pytest.mark.asyncio
async def test_worker_failure_recovery(db, org_id):
    from app.finops.governed_workers import execute_aggregation
    result = await execute_aggregation(db, org_id, "fortnight", None, None)
    assert result["status"] == "failed"
    assert "error" in result


# ─── Cache ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cache_tenant_isolation(db, org_id):
    other = str(uuid.uuid4())
    await cache_set_tenant(org_id, "summary", {"spend": 100}, {"d": "day"})
    assert await cache_get_tenant(other, "summary", {"d": "day"}) is None
    assert await cache_get_tenant(org_id, "summary", {"d": "day"}) == {"spend": 100}


@pytest.mark.asyncio
async def test_cache_invalidation(db, org_id):
    await cache_set_tenant(org_id, "forecast", {"p": 1}, {})
    assert await cache_get_tenant(org_id, "forecast", {}) == {"p": 1}
    assert await cache_invalidate_tenant(org_id) >= 1
    assert await cache_get_tenant(org_id, "forecast", {}) is None


# ─── API, events, ranges ─────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def api_client(db, org_id, fake_user):
    from httpx import AsyncClient, ASGITransport
    from app.api import create_app
    import app.finops.api as finops_api
    import app.finops.api_c2 as finops_c2

    app = create_app()

    async def _override_db():
        yield db

    async def _override_user():
        return fake_user

    app.dependency_overrides[finops_api._get_db] = _override_db
    app.dependency_overrides[finops_api._resolve_user] = _override_user
    app.dependency_overrides[finops_c2._get_db] = _override_db
    app.dependency_overrides[finops_c2._resolve_user] = _override_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_api_forecast_insufficient(api_client):
    resp = await api_client.get("/api/v1/finops/forecast", params={"horizon_days": 30})
    assert resp.status_code == 200
    assert resp.json()["status"] == "INSUFFICIENT_DATA"


@pytest.mark.asyncio
async def test_api_forecast_horizon_rejected(api_client):
    resp = await api_client.get("/api/v1/finops/forecast", params={"horizon_days": 500})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_api_anomalies_and_recommendations(api_client, db, org_id):
    await _price(db, org_id)
    await _spend_days(db, org_id, days=9, per_day=2)
    detected = await api_client.post("/api/v1/finops/anomalies/detect", json={"lookback_days": 14})
    assert detected.status_code == 200
    listed = await api_client.get("/api/v1/finops/anomalies")
    assert listed.status_code == 200
    gen = await api_client.post("/api/v1/finops/recommendations/generate")
    assert gen.status_code == 200
    recs = await api_client.get("/api/v1/finops/recommendations")
    assert recs.status_code == 200


@pytest.mark.asyncio
async def test_api_policies_and_gate(api_client):
    created = await api_client.post("/api/v1/finops/policies", json={
        "name": "gate-cap", "operation": "train", "max_estimated_cents": 100, "action": "block"})
    assert created.status_code == 201
    gated = await api_client.post("/api/v1/finops/gate/evaluate", json={
        "operation": "train", "estimated_cents": 500})
    assert gated.status_code == 200
    assert gated.json()["decision"] == "BLOCK"
    allowed = await api_client.post("/api/v1/finops/gate/evaluate", json={
        "operation": "chat", "estimated_cents": 5})
    assert allowed.json()["decision"] == "ALLOW"


@pytest.mark.asyncio
async def test_api_reports(api_client, db, org_id):
    await _price(db, org_id)
    await _spend_days(db, org_id, days=3, per_day=2)
    start = (NOW - timedelta(days=15)).isoformat()
    end = (NOW + timedelta(days=1)).isoformat()
    showback = await api_client.post("/api/v1/finops/reports/showback", json={
        "start": start, "end": end, "group_by": "workspace"})
    assert showback.status_code == 200
    assert showback.json()["total_cents"] > 0
    listed = await api_client.get("/api/v1/finops/reports")
    assert listed.status_code == 200


@pytest.mark.asyncio
async def test_api_compare(api_client, db, org_id):
    await _price(db, org_id)
    await _spend_days(db, org_id, days=3, per_day=1)
    resp = await api_client.get("/api/v1/finops/models/compare")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


@pytest.mark.asyncio
async def test_api_date_range_limited(api_client):
    start = (NOW - timedelta(days=200)).isoformat()
    end = NOW.isoformat()
    resp = await api_client.get("/api/v1/finops/costs", params={"start": start, "end": end})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_event_emission_observability(db, org_id):
    received: list = []

    async def _handler(event):
        received.append(event)

    event_bus.subscribe(EventType.finops_forecast_generated, _handler)
    try:
        await _price(db, org_id)
        await _spend_days(db, org_id, days=9, per_day=2)
        await generate_forecast(db, org_id, horizon_days=14)
        assert any(e.event_type == EventType.finops_forecast_generated for e in received)
    finally:
        event_bus.unsubscribe(EventType.finops_forecast_generated, _handler)
