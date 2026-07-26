"""Data Observability module for NovaForge Data Platform & Knowledge Fabric."""
import json, uuid, os, logging, time
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class ObservabilitySignal(Enum):
    PIPELINE_HEALTH = "pipeline_health"
    FRESHNESS = "freshness"
    FAILURES = "failures"
    LATENCY = "latency"
    COMPLETENESS = "completeness"
    SCHEMA_CHANGE = "schema_change"
    STORAGE_GROWTH = "storage_growth"
    THROUGHPUT = "throughput"
    ERROR_RATE = "error_rate"
    DATA_QUALITY = "data_quality"


class ObservabilitySeverity(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ObservabilityStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
    MAINTENANCE = "maintenance"


class ObservabilityAlertType(Enum):
    THRESHOLD = "threshold"
    ANOMALY = "anomaly"
    STALENESS = "staleness"
    SCHEMA_CHANGE = "schema_change"
    FAILURE_SPIKE = "failure_spike"
    LATENCY_SPIKE = "latency_spike"


@dataclass
class HealthCheck:
    id: str
    org_id: str
    target_type: str
    target_id: str
    signal: ObservabilitySignal
    status: ObservabilityStatus
    value: float = 0.0
    threshold: float = 0.0
    message: str = ""
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["signal"] = self.signal.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "HealthCheck":
        data = data.copy()
        data["signal"] = ObservabilitySignal(data.get("signal", "pipeline_health"))
        data["status"] = ObservabilityStatus(data.get("status", "unknown"))
        return cls(**data)


@dataclass
class ObservabilityDashboard:
    id: str
    org_id: str
    name: str
    checks: list = field(default_factory=list)
    overall_status: ObservabilityStatus = ObservabilityStatus.UNKNOWN
    healthy_count: int = 0
    degraded_count: int = 0
    unhealthy_count: int = 0
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["overall_status"] = self.overall_status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ObservabilityDashboard":
        data = data.copy()
        data["overall_status"] = ObservabilityStatus(data.get("overall_status", "unknown"))
        return cls(**data)


@dataclass
class ObservabilityAlert:
    id: str
    org_id: str
    alert_type: ObservabilityAlertType
    signal: ObservabilitySignal
    target_type: str = ""
    target_id: str = ""
    severity: ObservabilitySeverity = ObservabilitySeverity.MEDIUM
    title: str = ""
    message: str = ""
    current_value: float = 0.0
    threshold: float = 0.0
    status: str = "open"
    triggered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    acknowledged_at: str = ""
    resolved_at: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["alert_type"] = self.alert_type.value
        d["signal"] = self.signal.value
        d["severity"] = self.severity.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ObservabilityAlert":
        data = data.copy()
        data["alert_type"] = ObservabilityAlertType(data.get("alert_type", "threshold"))
        data["signal"] = ObservabilitySignal(data.get("signal", "pipeline_health"))
        data["severity"] = ObservabilitySeverity(data.get("severity", "medium"))
        return cls(**data)


@dataclass
class ObservabilityReport:
    id: str
    org_id: str
    period_start: str = ""
    period_end: str = ""
    total_checks: int = 0
    healthy_pct: float = 0.0
    degraded_pct: float = 0.0
    unhealthy_pct: float = 0.0
    alerts_triggered: int = 0
    alerts_resolved: int = 0
    avg_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    storage_growth_pct: float = 0.0
    schema_changes_detected: int = 0
    recommendations: list = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ObservabilityReport":
        return cls(**data)


class DataObservability:
    def __init__(self, storage_dir: str = "data_observability_data"):
        self.storage_dir = storage_dir
        self._health_checks: dict[str, HealthCheck] = {}
        self._dashboards: dict[str, ObservabilityDashboard] = {}
        self._alerts: dict[str, ObservabilityAlert] = {}
        self._reports: dict[str, ObservabilityReport] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _health_path(self) -> str: return os.path.join(self.storage_dir, "health_checks.json")
    def _dashboards_path(self) -> str: return os.path.join(self.storage_dir, "dashboards.json")
    def _alerts_path(self) -> str: return os.path.join(self.storage_dir, "alerts.json")
    def _reports_path(self) -> str: return os.path.join(self.storage_dir, "reports.json")

    def _save(self) -> None:
        try:
            with open(self._health_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._health_checks.items()}, f, indent=2, default=str)
            with open(self._dashboards_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._dashboards.items()}, f, indent=2, default=str)
            with open(self._alerts_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._alerts.items()}, f, indent=2, default=str)
            with open(self._reports_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._reports.items()}, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save observability data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            for path, store, cls in [
                (self._health_path(), self._health_checks, HealthCheck),
                (self._dashboards_path(), self._dashboards, ObservabilityDashboard),
                (self._alerts_path(), self._alerts, ObservabilityAlert),
                (self._reports_path(), self._reports, ObservabilityReport),
            ]:
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for k, v in data.items():
                        try:
                            store[k] = cls.from_dict(v)
                        except Exception as e:
                            logger.warning("Skipping malformed entry %s: %s", k, e)
        except Exception as e:
            logger.error("Failed to load observability data: %s", e, exc_info=True)

    def run_health_check(self, check: HealthCheck) -> HealthCheck:
        self._telemetry["run_health_check_calls"] += 1
        # Auto-determine status based on value vs threshold
        if check.signal in (ObservabilitySignal.FRESHNESS, ObservabilitySignal.COMPLETENESS, ObservabilitySignal.DATA_QUALITY):
            check.status = ObservabilityStatus.HEALTHY if check.value >= check.threshold else ObservabilityStatus.UNHEALTHY
        elif check.signal in (ObservabilitySignal.LATENCY, ObservabilitySignal.ERROR_RATE, ObservabilitySignal.STORAGE_GROWTH):
            check.status = ObservabilityStatus.HEALTHY if check.value <= check.threshold else ObservabilityStatus.UNHEALTHY
        if check.status == ObservabilityStatus.UNHEALTHY:
            pct = abs(check.value - check.threshold) / max(check.threshold, 0.01) * 100
            if pct < 20:
                check.status = ObservabilityStatus.DEGRADED
        self._health_checks[check.id] = check
        self._save()
        return check

    def get_health_summary(self, org_id: str, target_type: Optional[str] = None) -> dict:
        checks = [c for c in self._health_checks.values() if c.org_id == org_id]
        if target_type:
            checks = [c for c in checks if c.target_type == target_type]
        by_signal = defaultdict(list)
        for c in checks:
            by_signal[c.signal.value].append(c)
        summary = {}
        for signal, sig_checks in by_signal.items():
            latest = max(sig_checks, key=lambda x: x.checked_at)
            summary[signal] = {"status": latest.status.value, "value": latest.value, "message": latest.message}
        return summary

    def create_dashboard(self, dashboard: ObservabilityDashboard) -> ObservabilityDashboard:
        self._telemetry["create_dashboard_calls"] += 1
        checks = [c for c in self._health_checks.values() if c.org_id == dashboard.org_id]
        dashboard.healthy_count = sum(1 for c in checks if c.status == ObservabilityStatus.HEALTHY)
        dashboard.degraded_count = sum(1 for c in checks if c.status == ObservabilityStatus.DEGRADED)
        dashboard.unhealthy_count = sum(1 for c in checks if c.status == ObservabilityStatus.UNHEALTHY)
        total = dashboard.healthy_count + dashboard.degraded_count + dashboard.unhealthy_count
        if total == 0:
            dashboard.overall_status = ObservabilityStatus.UNKNOWN
        elif dashboard.unhealthy_count > 0:
            dashboard.overall_status = ObservabilityStatus.UNHEALTHY
        elif dashboard.degraded_count > 0:
            dashboard.overall_status = ObservabilityStatus.DEGRADED
        else:
            dashboard.overall_status = ObservabilityStatus.HEALTHY
        dashboard.last_updated = datetime.now(timezone.utc).isoformat()
        self._dashboards[dashboard.id] = dashboard
        self._save()
        return dashboard

    def get_dashboard(self, dashboard_id: str) -> Optional[ObservabilityDashboard]:
        return self._dashboards.get(dashboard_id)

    def create_alert(self, alert: ObservabilityAlert) -> ObservabilityAlert:
        self._telemetry["create_alert_calls"] += 1
        self._alerts[alert.id] = alert
        self._save()
        return alert

    def acknowledge_alert(self, alert_id: str) -> Optional[ObservabilityAlert]:
        alert = self._alerts.get(alert_id)
        if not alert:
            return None
        alert.status = "acknowledged"
        alert.acknowledged_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return alert

    def resolve_alert(self, alert_id: str) -> Optional[ObservabilityAlert]:
        alert = self._alerts.get(alert_id)
        if not alert:
            return None
        alert.status = "resolved"
        alert.resolved_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return alert

    def get_active_alerts(self, org_id: str, severity: Optional[ObservabilitySeverity] = None) -> list[ObservabilityAlert]:
        results = [a for a in self._alerts.values() if a.org_id == org_id and a.status == "open"]
        if severity:
            results = [a for a in results if a.severity == severity]
        return sorted(results, key=lambda a: a.triggered_at, reverse=True)

    def check_freshness(self, target_type: str, target_id: str, last_updated: str, max_age_hours: int = 24) -> HealthCheck:
        try:
            last = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
            age_hours = (datetime.now(timezone.utc) - last).total_seconds() / 3600
        except Exception:
            age_hours = 0
        return self.run_health_check(HealthCheck(
            id=str(uuid.uuid4()), org_id="", target_type=target_type, target_id=target_id,
            signal=ObservabilitySignal.FRESHNESS, value=max_age_hours - age_hours,
            threshold=0, message=f"Last updated {age_hours:.1f}h ago (max {max_age_hours}h)",
        ))

    def detect_schema_change(self, target_type: str, target_id: str, previous_schema: dict, current_schema: dict) -> Optional[ObservabilityAlert]:
        added = [k for k in current_schema if k not in previous_schema]
        removed = [k for k in previous_schema if k not in current_schema]
        modified = [k for k in current_schema if k in previous_schema and previous_schema[k] != current_schema[k]]
        if added or removed or modified:
            return self.create_alert(ObservabilityAlert(
                id=str(uuid.uuid4()), org_id="", alert_type=ObservabilityAlertType.SCHEMA_CHANGE,
                signal=ObservabilitySignal.SCHEMA_CHANGE, target_type=target_type, target_id=target_id,
                severity=ObservabilitySeverity.HIGH, title="Schema change detected",
                message=f"Added: {added}, Removed: {removed}, Modified: {modified}",
            ))
        return None

    def generate_report(self, org_id: str, start_date: str, end_date: str) -> ObservabilityReport:
        self._telemetry["generate_report_calls"] += 1
        checks = [c for c in self._health_checks.values() if c.org_id == org_id]
        alerts = [a for a in self._alerts.values() if a.org_id == org_id]
        total = len(checks)
        healthy = sum(1 for c in checks if c.status == ObservabilityStatus.HEALTHY)
        degraded = sum(1 for c in checks if c.status == ObservabilityStatus.DEGRADED)
        unhealthy = sum(1 for c in checks if c.status == ObservabilityStatus.UNHEALTHY)
        open_alerts = sum(1 for a in alerts if a.status == "open")
        resolved_alerts = sum(1 for a in alerts if a.status == "resolved")
        recs = []
        if unhealthy > 0:
            recs.append(f"{unhealthy} unhealthy checks require immediate attention")
        if degraded > 0:
            recs.append(f"{degraded} degraded checks should be reviewed")
        if open_alerts > 5:
            recs.append(f"Alert backlog of {open_alerts} open alerts needs triage")

        report = ObservabilityReport(
            id=str(uuid.uuid4()), org_id=org_id, period_start=start_date, period_end=end_date,
            total_checks=total, healthy_pct=round(healthy / max(total, 1) * 100, 2),
            degraded_pct=round(degraded / max(total, 1) * 100, 2),
            unhealthy_pct=round(unhealthy / max(total, 1) * 100, 2),
            alerts_triggered=open_alerts, alerts_resolved=resolved_alerts,
            recommendations=recs,
        )
        self._reports[report.id] = report
        self._save()
        return report

    def get_telemetry(self) -> dict:
        return dict(self._telemetry)
