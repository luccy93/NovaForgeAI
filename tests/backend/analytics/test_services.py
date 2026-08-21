"""Service tests for Analytics Platform (Volume 50)."""

from datetime import datetime, timezone

import pytest

from app.analytics.normalization_service import NormalizationService
from app.analytics.aggregation_service import AggregationService
from app.analytics.cost_service import CostService
from app.analytics.budget_service import BudgetService
from app.analytics.alert_service import AnalyticsAlertService
from app.analytics.report_service import ReportService
from app.analytics.forecasting_service import ForecastingService
from app.analytics.recommendation_service import RecommendationService
from app.analytics.slo_analytics_service import SLOAnalyticsService
from app.analytics.engineering_service import EngineeringService
from app.analytics.ai_analytics_service import AIAnalyticsService
from app.analytics.marketplace_analytics_service import MarketplaceAnalyticsService
from app.analytics.security_analytics_service import SecurityAnalyticsService
from app.analytics.data_quality_service import DataQualityService

TS = "2026-01-01T00:00:00+00:00"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _valid_event(**overrides) -> dict:
    event = {
        "tenant": "t",
        "source": "s",
        "event_type": "e",
        "event_timestamp": TS,
    }
    event.update(overrides)
    return event


class TestNormalizationService:

    def test_ingest_valid_event(self):
        svc = NormalizationService()
        result = svc.ingest(_valid_event())
        assert result["event_id"]
        assert result["tenant"] == "t"
        assert result["source"] == "s"
        assert result["event_type"] == "e"

    def test_ingest_generates_event_id(self):
        svc = NormalizationService()
        result = svc.ingest(_valid_event())
        assert result["event_id"]
        assert len(result["event_id"]) == 32

    def test_ingest_missing_tenant(self):
        svc = NormalizationService()
        result = svc.ingest({"source": "s", "event_type": "e",
                             "event_timestamp": TS})
        assert result["status"] == "invalid"
        assert any("tenant" in err for err in result["errors"])

    def test_ingest_missing_source(self):
        svc = NormalizationService()
        result = svc.ingest({"tenant": "t", "event_type": "e",
                             "event_timestamp": TS})
        assert result["status"] == "invalid"
        assert any("source" in err for err in result["errors"])

    def test_ingest_missing_event_type(self):
        svc = NormalizationService()
        result = svc.ingest({"tenant": "t", "source": "s",
                             "event_timestamp": TS})
        assert result["status"] == "invalid"
        assert any("event_type" in err for err in result["errors"])

    def test_ingest_duplicate_detection(self):
        svc = NormalizationService()
        first = svc.ingest(_valid_event())
        second = svc.ingest(_valid_event())
        assert first.get("status") is None
        assert second["status"] == "duplicate"
        assert second["fingerprint"] == first["fingerprint"]

    def test_validate_event_with_secrets(self):
        svc = NormalizationService()
        valid, errors = svc.validate_event(
            _valid_event(metadata_extra={"secret": "hunter2"}))
        assert valid is False
        assert any("secret" in err for err in errors)
        result = svc.ingest(_valid_event(metadata_extra={"api_key": "k"}))
        assert result["status"] == "invalid"

    def test_list_events_filter(self):
        svc = NormalizationService()
        svc.ingest(_valid_event(event_type="a"))
        svc.ingest(_valid_event(event_type="b"))
        svc.ingest(_valid_event(event_type="a", resource_id="r2"))
        filtered = svc.list_events(tenant="t", event_type="a")
        assert len(filtered) == 2
        assert all(e["event_type"] == "a" for e in filtered)

    def test_ingest_batch_and_stats(self):
        svc = NormalizationService()
        results = svc.ingest_batch([_valid_event(event_type=f"t{i}")
                                    for i in range(3)])
        assert len(results) == 3
        stats = svc.get_stats()
        assert stats["total"] == 3
        assert stats["processed"] == 3


