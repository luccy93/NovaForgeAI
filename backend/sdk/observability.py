"""Observability SDK mixin — Volume 59 Commit 1."""

from typing import Any, Optional


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
