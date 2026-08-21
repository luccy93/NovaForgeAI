"""NovaForge Analytics Platform -- CLI (Volume 50).

14 subcommand groups: ingest, metrics, costs, budgets, alerts, reports,
forecast, recommendations, slo, engineering, ai, marketplace, security,
quality.
"""

from __future__ import annotations

import json
import sys
from typing import Any

import click

from app.analytics.normalization_service import normalization_service
from app.analytics.aggregation_service import aggregation_service
from app.analytics.cost_service import cost_service
from app.analytics.budget_service import budget_service
from app.analytics.alert_service import analytics_alert_service
from app.analytics.report_service import report_service
from app.analytics.forecasting_service import ForecastingService
from app.analytics.recommendation_service import RecommendationService
from app.analytics.slo_analytics_service import slo_analytics_service
from app.analytics.engineering_service import engineering_service
from app.analytics.ai_analytics_service import ai_analytics_service
from app.analytics.marketplace_analytics_service import marketplace_analytics_service
from app.analytics.security_analytics_service import security_analytics_service
from app.analytics.data_quality_service import DataQualityService


def _print(title: str, data: Any):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")
    print(json.dumps(data, indent=2, default=str))


def _load_json(path: str) -> Any:
    """Load JSON from a file path, or stdin when path is '-'."""
    if path == "-":
        return json.load(sys.stdin)
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _parse_json_option(value: str, option_name: str) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise click.BadParameter(f"{option_name} must be valid JSON: {exc}")
    if not isinstance(parsed, dict):
        raise click.BadParameter(f"{option_name} must be a JSON object")
    return parsed


def _split_names(raw: str) -> list[str]:
    return [name.strip() for name in raw.split(",") if name.strip()]


analytics_commands_group = click.Group(name="analytics_commands")


@analytics_commands_group.group(name="analytics")
def analytics():
    """NovaForge Analytics Platform commands (Volume 50)."""


# ─── ingest ────────────────────────────────────────────────────────────


@analytics.group(name="ingest")
def ingest():
    """Event ingestion commands."""


@ingest.command(name="event")
@click.argument("event_type")
@click.option("--tenant", default="default", show_default=True)
@click.option("--source", default="platform", show_default=True)
@click.option("--timestamp", default="", help="ISO event timestamp.")
@click.option("--cost-usd", type=float, default=0.0, show_default=True)
@click.option("--duration-ms", type=float, default=0.0, show_default=True)
@click.option("--metadata", default="", help="JSON object with extra metadata.")
def ingest_event(event_type: str, tenant: str, source: str, timestamp: str,
                 cost_usd: float, duration_ms: float, metadata: str):
    """Ingest a single analytics event."""
    metadata_extra = _parse_json_option(metadata, "--metadata")
    result = normalization_service.ingest({
        "tenant": tenant, "source": source, "event_type": event_type,
        "event_timestamp": timestamp, "cost_usd": cost_usd,
        "duration_ms": duration_ms, "metadata_extra": metadata_extra})
    _print("Event Ingested", result)


@ingest.command(name="batch")
@click.argument("path")
def ingest_batch(path: str):
    """Ingest a batch of events from a JSON file ('-' for stdin)."""
    events = _load_json(path)
    if not isinstance(events, list):
        raise click.BadParameter("batch payload must be a JSON array of events")
    results = normalization_service.ingest_batch(events)
    _print("Batch Ingested", {"count": len(results), "events": results})


@ingest.command(name="list")
@click.option("--tenant", default="")
@click.option("--event-type", default="")
@click.option("--source", default="")
@click.option("--start-time", default="")
@click.option("--end-time", default="")
@click.option("--limit", type=int, default=100, show_default=True)
def ingest_list(tenant: str, event_type: str, source: str,
                start_time: str, end_time: str, limit: int):
    """List ingested analytics events."""
    events = normalization_service.list_events(
        tenant=tenant, event_type=event_type, source=source,
        start_time=start_time, end_time=end_time, limit=limit)
    _print("Events", {"count": len(events), "events": events})