class TestAggregationService:

    def test_record_metric(self):
        svc = AggregationService()
        dp = svc.record_metric("t", "ai.calls.count", 5,
                               timestamp=TS)
        assert dp["value"] == 5
        assert dp["metric_name"] == "ai.calls.count"
        assert dp["tenant"] == "t"

    def test_query_metric(self):
        svc = AggregationService()
        for i in range(3):
            svc.record_metric("t", "m.q", float(i + 1), timestamp=TS)
        results = svc.query_metric("t", "m.q")
        assert sum(r["count"] for r in results) == 3
        assert sum(r["value"] for r in results) == 6.0

    def test_aggregate(self):
        svc = AggregationService()
        svc.record_metric("t", "m.agg", 1.0, timestamp="2026-01-01T01:00:00+00:00")
        svc.record_metric("t", "m.agg", 2.0, timestamp="2026-01-01T02:00:00+00:00")
        svc.record_metric("t", "m.agg", 3.0, timestamp="2026-01-01T03:00:00+00:00")
        agg = svc.aggregate("t", "m.agg", "", "")
        assert agg["count"] == 3
        assert agg["sum"] == 6.0
        assert agg["avg"] == 2.0
        assert agg["min"] == 1.0
        assert agg["max"] == 3.0

    def test_get_trend(self):
        svc = AggregationService()
        svc.record_metric("t", "m.trend", 4.0, timestamp="2026-01-01T10:00:00+00:00",
                          granularity="day")
        svc.record_metric("t", "m.trend", 6.0, timestamp="2026-01-02T10:00:00+00:00",
                          granularity="day")
        trend = svc.get_trend("t", ["m.trend"], granularity="day")
        assert len(trend) == 2
        assert trend[0]["value"] == 4.0
        assert trend[1]["value"] == 6.0

    def test_list_metrics(self):
        svc = AggregationService()
        svc.record_metric("t", "alpha", 1.0, timestamp=TS)
        svc.record_metric("t", "beta", 2.0, timestamp=TS)
        names = svc.list_metrics("t")
        assert "alpha" in names
        assert "beta" in names

    def test_get_latest(self):
        svc = AggregationService()
        svc.record_metric("t", "m.latest", 2.0, timestamp=TS)
        svc.record_metric("t", "m.latest", 8.0, timestamp=TS)
        latest = svc.get_latest("t", "m.latest")
        assert latest is not None
        assert latest["count"] == 2
        assert latest["value"] == 10.0


class TestCostService:

    def test_record_cost(self):
        svc = CostService()
        entry = svc.record_cost("t", "ai_model", 1.5, "2026-01-01", "2026-01-31")
        assert entry["id"].startswith("cost_")
        assert entry["amount_usd"] == 1.5
        assert entry["currency"] == "USD"
        assert entry["cost_basis"] == "actual"

    def test_get_costs_filter(self):
        svc = CostService()
        svc.record_cost("t", "ai_model", 1.0, "2026-01-01", "2026-01-31")
        svc.record_cost("t", "storage", 2.0, "2026-01-01", "2026-01-31")
        svc.record_cost("t", "compute", 3.0, "2026-01-01", "2026-01-31")
        costs = svc.get_costs("t", cost_type="ai_model")
        assert len(costs) == 1
        assert costs[0]["cost_type"] == "ai_model"

    def test_get_cost_summary(self):
        svc = CostService()
        svc.record_cost("t", "ai_model", 5.0, "2026-01-01", "2026-01-31")
        svc.record_cost("t", "ai_model", 2.0, "2026-01-01", "2026-01-31")
        svc.record_cost("t", "storage", 3.0, "2026-01-01", "2026-01-31")
        summary = svc.get_cost_summary("t", group_by="cost_type")
        assert summary["total_usd"] == 10.0
        assert summary["entry_count"] == 3
        groups = {g["value"]: g["total_usd"] for g in summary["groups"]}
        assert groups["ai_model"] == 7.0
        assert groups["storage"] == 3.0

    def test_get_total_cost(self):
        svc = CostService()
        svc.record_cost("t", "ai_model", 2.5, "2026-01-01", "2026-01-31")
        svc.record_cost("t", "storage", 3.5, "2026-01-01", "2026-01-31")
        assert svc.get_total_cost("t") == 6.0
        assert svc.get_total_cost("t", cost_type="ai_model") == 2.5

    def test_get_ai_cost_breakdown(self):
        svc = CostService()
        svc.record_cost("t", "model", 4.0, "2026-01-01", "2026-01-31",
                        model="gpt-4", provider="openai", agent="coder")
        svc.record_cost("t", "model", 1.0, "2026-01-01", "2026-01-31",
                        model="claude-3", provider="anthropic", agent="writer")
        breakdown = svc.get_ai_cost_breakdown("t")
        assert breakdown["total_ai_cost_usd"] == 5.0
        by_model = {g["value"]: g["total_usd"] for g in breakdown["by_model"]}
        assert by_model["gpt-4"] == 4.0
        assert by_model["claude-3"] == 1.0
        by_provider = {g["value"] for g in breakdown["by_provider"]}
        assert by_provider == {"openai", "anthropic"}

    def test_get_cost_trend(self):
        svc = CostService()
        svc.record_cost("t", "ai_model", 2.0, "2026-01-01", "2026-01-31")
        svc.record_cost("t", "storage", 3.0, "2026-01-01", "2026-01-31")
        trend = svc.get_cost_trend("t", granularity="day")
        assert len(trend) >= 1
        assert sum(bucket["total_usd"] for bucket in trend) == 5.0
        assert sum(bucket["entry_count"] for bucket in trend) == 2

    def test_compare_models(self):
        svc = CostService()
        svc.record_cost("t", "model", 3.0, "2026-01-01", "2026-01-31",
                        model="gpt-4", metadata={"latency_ms": 200, "success": True})
        svc.record_cost("t", "model", 1.0, "2026-01-01", "2026-01-31",
                        model="claude-3")
        rows = svc.compare_models("t")
        models = {row["model"] for row in rows}
        assert models == {"gpt-4", "claude-3"}
        gpt_row = next(r for r in rows if r["model"] == "gpt-4")
        assert gpt_row["call_count"] == 1
        assert gpt_row["avg_latency_ms"] == 200.0


