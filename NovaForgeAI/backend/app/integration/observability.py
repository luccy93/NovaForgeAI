"""Integration Observability — connector health, sync latency, webhook success, retry count, API usage, connector failures, queue length."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class IntegrationMetric(Enum):
    CONNECTOR_HEALTH = "connector_health"
    SYNC_LATENCY = "sync_latency"
    WEBHOOK_SUCCESS = "webhook_success"
    RETRY_COUNT = "retry_count"
    API_USAGE = "api_usage"
    CONNECTOR_FAILURES = "connector_failures"
    QUEUE_LENGTH = "queue_length"
    EVENTS_PROCESSED = "events_processed"


@dataclass
class IntegrationMetricSnapshot:
    id: str
    org_id: str
    metric: IntegrationMetric
    value: float
    tags: dict = field(default_factory=dict)
    recorded_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["metric"] = self.metric.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "IntegrationMetricSnapshot":
        data = data.copy()
        data["metric"] = IntegrationMetric(data.get("metric", "connector_health"))
        return cls(**data)


class IntegrationObservability:
    def __init__(self, storage_dir: str = "integration_data/observability"):
        self.storage_dir = storage_dir
        self._snapshots: dict[str, IntegrationMetricSnapshot] = {}
        self._alerts: list = []
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _snap_path(self) -> str: return os.path.join(self.storage_dir, "snapshots.json")
    def _alert_path(self) -> str: return os.path.join(self.storage_dir, "alerts.json")

    def _load(self) -> None:
        for path, store in [(self._snap_path(), self._snapshots), (self._alert_path(), None)]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if store is not None:
                        for k, v in data.items():
                            try: store[k] = IntegrationMetricSnapshot.from_dict(v)
                            except Exception as e: logger.warning("Skipping %s: %s", k, e)
                    else:
                        self._alerts = data
                except Exception as e: logger.error("Failed to load integration observability: %s", e)

    def _save(self) -> None:
        try:
            with open(self._snap_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._snapshots.items()}, f, indent=2, default=str)
            with open(self._alert_path(), "w", encoding="utf-8") as f:
                json.dump(self._alerts, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save integration observability: %s", e)

    def record_metric(self, org_id: str, metric: IntegrationMetric, value: float, tags: dict = None) -> IntegrationMetricSnapshot:
        snap = IntegrationMetricSnapshot(id=str(uuid.uuid4()), org_id=org_id, metric=metric, value=value, tags=tags or {})
        self._snapshots[snap.id] = snap
        self._save()
        return snap

    def get_history(self, metric: IntegrationMetric, org_id: str = "", limit: int = 100) -> list[IntegrationMetricSnapshot]:
        results = [s for s in self._snapshots.values() if s.metric == metric]
        if org_id: results = [s for s in results if s.org_id == org_id]
        return sorted(results, key=lambda s: s.recorded_at, reverse=True)[:limit]

    def get_dashboard(self, org_id: str) -> dict:
        dashboard = {}
        for m in IntegrationMetric:
            history = self.get_history(m, org_id, limit=1)
            if history: dashboard[m.value] = history[0].value
        return dashboard

    def alert(self, message: str, severity: str = "warning", metric: str = "") -> dict:
        alert = {"id": str(uuid.uuid4()), "message": message, "severity": severity, "metric": metric, "created_at": datetime.now(timezone.utc).isoformat()}
        self._alerts.append(alert)
        self._save()
        return alert

    def get_alerts(self, severity: str = "") -> list[dict]:
        if severity: return [a for a in self._alerts if a.get("severity") == severity]
        return self._alerts

    def get_telemetry(self) -> dict: return dict(self._telemetry)
