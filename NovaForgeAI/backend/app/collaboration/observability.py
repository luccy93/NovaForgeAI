"""Collaboration Observability — track workspace usage, team activity, session duration, collaboration events, knowledge growth, search usage, conversation metrics."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class CollabMetric(Enum):
    WORKSPACE_USAGE = "workspace_usage"
    TEAM_ACTIVITY = "team_activity"
    SESSION_DURATION = "session_duration"
    COLLABORATION_EVENTS = "collaboration_events"
    KNOWLEDGE_GROWTH = "knowledge_growth"
    SEARCH_USAGE = "search_usage"
    CONVERSATION_METRICS = "conversation_metrics"
    REVIEW_ACTIVITY = "review_activity"
    MEETING_ACTIVITY = "meeting_activity"
    NOTIFICATION_VOLUME = "notification_volume"


@dataclass
class CollabMetricSnapshot:
    id: str
    org_id: str
    metric: CollabMetric
    value: float
    unit: str = ""
    tags: dict = field(default_factory=dict)
    recorded_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["metric"] = self.metric.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "CollabMetricSnapshot":
        data = data.copy()
        data["metric"] = CollabMetric(data.get("metric", "workspace_usage"))
        return cls(**data)


@dataclass
class CollabDashboard:
    current: dict = field(default_factory=dict)
    trends: dict = field(default_factory=dict)
    alerts: list = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)


class CollabObservability:
    def __init__(self, storage_dir: str = "collab_data/observability"):
        self.storage_dir = storage_dir
        self._snapshots: dict[str, CollabMetricSnapshot] = {}
        self._alerts: list = []
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _snapshots_path(self) -> str: return os.path.join(self.storage_dir, "snapshots.json")
    def _alerts_path(self) -> str: return os.path.join(self.storage_dir, "alerts.json")

    def _load(self) -> None:
        for path, store in [(self._snapshots_path(), self._snapshots), (self._alerts_path(), None)]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if store is not None:
                        for k, v in data.items():
                            try: store[k] = CollabMetricSnapshot.from_dict(v)
                            except Exception as e: logger.warning("Skipping %s: %s", k, e)
                    else:
                        self._alerts = data
                except Exception as e: logger.error("Failed to load collab observability: %s", e)

    def _save(self) -> None:
        try:
            with open(self._snapshots_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._snapshots.items()}, f, indent=2, default=str)
            with open(self._alerts_path(), "w", encoding="utf-8") as f:
                json.dump(self._alerts, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save collab observability: %s", e)

    def record_metric(self, org_id: str, metric: CollabMetric, value: float, unit: str = "", tags: dict = None) -> CollabMetricSnapshot:
        snap = CollabMetricSnapshot(id=str(uuid.uuid4()), org_id=org_id, metric=metric, value=value, unit=unit, tags=tags or {})
        self._snapshots[snap.id] = snap
        self._save()
        return snap

    def get_metric_history(self, metric: CollabMetric, org_id: str = "", limit: int = 100) -> list[CollabMetricSnapshot]:
        results = [s for s in self._snapshots.values() if s.metric == metric]
        if org_id: results = [s for s in results if s.org_id == org_id]
        return sorted(results, key=lambda s: s.recorded_at, reverse=True)[:limit]

    def get_dashboard(self, org_id: str) -> CollabDashboard:
        current, trends = {}, {}
        for m in CollabMetric:
            history = self.get_metric_history(m, org_id, limit=50)
            if history:
                current[m.value] = history[0].value
                if len(history) > 1:
                    values = [s.value for s in reversed(history)]
                    trends[m.value] = {"current": values[-1], "avg": round(sum(values) / len(values), 2), "min": min(values), "max": max(values), "direction": "up" if values[-1] > values[0] else "down"}
        return CollabDashboard(current=current, trends=trends, alerts=self._alerts)

    def add_alert(self, message: str, severity: str = "info", metric: str = "") -> dict:
        alert = {"id": str(uuid.uuid4()), "message": message, "severity": severity, "metric": metric, "created_at": datetime.now(timezone.utc).isoformat()}
        self._alerts.append(alert)
        self._save()
        return alert

    def get_alerts(self, severity: str = "") -> list[dict]:
        if severity: return [a for a in self._alerts if a.get("severity") == severity]
        return self._alerts

    def get_telemetry(self) -> dict: return dict(self._telemetry)