class TestBudgetService:

    def _budget(self, svc: BudgetService, limit_usd: float = 1000.0) -> dict:
        return svc.create_budget("t", "Monthly AI", "organization", "org-1",
                                 limit_usd=limit_usd)

    def test_create_budget(self):
        svc = BudgetService()
        budget = self._budget(svc)
        assert budget["id"].startswith("budget_")
        assert budget["limit_usd"] == 1000.0
        assert budget["active"] is True
        assert budget["period"] == "monthly"

    def test_list_budgets(self):
        svc = BudgetService()
        self._budget(svc)
        svc.create_budget("t", "Storage Cap", "workspace", "ws-1", limit_usd=500.0)
        budgets = svc.list_budgets(tenant="t")
        assert len(budgets) == 2
        names = {b["name"] for b in budgets}
        assert names == {"Monthly AI", "Storage Cap"}

    def test_update_budget(self):
        svc = BudgetService()
        budget = self._budget(svc)
        updated = svc.update_budget(budget["id"], limit_usd=2000.0, name="Renamed")
        assert updated["limit_usd"] == 2000.0
        assert updated["name"] == "Renamed"

    def test_check_budget_ok(self):
        svc = BudgetService()
        budget = self._budget(svc)
        result = svc.check_budget(budget["id"], 500.0)
        assert result["status"] == "ok"
        assert result["remaining_usd"] == 500.0

    def test_check_budget_warning(self):
        svc = BudgetService()
        budget = self._budget(svc)
        result = svc.check_budget(budget["id"], 850.0)
        assert result["status"] == "warning"

    def test_check_budget_soft_limit(self):
        svc = BudgetService()
        budget = self._budget(svc)
        result = svc.check_budget(budget["id"], 970.0)
        assert result["status"] == "soft_limit"

    def test_check_budget_hard_limit(self):
        svc = BudgetService()
        budget = self._budget(svc)
        result = svc.check_budget(budget["id"], 1100.0)
        assert result["status"] == "hard_limit"
        assert result["remaining_usd"] == -100.0


class TestAlertService:

    def test_create_alert(self):
        svc = AnalyticsAlertService()
        alert = svc.create_alert("t", "High AI spend", "threshold",
                                 metric_name="ai.cost.total",
                                 condition={"op": ">", "value": 100},
                                 severity="high")
        assert alert["id"].startswith("alert_")
        assert alert["name"] == "High AI spend"
        assert alert["severity"] == "high"
        assert alert["status"] == "active"
        assert alert["last_triggered"] is None

    def test_list_alerts_filter(self):
        svc = AnalyticsAlertService()
        svc.create_alert("t", "Cost spike", "threshold")
        svc.create_alert("t", "Anomaly", "anomaly")
        alerts = svc.list_alerts(tenant="t", alert_type="threshold")
        assert len(alerts) == 1
        assert alerts[0]["alert_type"] == "threshold"

    def test_update_alert(self):
        svc = AnalyticsAlertService()
        alert = svc.create_alert("t", "Latency", "threshold", severity="medium")
        updated = svc.update_alert(alert["id"], severity="critical")
        assert updated["severity"] == "critical"
        assert svc.get_alert(alert["id"])["severity"] == "critical"

    def test_trigger_alert(self):
        svc = AnalyticsAlertService()
        alert = svc.create_alert("t", "Budget burn", "threshold")
        entry = svc.trigger_alert(alert["id"], current_value=123.5)
        assert entry["alert_id"] == alert["id"]
        assert entry["current_value"] == 123.5
        history = svc.get_alert_history(alert_id=alert["id"])
        assert len(history) == 1
        assert svc.get_alert(alert["id"])["last_triggered"] is not None

    def test_evaluate_alerts(self):
        svc = AnalyticsAlertService()
        svc.create_alert("t", "CPU hot", "threshold", metric_name="cpu_pct")
        triggered = svc.evaluate_alerts("t", metrics={"cpu_pct": 97})
        assert len(triggered) == 1
        assert triggered[0]["current_value"] == 97.0

    def test_delete_alert(self):
        svc = AnalyticsAlertService()
        alert = svc.create_alert("t", "Temp", "threshold")
        assert svc.delete_alert(alert["id"]) is True
        assert svc.get_alert(alert["id"]) is None
        assert svc.delete_alert(alert["id"]) is False


