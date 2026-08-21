"""API endpoint tests for Analytics Platform (Volume 50)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.analytics import router

app = FastAPI()
app.include_router(router)
client = TestClient(app, raise_server_exceptions=False)


def _event(**kwargs):
    defaults = {"tenant": "t-events", "source": "pytest", "event_type": "test.event",
                "event_timestamp": "2026-01-01T00:00:00Z"}
    defaults.update(kwargs)
    return defaults


def _ingest(client, **kwargs):
    resp = client.post("/api/v1/analytics/events/ingest", json=_event(**kwargs))
    assert resp.status_code == 200
    return resp.json()


# ── Event Endpoints ────────────────────────────────────────────────────

def test_ingest_event():
    resp = client.post("/api/v1/analytics/events/ingest", json={
        "tenant": "t-ingest", "source": "s", "event_type": "e",
        "event_timestamp": "2026-01-01T00:00:00Z"})
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") != "invalid"
    assert data.get("event_id")
    assert data.get("tenant") == "t-ingest"
    assert data.get("event_type") == "e"


def test_ingest_event_invalid():
    resp = client.post("/api/v1/analytics/events/ingest", json={
        "tenant": "t-ingest", "source": "s", "event_type": "e",
        "cost_usd": -5.0})
    assert resp.status_code == 422
    assert resp.json()["status"] == "invalid"
    assert resp.json()["errors"]


def test_ingest_event_batch():
    resp = client.post("/api/v1/analytics/events/ingest/batch", json={
        "idempotency_key": "batch-1",
        "events": [
            _event(event_type="a"),
            _event(event_type="b"),
            _event(event_type="c", cost_usd=-1.0),
        ]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["received"] == 3
    assert data["accepted"] == 2
    assert data["invalid"] == 1
    assert data["duplicates"] == 0
    assert len(data["results"]) == 3


def test_list_events():
    _ingest(client, tenant="t-list", event_type="list.a")
    _ingest(client, tenant="t-list", event_type="list.b")
    resp = client.get("/api/v1/analytics/events", params={"tenant": "t-list"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 2
    assert len(data["events"]) == data["count"]
    assert all(e["tenant"] == "t-list" for e in data["events"])


def test_get_event():
    event = _ingest(client, tenant="t-get")
    resp = client.get(f"/api/v1/analytics/events/{event['event_id']}")
    assert resp.status_code == 200
    assert resp.json()["event_id"] == event["event_id"]


def test_get_event_not_found():
    resp = client.get("/api/v1/analytics/events/nonexistent-event-id")
    assert resp.status_code == 404
    assert "error" in resp.json()


def test_validate_event():
    resp = client.post("/api/v1/analytics/events/validate", json=_event())
    assert resp.status_code == 200
    assert resp.json() == {"valid": True, "errors": []}


def test_validate_event_errors():
    resp = client.post("/api/v1/analytics/events/validate", json={
        "tenant": "t-validate", "source": "s", "event_type": "e",
        "metadata_extra": {"password": "hunter2"}})
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is False
    assert any("secret" in e for e in data["errors"])


def test_event_stats():
    _ingest(client, tenant="t-stats")
    resp = client.get("/api/v1/analytics/events/stats", params={"tenant": "t-stats"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert data["processed"] >= 1
    assert data["tenant_events"] >= 1


# ── Metric Endpoints ───────────────────────────────────────────────────

def test_record_metric():
    resp = client.post("/api/v1/analytics/metrics/record", json={
        "tenant": "t-metrics", "metric_name": "ai.calls.count", "value": 42.0,
        "dimensions": {"model": "gpt-4"}, "granularity": "hour"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["metric_name"] == "ai.calls.count"
    assert data["value"] == 42.0
    assert data["bucket_start"]


def test_query_metrics():
    client.post("/api/v1/analytics/metrics/record", json={
        "tenant": "t-query", "metric_name": "latency.p50", "value": 120.0})
    resp = client.post("/api/v1/analytics/metrics/query",
                       params={"tenant": "t-query"},
                       json={"metric_name": "latency.p50", "granularity": "hour"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    point = data["points"][0]
    assert point["metric_name"] == "latency.p50"
    assert point["max"] >= point["min"]


def test_list_metrics():
    client.post("/api/v1/analytics/metrics/record", json={
        "tenant": "t-metric-list", "metric_name": "custom.metric", "value": 1.0})
    resp = client.get("/api/v1/analytics/metrics/list", params={"tenant": "t-metric-list"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    assert "custom.metric" in data["metrics"]


# ── Cost Endpoints ─────────────────────────────────────────────────────

def _record_cost(client, **kwargs):
    defaults = {"tenant": "t-cost", "cost_type": "ai_model", "amount_usd": 12.5,
                "period_start": "2026-01-01", "period_end": "2026-01-31"}
    defaults.update(kwargs)
    return client.post("/api/v1/analytics/costs/record", json=defaults)


def test_record_cost():
    resp = _record_cost(client, model="gpt-4", provider="openai")
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"].startswith("cost_")
    assert data["amount_usd"] == 12.5
    assert data["currency"] == "USD"
    assert data["model"] == "gpt-4"


def test_record_cost_invalid():
    resp = _record_cost(client, amount_usd=-3.0)
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_get_costs():
    _record_cost(client, tenant="t-cost-list")
    resp = client.get("/api/v1/analytics/costs", params={"tenant": "t-cost-list"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    assert all(c["tenant"] == "t-cost-list" for c in data["costs"])


def test_cost_summary():
    _record_cost(client, tenant="t-summary", amount_usd=30.0)
    resp = client.post("/api/v1/analytics/costs/summary", json={
        "tenant": "t-summary", "group_by": "cost_type"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_usd"] >= 30.0
    assert data["entry_count"] >= 1
    assert isinstance(data["groups"], list)


def test_cost_summary_invalid_group_by():
    resp = client.post("/api/v1/analytics/costs/summary", json={
        "tenant": "t-summary", "group_by": "bogus_dimension"})
    assert resp.status_code == 400
    assert "error" in resp.json()


# ── Budget Endpoints ───────────────────────────────────────────────────

def _create_budget(client, **kwargs):
    defaults = {"tenant": "t-budget", "name": "Monthly AI Budget", "scope": "organization",
                "scope_value": "org-1", "limit_usd": 1000.0, "period": "monthly"}
    defaults.update(kwargs)
    return client.post("/api/v1/analytics/budgets", json=defaults)


def test_create_budget():
    resp = _create_budget(client)
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"].startswith("budget_")
    assert data["name"] == "Monthly AI Budget"
    assert data["limit_usd"] == 1000.0
    assert data["active"] is True


def test_create_budget_invalid_scope():
    resp = _create_budget(client, scope="galaxy")
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_list_budgets():
    _create_budget(client, tenant="t-budget-list", name="B1")
    resp = client.get("/api/v1/analytics/budgets", params={"tenant": "t-budget-list"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    assert all(b["tenant"] == "t-budget-list" for b in data["budgets"])


def test_budget_status():
    _create_budget(client, tenant="t-budget-status", name="Status Budget")
    resp = client.get("/api/v1/analytics/budgets/status",
                      params={"tenant": "t-budget-status"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    entry = data["budgets"][0]
    assert entry["name"] == "Status Budget"
    assert "status" in entry


# ── Alert Endpoints ────────────────────────────────────────────────────

def test_create_alert():
    resp = client.post("/api/v1/analytics/alerts", json={
        "tenant": "t-alert", "name": "High spend", "alert_type": "cost_spike",
        "metric_name": "ai.cost.total",
        "condition": {"operator": "gt", "threshold": 500},
        "severity": "high"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"].startswith("alert_")
    assert data["name"] == "High spend"
    assert data["status"] == "active"
    assert data["severity"] == "high"


def test_list_alerts():
    client.post("/api/v1/analytics/alerts", json={
        "tenant": "t-alert-list", "name": "A1"})
    resp = client.get("/api/v1/analytics/alerts", params={"tenant": "t-alert-list"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    assert all(a["tenant"] == "t-alert-list" for a in data["alerts"])


# ── Report Endpoints ───────────────────────────────────────────────────

def test_generate_report():
    resp = client.post("/api/v1/analytics/reports/generate", json={
        "tenant": "t-report", "report_type": "executive",
        "period_start": "2026-01-01", "period_end": "2026-01-31"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"].startswith("rpt_")
    assert data["report_type"] == "executive"
    assert data["title"] == "Executive Report"


def test_list_reports():
    client.post("/api/v1/analytics/reports/generate", json={
        "tenant": "t-report-list", "report_type": "engineering"})
    resp = client.get("/api/v1/analytics/reports", params={"tenant": "t-report-list"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    assert all(r["tenant"] == "t-report-list" for r in data["reports"])


# ── Forecast Endpoints ─────────────────────────────────────────────────

def test_create_forecast():
    resp = client.post("/api/v1/analytics/forecast", json={
        "tenant": "t-forecast", "metric_name": "ai.cost.total",
        "horizon_days": 7})
    assert resp.status_code == 200
    data = resp.json()
    assert data["tenant"] == "t-forecast"
    assert data["metric_name"] == "ai.cost.total"
    assert data["horizon_days"] == 7
    assert data["forecast_count"] == 0
    assert "Insufficient" in data["note"]


# ── Recommendation Endpoints ───────────────────────────────────────────

def test_generate_recommendations():
    resp = client.post("/api/v1/analytics/recommendations/generate", json={
        "tenant": "t-rec",
        "data": {"cost_by_service": {"api": {"current_month_usd": 500,
                                             "previous_month_usd": 100}}}})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    rec = data["created"][0]
    assert rec["category"] == "cost_optimization"
    assert rec["status"] == "pending"


def test_list_recommendations():
    client.post("/api/v1/analytics/recommendations/generate", json={
        "tenant": "t-rec-list",
        "data": {"resources": [{"resource_id": "vm-1", "resource_type": "compute",
                                "monthly_cost_usd": 250.0, "utilization_pct": 1.0}]}})
    resp = client.get("/api/v1/analytics/recommendations",
                      params={"tenant": "t-rec-list"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    assert all(r["tenant"] == "t-rec-list" for r in data["recommendations"])


# ── SLO Endpoints ──────────────────────────────────────────────────────

def test_record_slo():
    resp = client.post("/api/v1/analytics/slo/record", json={
        "tenant": "t-slo", "service": "checkout", "metric_name": "availability",
        "actual_value": 99.9, "target": 99.0,
        "window_start": "2026-01-01T00:00:00Z",
        "window_end": "2026-01-01T01:00:00Z"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"].startswith("slo_")
    assert data["compliant"] is True
    assert data["service"] == "checkout"


def test_slo_status():
    client.post("/api/v1/analytics/slo/record", json={
        "tenant": "t-slo-status", "service": "billing", "metric_name": "latency",
        "actual_value": 98.0, "target": 99.0})
    resp = client.get("/api/v1/analytics/slo/status",
                      params={"tenant": "t-slo-status", "service": "billing"})
    assert resp.status_code == 200
    data = resp.json()
    assert "billing" in data
    assert data["billing"]["total_measurements"] >= 1
    assert data["billing"]["compliance_rate"] == 0.0


# ── Engineering / DORA Endpoints ───────────────────────────────────────

def test_record_deployment():
    resp = client.post("/api/v1/analytics/engineering/deployment", json={
        "tenant": "t-eng", "service": "api-gateway", "commit_sha": "abc1234",
        "environment": "production", "success": True})
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"]
    assert data["service"] == "api-gateway"
    assert data["success"] is True
    assert data["failed"] is False


def test_compute_dora():
    client.post("/api/v1/analytics/engineering/deployment", json={
        "tenant": "t-dora", "service": "web", "commit_sha": "deadbee",
        "environment": "production", "success": True})
    resp = client.post("/api/v1/analytics/engineering/dora", json={
        "tenant": "t-dora"})
    assert resp.status_code == 200
    data = resp.json()
    assert set(data) == {"deployment_frequency", "lead_time_minutes",
                         "change_failure_rate", "mttr_minutes"}
    assert data["deployment_frequency"] > 0
    assert data["change_failure_rate"] == 0.0


# ── AI Analytics Endpoints ─────────────────────────────────────────────

def test_record_ai_call():
    resp = client.post("/api/v1/analytics/ai/record-call", json={
        "tenant": "t-ai", "model": "gpt-test", "provider": "openai",
        "input_tokens": 100, "output_tokens": 50, "cached_tokens": 10,
        "latency_ms": 850.0, "cost_usd": 0.02, "agent": "coder"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"]
    assert data["model"] == "gpt-test"
    assert data["total_tokens"] == 150
    assert data["success"] is True


def test_model_comparison():
    client.post("/api/v1/analytics/ai/record-call", json={
        "tenant": "t-ai-compare", "model": "gpt-cmp", "provider": "openai",
        "input_tokens": 10, "output_tokens": 5, "cost_usd": 0.01})
    resp = client.get("/api/v1/analytics/ai/model-comparison",
                      params={"tenant": "t-ai-compare"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    row = next(r for r in data["comparison"] if r["model"] == "gpt-cmp")
    assert row["calls"] >= 1
    assert row["total_cost_usd"] >= 0.01


# ── Marketplace Endpoints ──────────────────────────────────────────────

def test_marketplace_event():
    resp = client.post("/api/v1/analytics/marketplace/event", json={
        "tenant": "t-market", "event_type": "install", "package_name": "toolkit",
        "package_id": "pkg_123", "version": "1.2.0", "user_id": "user_9"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"].startswith("mkt_")
    assert data["event_type"] == "install"
    assert data["package_id"] == "pkg_123"


# ── Security Endpoints ─────────────────────────────────────────────────

def test_security_finding():
    resp = client.post("/api/v1/analytics/security/finding", json={
        "tenant": "t-sec", "repository": "core-api", "severity": "high",
        "category": "dependency", "title": "Vulnerable dependency",
        "file_path": "requirements.txt"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"]
    assert data["severity"] == "high"
    assert data["remediated"] is False
    assert data["fingerprint"]


# ── Data Quality Endpoints ─────────────────────────────────────────────

def test_quality_validate():
    resp = client.post("/api/v1/analytics/quality/validate", json={
        "tenant": "t-quality",
        "events": [
            {"event_id": "e1", "event_type": "click", "timestamp": "2026-01-01T00:00:00Z"},
            {"event_id": "", "event_type": "", "timestamp": "not-a-date"},
        ]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["valid"] == 1
    assert data["invalid"] == 1
    assert data["issues"]


def test_quality_issues():
    resp = client.get("/api/v1/analytics/quality/issues",
                      params={"tenant": "t-quality-issues"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["issues"], list)
    assert data["count"] == len(data["issues"])