@ingest.command(name="get")
@click.argument("event_id")
def ingest_get(event_id: str):
    """Fetch a single ingested event by ID."""
    event = normalization_service.get_event(event_id)
    if event:
        _print("Event", event)
    else:
        click.echo("Event not found")


@ingest.command(name="validate")
@click.argument("path")
def ingest_validate(path: str):
    """Validate an event payload from a JSON file ('-' for stdin)."""
    event = _load_json(path)
    valid, errors = normalization_service.validate_event(event)
    _print("Validation", {"valid": valid, "errors": errors})


# ─── metrics ───────────────────────────────────────────────────────────


@analytics.group(name="metrics")
def metrics():
    """Metric recording and querying commands."""


@metrics.command(name="record")
@click.argument("metric_name")
@click.argument("value", type=float)
@click.option("--tenant", default="default", show_default=True)
@click.option("--dimensions", default="", help="JSON object of dimensions.")
@click.option("--timestamp", default="", help="ISO timestamp override.")
@click.option("--granularity", default="hour", show_default=True)
def metrics_record(metric_name: str, value: float, tenant: str,
                   dimensions: str, timestamp: str, granularity: str):
    """Record a metric observation."""
    dims = _parse_json_option(dimensions, "--dimensions")
    result = aggregation_service.record_metric(
        tenant=tenant, metric_name=metric_name, value=value,
        dimensions=dims, timestamp=timestamp, granularity=granularity)
    _print("Metric Recorded", result)


@metrics.command(name="query")
@click.argument("metric_name")
@click.option("--tenant", default="default", show_default=True)
@click.option("--granularity", default="hour", show_default=True)
@click.option("--dimensions", default="", help="JSON object of dimensions.")
@click.option("--start-time", default="")
@click.option("--end-time", default="")
@click.option("--limit", type=int, default=1000, show_default=True)
def metrics_query(metric_name: str, tenant: str, granularity: str,
                  dimensions: str, start_time: str, end_time: str,
                  limit: int):
    """Query recorded metric points."""
    dims = _parse_json_option(dimensions, "--dimensions")
    points = aggregation_service.query_metric(
        tenant=tenant, metric_name=metric_name, granularity=granularity,
        dimensions=dims, start_time=start_time, end_time=end_time,
        limit=limit)
    _print("Metric Points", {"count": len(points), "points": points})


@metrics.command(name="aggregate")
@click.argument("metric_name")
@click.argument("start_time")
@click.argument("end_time")
@click.option("--tenant", default="default", show_default=True)
@click.option("--granularity", default="hour", show_default=True)
@click.option("--dimensions", default="", help="JSON object of dimensions.")
def metrics_aggregate(metric_name: str, start_time: str, end_time: str,
                      tenant: str, granularity: str, dimensions: str):
    """Aggregate a metric over a time window."""
    dims = _parse_json_option(dimensions, "--dimensions")
    summary = aggregation_service.aggregate(
        tenant=tenant, metric_name=metric_name, start_time=start_time,
        end_time=end_time, granularity=granularity, dimensions=dims)
    _print("Aggregation", summary)


@metrics.command(name="trend")
@click.argument("metric_names")
@click.option("--tenant", default="default", show_default=True)
@click.option("--granularity", default="day", show_default=True)
@click.option("--start-time", default="")
@click.option("--end-time", default="")
def metrics_trend(metric_names: str, tenant: str, granularity: str,
                  start_time: str, end_time: str):
    """Compute trends for comma-separated metric names."""
    names = _split_names(metric_names)
    if not names:
        raise click.BadParameter("provide at least one metric name")
    trend = aggregation_service.get_trend(
        tenant=tenant, metric_names=names, granularity=granularity,
        start_time=start_time, end_time=end_time)
    _print("Trend", {"count": len(trend), "points": trend})


# ─── costs ─────────────────────────────────────────────────────────────


@analytics.group(name="costs")
def costs():
    """Cost recording and analysis commands."""