class TestReportService:

    def test_generate_report(self):
        svc = ReportService()
        report = svc.generate_report("t", "finops", "2026-01-01", "2026-01-31",
                                     data={"total_cost_usd": 42.0})
        assert report["id"].startswith("rpt_")
        assert report["report_type"] == "finops"
        assert report["data"]["total_cost_usd"] == 42.0

    def test_list_reports(self):
        svc = ReportService()
        for i in range(3):
            svc.generate_report("t", "executive", "2026-01-01", "2026-01-31")
        reports = svc.list_reports(tenant="t")
        assert len(reports) == 3

    def test_generate_executive_report(self):
        svc = ReportService()
        report = svc.generate_executive_report(
            "t", "2026-01-01", "2026-01-31",
            analytics_data={"total_cost_usd": 1500.0, "ai_calls": 250,
                            "recommendations_count": 4})
        assert report["report_type"] == "executive"
        assert report["data"]["total_cost_usd"] == 1500.0
        assert report["data"]["ai_calls"] == 250
        assert report["title"] == "Executive Report"

    def test_export_report(self):
        svc = ReportService()
        report = svc.generate_report("t", "sre", "2026-01-01", "2026-01-31")
        exported = svc.export_report(report["id"], format="json")
        assert exported["format"] == "json"
        assert exported["filename"].endswith(".json")
        assert exported["data"]["id"] == report["id"]

    def test_delete_report(self):
        svc = ReportService()
        report = svc.generate_report("t", "security", "2026-01-01", "2026-01-31")
        assert svc.delete_report(report["id"]) is True
        assert svc.get_report(report["id"]) is None
        assert svc.delete_report(report["id"]) is False


class TestForecastingService:

    def test_forecast_insufficient_data(self):
        svc = ForecastingService()
        assert svc.forecast("t", "ai.cost.total", horizon_days=7) == []

    def test_forecast_with_sufficient_data(self):
        svc = ForecastingService()
        for day in range(1, 7):
            svc.record_data_point("t", "ai.cost.total", float(day),
                                  timestamp=f"2026-06-{day:02d}T00:00:00+00:00")
        points = svc.forecast("t", "ai.cost.total", horizon_days=7)
        assert len(points) == 7
        assert points[-1]["predicted_value"] > points[0]["predicted_value"]
        assert points[0]["confidence_upper"] >= points[0]["confidence_lower"]

    def test_record_forecast_then_get(self):
        svc = ForecastingService()
        record = svc.record_forecast("t", "ai.cost.total", "2026-09-01",
                                     predicted_value=120.0,
                                     confidence_lower=100.0,
                                     confidence_upper=140.0)
        assert record["forecast_id"]
        assert record["status"] == "active"
        forecasts = svc.get_forecasts("t", metric_name="ai.cost.total")
        assert len(forecasts) == 1
        assert forecasts[0]["predicted_value"] == 120.0

    def test_get_forecast_accuracy(self):
        svc = ForecastingService()
        accuracy = svc.get_forecast_accuracy("t", "ai.cost.total")
        assert accuracy["forecasts_evaluated"] == 0
        assert accuracy["mean_absolute_error"] == 0.0
        assert "note" in accuracy


