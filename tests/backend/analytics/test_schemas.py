"""Pydantic schema tests for Analytics Platform (Volume 50)."""

import pytest
from app.analytics.schemas import (
    AnalyticsEventIngest, AnalyticsEventBatch,
    MetricDefinitionCreate, MetricQuery, TrendQuery,
    CostRecordCreate, CostAttributionQuery,
    BudgetCreate, BudgetUpdate,
    AnalyticsAlertCreate, ReportGenerate,
    ForecastCreate, RecommendationAction,
    EngineeringQuery, DashboardQuery, DataQualityQuery,
)


class TestEventSchemas:

    def test_event_ingest_valid(self):
        e = AnalyticsEventIngest(tenant="t", source="s", event_type="test.event",
                                  event_timestamp="2026-01-01T00:00:00Z")
        assert e.tenant == "t"
        assert e.cost_usd == 0.0

    def test_event_ingest_defaults(self):
        e = AnalyticsEventIngest(tenant="t", source="s", event_type="e")
        assert e.tenant == "t"
        assert e.workspace == ""
        assert e.metadata_extra == {}

    def test_event_batch(self):
        batch = AnalyticsEventBatch(events=[
            AnalyticsEventIngest(tenant="t", source="s", event_type="e1"),
            AnalyticsEventIngest(tenant="t", source="s", event_type="e2"),
        ])
        assert len(batch.events) == 2
        assert batch.idempotency_key == ""


class TestMetricSchemas:

    def test_metric_definition_create(self):
        m = MetricDefinitionCreate(name="ai.cost", category="cost", aggregation="sum")
        assert m.name == "ai.cost"
        assert m.dimensions == []
        assert m.aggregation == "sum"

    def test_metric_query(self):
        q = MetricQuery(metric_name="ai.cost", granularity="hour")
        assert q.metric_name == "ai.cost"
        assert q.dimensions == {}
        assert q.limit == 1000

    def test_trend_query(self):
        t = TrendQuery(metric_names=["ai.cost", "ai.calls"])
        assert len(t.metric_names) == 2
        assert t.granularity == "day"


class TestCostSchemas:

    def test_cost_record_create(self):
        c = CostRecordCreate(cost_type="ai_model", amount_usd=5.0,
                              period_start="2026-01-01", period_end="2026-01-31")
        assert c.amount_usd == 5.0
        assert c.currency == "USD"

    def test_cost_attribution_query(self):
        q = CostAttributionQuery(tenant="t", group_by="model")
        assert q.group_by == "model"


class TestBudgetSchemas:

    def test_budget_create(self):
        b = BudgetCreate(name="test", scope="organization", scope_value="org",
                          limit_usd=500.0)
        assert b.limit_usd == 500.0
        assert b.warning_threshold == 0.8

    def test_budget_update(self):
        u = BudgetUpdate(limit_usd=1000.0, warning_threshold=0.7)
        assert u.limit_usd == 1000.0
        assert u.soft_limit_threshold is None


class TestAlertSchemas:

    def test_alert_create(self):
        a = AnalyticsAlertCreate(name="cost_spike", alert_type="cost_spike",
                                  metric_name="ai.cost")
        assert a.severity == "medium"
        assert a.cooldown_seconds == 3600


class TestReportSchemas:

    def test_report_generate(self):
        r = ReportGenerate(report_type="executive", period_start="2026-01-01",
                            period_end="2026-01-31")
        assert r.format == "json"


class TestForecastSchemas:

    def test_forecast_create(self):
        f = ForecastCreate(metric_name="ai.cost", horizon_days=30)
        assert f.horizon_days == 30


class TestRecommendationSchemas:

    def test_recommendation_action(self):
        r = RecommendationAction(recommendation_id="r1", action="dismiss")
        assert r.action == "dismiss"


class TestEngineeringSchemas:

    def test_engineering_query(self):
        q = EngineeringQuery(project="novaforge")
        assert q.project == "novaforge"


class TestDashboardSchemas:

    def test_dashboard_query(self):
        d = DashboardQuery(tenant="t")
        assert d.filters == {}


class TestDataQualitySchemas:

    def test_data_quality_query(self):
        q = DataQualityQuery(tenant="t", limit=50)
        assert q.limit == 50
        assert q.resolved is None