@costs.command(name="record")
@click.argument("cost_type")
@click.argument("amount_usd", type=float)
@click.argument("period_start")
@click.argument("period_end")
@click.option("--tenant", default="default", show_default=True)
def costs_record(cost_type: str, amount_usd: float, period_start: str,
                 period_end: str, tenant: str):
    """Record a cost entry for a billing period."""
    result = cost_service.record_cost(
        tenant=tenant, cost_type=cost_type, amount_usd=amount_usd,
        period_start=period_start, period_end=period_end)
    _print("Cost Recorded", result)


@costs.command(name="list")
@click.option("--tenant", default="default", show_default=True)
@click.option("--cost-type", default="")
@click.option("--start-time", default="")
@click.option("--end-time", default="")
@click.option("--limit", type=int, default=1000, show_default=True)
def costs_list(tenant: str, cost_type: str, start_time: str,
               end_time: str, limit: int):
    """List recorded cost entries."""
    entries = cost_service.get_costs(
        tenant=tenant, cost_type=cost_type, start_time=start_time,
        end_time=end_time, limit=limit)
    _print("Costs", {"count": len(entries), "costs": entries})


@costs.command(name="summary")
@click.argument("tenant")
@click.option("--group-by", default="cost_type", show_default=True)
@click.option("--start-time", default="")
@click.option("--end-time", default="")
def costs_summary(tenant: str, group_by: str, start_time: str,
                  end_time: str):
    """Summarize costs grouped by a dimension."""
    summary = cost_service.get_cost_summary(
        tenant=tenant, group_by=group_by, start_time=start_time,
        end_time=end_time)
    _print("Cost Summary", summary)


@costs.command(name="ai-breakdown")
@click.argument("tenant")
@click.option("--start-time", default="")
@click.option("--end-time", default="")
def costs_ai_breakdown(tenant: str, start_time: str, end_time: str):
    """Show AI cost breakdown by model/provider."""
    breakdown = cost_service.get_ai_cost_breakdown(
        tenant=tenant, start_time=start_time, end_time=end_time)
    _print("AI Cost Breakdown", breakdown)


@costs.command(name="compare-models")
@click.argument("tenant")
@click.option("--models", default="", help="Comma-separated model names.")
@click.option("--start-time", default="")
@click.option("--end-time", default="")
def costs_compare_models(tenant: str, models: str, start_time: str,
                         end_time: str):
    """Compare unit economics across models."""
    comparison = cost_service.compare_models(
        tenant=tenant, models=_split_names(models) or None,
        start_time=start_time, end_time=end_time)
    _print("Model Comparison", comparison)


# ─── budgets ───────────────────────────────────────────────────────────


@analytics.group(name="budgets")
def budgets():
    """Budget management commands."""


@budgets.command(name="create")
@click.argument("name")
@click.argument("limit_usd", type=float)
@click.option("--tenant", default="default", show_default=True)
@click.option("--scope", default="organization", show_default=True)
@click.option("--scope-value", default="")
@click.option("--cost-type", default="total", show_default=True)
@click.option("--period", default="monthly", show_default=True)
def budgets_create(name: str, limit_usd: float, tenant: str, scope: str,
                   scope_value: str, cost_type: str, period: str):
    """Create a budget."""
    result = budget_service.create_budget(
        tenant=tenant, name=name, scope=scope, scope_value=scope_value,
        limit_usd=limit_usd, cost_type=cost_type, period=period)
    _print("Budget Created", result)


@budgets.command(name="list")
@click.option("--tenant", default="")
@click.option("--scope", default="")
def budgets_list(tenant: str, scope: str):
    """List budgets."""
    items = budget_service.list_budgets(tenant=tenant, scope=scope)
    _print("Budgets", {"count": len(items), "budgets": items})


@budgets.command(name="get")
@click.argument("budget_id")
def budgets_get(budget_id: str):
    """Fetch a budget by ID."""
    item = budget_service.get_budget(budget_id)
    if item:
        _print("Budget", item)
    else:
        click.echo("Budget not found")