class TestRecommendationService:

    def _record(self, svc: RecommendationService, category: str = "cost_optimization",
                title: str = "Rightsize model") -> dict:
        return svc.record_recommendation(
            tenant="t", category=category, title=title,
            description="Switch to a cheaper model.",
            reason="Cost per call is above benchmark.",
            evidence={"model": "gpt-4"},
            estimated_impact_usd=25.0, confidence=0.8, risk="low")

    def test_record_recommendation(self):
        svc = RecommendationService()
        rec = self._record(svc)
        assert rec["recommendation_id"]
        assert rec["category"] == "cost_optimization"
        assert rec["status"] == "pending"
        assert rec["estimated_impact_usd"] == 25.0

    def test_list_recommendations(self):
        svc = RecommendationService()
        self._record(svc)
        self._record(svc, title="Cache responses")
        self._record(svc, category="resource_management", title="Idle VM")
        recs = svc.get_recommendations(tenant="t", category="cost_optimization")
        assert len(recs) == 2
        assert all(r["category"] == "cost_optimization" for r in recs)

    def test_dismiss_recommendation(self):
        svc = RecommendationService()
        rec = self._record(svc)
        dismissed = svc.dismiss_recommendation(rec["recommendation_id"])
        assert dismissed["status"] == "dismissed"
        assert dismissed["resolved_at"] is not None
        pending = svc.get_recommendations(tenant="t")
        assert all(r["recommendation_id"] != rec["recommendation_id"]
                   for r in pending)

    def test_accept_recommendation(self):
        svc = RecommendationService()
        rec = self._record(svc)
        accepted = svc.accept_recommendation(rec["recommendation_id"])
        assert accepted["status"] == "accepted"


class TestSLOAnalyticsService:

    def test_record_slo_measurement(self):
        svc = SLOAnalyticsService()
        m = svc.record_slo_measurement("t", "api", "availability",
                                       actual_value=99.9, target=99.5,
                                       window_start="2026-08-20T00:00:00+00:00",
                                       window_end=_now_iso())
        assert m["id"].startswith("slo_")
        assert m["compliant"] is True

    def test_get_slo_status(self):
        svc = SLOAnalyticsService()
        end = _now_iso()
        svc.record_slo_measurement("t", "api", "availability", 99.9, 99.5,
                                   "2026-08-20T00:00:00+00:00", end)
        svc.record_slo_measurement("t", "api", "availability", 98.0, 99.5,
                                   "2026-08-20T00:00:00+00:00", end)
        status = svc.get_slo_status("t")
        assert status["api"]["total_measurements"] == 2
        assert status["api"]["compliant"] == 1
        assert status["api"]["compliance_rate"] == 0.5

    def test_get_error_budget(self):
        svc = SLOAnalyticsService()
        end = _now_iso()
        for _ in range(3):
            svc.record_slo_measurement("t", "api", "availability", 99.9, 99.5,
                                       "2026-08-20T00:00:00+00:00", end)
        svc.record_slo_measurement("t", "api", "availability", 99.0, 99.5,
                                   "2026-08-20T00:00:00+00:00", end)
        budget = svc.get_error_budget("t", service="api")
        assert budget["violations"] == 1
        assert budget["total"] == 4
        assert budget["budget_remaining_pct"] == 0.75

    def test_get_slo_breaches(self):
        svc = SLOAnalyticsService()
        end = _now_iso()
        svc.record_slo_measurement("t", "api", "availability", 99.9, 99.5,
                                   "2026-08-20T00:00:00+00:00", end)
        breach = svc.record_slo_measurement("t", "api", "availability", 90.0, 99.5,
                                            "2026-08-20T00:00:00+00:00", end)
        breaches = svc.get_slo_breaches("t", service="api")
        assert len(breaches) == 1
        assert breaches[0]["id"] == breach["id"]
        assert breaches[0]["compliant"] is False

    def test_compute_burn_rate(self):
        svc = SLOAnalyticsService()
        end = _now_iso()
        svc.record_slo_measurement("t", "api", "availability", 90.0, 99.5,
                                   "2026-08-20T00:00:00+00:00", end)
        svc.record_slo_measurement("t", "api", "availability", 91.0, 99.5,
                                   "2026-08-20T00:00:00+00:00", end)
        assert svc.compute_burn_rate("t", service="api", window_hours=1) == 1.0

    def test_get_slo_summary(self):
        svc = SLOAnalyticsService()
        end = _now_iso()
        svc.record_slo_measurement("t", "api", "availability", 99.9, 99.5,
                                   "2026-08-20T00:00:00+00:00", end)
        summary = svc.get_slo_summary("t")
        assert summary["api"]["total"] == 1
        assert summary["api"]["compliance_rate"] == 1.0


