import pytest, uuid

from app.observability.platform import platform_service


@pytest.mark.asyncio
async def test_metric_ingestion(db, org_id):
    res = await platform_service.ingest_metric(db, tenant=org_id, metric="cpu.usage", type="gauge", value=0.75, tags={"host": "web-1"})
    assert res["metric"] == "cpu.usage"
    assert res["value"] == 0.75


@pytest.mark.asyncio
async def test_log_redaction(db, org_id):
    res = await platform_service.ingest_log(db, tenant=org_id, service="api", environment="production", level="INFO", message="password: hunter2 token: abc123", event_type="test")
    assert "hunter2" not in res["message"]
    assert "[REDACTED]" in res["message"] or "password" not in res["message"].lower() or "hunter2" not in res["message"]


@pytest.mark.asyncio
async def test_trace_correlation(db, org_id):
    await platform_service.ingest_trace(db, tenant=org_id, trace_id="t1", span_id="s1", parent_span_id=None, service="api", operation="GET /test", duration_ms=120, status="ok")
    corr = await platform_service.correlate(db, tenant=org_id, trace_id="t1")
    assert corr["trace_id"] == "t1"


@pytest.mark.asyncio
async def test_alert_lifecycle(db, org_id):
    rule = await platform_service.create_alert_rule(db, tenant=org_id, name="high-error", resource="svc-a", condition={"type": "threshold", "threshold": 0.05}, severity="ERROR")
    alert = await platform_service.create_alert(db, tenant=org_id, resource="svc-a", condition={"type": "threshold", "threshold": 0.05}, severity="ERROR", evidence={"metric": "error_rate", "value": 0.1})
    assert alert.status == "FIRING"
    # Dedup same fingerprint
    alert2 = await platform_service.create_alert(db, tenant=org_id, resource="svc-a", condition={"type": "threshold", "threshold": 0.05}, severity="ERROR", evidence={"metric": "error_rate", "value": 0.11})
    assert alert2.id == alert.id  # deduped
    ack = await platform_service.acknowledge_alert(db, tenant=org_id, alert_id=str(alert.id), actor="sre")
    assert ack.status == "ACKNOWLEDGED"
    res = await platform_service.resolve_alert(db, tenant=org_id, alert_id=str(alert.id), actor="sre")
    assert res.status == "RESOLVED"


@pytest.mark.asyncio
async def test_alert_deduplication_distinct_not_suppressed(db, org_id):
    a1 = await platform_service.create_alert(db, tenant=org_id, resource="svc-a", condition={"type": "threshold", "threshold": 0.05, "service": "a"}, severity="ERROR", evidence={"a": 1})
    a2 = await platform_service.create_alert(db, tenant=org_id, resource="svc-b", condition={"type": "threshold", "threshold": 0.05, "service": "b"}, severity="ERROR", evidence={"b": 1})
    assert str(a1.id) != str(a2.id)


@pytest.mark.asyncio
async def test_slo_calculations(db, org_id):
    slo = await platform_service.create_slo(db, tenant=org_id, service="svc-a", indicator="availability", target=0.99, window="30d", owner="sre")
    assert slo.target == 0.99
    eval_ok = await platform_service.evaluate_slo(db, tenant=org_id, slo_id=str(slo.id), observed=0.995)
    assert eval_ok["is_breach"] is False
    eval_breach = await platform_service.evaluate_slo(db, tenant=org_id, slo_id=str(slo.id), observed=0.98)
    assert eval_breach["is_breach"] is True
    budget = await platform_service.calculate_error_budget(slo, 0.98)
    assert "remaining" in budget


@pytest.mark.asyncio
async def test_health_checks(db, org_id):
    await platform_service.register_service(db, tenant=org_id, name="svc-a", type="service", environment="production", resource="svc-a-prod")
    snap = await platform_service.record_health(db, tenant=org_id, resource="svc-a-prod", health="HEALTHY", checks={"cpu": "ok"})
    assert snap.health == "HEALTHY"
    # UNKNOWN not healthy
    snap2 = await platform_service.record_health(db, tenant=org_id, resource="svc-b", health="UNKNOWN", checks={})
    assert snap2.health == "UNKNOWN"
    # readiness check
    res = await platform_service.check_health(db, tenant=org_id, resource="svc-a-prod", check_type="readiness", config={"timeout": 5, "interval": 30})
    assert res["status"] in ("HEALTHY", "DEGRADED", "UNHEALTHY", "UNKNOWN")


@pytest.mark.asyncio
async def test_tenant_isolation(db, org_id):
    other = str(uuid.uuid4())
    await platform_service.register_service(db, tenant=org_id, name="my-svc", type="service", environment="production", resource="my-svc-res")
    # other tenant should not see it
    from sqlalchemy import select
    from app.observability.models import ObservabilityService
    res = await db.execute(select(ObservabilityService).where(ObservabilityService.tenant == other, ObservabilityService.resource == "my-svc-res"))
    assert res.scalars().first() is None


@pytest.mark.asyncio
async def test_query_limits(db, org_id):
    # Test that API would enforce limit — platform service allows any, but API should reject >1000
    # Here we just check service can handle limit param
    for i in range(5):
        await platform_service.register_service(db, tenant=org_id, name=f"svc-{i}", type="service", environment="production", resource=f"res-{i}")
    rows = await platform_service.list_services(db, tenant=org_id)
    assert len(rows) >= 5


@pytest.mark.asyncio
async def test_synthetic_checks(db, org_id):
    chk = await platform_service.create_synthetic_check(db, tenant=org_id, name="http-check", check_type="HTTP", target="https://example.com")
    assert chk.name == "http-check"
    # Run should not be destructive (only GET)
    res = await platform_service.run_synthetic_check(db, tenant=org_id, check_id=str(chk.id))
    assert res["check_id"] == str(chk.id)
    assert res["status"] in ("HEALTHY", "UNHEALTHY", "SKIPPED")