@budgets.command(name="update")
@click.argument("budget_id")
@click.option("--limit-usd", type=float, default=None)
@click.option("--warning-threshold", type=float, default=None)
@click.option("--soft-limit-threshold", type=float, default=None)
@click.option("--hard-limit-threshold", type=float, default=None)
@click.option("--enabled/--disabled", default=None)
def budgets_update(budget_id: str, limit_usd: float,
                   warning_threshold: float, soft_limit_threshold: float,
                   hard_limit_threshold: float, enabled: bool):
    """Update budget fields."""
    updates: dict[str, Any] = {}
    if limit_usd is not None:
        updates["limit_usd"] = limit_usd
    if warning_threshold is not None:
        updates["warning_threshold"] = warning_threshold
    if soft_limit_threshold is not None:
        updates["soft_limit_threshold"] = soft_limit_threshold
    if hard_limit_threshold is not None:
        updates["hard_limit_threshold"] = hard_limit_threshold
    if enabled is not None:
        updates["enabled"] = enabled
    if not updates:
        raise click.UsageError("nothing to update")
    item = budget_service.update_budget(budget_id, **updates)
    if item:
        _print("Budget Updated", item)
    else:
        click.echo("Budget not found")


@budgets.command(name="delete")
@click.argument("budget_id")
def budgets_delete(budget_id: str):
    """Delete a budget by ID."""
    deleted = budget_service.delete_budget(budget_id)
    _print("Budget Deleted", {"budget_id": budget_id, "deleted": deleted})


@budgets.command(name="status")
@click.option("--tenant", default="default", show_default=True)
def budgets_status(tenant: str):
    """Show budget utilization status."""
    status = budget_service.get_budget_status(tenant)
    _print("Budget Status", status)


# ─── alerts ────────────────────────────────────────────────────────────


@analytics.group(name="alerts")
def alerts():
    """Analytics alert management commands."""


@alerts.command(name="create")
@click.argument("name")
@click.argument("alert_type")
@click.option("--tenant", default="default", show_default=True)
@click.option("--metric-name", default="")
@click.option("--severity", default="medium", show_default=True)
def alerts_create(name: str, alert_type: str, tenant: str,
                  metric_name: str, severity: str):
    """Create an analytics alert rule."""
    result = analytics_alert_service.create_alert(
        tenant=tenant, name=name, alert_type=alert_type,
        metric_name=metric_name, severity=severity)
    _print("Alert Created", result)


@alerts.command(name="list")
@click.option("--tenant", default="")
@click.option("--alert-type", default="")
@click.option("--status", default="")
@click.option("--limit", type=int, default=50, show_default=True)
def alerts_list(tenant: str, alert_type: str, status: str, limit: int):
    """List alert rules."""
    items = analytics_alert_service.list_alerts(
        tenant=tenant, alert_type=alert_type, status=status, limit=limit)
    _print("Alerts", {"count": len(items), "alerts": items})


@alerts.command(name="get")
@click.argument("alert_id")
def alerts_get(alert_id: str):
    """Fetch an alert rule by ID."""
    item = analytics_alert_service.get_alert(alert_id)
    if item:
        _print("Alert", item)
    else:
        click.echo("Alert not found")


@alerts.command(name="delete")
@click.argument("alert_id")
def alerts_delete(alert_id: str):
    """Delete an alert rule by ID."""
    deleted = analytics_alert_service.delete_alert(alert_id)
    _print("Alert Deleted", {"alert_id": alert_id, "deleted": deleted})


# ─── reports ───────────────────────────────────────────────────────────


@analytics.group(name="reports")
def reports():
    """Report generation commands."""


@reports.command(name="generate")
@click.argument("report_type")
@click.argument("period_start")
@click.argument("period_end")
@click.option("--tenant", default="default", show_default=True)
@click.option("--data", default="", help="JSON object with report inputs.")
def reports_generate(report_type: str, period_start: str, period_end: str,
                     tenant: str, data: str):
    """Generate a report for a period."""
    extra = _parse_json_option(data, "--data")
    result = report_service.generate_report(
        tenant=tenant, report_type=report_type, period_start=period_start,
        period_end=period_end, data=extra)
    _print("Report Generated", result)