class TestEngineeringService:

    def test_record_deployment(self):
        svc = EngineeringService()
        dep = svc.record_deployment("t", "api", commit_sha="abc123",
                                    deployed_at="2026-08-20T10:00:00+00:00")
        assert dep["id"]
        assert dep["service"] == "api"
        assert dep["success"] is True
        assert dep["failed"] is False
        assert dep["deployed_at"].startswith("2026-08-20T10:00:00")

    def test_record_lead_time_event(self):
        svc = EngineeringService()
        event = svc.record_lead_time_event("t", "repo-x", commit_sha="abc123",
                                           commit_time="2026-08-20T09:00:00+00:00",
                                           deploy_time="2026-08-20T10:00:00+00:00")
        assert event["resolved"] is True
        assert event["lead_time_minutes"] == 60.0

    def test_compute_dora(self):
        svc = EngineeringService()
        for i, sha in enumerate(("sha-a", "sha-b")):
            minute = 10 + i
            svc.record_deployment("t", "api", commit_sha=sha,
                                  deployed_at=f"2026-08-20T10:{minute:02d}:00+00:00")
            svc.record_lead_time_event("t", "repo-x", commit_sha=sha,
                                       commit_time=f"2026-08-20T09:{minute:02d}:00+00:00",
                                       deploy_time=f"2026-08-20T10:{minute:02d}:00+00:00")
        dora = svc.compute_dora("t")
        assert dora["deployment_frequency"] > 0
        assert dora["lead_time_minutes"] == 60.0
        assert dora["change_failure_rate"] == 0.0
        assert dora["mttr_minutes"] == 0.0

    def test_get_deployment_frequency(self):
        svc = EngineeringService()
        svc.record_deployment("t", "api", deployed_at="2026-08-20T10:00:00+00:00")
        svc.record_deployment("t", "api", deployed_at="2026-08-20T11:00:00+00:00")
        freq = svc.get_deployment_frequency("t", period="day")
        assert freq == 2.0

    def test_record_pr_event(self):
        svc = EngineeringService()
        pr = svc.record_pr_event("t", "repo-x", pr_id="PR-1", status="merged",
                                 created_at="2026-08-20T10:00:00+00:00",
                                 merged_at="2026-08-20T11:00:00+00:00",
                                 review_time_minutes=15)
        assert pr["merged"] is True
        assert pr["cycle_time_minutes"] == 60.0
        assert pr["merge_time_minutes"] == 45.0

    def test_get_pr_metrics(self):
        svc = EngineeringService()
        for pr_id, hour in (("PR-1", 10), ("PR-2", 12)):
            svc.record_pr_event("t", "repo-x", pr_id=pr_id, status="merged",
                                created_at=f"2026-08-20T{hour:02d}:00:00+00:00",
                                merged_at=f"2026-08-20T{hour + 1:02d}:00:00+00:00",
                                review_time_minutes=10)
        metrics = svc.get_pr_metrics("t", repository="repo-x")
        assert metrics["total_prs"] == 2
        assert metrics["merged_prs"] == 2
        assert metrics["merge_rate"] == 1.0
        assert metrics["cycle_time_minutes"] == 60.0


