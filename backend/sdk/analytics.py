"""NovaForge Analytics Platform -- SDK (Volume 50)."""

from __future__ import annotations

from typing import Any, Optional


class AnalyticsMixin:
    """Sync SDK methods for the NovaForge Analytics Platform."""

    def ingest_event(self, tenant: str, source: str, event_type: str,
                     event_timestamp: str = "", cost_usd: float = 0.0,
                     duration_ms: float = 0.0,
                     metadata_extra: dict | None = None) -> dict:
        return self._request("POST", "/api/v1/analytics/events/ingest", json={
            "tenant": tenant, "source": source, "event_type": event_type,
            "event_timestamp": event_timestamp, "cost_usd": cost_usd,
            "duration_ms": duration_ms, "metadata_extra": metadata_extra or {}})

    def ingest_events_batch(self, events: list[dict],
                            idempotency_key: str = "") -> dict:
        return self._request("POST", "/api/v1/analytics/events/ingest/batch",
                             json={"events": events,
                                   "idempotency_key": idempotency_key})

    def list_events(self, tenant: str = "", event_type: str = "",
                    source: str = "", start_time: str = "",
                    end_time: str = "", limit: int = 100) -> list:
        params: dict[str, Any] = {"limit": limit}
        for k, v in [("tenant", tenant), ("event_type", event_type),
                     ("source", source), ("start_time", start_time),
                     ("end_time", end_time)]:
            if v:
                params[k] = v
        return self._request("GET", "/api/v1/analytics/events", params=params)

    def get_event(self, event_id: str) -> dict:
        return self._request("GET", f"/api/v1/analytics/events/{event_id}")

    def validate_event(self, event: dict) -> dict:
        return self._request("POST", "/api/v1/analytics/events/validate",
                             json=event)

    def record_metric(self, tenant: str, metric_name: str, value: float,
                      dimensions: dict | None = None, timestamp: str = "",
                      granularity: str = "hour") -> dict:
        return self._request("POST", "/api/v1/analytics/metrics/record", json={
            "tenant": tenant, "metric_name": metric_name, "value": value,
            "dimensions": dimensions or {}, "timestamp": timestamp,
            "granularity": granularity})

    def query_metrics(self, metric_name: str, granularity: str = "hour",
                      dimensions: dict | None = None, start_time: str = "",
                      end_time: str = "", limit: int = 1000) -> list:
        return self._request("POST", "/api/v1/analytics/metrics/query", json={
            "metric_name": metric_name, "granularity": granularity,
            "dimensions": dimensions or {}, "start_time": start_time,
            "end_time": end_time, "limit": limit})

    def aggregate_metrics(self, metric_name: str, start_time: str,
                          end_time: str, granularity: str = "hour",
                          dimensions: dict | None = None) -> dict:
        return self._request("POST", "/api/v1/analytics/metrics/aggregate",
                             json={"metric_name": metric_name,
                                   "start_time": start_time,
                                   "end_time": end_time,
                                   "granularity": granularity,
                                   "dimensions": dimensions or {}})

    def get_metric_trend(self, metric_names: list[str],
                         granularity: str = "day", start_time: str = "",
                         end_time: str = "",
                         dimensions: dict | None = None) -> list:
        return self._request("POST", "/api/v1/analytics/metrics/trend", json={
            "metric_names": metric_names, "granularity": granularity,
            "start_time": start_time, "end_time": end_time,
            "dimensions": dimensions or {}})

    def record_cost(self, tenant: str, cost_type: str, amount_usd: float,
                    period_start: str, period_end: str, **kwargs) -> dict:
        payload: dict[str, Any] = {"tenant": tenant, "cost_type": cost_type,
                                   "amount_usd": amount_usd,
                                   "period_start": period_start,
                                   "period_end": period_end}
        payload.update(kwargs)
        return self._request("POST", "/api/v1/analytics/costs/record",
                             json=payload)

    def get_costs(self, tenant: str = "", cost_type: str = "",
                  start_time: str = "", end_time: str = "",
                  limit: int = 1000) -> list:
        params: dict[str, Any] = {"limit": limit}
        for k, v in [("tenant", tenant), ("cost_type", cost_type),
                     ("start_time", start_time), ("end_time", end_time)]:
            if v:
                params[k] = v
        return self._request("GET", "/api/v1/analytics/costs", params=params)

    def get_cost_summary(self, tenant: str, group_by: str = "cost_type",
                         start_time: str = "", end_time: str = "") -> dict:
        return self._request("POST", "/api/v1/analytics/costs/summary", json={
            "tenant": tenant, "group_by": group_by,
            "start_time": start_time, "end_time": end_time})

    def get_ai_cost_breakdown(self, tenant: str, start_time: str = "",
                              end_time: str = "") -> dict:
        params: dict[str, Any] = {"tenant": tenant}
        for k, v in [("start_time", start_time), ("end_time", end_time)]:
            if v:
                params[k] = v
        return self._request("GET", "/api/v1/analytics/costs/ai-breakdown",
                             params=params)

    def compare_models(self, tenant: str, models: list[str] | None = None,
                       start_time: str = "", end_time: str = "") -> list:
        return self._request("POST",
                             "/api/v1/analytics/costs/compare-models", json={
                                 "tenant": tenant, "models": models or [],
                                 "start_time": start_time,
                                 "end_time": end_time})

    def create_budget(self, tenant: str, name: str, scope: str,
                      scope_value: str, limit_usd: float,
                      cost_type: str = "total",
                      period: str = "monthly") -> dict:
        return self._request("POST", "/api/v1/analytics/budgets", json={
            "tenant": tenant, "name": name, "scope": scope,
            "scope_value": scope_value, "limit_usd": limit_usd,
            "cost_type": cost_type, "period": period})

    def list_budgets(self, tenant: str = "", scope: str = "") -> list:
        params: dict[str, Any] = {}
        for k, v in [("tenant", tenant), ("scope", scope)]:
            if v:
                params[k] = v
        return self._request("GET", "/api/v1/analytics/budgets", params=params)

    def get_budget(self, budget_id: str) -> dict:
        return self._request("GET", f"/api/v1/analytics/budgets/{budget_id}")

    def update_budget(self, budget_id: str, **kwargs) -> dict:
        return self._request("PUT", f"/api/v1/analytics/budgets/{budget_id}",
                             json=kwargs)

    def delete_budget(self, budget_id: str) -> dict:
        return self._request("DELETE",
                             f"/api/v1/analytics/budgets/{budget_id}")

    def get_budget_status(self, tenant: str = "") -> list:
        params: dict[str, Any] = {}
        if tenant:
            params["tenant"] = tenant
        return self._request("GET", "/api/v1/analytics/budgets/status",
                             params=params)

    def create_alert(self, tenant: str, name: str, alert_type: str,
                     metric_name: str = "", severity: str = "medium") -> dict:
        return self._request("POST", "/api/v1/analytics/alerts", json={
            "tenant": tenant, "name": name, "alert_type": alert_type,
            "metric_name": metric_name, "severity": severity})

    def list_alerts(self, tenant: str = "", alert_type: str = "",
                    status: str = "", limit: int = 50) -> list:
        params: dict[str, Any] = {"limit": limit}
        for k, v in [("tenant", tenant), ("alert_type", alert_type),
                     ("status", status)]:
            if v:
                params[k] = v
        return self._request("GET", "/api/v1/analytics/alerts", params=params)

    def get_alert(self, alert_id: str) -> dict:
        return self._request("GET", f"/api/v1/analytics/alerts/{alert_id}")

    def delete_alert(self, alert_id: str) -> dict:
        return self._request("DELETE", f"/api/v1/analytics/alerts/{alert_id}")

    def generate_report(self, tenant: str, report_type: str,
                        period_start: str, period_end: str,
                        data: dict | None = None) -> dict:
        return self._request("POST", "/api/v1/analytics/reports/generate",
                             json={"tenant": tenant,
                                   "report_type": report_type,
                                   "period_start": period_start,
                                   "period_end": period_end,
                                   "data": data or {}})

    def list_reports(self, tenant: str = "", report_type: str = "",
                     limit: int = 20) -> list:
        params: dict[str, Any] = {"limit": limit}
        for k, v in [("tenant", tenant), ("report_type", report_type)]:
            if v:
                params[k] = v
        return self._request("GET", "/api/v1/analytics/reports", params=params)

    def get_report(self, report_id: str) -> dict:
        return self._request("GET", f"/api/v1/analytics/reports/{report_id}")

    def delete_report(self, report_id: str) -> dict:
        return self._request("DELETE",
                             f"/api/v1/analytics/reports/{report_id}")

    def create_forecast(self, tenant: str, metric_name: str,
                        horizon_days: int = 30, scope: str = "",
                        scope_value: str = "") -> dict:
        return self._request("POST", "/api/v1/analytics/forecast", json={
            "tenant": tenant, "metric_name": metric_name,
            "horizon_days": horizon_days, "scope": scope,
            "scope_value": scope_value})

    def get_forecast(self, tenant: str, metric_name: str) -> list:
        return self._request("GET",
                             f"/api/v1/analytics/forecast/{metric_name}",
                             params={"tenant": tenant})

    def generate_recommendations(self, tenant: str,
                                 data: dict | None = None) -> list:
        return self._request("POST",
                             "/api/v1/analytics/recommendations/generate",
                             json={"tenant": tenant, "data": data or {}})

    def list_recommendations(self, tenant: str = "", category: str = "",
                             status: str = "pending",
                             limit: int = 50) -> list:
        params: dict[str, Any] = {"status": status, "limit": limit}
        for k, v in [("tenant", tenant), ("category", category)]:
            if v:
                params[k] = v
        return self._request("GET", "/api/v1/analytics/recommendations",
                             params=params)

    def dismiss_recommendation(self, recommendation_id: str) -> dict:
        return self._request(
            "POST",
            f"/api/v1/analytics/recommendations/{recommendation_id}/action",
            json={"recommendation_id": recommendation_id,
                  "action": "dismiss"})

    def record_slo_measurement(self, tenant: str, service: str,
                               metric_name: str, actual_value: float,
                               target: float, window_start: str,
                               window_end: str) -> dict:
        return self._request("POST", "/api/v1/analytics/slo/record", json={
            "tenant": tenant, "service": service,
            "metric_name": metric_name, "actual_value": actual_value,
            "target": target, "window_start": window_start,
            "window_end": window_end})

    def get_slo_status(self, tenant: str, service: str = "") -> dict:
        params: dict[str, Any] = {"tenant": tenant}
        if service:
            params["service"] = service
        return self._request("GET", "/api/v1/analytics/slo/status",
                             params=params)

    def record_deployment(self, tenant: str, service: str,
                          commit_sha: str = "",
                          environment: str = "production",
                          success: bool = True) -> dict:
        return self._request("POST",
                             "/api/v1/analytics/engineering/deployment", json={
                                 "tenant": tenant, "service": service,
                                 "commit_sha": commit_sha,
                                 "environment": environment,
                                 "success": success})

    def compute_dora(self, tenant: str, project: str = "",
                     repository: str = "", start_time: str = "",
                     end_time: str = "") -> dict:
        return self._request("POST",
                             "/api/v1/analytics/engineering/dora", json={
                                 "tenant": tenant, "project": project,
                                 "repository": repository,
                                 "start_time": start_time,
                                 "end_time": end_time})

    def record_ai_call(self, tenant: str, model: str, provider: str,
                       input_tokens: int = 0, output_tokens: int = 0,
                       latency_ms: float = 0, success: bool = True,
                       cost_usd: float = 0) -> dict:
        return self._request("POST", "/api/v1/analytics/ai/record-call", json={
            "tenant": tenant, "model": model, "provider": provider,
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "latency_ms": latency_ms, "success": success,
            "cost_usd": cost_usd})

    def get_model_comparison(self, tenant: str,
                             models: list[str] | None = None,
                             start_time: str = "",
                             end_time: str = "") -> list:
        params: dict[str, Any] = {"tenant": tenant}
        if models:
            params["models"] = ",".join(models)
        for k, v in [("start_time", start_time), ("end_time", end_time)]:
            if v:
                params[k] = v
        return self._request("GET",
                             "/api/v1/analytics/ai/model-comparison",
                             params=params)

    def record_marketplace_event(self, tenant: str, event_type: str,
                                 package_name: str = "",
                                 package_id: str = "",
                                 version: str = "") -> dict:
        return self._request("POST",
                             "/api/v1/analytics/marketplace/event", json={
                                 "tenant": tenant, "event_type": event_type,
                                 "package_name": package_name,
                                 "package_id": package_id,
                                 "version": version})

    def get_marketplace_summary(self, tenant: str, start_time: str = "",
                                end_time: str = "") -> dict:
        params: dict[str, Any] = {"tenant": tenant}
        for k, v in [("start_time", start_time), ("end_time", end_time)]:
            if v:
                params[k] = v
        return self._request("GET", "/api/v1/analytics/marketplace/summary",
                             params=params)

    def record_security_finding(self, tenant: str, repository: str = "",
                                severity: str = "medium",
                                category: str = "", title: str = "",
                                file_path: str = "",
                                remediated: bool = False) -> dict:
        return self._request("POST",
                             "/api/v1/analytics/security/finding", json={
                                 "tenant": tenant, "repository": repository,
                                 "severity": severity, "category": category,
                                 "title": title, "file_path": file_path,
                                 "remediated": remediated})

    def get_security_summary(self, tenant: str, repository: str = "",
                             start_time: str = "",
                             end_time: str = "") -> dict:
        params: dict[str, Any] = {"tenant": tenant}
        for k, v in [("repository", repository), ("start_time", start_time),
                     ("end_time", end_time)]:
            if v:
                params[k] = v
        return self._request("GET", "/api/v1/analytics/security/summary",
                             params=params)

    def validate_batch(self, events: list[dict],
                       tenant: str = "default") -> dict:
        return self._request("POST", "/api/v1/analytics/quality/validate",
                             json={"events": events, "tenant": tenant})

    def list_quality_issues(self, tenant: str = "", issue_type: str = "",
                            resolved: bool | None = None,
                            limit: int = 100) -> list:
        params: dict[str, Any] = {"limit": limit}
        for k, v in [("tenant", tenant), ("issue_type", issue_type)]:
            if v:
                params[k] = v
        if resolved is not None:
            params["resolved"] = resolved
        return self._request("GET", "/api/v1/analytics/quality/issues",
                             params=params)

    def resolve_quality_issue(self, issue_id: str) -> dict:
        return self._request(
            "POST", f"/api/v1/analytics/quality/{issue_id}/resolve")