@reports.command(name="list")
@click.option("--tenant", default="")
@click.option("--report-type", default="")
@click.option("--limit", type=int, default=20, show_default=True)
def reports_list(tenant: str, report_type: str, limit: int):
    """List generated reports."""
    items = report_service.list_reports(
        tenant=tenant, report_type=report_type, limit=limit)
    _print("Reports", {"count": len(items), "reports": items})


@reports.command(name="get")
@click.argument("report_id")
def reports_get(report_id: str):
    """Fetch a report by ID."""
    item = report_service.get_report(report_id)
    if item:
        _print("Report", item)
    else:
        click.echo("Report not found")


@reports.command(name="delete")
@click.argument("report_id")
def reports_delete(report_id: str):
    """Delete a report by ID."""
    deleted = report_service.delete_report(report_id)
    _print("Report Deleted", {"report_id": report_id, "deleted": deleted})


# ─── forecast ──────────────────────────────────────────────────────────


@analytics.group(name="forecast")
def forecast():
    """Forecasting commands."""


@forecast.command(name="create")
@click.argument("metric_name")
@click.option("--tenant", default="default", show_default=True)
@click.option("--horizon-days", type=int, default=30, show_default=True)
@click.option("--scope", default="")
@click.option("--scope-value", default="")
def forecast_create(metric_name: str, tenant: str, horizon_days: int,
                    scope: str, scope_value: str):
    """Forecast a metric over a horizon."""
    service = ForecastingService()
    points = service.forecast(
        tenant=tenant, metric_name=metric_name, horizon_days=horizon_days,
        scope=scope, scope_value=scope_value)
    _print("Forecast", {"metric_name": metric_name, "points": points})


@forecast.command(name="get")
@click.argument("metric_name", required=False, default="")
@click.option("--tenant", default="default", show_default=True)
@click.option("--limit", type=int, default=100, show_default=True)
def forecast_get(metric_name: str, tenant: str, limit: int):
    """Show stored forecasts, optionally filtered by metric."""
    service = ForecastingService()
    items = service.get_forecasts(tenant=tenant, metric_name=metric_name,
                                  limit=limit)
    _print("Forecasts", {"count": len(items), "forecasts": items})


# ─── recommendations ───────────────────────────────────────────────────


@analytics.group(name="recommendations")
def recommendations():
    """Optimization recommendation commands."""


@recommendations.command(name="generate")
@click.option("--tenant", default="default", show_default=True)
@click.option("--data", default="", help="JSON object with context data.")
def recommendations_generate(tenant: str, data: str):
    """Generate optimization recommendations."""
    context = _parse_json_option(data, "--data")
    service = RecommendationService()
    items = service.generate_recommendations(tenant, data=context or None)
    _print("Recommendations", {"count": len(items), "items": items})


@recommendations.command(name="list")
@click.option("--tenant", default="")
@click.option("--category", default="")
@click.option("--status", default="pending", show_default=True)
@click.option("--limit", type=int, default=50, show_default=True)
def recommendations_list(tenant: str, category: str, status: str,
                         limit: int):
    """List recommendations."""
    service = RecommendationService()
    items = service.get_recommendations(
        tenant=tenant, category=category, status=status, limit=limit)
    _print("Recommendations", {"count": len(items), "items": items})


@recommendations.command(name="dismiss")
@click.argument("recommendation_id")
def recommendations_dismiss(recommendation_id: str):
    """Dismiss a recommendation by ID."""
    service = RecommendationService()
    item = service.dismiss_recommendation(recommendation_id)
    if item:
        _print("Recommendation Dismissed", item)
    else:
        click.echo("Recommendation not found")


# ─── slo ───────────────────────────────────────────────────────────────