class TestAIAnalyticsService:

    def test_record_ai_call(self):
        svc = AIAnalyticsService()
        call = svc.record_ai_call("t", "gpt-4", "openai", input_tokens=100,
                                  output_tokens=50, latency_ms=250.0,
                                  cost_usd=0.02)
        assert call["id"]
        assert call["total_tokens"] == 150
        assert call["success"] is True
        assert call["cost_usd"] == 0.02

    def test_get_model_comparison(self):
        svc = AIAnalyticsService()
        svc.record_ai_call("t", "gpt-4", "openai", input_tokens=100,
                           output_tokens=50, cost_usd=0.02)
        svc.record_ai_call("t", "gpt-4", "openai", input_tokens=80,
                           output_tokens=40, cost_usd=0.03)
        svc.record_ai_call("t", "claude-3", "anthropic", input_tokens=100,
                           output_tokens=50, cost_usd=0.01)
        comparison = svc.get_model_comparison("t")
        by_model = {row["model"]: row for row in comparison}
        assert set(by_model) == {"gpt-4", "claude-3"}
        assert by_model["gpt-4"]["calls"] == 2
        assert by_model["gpt-4"]["total_cost_usd"] == 0.05
        assert comparison[0]["model"] == "gpt-4"

    def test_get_ai_usage_summary(self):
        svc = AIAnalyticsService()
        svc.record_ai_call("t", "gpt-4", "openai", input_tokens=100,
                           output_tokens=50, cached_tokens=20, cost_usd=0.01)
        svc.record_ai_call("t", "claude-3", "anthropic", input_tokens=200,
                           output_tokens=100, success=False,
                           error_message="rate limited")
        summary = svc.get_ai_usage_summary("t")
        assert summary["total_calls"] == 2
        assert summary["successful_calls"] == 1
        assert summary["failed_calls"] == 1
        assert summary["total_tokens"] == 450
        assert summary["distinct_models"] == 2

    def test_get_agent_analytics(self):
        svc = AIAnalyticsService()
        svc.record_agent_run("t", "coder", task="fix bug", tool_calls=5,
                             iterations=3, tokens=500, cost_usd=0.5,
                             duration_ms=4000.0, human_approved=True)
        svc.record_agent_run("t", "coder", task="write docs", tool_calls=2,
                             iterations=2, tokens=300, cost_usd=0.2,
                             duration_ms=2000.0)
        analytics = svc.get_agent_analytics("t")
        assert analytics["total_runs"] == 2
        assert analytics["successful_runs"] == 2
        assert analytics["distinct_agents"] == 1
        assert analytics["by_agent"]["coder"]["runs"] == 2
        assert analytics["human_approval_rate"] == 0.5

    def test_detect_runaway_agent(self):
        svc = AIAnalyticsService()
        svc.record_agent_run("t", "runaway-agent", iterations=5, cost_usd=25.0)
        svc.record_agent_run("t", "calm-agent", iterations=2, cost_usd=0.5)
        flagged = svc.detect_runaway_agent("t")
        assert len(flagged) == 1
        assert flagged[0]["agent_name"] == "runaway-agent"
        assert "cost_threshold_exceeded" in flagged[0]["reasons"]
        assert flagged[0]["total_cost_usd"] == 25.0

    def test_rag_analytics(self):
        svc = AIAnalyticsService()
        svc.record_rag_query("t", query="what is graphrag?", results_count=5,
                             context_size=1200, latency_ms=180.0)
        svc.record_rag_query("t", query="empty query", results_count=0,
                             latency_ms=90.0)
        rag = svc.get_rag_analytics("t")
        assert rag["total_queries"] == 2
        assert rag["zero_result_queries"] == 1
        assert rag["zero_result_rate"] == 0.5


class TestMarketplaceAnalyticsService:

    def test_record_marketplace_event(self):
        svc = MarketplaceAnalyticsService()
        event = svc.record_marketplace_event("t", "install",
                                             package_name="code-graph",
                                             package_id="pkg-1", version="1.2.0",
                                             user_id="u1")
        assert event["id"].startswith("mkt_")
        assert event["event_type"] == "install"
        assert event["package_id"] == "pkg-1"

    def test_get_marketplace_summary(self):
        svc = MarketplaceAnalyticsService()
        svc.record_marketplace_event("t", "install", package_id="pkg-1",
                                     user_id="u1")
        svc.record_marketplace_event("t", "view", package_id="pkg-2",
                                     user_id="u2")
        summary = svc.get_marketplace_summary("t")
        assert summary["total_events"] == 2
        assert summary["unique_packages"] == 2
        assert summary["unique_users"] == 2
        assert summary["by_type"] == {"install": 1, "view": 1}

    def test_get_popular_packages(self):
        svc = MarketplaceAnalyticsService()
        for _ in range(3):
            svc.record_marketplace_event("t", "install", package_id="pkg-hot")
        svc.record_marketplace_event("t", "install", package_id="pkg-cold")
        popular = svc.get_popular_packages("t")
        assert popular[0] == {"package": "pkg-hot", "count": 3}
        assert {"package": "pkg-cold", "count": 1} in popular

    def test_get_package_analytics(self):
        svc = MarketplaceAnalyticsService()
        svc.record_marketplace_event("t", "install", package_id="pkg-1",
                                     user_id="u1")
        svc.record_marketplace_event("t", "uninstall", package_id="pkg-1",
                                     user_id="u2")
        analytics = svc.get_package_analytics("t", package_id="pkg-1")
        assert analytics["total_events"] == 2
        assert analytics["by_type"] == {"install": 1, "uninstall": 1}
        assert analytics["unique_users"] == 2