class AsyncAnalyticsMixin:
    """Async SDK methods for the NovaForge Analytics Platform."""

    async def ingest_event(self, tenant: str, source: str, event_type: str,
                           event_timestamp: str = "",
                           cost_usd: float = 0.0, duration_ms: float = 0.0,
                           metadata_extra: dict | None = None) -> dict:
        return await self._arequest("POST",
                                    "/api/v1/analytics/events/ingest", json={
                                        "tenant": tenant, "source": source,
                                        "event_type": event_type,
                                        "event_timestamp": event_timestamp,
                                        "cost_usd": cost_usd,
                                        "duration_ms": duration_ms,
                                        "metadata_extra": metadata_extra or {}})

    async def ingest_events_batch(self, events: list[dict],
                                  idempotency_key: str = "") -> dict:
        return await self._arequest(
            "POST", "/api/v1/analytics/events/ingest/batch",
            json={"events": events, "idempotency_key": idempotency_key})

    async def list_events(self, tenant: str = "", event_type: str = "",
                          source: str = "", start_time: str = "",
                          end_time: str = "", limit: int = 100) -> list:
        params: dict[str, Any] = {"limit": limit}
        for k, v in [("tenant", tenant), ("event_type", event_type),
                     ("source", source), ("start_time", start_time),
                     ("end_time", end_time)]:
            if v:
                params[k] = v
        return await self._arequest("GET", "/api/v1/analytics/events",
                                    params=params)

    async def get_event(self, event_id: str) -> dict:
        return await self._arequest("GET",
                                    f"/api/v1/analytics/events/{event_id}")

    async def validate_event(self, event: dict) -> dict:
        return await self._arequest("POST",
                                    "/api/v1/analytics/events/validate",
                                    json=event)

    async def record_metric(self, tenant: str, metric_name: str,
                            value: float, dimensions: dict | None = None,
                            timestamp: str = "",
                            granularity: str = "hour") -> dict:
        return await self._arequest(
            "POST", "/api/v1/analytics/metrics/record", json={
                "tenant": tenant, "metric_name": metric_name,
                "value": value, "dimensions": dimensions or {},
                "timestamp": timestamp, "granularity": granularity})

    async def query_metrics(self, metric_name: str,
                            granularity: str = "hour",
                            dimensions: dict | None = None,
                            start_time: str = "", end_time: str = "",
                            limit: int = 1000) -> list:
        return await self._arequest(
            "POST", "/api/v1/analytics/metrics/query", json={
                "metric_name": metric_name, "granularity": granularity,
                "dimensions": dimensions or {}, "start_time": start_time,
                "end_time": end_time, "limit": limit})

    async def aggregate_metrics(self, metric_name: str, start_time: str,
                                end_time: str, granularity: str = "hour",
                                dimensions: dict | None = None) -> dict:
        return await self._arequest(
            "POST", "/api/v1/analytics/metrics/aggregate", json={
                "metric_name": metric_name, "start_time": start_time,
                "end_time": end_time, "granularity": granularity,
                "dimensions": dimensions or {}})

    async def get_metric_trend(self, metric_names: list[str],
                               granularity: str = "day", start_time: str = "",
                               end_time: str = "",
                               dimensions: dict | None = None) -> list:
        return await self._arequest(
            "POST", "/api/v1/analytics/metrics/trend", json={
                "metric_names": metric_names, "granularity": granularity,
                "start_time": start_time, "end_time": end_time,
                "dimensions": dimensions or {}})

    async def record_cost(self, tenant: str, cost_type: str,
                          amount_usd: float, period_start: str,
                          period_end: str, **kwargs) -> dict:
        payload: dict[str, Any] = {"tenant": tenant, "cost_type": cost_type,
                                   "amount_usd": amount_usd,
                                   "period_start": period_start,
                                   "period_end": period_end}
        payload.update(kwargs)
        return await self._arequest("POST",
                                    "/api/v1/analytics/costs/record",
                                    json=payload)

    async def get_costs(self, tenant: str = "", cost_type: str = "",
                        start_time: str = "", end_time: str = "",
                        limit: int = 1000) -> list:
        params: dict[str, Any] = {"limit": limit}
        for k, v in [("tenant", tenant), ("cost_type", cost_type),
                     ("start_time", start_time), ("end_time", end_time)]:
            if v:
                params[k] = v
        return await self._arequest("GET", "/api/v1/analytics/costs",
                                    params=params)

    async def get_cost_summary(self, tenant: str,
                               group_by: str = "cost_type",
                               start_time: str = "",
                               end_time: str = "") -> dict:
        return await self._arequest(
            "POST", "/api/v1/analytics/costs/summary", json={
                "tenant": tenant, "group_by": group_by,
                "start_time": start_time, "end_time": end_time})

    async def get_ai_cost_breakdown(self, tenant: str, start_time: str = "",
                                    end_time: str = "") -> dict:
        params: dict[str, Any] = {"tenant": tenant}
        for k, v in [("start_time", start_time), ("end_time", end_time)]:
            if v:
                params[k] = v
        return await self._arequest("GET",
                                    "/api/v1/analytics/costs/ai-breakdown",
                                    params=params)

    async def compare_models(self, tenant: str,
                             models: list[str] | None = None,
                             start_time: str = "",
                             end_time: str = "") -> list:
        return await self._arequest(
            "POST", "/api/v1/analytics/costs/compare-models", json={
                "tenant": tenant, "models": models or [],
                "start_time": start_time, "end_time": end_time})

    async def create_budget(self, tenant: str, name: str, scope: str,
                            scope_value: str, limit_usd: float,
                            cost_type: str = "total",
                            period: str = "monthly") -> dict:
        return await self._arequest("POST", "/api/v1/analytics/budgets", json={
            "tenant": tenant, "name": name, "scope": scope,
            "scope_value": scope_value, "limit_usd": limit_usd,
            "cost_type": cost_type, "period": period})

    async def list_budgets(self, tenant: str = "", scope: str = "") -> list:
        params: dict[str, Any] = {}
        for k, v in [("tenant", tenant), ("scope", scope)]:
            if v:
                params[k] = v
        return await self._arequest("GET", "/api/v1/analytics/budgets",
                                    params=params)

    async def get_budget(self, budget_id: str) -> dict:
        return await self._arequest("GET",
                                    f"/api/v1/analytics/budgets/{budget_id}")

    async def update_budget(self, budget_id: str, **kwargs) -> dict:
        return await self._arequest(
            "PUT", f"/api/v1/analytics/budgets/{budget_id}", json=kwargs)

    async def delete_budget(self, budget_id: str) -> dict:
        return await self._arequest("DELETE",
                                    f"/api/v1/analytics/budgets/{budget_id}")

    async def get_budget_status(self, tenant: str = "") -> list:
        params: dict[str, Any] = {}
        if tenant:
            params["tenant"] = tenant
        return await self._arequest("GET", "/api/v1/analytics/budgets/status",
                                    params=params)

    async def create_alert(self, tenant: str, name: str, alert_type: str,
                           metric_name: str = "",
                           severity: str = "medium") -> dict:
        return await self._arequest("POST", "/api/v1/analytics/alerts", json={
            "tenant": tenant, "name": name, "alert_type": alert_type,
            "metric_name": metric_name, "severity": severity})

    async def list_alerts(self, tenant: str = "", alert_type: str = "",
                          status: str = "", limit: int = 50) -> list:
        params: dict[str, Any] = {"limit": limit}
        for k, v in [("tenant", tenant), ("alert_type", alert_type),
                     ("status", status)]:
            if v:
                params[k] = v
        return await self._arequest("GET", "/api/v1/analytics/alerts",
                                    params=params)

    async def get_alert(self, alert_id: str) -> dict:
        return await self._arequest("GET",
                                    f"/api/v1/analytics/alerts/{alert_id}")

    async def delete_alert(self, alert_id: str) -> dict:
        return await self._arequest("DELETE",
                                    f"/api/v1/analytics/alerts/{alert_id}")

    async def generate_report(self, tenant: str, report_type: str,
                              period_start: str, period_end: str,
                              data: dict | None = None) -> dict:
        return await self._arequest(
            "POST", "/api/v1/analytics/reports/generate", json={
                "tenant": tenant, "report_type": report_type,
                "period_start": period_start, "period_end": period_end,
                "data": data or {}})

    async def list_reports(self, tenant: str = "", report_type: str = "",
                           limit: int = 20) -> list:
        params: dict[str, Any] = {"limit": limit}
        for k, v in [("tenant", tenant), ("report_type", report_type)]:
            if v:
                params[k] = v
        return await self._arequest("GET", "/api/v1/analytics/reports",
                                    params=params)

    async def get_report(self, report_id: str) -> dict:
        return await self._arequest("GET",
                                    f"/api/v1/analytics/reports/{report_id}")

    async def delete_report(self, report_id: str) -> dict:
        return await self._arequest("DELETE",
                                    f"/api/v1/analytics/reports/{report_id}")

    async def create_forecast(self, tenant: str, metric_name: str,
                              horizon_days: int = 30, scope: str = "",
                              scope_value: str = "") -> dict:
        return await self._arequest("POST", "/api/v1/analytics/forecast", json={
            "tenant": tenant, "metric_name": metric_name,
            "horizon_days": horizon_days, "scope": scope,
            "scope_value": scope_value})

    async def get_forecast(self, tenant: str, metric_name: str) -> list:
        return await self._arequest(
            "GET", f"/api/v1/analytics/forecast/{metric_name}",
            params={"tenant": tenant})

    async def generate_recommendations(self, tenant: str,
                                       data: dict | None = None) -> list:
        return await self._arequest(
            "POST", "/api/v1/analytics/recommendations/generate",
            json={"tenant": tenant, "data": data or {}})

    async def list_recommendations(self, tenant: str = "", category: str = "",
                                   status: str = "pending",
                                   limit: int = 50) -> list:
        params: dict[str, Any] = {"status": status, "limit": limit}
        for k, v in [("tenant", tenant), ("category", category)]:
            if v:
                params[k] = v
        return await self._arequest("GET",
                                    "/api/v1/analytics/recommendations",
                                    params=params)

    async def dismiss_recommendation(self, recommendation_id: str) -> dict:
        return await self._arequest(
            "POST",
            f"/api/v1/analytics/recommendations/{recommendation_id}/action",
            json={"recommendation_id": recommendation_id,
                  "action": "dismiss"})

    async def record_slo_measurement(self, tenant: str, service: str,
                                     metric_name: str, actual_value: float,
                                     target: float, window_start: str,
                                     window_end: str) -> dict:
        return await self._arequest(
            "POST", "/api/v1/analytics/slo/record", json={
                "tenant": tenant, "service": service,
                "metric_name": metric_name, "actual_value": actual_value,
                "target": target, "window_start": window_start,
                "window_end": window_end})

    async def get_slo_status(self, tenant: str, service: str = "") -> dict:
        params: dict[str, Any] = {"tenant": tenant}
        if service:
            params["service"] = service
        return await self._arequest("GET", "/api/v1/analytics/slo/status",
                                    params=params)

    async def record_deployment(self, tenant: str, service: str,
                                commit_sha: str = "",
                                environment: str = "production",
                                success: bool = True) -> dict:
        return await self._arequest(
            "POST", "/api/v1/analytics/engineering/deployment", json={
                "tenant": tenant, "service": service,
                "commit_sha": commit_sha, "environment": environment,
                "success": success})

    async def compute_dora(self, tenant: str, project: str = "",
                           repository: str = "", start_time: str = "",
                           end_time: str = "") -> dict:
        return await self._arequest(
            "POST", "/api/v1/analytics/engineering/dora", json={
                "tenant": tenant, "project": project,
                "repository": repository, "start_time": start_time,
                "end_time": end_time})

    async def record_ai_call(self, tenant: str, model: str, provider: str,
                             input_tokens: int = 0, output_tokens: int = 0,
                             latency_ms: float = 0, success: bool = True,
                             cost_usd: float = 0) -> dict:
        return await self._arequest(
            "POST", "/api/v1/analytics/ai/record-call", json={
                "tenant": tenant, "model": model, "provider": provider,
                "input_tokens": input_tokens, "output_tokens": output_tokens,
                "latency_ms": latency_ms, "success": success,
                "cost_usd": cost_usd})

    async def get_model_comparison(self, tenant: str,
                                   models: list[str] | None = None,
                                   start_time: str = "",
                                   end_time: str = "") -> list:
        params: dict[str, Any] = {"tenant": tenant}
        if models:
            params["models"] = ",".join(models)
        for k, v in [("start_time", start_time), ("end_time", end_time)]:
            if v:
                params[k] = v
        return await self._arequest(
            "GET", "/api/v1/analytics/ai/model-comparison", params=params)

    async def record_marketplace_event(self, tenant: str, event_type: str,
                                       package_name: str = "",
                                       package_id: str = "",
                                       version: str = "") -> dict:
        return await self._arequest(
            "POST", "/api/v1/analytics/marketplace/event", json={
                "tenant": tenant, "event_type": event_type,
                "package_name": package_name, "package_id": package_id,
                "version": version})

    async def get_marketplace_summary(self, tenant: str, start_time: str = "",
                                      end_time: str = "") -> dict:
        params: dict[str, Any] = {"tenant": tenant}
        for k, v in [("start_time", start_time), ("end_time", end_time)]:
            if v:
                params[k] = v
        return await self._arequest(
            "GET", "/api/v1/analytics/marketplace/summary", params=params)

    async def record_security_finding(self, tenant: str,
                                      repository: str = "",
                                      severity: str = "medium",
                                      category: str = "", title: str = "",
                                      file_path: str = "",
                                      remediated: bool = False) -> dict:
        return await self._arequest(
            "POST", "/api/v1/analytics/security/finding", json={
                "tenant": tenant, "repository": repository,
                "severity": severity, "category": category, "title": title,
                "file_path": file_path, "remediated": remediated})

    async def get_security_summary(self, tenant: str, repository: str = "",
                                   start_time: str = "",
                                   end_time: str = "") -> dict:
        params: dict[str, Any] = {"tenant": tenant}
        for k, v in [("repository", repository), ("start_time", start_time),
                     ("end_time", end_time)]:
            if v:
                params[k] = v
        return await self._arequest(
            "GET", "/api/v1/analytics/security/summary", params=params)

    async def validate_batch(self, events: list[dict],
                             tenant: str = "default") -> dict:
        return await self._arequest(
            "POST", "/api/v1/analytics/quality/validate",
            json={"events": events, "tenant": tenant})

    async def list_quality_issues(self, tenant: str = "",
                                  issue_type: str = "",
                                  resolved: bool | None = None,
                                  limit: int = 100) -> list:
        params: dict[str, Any] = {"limit": limit}
        for k, v in [("tenant", tenant), ("issue_type", issue_type)]:
            if v:
                params[k] = v
        if resolved is not None:
            params["resolved"] = resolved
        return await self._arequest("GET",
                                    "/api/v1/analytics/quality/issues",
                                    params=params)

    async def resolve_quality_issue(self, issue_id: str) -> dict:
        return await self._arequest(
            "POST", f"/api/v1/analytics/quality/{issue_id}/resolve")