@analytics.group(name="slo")
def slo():
    """SLO tracking commands."""


@slo.command(name="record")
@click.argument("service")
@click.argument("metric_name")
@click.argument("actual_value", type=float)
@click.argument("target", type=float)
@click.argument("window_start")
@click.argument("window_end")
@click.option("--tenant", default="default", show_default=True)
def slo_record(service: str, metric_name: str, actual_value: float,
               target: float, window_start: str, window_end: str,
               tenant: str):
    """Record an SLO measurement window."""
    result = slo_analytics_service.record_slo_measurement(
        tenant=tenant, service=service, metric_name=metric_name,
        actual_value=actual_value, target=target,
        window_start=window_start, window_end=window_end)
    _print("SLO Measurement Recorded", result)


@slo.command(name="status")
@click.argument("tenant")
@click.option("--service", default="")
def slo_status(tenant: str, service: str):
    """Show SLO compliance status."""
    status = slo_analytics_service.get_slo_status(tenant, service=service)
    _print("SLO Status", status)


# ─── engineering ───────────────────────────────────────────────────────


@analytics.group(name="engineering")
def engineering():
    """Engineering metrics (DORA) commands."""


@engineering.command(name="deployment")
@click.argument("service")
@click.option("--tenant", default="default", show_default=True)
@click.option("--commit-sha", default="")
@click.option("--environment", default="production", show_default=True)
@click.option("--success/--failed", default=True, show_default=True)
def engineering_deployment(service: str, tenant: str, commit_sha: str,
                           environment: str, success: bool):
    """Record a deployment event."""
    result = engineering_service.record_deployment(
        tenant=tenant, service=service, commit_sha=commit_sha,
        environment=environment, success=success)
    _print("Deployment Recorded", result)


@engineering.command(name="dora")
@click.argument("tenant")
@click.option("--project", default="")
@click.option("--repository", default="")
@click.option("--start-time", default="")
@click.option("--end-time", default="")
def engineering_dora(tenant: str, project: str, repository: str,
                     start_time: str, end_time: str):
    """Compute DORA metrics for a window."""
    result = engineering_service.compute_dora(
        tenant=tenant, project=project, repository=repository,
        start_time=start_time, end_time=end_time)
    _print("DORA Metrics", result)


# ─── ai ────────────────────────────────────────────────────────────────


@analytics.group(name="ai")
def ai():
    """AI usage analytics commands."""


@ai.command(name="record-call")
@click.argument("model")
@click.argument("provider")
@click.option("--tenant", default="default", show_default=True)
@click.option("--input-tokens", type=int, default=0, show_default=True)
@click.option("--output-tokens", type=int, default=0, show_default=True)
@click.option("--latency-ms", type=float, default=0, show_default=True)
@click.option("--success/--failed", default=True, show_default=True)
@click.option("--cost-usd", type=float, default=0, show_default=True)
def ai_record_call(model: str, provider: str, tenant: str,
                   input_tokens: int, output_tokens: int,
                   latency_ms: float, success: bool, cost_usd: float):
    """Record a single AI model call."""
    result = ai_analytics_service.record_ai_call(
        tenant=tenant, model=model, provider=provider,
        input_tokens=input_tokens, output_tokens=output_tokens,
        latency_ms=latency_ms, success=success, cost_usd=cost_usd)
    _print("AI Call Recorded", result)


@ai.command(name="model-comparison")
@click.argument("tenant")
@click.option("--models", default="", help="Comma-separated model names.")
@click.option("--start-time", default="")
@click.option("--end-time", default="")
def ai_model_comparison(tenant: str, models: str, start_time: str,
                        end_time: str):
    """Compare model usage, latency, and cost."""
    comparison = ai_analytics_service.get_model_comparison(
        tenant=tenant, models=_split_names(models) or None,
        start_time=start_time, end_time=end_time)
    _print("AI Model Comparison", comparison)


# ─── marketplace ───────────────────────────────────────────────────────


