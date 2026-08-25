"""Observability SDK mixin — Volume 59 Commit 1 + Commit 2."""

from typing import Any, Dict, Optional


class ObservabilityMixin:
    def observe_register_service(self, data: dict) -> dict:
        return self.post(self._build_url("/observability/services"), data=data)

    def observe_list_services(self, environment: Optional[str] = None) -> dict:
        params = {}
        if environment:
            params["environment"] = environment
        return self.get(self._build_url("/observability/services"), params=params)

    def observe_service_map(self) -> dict:
        return self.get(self._build_url("/observability/service-map"))

    def observe_ingest_metric(self, metric: str, type: str, value: float, tags: Optional[dict] = None) -> dict:
        return self.post(self._build_url("/observability/metrics"), data={"metric": metric, "type": type, "value": value, "tags": tags or {}})

    def observe_ingest_log(self, service: str, level: str, message: str, **kwargs: Any) -> dict:
        payload = {"service": service, "level": level, "message": message, **kwargs}
        return self.post(self._build_url("/observability/logs"), data=payload)

    def observe_ingest_trace(self, trace_id: str, span_id: str, service: str, operation: str, duration_ms: int, **kwargs: Any) -> dict:
        payload = {"trace_id": trace_id, "span_id": span_id, "service": service, "operation": operation, "duration_ms": duration_ms, **kwargs}
        return self.post(self._build_url("/observability/traces"), data=payload)

    def observe_health(self, resource: str, health: str, checks: Optional[dict] = None) -> dict:
        return self.post(self._build_url("/observability/health"), data={"resource": resource, "health": health, "checks": checks or {}})

    def observe_create_alert_rule(self, name: str, resource: str, condition: dict, severity: str = "WARNING") -> dict:
        return self.post(self._build_url("/observability/alert-rules"), data={"name": name, "resource": resource, "condition": condition, "severity": severity})

    def observe_list_alert_rules(self) -> dict:
        return self.get(self._build_url("/observability/alert-rules"))

    def observe_create_alert(self, resource: str, condition: dict, severity: str = "WARNING") -> dict:
        return self.post(self._build_url("/observability/alerts"), data={"resource": resource, "condition": condition, "severity": severity})

    def observe_list_alerts(self, status: Optional[str] = None) -> dict:
        params = {}
        if status:
            params["status"] = status
        return self.get(self._build_url("/observability/alerts"), params=params)

    def observe_ack_alert(self, alert_id: str) -> dict:
        return self.post(self._build_url(f"/observability/alerts/{alert_id}/acknowledge"), data={})

    def observe_resolve_alert(self, alert_id: str) -> dict:
        return self.post(self._build_url(f"/observability/alerts/{alert_id}/resolve"), data={})

    def observe_create_slo(self, service: str, indicator: str, target: float, window: str = "30d") -> dict:
        return self.post(self._build_url("/observability/slos"), data={"service": service, "indicator": indicator, "target": target, "window": window})

    def observe_list_slos(self) -> dict:
        return self.get(self._build_url("/observability/slos"))

    def observe_evaluate_slo(self, slo_id: str, observed: float) -> dict:
        return self.post(self._build_url(f"/observability/slos/{slo_id}/evaluate"), data={"observed": observed})

    def observe_create_synthetic(self, name: str, target: str, check_type: str = "HTTP") -> dict:
        return self.post(self._build_url("/observability/synthetics"), data={"name": name, "target": target, "check_type": check_type})

    def observe_run_synthetic(self, check_id: str) -> dict:
        return self.post(self._build_url(f"/observability/synthetics/{check_id}/run"), data={})

    def observe_dashboard(self) -> dict:
        return self.get(self._build_url("/observability/dashboard"))

    # ── Volume 59 Commit 2 — AIOps extensions ──────────────────────────────────

    # keep additive: reuse existing platform/aiops/remediation services via API, no placeholders

    def get_anomalies(self, metric: Optional[str] = None, window_hours: int = 24, limit: int = 100) -> dict:
        params: Dict[str, Any] = {"window_hours": window_hours, "limit": limit}
        if metric:
            params["metric"] = metric
        return self.get(self._build_url("/observability/anomalies"), params=params)

    def detect_anomalies(self, metric: str = "", window_hours: int = 24) -> dict:
        return self.post(self._build_url("/observability/anomalies/detect"), data={"metric": metric, "window_hours": window_hours})

    def get_correlated_alerts(self, alert_id: str, window_minutes: int = 15) -> dict:
        return self.get(self._build_url(f"/observability/correlations/{alert_id}"), params={"window_minutes": window_minutes})

    def get_root_cause(self, incident_id: str) -> dict:
        return self.post(self._build_url(f"/observability/root-cause/{incident_id}"), data={})

    def get_recommendations(self, category: Optional[str] = None, limit: int = 50, status: Optional[str] = None) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if category:
            params["category"] = category
        if status:
            params["status"] = status
        return self.get(self._build_url("/observability/recommendations"), params=params)

    def approve_recommendation(self, recommendation_id: str, approver: str = "") -> dict:
        return self.post(self._build_url(f"/observability/recommendations/{recommendation_id}/approve"), data={"approver": approver})

    def request_remediation(self, incident_id: str, action: str, scope: Optional[dict] = None) -> dict:
        return self.post(self._build_url("/observability/remediation/request"), data={"incident_id": incident_id, "action": action, "scope": scope or {}})

    def approve_remediation(self, request_id: str, approver: str = "") -> dict:
        return self.post(self._build_url(f"/observability/remediation/{request_id}/approve"), data={"approver": approver})

    def execute_remediation(self, request_id: str, actor: str = "") -> dict:
        return self.post(self._build_url(f"/observability/remediation/{request_id}/execute"), data={"actor": actor})

    def get_capacity_forecast(self, service: str = "", horizon_hours: int = 24, metric: str = "") -> dict:
        params: Dict[str, Any] = {"horizon_hours": horizon_hours}
        if service:
            params["service"] = service
        if metric:
            params["metric"] = metric
        return self.get(self._build_url("/observability/forecast/capacity"), params=params)

    def get_cost_forecast(self, window_hours: int = 24, sensitivity: float = 2.0) -> dict:
        return self.get(self._build_url("/observability/forecast/cost"), params={"window_hours": window_hours, "sensitivity": sensitivity})

    def get_observability_quality(self, service: str = "") -> dict:
        params: Dict[str, Any] = {}
        if service:
            params["service"] = service
        return self.get(self._build_url("/observability/observability-quality"), params=params)

    def get_aiops_status(self) -> dict:
        return self.get(self._build_url("/observability/aiops/status"))

    def get_incident_summary(self, incident_id: str) -> dict:
        return self.get(self._build_url(f"/observability/incidents/{incident_id}/summary"))

    # ── observe_ aliases (backward compat for SDK consumers expecting observe_ prefix) ──

    def observe_get_anomalies(self, *args: Any, **kwargs: Any) -> dict:
        return self.get_anomalies(*args, **kwargs)

    def observe_detect_anomalies(self, *args: Any, **kwargs: Any) -> dict:
        return self.detect_anomalies(*args, **kwargs)

    def observe_get_correlated_alerts(self, *args: Any, **kwargs: Any) -> dict:
        return self.get_correlated_alerts(*args, **kwargs)

    def observe_get_root_cause(self, *args: Any, **kwargs: Any) -> dict:
        return self.get_root_cause(*args, **kwargs)

    def observe_get_recommendations(self, *args: Any, **kwargs: Any) -> dict:
        return self.get_recommendations(*args, **kwargs)

    def observe_request_remediation(self, *args: Any, **kwargs: Any) -> dict:
        return self.request_remediation(*args, **kwargs)

    def observe_approve_remediation(self, *args: Any, **kwargs: Any) -> dict:
        return self.approve_remediation(*args, **kwargs)

    def observe_execute_remediation(self, *args: Any, **kwargs: Any) -> dict:
        return self.execute_remediation(*args, **kwargs)

    def observe_get_capacity_forecast(self, *args: Any, **kwargs: Any) -> dict:
        return self.get_capacity_forecast(*args, **kwargs)

    def observe_get_observability_quality(self, *args: Any, **kwargs: Any) -> dict:
        return self.get_observability_quality(*args, **kwargs)

    def observe_get_aiops_status(self, *args: Any, **kwargs: Any) -> dict:
        return self.get_aiops_status(*args, **kwargs)


