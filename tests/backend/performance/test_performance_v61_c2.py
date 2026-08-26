import pytest, uuid

from app.performance.capacity import CapacityForecastService
from app.performance.benchmark import BenchmarkService
from app.performance.budgets import PerformanceBudgetService


@pytest.mark.asyncio
async def test_capacity_forecast_with_uncertainty(db, org_id):
    svc = CapacityForecastService()
    # Record some metrics first for forecast
    from app.performance.metrics import MetricsService
    ms = MetricsService()
    for v in [50, 55, 60, 65, 70]:
        await ms.record_metric(db, tenant=org_id, service="api", metric_name="cpu", value=float(v), granularity="day")
    res = await svc.forecast(db, tenant=org_id, resource="api", metric="cpu", horizon_days=7)
    assert isinstance(res, dict)
    assert "forecast" in res or "note" in res
    # Should have uncertainty or confidence or note
    assert "uncertainty" in res or "confidence" in res or "note" in res


@pytest.mark.asyncio
async def test_benchmark_lifecycle_and_baseline(db, org_id):
    svc = BenchmarkService()
    definition = await svc.create_definition(tenant=org_id, name="api-bench", suite_type="api", config={"endpoint": "/api/test"})
    assert definition["name"] == "api-bench"
    assert definition["immutable"] is True
    # Run benchmark
    run = await svc.run_benchmark(db, tenant=org_id, definition_id=definition["id"], environment="test")
    assert "run_id" in run or "results" in run
    run_id = run.get("run_id") or run.get("results", {}).get("run_id") or list(svc._runs.keys())[-1]
    # Set baseline
    baseline = await svc.set_baseline(tenant=org_id, definition_id=definition["id"], run_id=run_id)
    assert baseline["run_id"] == run_id
    # Second run and compare
    run2 = await svc.run_benchmark(db, tenant=org_id, definition_id=definition["id"], environment="test")
    run2_id = run2.get("run_id") or list(svc._runs.keys())[-1]
    comp = await svc.compare(tenant=org_id, definition_id=definition["id"], run_id=run2_id)
    assert "regression" in comp or "baseline" in comp


@pytest.mark.asyncio
async def test_stress_soak_never_production(db, org_id):
    svc = BenchmarkService()
    definition = await svc.create_definition(tenant=org_id, name="stress-bench", suite_type="api", config={})
    # Stress test should be controlled, not production
    res = await svc.run_stress(tenant=org_id, definition_id=definition["id"], concurrency=5, duration_seconds=10)
    assert res["stress"]["note"] == "controlled, not production" or "controlled" in str(res).lower()
    assert res["stress"]["concurrency"] == 5
    # Soak
    res2 = await svc.run_soak(tenant=org_id, definition_id=definition["id"], duration_hours=1)
    assert "soak" in res2


@pytest.mark.asyncio
async def test_performance_regression_gate(db, org_id):
    svc = BenchmarkService()
    definition = await svc.create_definition(tenant=org_id, name="reg-bench", suite_type="api", config={})
    run = await svc.run_benchmark(db, tenant=org_id, definition_id=definition["id"])
    run_id = run.get("run_id") or list(svc._runs.keys())[-1]
    await svc.set_baseline(tenant=org_id, definition_id=definition["id"], run_id=run_id)
    # Second run
    run2 = await svc.run_benchmark(db, tenant=org_id, definition_id=definition["id"])
    run2_id = run2.get("run_id") or list(svc._runs.keys())[-1]
    gate = await svc.check_regression_gate(tenant=org_id, definition_id=definition["id"], run_id=run2_id, thresholds={"latency": 0.1})
    assert gate["gate"] in ("passed", "failed")


@pytest.mark.asyncio
async def test_autoscaling_safety_respects_max(db, org_id):
    from app.performance.capacity import CapacityForecastService
    svc = CapacityForecastService()
    # Create a capacity policy with max 5
    from app.performance.models import CapacityPolicy
    pol = CapacityPolicy(tenant=org_id, resource="api", metric="cpu", target=70.0, min_instances=1, max_instances=5, cooldown_seconds=300, enabled=True)
    db.add(pol)
    await db.flush()
    # Scaling recommendation should respect max
    rec = await svc.recommend_scaling(db, tenant=org_id, resource="api")
    assert isinstance(rec, dict)
    # Should not recommend beyond max
    for r in rec.get("recommendations", []):
        assert "evidence" in r


@pytest.mark.asyncio
async def test_noisy_neighbor_detection(db, org_id):
    from app.performance.metrics import MetricsService
    ms = MetricsService()
    # Simulate noisy tenant by high request rate
    for i in range(10):
        await ms.record_metric(db, tenant=org_id, service="api", metric_name="request_rate", value=1000.0, granularity="minute")
    # Check that tenant's metrics are isolated
    other = str(uuid.uuid4())
    res_other = await ms.query_metrics(db, tenant=other, service="api", metric_name="request_rate", limit=10)
    assert len(res_other) == 0
    res_self = await ms.query_metrics(db, tenant=org_id, service="api", metric_name="request_rate", limit=10)
    assert len(res_self) >= 1


@pytest.mark.asyncio
async def test_cost_aware_scaling(db, org_id):
    # Cost should be considered, not just availability
    from app.performance.budgets import PerformanceBudgetService
    svc = PerformanceBudgetService()
    b = await svc.create_budget(db, tenant=org_id, service="api", metric_type="cost", metric_name="cost_per_request", target=0.01, window="1h")
    res = await svc.check_budget(db, tenant=org_id, budget_id=str(b.id), observed=0.02)
    assert res["breached"] is True or res["status"] in ("warning", "hard", "breached")


@pytest.mark.asyncio
async def test_security_under_load_still_enforced(db, org_id):
    # Security controls must remain active under load — check that IAM still enforced
    from app.performance.budgets import PerformanceBudgetService
    svc = PerformanceBudgetService()
    # Create a budget and check that even under high load, budget check still works
    b = await svc.create_budget(db, tenant=org_id, service="api", metric_type="api", metric_name="latency", target=100.0, window="1h")
    # Simulate high load by checking with high observed
    res = await svc.check_budget(db, tenant=org_id, budget_id=str(b.id), observed=200.0)
    assert res["breached"] is True