@analytics.group(name="marketplace")
def marketplace():
    """Marketplace analytics commands."""


@marketplace.command(name="event")
@click.argument("event_type")
@click.option("--tenant", default="default", show_default=True)
@click.option("--package-name", default="")
@click.option("--package-id", default="")
@click.option("--version", default="")
def marketplace_event(event_type: str, tenant: str, package_name: str,
                      package_id: str, version: str):
    """Record a marketplace event."""
    result = marketplace_analytics_service.record_marketplace_event(
        tenant=tenant, event_type=event_type, package_name=package_name,
        package_id=package_id, version=version)
    _print("Marketplace Event Recorded", result)


@marketplace.command(name="summary")
@click.argument("tenant")
@click.option("--start-time", default="")
@click.option("--end-time", default="")
def marketplace_summary(tenant: str, start_time: str, end_time: str):
    """Show marketplace activity summary."""
    summary = marketplace_analytics_service.get_marketplace_summary(
        tenant=tenant, start_time=start_time, end_time=end_time)
    _print("Marketplace Summary", summary)


# ─── security ──────────────────────────────────────────────────────────


@analytics.group(name="security")
def security():
    """Security analytics commands."""


@security.command(name="finding")
@click.argument("tenant")
@click.option("--repository", default="")
@click.option("--severity", default="medium", show_default=True)
@click.option("--category", default="")
@click.option("--title", default="")
@click.option("--file-path", default="")
@click.option("--remediated/--open", default=False, show_default=True)
def security_finding(tenant: str, repository: str, severity: str,
                     category: str, title: str, file_path: str,
                     remediated: bool):
    """Record a security finding."""
    result = security_analytics_service.record_security_finding(
        tenant=tenant, repository=repository, severity=severity,
        category=category, title=title, file_path=file_path,
        remediated=remediated)
    _print("Security Finding Recorded", result)


@security.command(name="summary")
@click.argument("tenant")
@click.option("--repository", default="")
@click.option("--start-time", default="")
@click.option("--end-time", default="")
def security_summary(tenant: str, repository: str, start_time: str,
                     end_time: str):
    """Show security posture summary."""
    summary = security_analytics_service.get_security_summary(
        tenant=tenant, repository=repository, start_time=start_time,
        end_time=end_time)
    _print("Security Summary", summary)


# ─── quality ───────────────────────────────────────────────────────────


@analytics.group(name="quality")
def quality():
    """Data quality commands."""


@quality.command(name="validate")
@click.argument("path")
@click.option("--tenant", default="default", show_default=True)
def quality_validate(path: str, tenant: str):
    """Validate a batch of events from a JSON file ('-' for stdin)."""
    events = _load_json(path)
    if not isinstance(events, list):
        raise click.BadParameter("payload must be a JSON array of events")
    service = DataQualityService()
    result = service.validate_batch(events, tenant=tenant)
    _print("Batch Validation", result)


@quality.command(name="issues")
@click.option("--tenant", default="")
@click.option("--issue-type", default="")
@click.option("--resolved/--unresolved", default=None)
@click.option("--limit", type=int, default=100, show_default=True)
def quality_issues(tenant: str, issue_type: str, resolved: bool,
                   limit: int):
    """List data quality issues."""
    service = DataQualityService()
    items = service.get_issues(
        tenant=tenant, issue_type=issue_type, resolved=resolved,
        limit=limit)
    _print("Quality Issues", {"count": len(items), "issues": items})


@quality.command(name="resolve")
@click.argument("issue_id")
def quality_resolve(issue_id: str):
    """Resolve a data quality issue by ID."""
    service = DataQualityService()
    resolved = service.resolve_issue(issue_id)
    _print("Issue Resolved", {"issue_id": issue_id, "resolved": resolved})


def handle_analytics_command(args: list[str]):
    """Dispatch analytics CLI subcommands."""
    import sys as _sys
    _sys.argv = ["analytics"] + args
    analytics_commands_group(standalone_mode=False)


if __name__ == "__main__":
    analytics_commands_group()