class TestSecurityAnalyticsService:

    def test_record_security_finding(self):
        svc = SecurityAnalyticsService()
        finding = svc.record_security_finding("t", repository="repo-x",
                                              severity="CRITICAL",
                                              category="sast", title="SQLi risk",
                                              file_path="app/db.py",
                                              detected_at="2026-08-20T10:00:00+00:00")
        assert finding["id"]
        assert finding["severity"] == "critical"
        assert finding["fingerprint"]
        assert finding["remediated"] is False

    def test_get_security_summary(self):
        svc = SecurityAnalyticsService()
        svc.record_security_finding("t", repository="repo-x", severity="critical",
                                    title="f1")
        svc.record_security_finding("t", repository="repo-x", severity="high",
                                    title="f2")
        svc.record_security_finding("t", repository="repo-y", severity="low",
                                    title="f3", remediated=True)
        summary = svc.get_security_summary("t")
        assert summary["total_findings"] == 3
        assert summary["by_severity"]["critical"] == 1
        assert summary["by_severity"]["high"] == 1
        assert summary["open_critical"] == 1
        assert summary["remediation_rate"] == round(1 / 3, 4)
        assert summary["repositories"] == 2

    def test_get_repositories_at_risk(self):
        svc = SecurityAnalyticsService()
        for i in range(5):
            svc.record_security_finding("t", repository="repo-risky",
                                        severity="critical", title=f"c{i}")
        svc.record_security_finding("t", repository="repo-safe",
                                    severity="critical", title="single")
        at_risk = svc.get_repositories_at_risk("t", threshold=5)
        assert len(at_risk) == 1
        assert at_risk[0]["repository"] == "repo-risky"
        assert at_risk[0]["critical_count"] == 5
        assert at_risk[0]["open_critical"] == 5

    def test_get_finding_trends(self):
        svc = SecurityAnalyticsService()
        svc.record_security_finding("t", repository="repo-x", severity="critical",
                                    title="f1",
                                    detected_at="2026-08-20T10:00:00+00:00")
        svc.record_security_finding("t", repository="repo-x", severity="low",
                                    title="f2", remediated=True,
                                    detected_at="2026-08-20T11:00:00+00:00")
        trends = svc.get_finding_trends("t", granularity="day")
        assert len(trends) == 1
        assert trends[0]["period"] == "2026-08-20"
        assert trends[0]["findings"] == 2
        assert trends[0]["critical"] == 1
        assert trends[0]["remediated"] == 1


class TestDataQualityService:

    def test_validate_event_quality(self):
        svc = DataQualityService()
        issues = svc.validate_event({"event_id": "e1", "event_type": "ai.call",
                                     "timestamp": TS, "cost_usd": 0.05,
                                     "duration_ms": 120.0})
        assert issues == []

    def test_validate_event_bad_cost(self):
        svc = DataQualityService()
        issues = svc.validate_event({"event_id": "e2", "event_type": "ai.call",
                                     "timestamp": TS, "cost_usd": -5.0})
        assert len(issues) == 1
        assert issues[0]["issue_type"] == "negative_cost"
        assert issues[0]["field"] == "cost_usd"
        assert issues[0]["severity"] == "high"

    def test_validate_event_missing_fields(self):
        svc = DataQualityService()
        issues = svc.validate_event({"timestamp": "not-a-date"})
        types = {issue["issue_type"] for issue in issues}
        assert "missing_field" in types
        assert "invalid_timestamp" in types

    def test_detect_duplicates(self):
        svc = DataQualityService()
        events = [{"event_id": "dup-1"}, {"event_id": "dup-1"},
                  {"event_id": "uniq"}]
        duplicates = svc.detect_duplicates(events)
        assert len(duplicates) == 1
        assert duplicates[0]["event_id"] == "dup-1"
        assert duplicates[0]["occurrences"] == 2

    def test_get_quality_summary(self):
        svc = DataQualityService()
        svc.record_issue("t", "missing_field", "ingestor", "Field missing.",
                         severity="high")
        svc.record_issue("t", "negative_cost", "ingestor", "Negative cost.",
                         severity="medium")
        summary = svc.get_quality_summary("t")
        assert summary["total_issues"] == 2
        assert summary["unresolved_count"] == 2
        assert summary["by_type"]["missing_field"] == 1

    def test_resolve_issue(self):
        svc = DataQualityService()
        issue = svc.record_issue("t", "missing_events", "pipeline",
                                 "Gap detected.", severity="critical")
        assert svc.resolve_issue(issue["issue_id"]) is True
        remaining = svc.get_issues(tenant="t", resolved=False)
        assert all(i["issue_id"] != issue["issue_id"] for i in remaining)
        summary = svc.get_quality_summary("t")
        assert summary["resolved_count"] == 1
        assert svc.resolve_issue("nonexistent-id") is False

    def test_check_missing_events(self):
        svc = DataQualityService()
        issue = svc.check_missing_events("t", expected_count=100,
                                         actual_count=85, source="events")
        assert issue is not None
        assert issue["issue_type"] == "missing_events"
        assert issue["severity"] == "critical"
        assert issue["metadata"]["missing_count"] == 15