class AsyncObservabilityMixin:
    async def observe_register_service(self, data: dict) -> dict:
        return await self.post(self._build_url("/observability/services"), data=data)

    async def observe_list_services(self, environment: Optional[str] = None) -> dict:
        params = {}
        if environment:
            params["environment"] = environment
        return await self.get(self._build_url("/observability/services"), params=params)

    async def observe_service_map(self) -> dict:
        return await self.get(self._build_url("/observability/service-map"))

    async def observe_ingest_metric(self, metric: str, type: str, value: float, tags: Optional[dict] = None) -> dict:
        return await self.post(self._build_url("/observability/metrics"), data={"metric": metric, "type": type, "value": value, "tags": tags or {}})

    async def observe_health(self, resource: str, health: str, checks: Optional[dict] = None) -> dict:
        return await self.post(self._build_url("/observability/health"), data={"resource": resource, "health": health, "checks": checks or {}})

    async def observe_create_alert(self, resource: str, condition: dict, severity: str = "WARNING") -> dict:
        return await self.post(self._build_url("/observability/alerts"), data={"resource": resource, "condition": condition, "severity": severity})

    async def observe_list_alerts(self, status: Optional[str] = None) -> dict:
        params = {}
        if status:
            params["status"] = status
        return await self.get(self._build_url("/observability/alerts"), params=params)

    async def observe_create_slo(self, service: str, indicator: str, target: float, window: str = "30d") -> dict:
        return await self.post(self._build_url("/observability/slos"), data={"service": service, "indicator": indicator, "target": target, "window": window})

    async def observe_evaluate_slo(self, slo_id: str, observed: float) -> dict:
        return await self.post(self._build_url(f"/observability/slos/{slo_id}/evaluate"), data={"observed": observed})

    # ── Volume 59 Commit 2 — async AIOps extensions ───────────────────────────

    async def get_anomalies(self, metric: Optional[str] = None, window_hours: int = 24, limit: int = 100) -> dict:
        params: Dict[str, Any] = {"window_hours": window_hours, "limit": limit}
        if metric:
            params["metric"] = metric
        return await self.get(self._build_url("/observability/anomalies"), params=params)

    async def detect_anomalies(self, metric: str = "", window_hours: int = 24) -> dict:
        return await self.post(self._build_url("/observability/anomalies/detect"), data={"metric": metric, "window_hours": window_hours})

    async def get_correlated_alerts(self, alert_id: str, window_minutes: int = 15) -> dict:
        return await self.get(self._build_url(f"/observability/correlations/{alert_id}"), params={"window_minutes": window_minutes})

    async def get_root_cause(self, incident_id: str) -> dict:
        return await self.post(self._build_url(f"/observability/root-cause/{incident_id}"), data={})

    async def get_recommendations(self, category: Optional[str] = None, limit: int = 50, status: Optional[str] = None) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if category:
            params["category"] = category
        if status:
            params["status"] = status
        return await self.get(self._build_url("/observability/recommendations"), params=params)

    async def approve_recommendation(self, recommendation_id: str, approver: str = "") -> dict:
        return await self.post(self._build_url(f"/observability/recommendations/{recommendation_id}/approve"), data={"approver": approver})

    async def request_remediation(self, incident_id: str, action: str, scope: Optional[dict] = None) -> dict:
        return await self.post(self._build_url("/observability/remediation/request"), data={"incident_id": incident_id, "action": action, "scope": scope or {}})

    async def approve_remediation(self, request_id: str, approver: str = "") -> dict:
        return await self.post(self._build_url(f"/observability/remediation/{request_id}/approve"), data={"approver": approver})

    async def execute_remediation(self, request_id: str, actor: str = "") -> dict:
        return await self.post(self._build_url(f"/observability/remediation/{request_id}/execute"), data={"actor": actor})

    async def get_capacity_forecast(self, service: str = "", horizon_hours: int = 24, metric: str = "") -> dict:
        params: Dict[str, Any] = {"horizon_hours": horizon_hours}
        if service:
            params["service"] = service
        if metric:
            params["metric"] = metric
        return await self.get(self._build_url("/observability/forecast/capacity"), params=params)

    async def get_cost_forecast(self, window_hours: int = 24, sensitivity: float = 2.0) -> dict:
        return await self.get(self._build_url("/observability/forecast/cost"), params={"window_hours": window_hours, "sensitivity": sensitivity})

    async def get_observability_quality(self, service: str = "") -> dict:
        params: Dict[str, Any] = {}
        if service:
            params["service"] = service
        return await self.get(self._build_url("/observability/observability-quality"), params=params)

    async def get_aiops_status(self) -> dict:
        return await self.get(self._build_url("/observability/aiops/status"))

    async def get_incident_summary(self, incident_id: str) -> dict:
        return await self.get(self._build_url(f"/observability/incidents/{incident_id}/summary"))

    # aliases
    async def observe_get_anomalies(self, *args: Any, **kwargs: Any) -> dict:
        return await self.get_anomalies(*args, **kwargs)

    async def observe_detect_anomalies(self, *args: Any, **kwargs: Any) -> dict:
        return await self.detect_anomalies(*args, **kwargs)

    async def observe_get_correlated_alerts(self, *args: Any, **kwargs: Any) -> dict:
        return await self.get_correlated_alerts(*args, **kwargs)

    async def observe_get_root_cause(self, *args: Any, **kwargs: Any) -> dict:
        return await self.get_root_cause(*args, **kwargs)

    async def observe_get_recommendations(self, *args: Any, **kwargs: Any) -> dict:
        return await self.get_recommendations(*args, **kwargs)

    async def observe_request_remediation(self, *args: Any, **kwargs: Any) -> dict:
        return await self.request_remediation(*args, **kwargs)

    async def observe_approve_remediation(self, *args: Any, **kwargs: Any) -> dict:
        return await self.approve_remediation(*args, **kwargs)

    async def observe_execute_remediation(self, *args: Any, **kwargs: Any) -> dict:
        return await self.execute_remediation(*args, **kwargs)

    async def observe_get_capacity_forecast(self, *args: Any, **kwargs: Any) -> dict:
        return await self.get_capacity_forecast(*args, **kwargs)

    async def observe_get_observability_quality(self, *args: Any, **kwargs: Any) -> dict:
        return await self.get_observability_quality(*args, **kwargs)

    async def observe_get_aiops_status(self, *args: Any, **kwargs: Any) -> dict:
        return await self.get_aiops_status(*args, **kwargs)
