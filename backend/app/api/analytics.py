"""NovaForge Analytics Platform -- API (Volume 50).

FastAPI endpoints for event ingestion & normalization, metric aggregation,
cost attribution, budgets, alerts, reports, forecasting, recommendations,
SLO analytics, engineering/DORA intelligence, AI usage analytics,
marketplace analytics, security analytics, data quality, and dashboards.

Every blocking service call is dispatched via ``asyncio.to_thread`` and
analytics services are imported lazily inside each handler.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.analytics.schemas import (
    AnalyticsEventIngest, AnalyticsEventBatch,
    MetricQuery, TrendQuery,
    CostRecordCreate, CostAttributionQuery,
    BudgetCreate, BudgetUpdate,
    AnalyticsAlertCreate,
    ReportGenerate, ReportExport,
    ForecastCreate, RecommendationAction,
    EngineeringQuery, DashboardQuery,
)

router = APIRouter(tags=["Analytics Platform"])


# ── Additional request models ──────────────────────────────────────────

class MetricRecordRequest(BaseModel):
    tenant: str = "default"
    metric_name: str
    value: float
    dimensions: dict = Field(default_factory=dict)
    timestamp: str = ""
    granularity: str = "hour"


class CostTrendRequest(BaseModel):
    tenant: str = "default"
    granularity: str = "day"
    start_time: Optional[str] = None
    end_time: Optional[str] = None


class ModelCompareRequest(BaseModel):
    tenant: str = "default"
    models: list[str] = Field(default_factory=list)
    start_time: Optional[str] = None
    end_time: Optional[str] = None


class AlertEvaluateRequest(BaseModel):
    tenant: str = "default"
    metrics: dict = Field(default_factory=dict)


class RecommendationGenerateRequest(BaseModel):
    tenant: str = "default"
    data: dict = Field(default_factory=dict)


class SLOMeasurementRequest(BaseModel):
    tenant: str = "default"
    service: str
    metric_name: str
    actual_value: float
    target: float
    window_start: str = ""
    window_end: str = ""


class DeploymentRecordRequest(BaseModel):
    tenant: str = "default"
    service: str
    commit_sha: str = ""
    environment: str = "production"
    deployed_at: str = ""
    success: bool = True
    rollback: bool = False
    metadata: dict = Field(default_factory=dict)


class PullRequestEventRequest(BaseModel):
    tenant: str = "default"
    repository: str
    pr_id: str = ""
    status: str = "merged"
    created_at: str = ""
    merged_at: str = ""
    review_time_minutes: float = 0


class AICallRecordRequest(BaseModel):
    tenant: str = "default"
    model: str
    provider: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    latency_ms: float = 0
    success: bool = True
    cost_usd: float = 0
    agent: str = ""
    workflow: str = ""
    error_message: str = ""


class AgentRunRequest(BaseModel):
    tenant: str = "default"
    agent_name: str
    task: str = ""
    success: bool = True
    tool_calls: int = 0
    iterations: int = 0
    tokens: int = 0
    cost_usd: float = 0
    duration_ms: float = 0
    human_approved: bool = False


class MarketplaceEventRequest(BaseModel):
    tenant: str = "default"
    event_type: str
    package_name: str = ""
    package_id: str = ""
    version: str = ""
    user_id: str = ""
    metadata: dict = Field(default_factory=dict)


class SecurityFindingRequest(BaseModel):
    tenant: str = "default"
    repository: str = ""
    severity: str = "medium"
    category: str = ""
    title: str = ""
    file_path: str = ""
    remediated: bool = False
    detected_at: str = ""


class QualityValidateRequest(BaseModel):
    tenant: str = "default"
    events: list[dict] = Field(default_factory=list)


# ── Event Management ───────────────────────────────────────────────────

@router.post("/events/ingest")
async def ingest_event(req: AnalyticsEventIngest) -> JSONResponse:
    from app.analytics.normalization_service import normalization_service
    result = await asyncio.to_thread(normalization_service.ingest, req.model_dump())
    if result.get("status") == "invalid":
        return JSONResponse(status_code=422, content=result)
    return JSONResponse(content=result)


@router.post("/events/ingest/batch")
async def ingest_events_batch(req: AnalyticsEventBatch) -> JSONResponse:
    from app.analytics.normalization_service import normalization_service
    results = await asyncio.to_thread(
        normalization_service.ingest_batch, [e.model_dump() for e in req.events])
    accepted = sum(1 for r in results if r.get("status") != "invalid")
    duplicates = sum(1 for r in results if r.get("status") == "duplicate")
    invalid = sum(1 for r in results if r.get("status") == "invalid")
    return JSONResponse(content={
        "idempotency_key": req.idempotency_key,
        "received": len(results), "accepted": accepted,
        "duplicates": duplicates, "invalid": invalid,
        "results": results})


@router.get("/events")
async def list_events(
    tenant: str = Query(""),
    event_type: str = Query(""),
    source: str = Query(""),
    start_time: str = Query(""),
    end_time: str = Query(""),
    limit: int = Query(100),
) -> JSONResponse:
    from app.analytics.normalization_service import normalization_service
    events = await asyncio.to_thread(
        normalization_service.list_events,
        tenant=tenant, event_type=event_type, source=source,
        start_time=start_time, end_time=end_time, limit=limit)
    return JSONResponse(content={"events": events, "count": len(events)})


@router.get("/events/duplicates")
async def detect_duplicate_events(limit: int = Query(100)) -> JSONResponse:
    from app.analytics.normalization_service import normalization_service
    events = await asyncio.to_thread(normalization_service.list_events, limit=limit)
    duplicates = await asyncio.to_thread(normalization_service.detect_duplicates, events)
    return JSONResponse(content={"scanned": len(events), "duplicates": duplicates})


@router.get("/events/stats")
async def get_normalization_stats(tenant: str = Query("")) -> JSONResponse:
    from app.analytics.normalization_service import normalization_service
    stats = await asyncio.to_thread(normalization_service.get_stats, tenant)
    return JSONResponse(content=stats)


@router.get("/events/{event_id}")
async def get_event(event_id: str) -> JSONResponse:
    from app.analytics.normalization_service import normalization_service
    event = await asyncio.to_thread(normalization_service.get_event, event_id)
    if not event:
        return JSONResponse(status_code=404, content={"error": "Event not found"})
    return JSONResponse(content=event)


@router.post("/events/validate")
async def validate_event(req: AnalyticsEventIngest) -> JSONResponse:
    from app.analytics.normalization_service import normalization_service
    valid, errors = await asyncio.to_thread(
        normalization_service.validate_event, req.model_dump())
    return JSONResponse(content={"valid": valid, "errors": errors})


@router.post("/events/{event_id}/processed")
async def mark_event_processed(event_id: str) -> JSONResponse:
    from app.analytics.normalization_service import normalization_service
    processed = await asyncio.to_thread(normalization_service.mark_processed, event_id)
    if not processed:
        return JSONResponse(status_code=404, content={"error": "Event not found"})
    return JSONResponse(content={"event_id": event_id, "processed": True})


# ── Metric Management ──────────────────────────────────────────────────

@router.post("/metrics/record")
async def record_metric(req: MetricRecordRequest) -> JSONResponse:
    from app.analytics.aggregation_service import aggregation_service
    data_point = await asyncio.to_thread(
        aggregation_service.record_metric,
        tenant=req.tenant, metric_name=req.metric_name, value=req.value,
        dimensions=req.dimensions, timestamp=req.timestamp,
        granularity=req.granularity)
    return JSONResponse(status_code=201, content=data_point)


@router.post("/metrics/query")
async def query_metrics(req: MetricQuery, tenant: str = Query("default")) -> JSONResponse:
    from app.analytics.aggregation_service import aggregation_service
    points = await asyncio.to_thread(
        aggregation_service.query_metric,
        tenant=tenant, metric_name=req.metric_name, granularity=req.granularity,
        dimensions=req.dimensions, start_time=req.start_time or "",
        end_time=req.end_time or "", limit=req.limit)
    return JSONResponse(content={"points": points, "count": len(points)})


@router.post("/metrics/aggregate")
async def aggregate_metrics(req: MetricQuery, tenant: str = Query("default")) -> JSONResponse:
    from app.analytics.aggregation_service import aggregation_service
    result = await asyncio.to_thread(
        aggregation_service.aggregate,
        tenant=tenant, metric_name=req.metric_name, granularity=req.granularity,
        dimensions=req.dimensions, start_time=req.start_time or "",
        end_time=req.end_time or "")
    return JSONResponse(content=result)


@router.post("/metrics/trend")
async def get_metric_trend(req: TrendQuery, tenant: str = Query("default")) -> JSONResponse:
    from app.analytics.aggregation_service import aggregation_service
    trend = await asyncio.to_thread(
        aggregation_service.get_trend,
        tenant=tenant, metric_names=req.metric_names, granularity=req.granularity,
        start_time=req.start_time or "", end_time=req.end_time or "")
    return JSONResponse(content={"trend": trend, "count": len(trend)})


@router.get("/metrics/latest/{metric_name}")
async def get_latest_metric(metric_name: str, tenant: str = Query("default")) -> JSONResponse:
    from app.analytics.aggregation_service import aggregation_service
    latest = await asyncio.to_thread(aggregation_service.get_latest, tenant, metric_name)
    if not latest:
        return JSONResponse(status_code=404, content={"error": "No data points recorded for metric"})
    return JSONResponse(content=latest)


@router.get("/metrics/list")
async def list_metrics(tenant: str = Query("")) -> JSONResponse:
    from app.analytics.aggregation_service import aggregation_service
    metrics = await asyncio.to_thread(aggregation_service.list_metrics, tenant)
    return JSONResponse(content={"metrics": metrics, "count": len(metrics)})


# ── Cost Management ────────────────────────────────────────────────────

@router.post("/costs/record")
async def record_cost(req: CostRecordCreate) -> JSONResponse:
    from app.analytics.cost_service import cost_service
    try:
        entry = await asyncio.to_thread(
            cost_service.record_cost,
            tenant=req.tenant, cost_type=req.cost_type, amount_usd=req.amount_usd,
            period_start=req.period_start, period_end=req.period_end,
            organization=req.organization, workspace=req.workspace,
            project=req.project, repository=req.repository,
            environment=req.environment, model=req.model, provider=req.provider,
            agent=req.agent, workflow=req.workflow, user_id=req.user_id,
            is_estimated=req.is_estimated)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    return JSONResponse(status_code=201, content=entry)


@router.get("/costs")
async def list_costs(
    tenant: str = Query("default"),
    cost_type: str = Query(""),
    organization: str = Query(""),
    project: str = Query(""),
    model: str = Query(""),
    provider: str = Query(""),
    start_time: str = Query(""),
    end_time: str = Query(""),
    limit: int = Query(1000),
) -> JSONResponse:
    from app.analytics.cost_service import cost_service
    entries = await asyncio.to_thread(
        cost_service.get_costs,
        tenant=tenant, cost_type=cost_type, organization=organization,
        project=project, model=model, provider=provider,
        start_time=start_time, end_time=end_time, limit=limit)
    return JSONResponse(content={"costs": entries, "count": len(entries)})


@router.post("/costs/summary")
async def get_cost_summary(req: CostAttributionQuery) -> JSONResponse:
    from app.analytics.cost_service import cost_service
    try:
        summary = await asyncio.to_thread(
            cost_service.get_cost_summary,
            tenant=req.tenant, group_by=req.group_by,
            start_time=req.start_time or "", end_time=req.end_time or "")
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    return JSONResponse(content=summary)


@router.get("/costs/ai-breakdown")
async def get_ai_cost_breakdown(
    tenant: str = Query("default"),
    start_time: str = Query(""),
    end_time: str = Query(""),
) -> JSONResponse:
    from app.analytics.cost_service import cost_service
    breakdown = await asyncio.to_thread(
        cost_service.get_ai_cost_breakdown,
        tenant=tenant, start_time=start_time, end_time=end_time)
    return JSONResponse(content=breakdown)


@router.post("/costs/trend")
async def get_cost_trend(req: CostTrendRequest) -> JSONResponse:
    from app.analytics.cost_service import cost_service
    try:
        trend = await asyncio.to_thread(
            cost_service.get_cost_trend,
            tenant=req.tenant, granularity=req.granularity,
            start_time=req.start_time or "", end_time=req.end_time or "")
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    return JSONResponse(content={"trend": trend, "count": len(trend)})


@router.post("/costs/compare-models")
async def compare_model_costs(req: ModelCompareRequest) -> JSONResponse:
    from app.analytics.cost_service import cost_service
    comparison = await asyncio.to_thread(
        cost_service.compare_models,
        tenant=req.tenant, models=req.models or None,
        start_time=req.start_time or "", end_time=req.end_time or "")
    return JSONResponse(content={"comparison": comparison, "count": len(comparison)})


# ── Budget Management ──────────────────────────────────────────────────

@router.post("/budgets")
async def create_budget(req: BudgetCreate) -> JSONResponse:
    from app.analytics.budget_service import budget_service
    try:
        budget = await asyncio.to_thread(
            budget_service.create_budget,
            tenant=req.tenant, name=req.name, scope=req.scope,
            scope_value=req.scope_value, limit_usd=req.limit_usd,
            cost_type=req.cost_type, period=req.period,
            warning_threshold=req.warning_threshold,
            soft_limit_threshold=req.soft_limit_threshold,
            hard_limit_threshold=req.hard_limit_threshold)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    return JSONResponse(status_code=201, content=budget)


@router.get("/budgets")
async def list_budgets(
    tenant: str = Query(""),
    scope: str = Query(""),
) -> JSONResponse:
    from app.analytics.budget_service import budget_service
    budgets = await asyncio.to_thread(
        budget_service.list_budgets, tenant=tenant, scope=scope)
    return JSONResponse(content={"budgets": budgets, "count": len(budgets)})


@router.get("/budgets/status")
async def get_budget_status(tenant: str = Query("")) -> JSONResponse:
    from app.analytics.budget_service import budget_service
    status = await asyncio.to_thread(budget_service.get_budget_status, tenant)
    return JSONResponse(content={"budgets": status, "count": len(status)})


@router.get("/budgets/{budget_id}")
async def get_budget(budget_id: str) -> JSONResponse:
    from app.analytics.budget_service import budget_service
    budget = await asyncio.to_thread(budget_service.get_budget, budget_id)
    if not budget:
        return JSONResponse(status_code=404, content={"error": "Budget not found"})
    return JSONResponse(content=budget)


@router.put("/budgets/{budget_id}")
async def update_budget(budget_id: str, req: BudgetUpdate) -> JSONResponse:
    from app.analytics.budget_service import budget_service
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if "enabled" in updates:
        updates["active"] = updates.pop("enabled")
    try:
        budget = await asyncio.to_thread(budget_service.update_budget, budget_id, **updates)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    if not budget:
        return JSONResponse(status_code=404, content={"error": "Budget not found"})
    return JSONResponse(content=budget)


@router.delete("/budgets/{budget_id}")
async def delete_budget(budget_id: str) -> JSONResponse:
    from app.analytics.budget_service import budget_service
    deleted = await asyncio.to_thread(budget_service.delete_budget, budget_id)
    if not deleted:
        return JSONResponse(status_code=404, content={"error": "Budget not found"})
    return JSONResponse(content={"deleted": True, "budget_id": budget_id})


# ── Alert Management ───────────────────────────────────────────────────

@router.post("/alerts")
async def create_alert(req: AnalyticsAlertCreate) -> JSONResponse:
    from app.analytics.alert_service import analytics_alert_service
    alert = await asyncio.to_thread(
        analytics_alert_service.create_alert,
        tenant=req.tenant, name=req.name, alert_type=req.alert_type,
        metric_name=req.metric_name, condition=req.condition,
        severity=req.severity, cooldown_seconds=req.cooldown_seconds)
    return JSONResponse(status_code=201, content=alert)


@router.get("/alerts")
async def list_alerts(
    tenant: str = Query(""),
    alert_type: str = Query(""),
    status: str = Query(""),
    limit: int = Query(50),
) -> JSONResponse:
    from app.analytics.alert_service import analytics_alert_service
    alerts = await asyncio.to_thread(
        analytics_alert_service.list_alerts,
        tenant=tenant, alert_type=alert_type, status=status, limit=limit)
    return JSONResponse(content={"alerts": alerts, "count": len(alerts)})


@router.post("/alerts/evaluate")
async def evaluate_alerts(req: AlertEvaluateRequest) -> JSONResponse:
    from app.analytics.alert_service import analytics_alert_service
    triggered = await asyncio.to_thread(
        analytics_alert_service.evaluate_alerts,
        tenant=req.tenant, metrics=req.metrics)
    return JSONResponse(content={"triggered": triggered, "count": len(triggered)})


@router.get("/alerts/history")
async def get_alert_history(
    tenant: str = Query(""),
    alert_id: str = Query(""),
    limit: int = Query(50),
) -> JSONResponse:
    from app.analytics.alert_service import analytics_alert_service
    history = await asyncio.to_thread(
        analytics_alert_service.get_alert_history,
        tenant=tenant, alert_id=alert_id, limit=limit)
    return JSONResponse(content={"history": history, "count": len(history)})


@router.get("/alerts/summary")
async def get_alert_summary(tenant: str = Query("")) -> JSONResponse:
    from app.analytics.alert_service import analytics_alert_service
    summary = await asyncio.to_thread(analytics_alert_service.get_alert_summary, tenant)
    return JSONResponse(content=summary)


@router.get("/alerts/{alert_id}")
async def get_alert(alert_id: str) -> JSONResponse:
    from app.analytics.alert_service import analytics_alert_service
    alert = await asyncio.to_thread(analytics_alert_service.get_alert, alert_id)
    if not alert:
        return JSONResponse(status_code=404, content={"error": "Alert not found"})
    return JSONResponse(content=alert)


@router.put("/alerts/{alert_id}")
async def update_alert(alert_id: str, req: AnalyticsAlertCreate) -> JSONResponse:
    from app.analytics.alert_service import analytics_alert_service
    alert = await asyncio.to_thread(
        analytics_alert_service.update_alert,
        alert_id, name=req.name, condition=req.condition,
        severity=req.severity, cooldown_seconds=req.cooldown_seconds)
    if not alert:
        return JSONResponse(status_code=404, content={"error": "Alert not found"})
    return JSONResponse(content=alert)


@router.delete("/alerts/{alert_id}")
async def delete_alert(alert_id: str) -> JSONResponse:
    from app.analytics.alert_service import analytics_alert_service
    deleted = await asyncio.to_thread(analytics_alert_service.delete_alert, alert_id)
    if not deleted:
        return JSONResponse(status_code=404, content={"error": "Alert not found"})
    return JSONResponse(content={"deleted": True, "alert_id": alert_id})


# ── Report Management ──────────────────────────────────────────────────

@router.post("/reports/generate")
async def generate_report(req: ReportGenerate) -> JSONResponse:
    from app.analytics.report_service import report_service
    report = await asyncio.to_thread(
        report_service.generate_report,
        tenant=req.tenant, report_type=req.report_type,
        period_start=req.period_start, period_end=req.period_end)
    return JSONResponse(status_code=201, content=report)


@router.get("/reports")
async def list_reports(
    tenant: str = Query(""),
    report_type: str = Query(""),
    limit: int = Query(20),
) -> JSONResponse:
    from app.analytics.report_service import report_service
    reports = await asyncio.to_thread(
        report_service.list_reports,
        tenant=tenant, report_type=report_type, limit=limit)
    return JSONResponse(content={"reports": reports, "count": len(reports)})


@router.get("/reports/{report_id}")
async def get_report(report_id: str) -> JSONResponse:
    from app.analytics.report_service import report_service
    report = await asyncio.to_thread(report_service.get_report, report_id)
    if not report:
        return JSONResponse(status_code=404, content={"error": "Report not found"})
    return JSONResponse(content=report)


@router.post("/reports/{report_id}/export")
async def export_report(report_id: str, req: ReportExport) -> JSONResponse:
    from app.analytics.report_service import report_service
    exported = await asyncio.to_thread(report_service.export_report, report_id, req.format)
    if "error" in exported:
        return JSONResponse(status_code=404, content={"error": "Report not found"})
    return JSONResponse(content=exported)


@router.delete("/reports/{report_id}")
async def delete_report(report_id: str) -> JSONResponse:
    from app.analytics.report_service import report_service
    deleted = await asyncio.to_thread(report_service.delete_report, report_id)
    if not deleted:
        return JSONResponse(status_code=404, content={"error": "Report not found"})
    return JSONResponse(content={"deleted": True, "report_id": report_id})


# ── Forecasting ────────────────────────────────────────────────────────

@router.post("/forecast")
async def create_forecast(req: ForecastCreate) -> JSONResponse:
    from app.analytics.forecasting_service import forecasting_service
    points = await asyncio.to_thread(
        forecasting_service.forecast,
        tenant=req.tenant, metric_name=req.metric_name,
        horizon_days=req.horizon_days, scope=req.scope,
        scope_value=req.scope_value)
    stored = []
    for point in points:
        record = await asyncio.to_thread(
            forecasting_service.record_forecast,
            tenant=req.tenant, metric_name=req.metric_name,
            forecast_date=point["forecast_date"],
            predicted_value=point["predicted_value"],
            confidence_lower=point["confidence_lower"],
            confidence_upper=point["confidence_upper"],
            scope=req.scope, scope_value=req.scope_value)
        stored.append(record)
    return JSONResponse(content={
        "tenant": req.tenant, "metric_name": req.metric_name,
        "horizon_days": req.horizon_days,
        "forecast_count": len(stored), "forecasts": stored,
        "note": "" if stored else "Insufficient historical data points for a forecast."})


@router.get("/forecast/accuracy/{metric_name}")
async def get_forecast_accuracy(metric_name: str, tenant: str = Query("default")) -> JSONResponse:
    from app.analytics.forecasting_service import forecasting_service
    accuracy = await asyncio.to_thread(
        forecasting_service.get_forecast_accuracy, tenant, metric_name)
    return JSONResponse(content=accuracy)


@router.get("/forecast/{metric_name}")
async def get_metric_forecasts(
    metric_name: str,
    tenant: str = Query("default"),
    limit: int = Query(100),
) -> JSONResponse:
    from app.analytics.forecasting_service import forecasting_service
    forecasts = await asyncio.to_thread(
        forecasting_service.get_forecasts, tenant, metric_name, limit)
    return JSONResponse(content={"forecasts": forecasts, "count": len(forecasts)})


# ── Recommendations ────────────────────────────────────────────────────

@router.post("/recommendations/generate")
async def generate_recommendations(req: RecommendationGenerateRequest) -> JSONResponse:
    from app.analytics.recommendation_service import recommendation_service
    created = await asyncio.to_thread(
        recommendation_service.generate_recommendations, req.tenant, req.data)
    return JSONResponse(content={"created": created, "count": len(created)})


@router.get("/recommendations")
async def list_recommendations(
    tenant: str = Query(""),
    category: str = Query(""),
    status: str = Query(""),
    limit: int = Query(50),
) -> JSONResponse:
    from app.analytics.recommendation_service import recommendation_service
    recommendations = await asyncio.to_thread(
        recommendation_service.get_recommendations,
        tenant=tenant, category=category, status=status, limit=limit)
    return JSONResponse(content={
        "recommendations": recommendations, "count": len(recommendations)})


@router.post("/recommendations/{recommendation_id}/action")
async def act_on_recommendation(recommendation_id: str, req: RecommendationAction) -> JSONResponse:
    from app.analytics.recommendation_service import recommendation_service
    action = (req.action or "").strip().lower()
    if action == "dismiss":
        record = await asyncio.to_thread(
            recommendation_service.dismiss_recommendation, recommendation_id)
    elif action == "accept":
        record = await asyncio.to_thread(
            recommendation_service.accept_recommendation, recommendation_id)
    else:
        return JSONResponse(
            status_code=400,
            content={"error": f"Unsupported action: {req.action!r} (expected 'dismiss' or 'accept')"})
    if not record:
        return JSONResponse(status_code=404, content={"error": "Recommendation not found"})
    return JSONResponse(content=record)


# ── SLO Analytics ──────────────────────────────────────────────────────

@router.post("/slo/record")
async def record_slo_measurement(req: SLOMeasurementRequest) -> JSONResponse:
    from app.analytics.slo_analytics_service import slo_analytics_service
    measurement = await asyncio.to_thread(
        slo_analytics_service.record_slo_measurement,
        tenant=req.tenant, service=req.service, metric_name=req.metric_name,
        actual_value=req.actual_value, target=req.target,
        window_start=req.window_start, window_end=req.window_end)
    return JSONResponse(status_code=201, content=measurement)


@router.get("/slo/status")
async def get_slo_status(
    tenant: str = Query("default"),
    service: str = Query(""),
) -> JSONResponse:
    from app.analytics.slo_analytics_service import slo_analytics_service
    status = await asyncio.to_thread(slo_analytics_service.get_slo_status, tenant, service)
    return JSONResponse(content=status)


@router.get("/slo/breaches")
async def get_slo_breaches(
    tenant: str = Query("default"),
    service: str = Query(""),
    start_time: str = Query(""),
    end_time: str = Query(""),
) -> JSONResponse:
    from app.analytics.slo_analytics_service import slo_analytics_service
    breaches = await asyncio.to_thread(
        slo_analytics_service.get_slo_breaches,
        tenant, service, start_time, end_time)
    return JSONResponse(content={"breaches": breaches, "count": len(breaches)})


# ── Engineering / DORA ─────────────────────────────────────────────────

@router.post("/engineering/deployment")
async def record_deployment(req: DeploymentRecordRequest) -> JSONResponse:
    from app.analytics.engineering_service import engineering_service
    record = await asyncio.to_thread(
        engineering_service.record_deployment,
        tenant=req.tenant, service=req.service, commit_sha=req.commit_sha,
        environment=req.environment, deployed_at=req.deployed_at,
        success=req.success, rollback=req.rollback, metadata=req.metadata)
    return JSONResponse(status_code=201, content=record)


@router.post("/engineering/pr")
async def record_pr_event(req: PullRequestEventRequest) -> JSONResponse:
    from app.analytics.engineering_service import engineering_service
    record = await asyncio.to_thread(
        engineering_service.record_pr_event,
        tenant=req.tenant, repository=req.repository, pr_id=req.pr_id,
        status=req.status, created_at=req.created_at, merged_at=req.merged_at,
        review_time_minutes=req.review_time_minutes)
    return JSONResponse(status_code=201, content=record)


@router.post("/engineering/dora")
async def compute_dora_metrics(req: EngineeringQuery) -> JSONResponse:
    from app.analytics.engineering_service import engineering_service
    dora = await asyncio.to_thread(
        engineering_service.compute_dora,
        tenant=req.tenant, project=req.project, repository=req.repository,
        start_time=req.start_time or "", end_time=req.end_time or "")
    return JSONResponse(content=dora)


# ── AI Analytics ───────────────────────────────────────────────────────

@router.post("/ai/record-call")
async def record_ai_call(req: AICallRecordRequest) -> JSONResponse:
    from app.analytics.ai_analytics_service import ai_analytics_service
    record = await asyncio.to_thread(
        ai_analytics_service.record_ai_call,
        tenant=req.tenant, model=req.model, provider=req.provider,
        input_tokens=req.input_tokens, output_tokens=req.output_tokens,
        cached_tokens=req.cached_tokens, latency_ms=req.latency_ms,
        success=req.success, cost_usd=req.cost_usd, agent=req.agent,
        workflow=req.workflow, error_message=req.error_message)
    return JSONResponse(status_code=201, content=record)


@router.post("/ai/agent-run")
async def record_agent_run(req: AgentRunRequest) -> JSONResponse:
    from app.analytics.ai_analytics_service import ai_analytics_service
    record = await asyncio.to_thread(
        ai_analytics_service.record_agent_run,
        tenant=req.tenant, agent_name=req.agent_name, task=req.task,
        success=req.success, tool_calls=req.tool_calls,
        iterations=req.iterations, tokens=req.tokens, cost_usd=req.cost_usd,
        duration_ms=req.duration_ms, human_approved=req.human_approved)
    return JSONResponse(status_code=201, content=record)


@router.get("/ai/model-comparison")
async def get_ai_model_comparison(
    tenant: str = Query("default"),
    start_time: str = Query(""),
    end_time: str = Query(""),
) -> JSONResponse:
    from app.analytics.ai_analytics_service import ai_analytics_service
    comparison = await asyncio.to_thread(
        ai_analytics_service.get_model_comparison,
        tenant=tenant, start_time=start_time, end_time=end_time)
    return JSONResponse(content={"comparison": comparison, "count": len(comparison)})


# ── Marketplace Analytics ──────────────────────────────────────────────

@router.post("/marketplace/event")
async def record_marketplace_event(req: MarketplaceEventRequest) -> JSONResponse:
    from app.analytics.marketplace_analytics_service import marketplace_analytics_service
    event = await asyncio.to_thread(
        marketplace_analytics_service.record_marketplace_event,
        tenant=req.tenant, event_type=req.event_type,
        package_name=req.package_name, package_id=req.package_id,
        version=req.version, user_id=req.user_id, metadata=req.metadata)
    return JSONResponse(status_code=201, content=event)


@router.get("/marketplace/summary")
async def get_marketplace_summary(
    tenant: str = Query("default"),
    start_time: str = Query(""),
    end_time: str = Query(""),
) -> JSONResponse:
    from app.analytics.marketplace_analytics_service import marketplace_analytics_service
    summary = await asyncio.to_thread(
        marketplace_analytics_service.get_marketplace_summary,
        tenant=tenant, start_time=start_time, end_time=end_time)
    return JSONResponse(content=summary)


# ── Security Analytics ─────────────────────────────────────────────────

@router.post("/security/finding")
async def record_security_finding(req: SecurityFindingRequest) -> JSONResponse:
    from app.analytics.security_analytics_service import security_analytics_service
    finding = await asyncio.to_thread(
        security_analytics_service.record_security_finding,
        tenant=req.tenant, repository=req.repository, severity=req.severity,
        category=req.category, title=req.title, file_path=req.file_path,
        remediated=req.remediated, detected_at=req.detected_at)
    return JSONResponse(status_code=201, content=finding)


@router.get("/security/summary")
async def get_security_summary(
    tenant: str = Query("default"),
    repository: str = Query(""),
    start_time: str = Query(""),
    end_time: str = Query(""),
) -> JSONResponse:
    from app.analytics.security_analytics_service import security_analytics_service
    summary = await asyncio.to_thread(
        security_analytics_service.get_security_summary,
        tenant, repository, start_time, end_time)
    return JSONResponse(content=summary)


# ── Data Quality ───────────────────────────────────────────────────────

@router.post("/quality/validate")
async def validate_event_batch(req: QualityValidateRequest) -> JSONResponse:
    from app.analytics.data_quality_service import data_quality_service
    result = await asyncio.to_thread(
        data_quality_service.validate_batch, req.events, req.tenant)
    return JSONResponse(content=result)


@router.get("/quality/issues")
async def list_quality_issues(
    tenant: str = Query(""),
    issue_type: str = Query(""),
    resolved: Optional[bool] = Query(None),
    limit: int = Query(100),
) -> JSONResponse:
    from app.analytics.data_quality_service import data_quality_service
    issues = await asyncio.to_thread(
        data_quality_service.get_issues,
        tenant=tenant, issue_type=issue_type, resolved=resolved, limit=limit)
    return JSONResponse(content={"issues": issues, "count": len(issues)})


@router.post("/quality/{issue_id}/resolve")
async def resolve_quality_issue(issue_id: str) -> JSONResponse:
    from app.analytics.data_quality_service import data_quality_service
    resolved = await asyncio.to_thread(data_quality_service.resolve_issue, issue_id)
    if not resolved:
        return JSONResponse(status_code=404, content={"error": "Issue not found"})
    return JSONResponse(content={"issue_id": issue_id, "resolved": True})


# ── Dashboard ──────────────────────────────────────────────────────────

@router.post("/dashboard")
async def get_dashboard_data(req: DashboardQuery) -> JSONResponse:
    from app.analytics.cost_service import cost_service
    from app.analytics.ai_analytics_service import ai_analytics_service
    from app.analytics.engineering_service import engineering_service
    from app.analytics.security_analytics_service import security_analytics_service
    from app.analytics.slo_analytics_service import slo_analytics_service
    from app.analytics.budget_service import budget_service
    from app.analytics.alert_service import analytics_alert_service
    from app.analytics.data_quality_service import data_quality_service
    from app.analytics.recommendation_service import recommendation_service

    tenant = req.tenant
    start = req.start_time or ""
    end = req.end_time or ""
    (costs, ai_usage, dora, security, slo,
     budgets, alerts, quality, recommendations) = await asyncio.gather(
        asyncio.to_thread(cost_service.get_cost_summary, tenant, "total", start, end),
        asyncio.to_thread(ai_analytics_service.get_ai_usage_summary, tenant, start, end),
        asyncio.to_thread(engineering_service.compute_dora, tenant, "", "", start, end),
        asyncio.to_thread(security_analytics_service.get_security_summary, tenant, "", start, end),
        asyncio.to_thread(slo_analytics_service.get_slo_status, tenant),
        asyncio.to_thread(budget_service.get_budget_status, tenant),
        asyncio.to_thread(analytics_alert_service.get_alert_summary, tenant),
        asyncio.to_thread(data_quality_service.get_quality_summary, tenant),
        asyncio.to_thread(recommendation_service.get_recommendation_summary, tenant),
    )
    return JSONResponse(content={
        "tenant": tenant, "start_time": req.start_time, "end_time": req.end_time,
        "filters": req.filters,
        "costs": costs, "ai_usage": ai_usage, "dora": dora,
        "security": security, "slo": slo, "budgets": budgets,
        "alerts": alerts, "data_quality": quality,
        "recommendations": recommendations,
    })


@router.get("/dashboard/overview")
async def get_dashboard_overview(tenant: str = Query("default")) -> JSONResponse:
    from app.analytics.normalization_service import normalization_service
    from app.analytics.cost_service import cost_service
    from app.analytics.ai_analytics_service import ai_analytics_service
    from app.analytics.engineering_service import engineering_service
    from app.analytics.alert_service import analytics_alert_service

    events, total_cost, ai_usage, dora, alerts = await asyncio.gather(
        asyncio.to_thread(normalization_service.get_stats, tenant),
        asyncio.to_thread(cost_service.get_total_cost, tenant),
        asyncio.to_thread(ai_analytics_service.get_ai_usage_summary, tenant),
        asyncio.to_thread(engineering_service.compute_dora, tenant),
        asyncio.to_thread(analytics_alert_service.get_alert_summary, tenant),
    )
    return JSONResponse(content={
        "tenant": tenant, "events": events, "total_cost_usd": total_cost,
        "ai_usage": ai_usage, "dora": dora, "alerts": alerts,
    })
