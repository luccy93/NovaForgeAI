"""10x Enhanced service layer for Volume 28 — Observability & Performance."""
import logging, asyncio
from ..common.services import AsyncService, registry
from ..common.base import Validator
from ..common.storage import JsonFileStorage
from . import telemetry_collector, metric_engine, tracing, logging_engine
from . import monitoring, alert_manager, dashboard_engine, anomaly_detection
from . import perf_monitoring, slo_engine, capacity_planning, tracing_analytics
from . import ai_observability, cost_analytics, real_time_monitoring
from . import enterprise_obs, integration, reporting, alerting_chains, intelligent_sampling

logger = logging.getLogger(__name__)


class ObservabilityService(AsyncService):
    def __init__(self):
        super().__init__("observability", JsonFileStorage("data/observability/service.json"))
        self.tel_collector = telemetry_collector.TelemetryCollector("data/observability/telemetry")
        self.metrics = metric_engine.MetricEngine("data/observability/metrics")
        self.trace = tracing.Tracing("data/observability/traces")
        self.logging = logging_engine.LoggingEngine("data/observability/logs")
        self.monitoring = monitoring.Monitoring("data/observability/monitoring")
        self.alerts = alert_manager.AlertManager("data/observability/alerts")
        self.dashboards = dashboard_engine.DashboardEngine("data/observability/dashboards")
        self.anomaly = anomaly_detection.AnomalyDetection("data/observability/anomalies")
        self.perf = perf_monitoring.PerfMonitoring("data/observability/perf")
        self.slo = slo_engine.SLOEngine("data/observability/slos")
        self.capacity = capacity_planning.CapacityPlanning("data/observability/capacity")
        self.trace_analytics = tracing_analytics.TracingAnalytics("data/observability/trace_analytics")
        self.ai_obs = ai_observability.AIObservability("data/observability/ai_obs")
        self.cost = cost_analytics.CostAnalytics("data/observability/cost")
        self.realtime = real_time_monitoring.RealTimeMonitoring("data/observability/realtime")
        self.ent_obs = enterprise_obs.EnterpriseObservability("data/observability/enterprise")
        self.integration = integration.ObservabilityIntegration("data/observability/integration")
        self.reporting = reporting.ObservabilityReporting("data/observability/reports")
        self.alert_chains = alerting_chains.AlertingChains("data/observability/alert_chains")
        self.sampling = intelligent_sampling.IntelligentSampling("data/observability/sampling")

    async def ingest_metric(self, org_id: str, name: str, value: float, tags: dict = None):
        metric = self.metrics.ingest(name, value, tags or {})
        self.telemetry.increment("metrics_ingested")
        asyncio.create_task(self._check_alerts(name, value))
        return metric

    async def _check_alerts(self, metric_name: str, value: float):
        rules = self.alerts.list_rules()
        for rule in rules:
            if rule.get("metric") == metric_name and value > rule.get("threshold", float("inf")):
                self.alerts.fire(rule.get("id"))

    async def get_dashboard(self, org_id: str, dashboard_id: str):
        return self.dashboards.get(dashboard_id)

    async def health_check(self) -> dict:
        return self.health()


svc = ObservabilityService()
registry.register(svc)
