"""Observability — metrics, monitoring, alerts, dashboards, tracing for release pipelines."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class ReleaseMetrics:
    id: str; org_id: str; pipeline_id: str = ""; deployment_id: str = ""
    total_releases: int = 0; successful_releases: int = 0; failed_releases: int = 0
    avg_deploy_duration: float = 0.0; rollback_count: int = 0; pass_rate: float = 0.0
    metrics: dict = field(default_factory=dict); tags: dict = field(default_factory=dict)
    collected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "ReleaseMetrics": return cls(**data)

@dataclass
class Alert:
    id: str; org_id: str; severity: str; title: str; message: str = ""
    resource_type: str = ""; resource_id: str = ""
    acknowledged: bool = False; acknowledged_by: str = ""
    resolved: bool = False; resolved_at: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "Alert": return cls(**data)

class Observability:
    def __init__(self, storage_dir: str = "release_data/observability"):
        self.storage_dir = storage_dir; self._metrics: dict[str, ReleaseMetrics] = {}
        self._alerts: dict[str, Alert] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _met_path(self) -> str: return os.path.join(self.storage_dir, "metrics.json")
    def _alert_path(self) -> str: return os.path.join(self.storage_dir, "alerts.json")

    def _load(self) -> None:
        for path, store, cls in [(self._met_path(), self._metrics, ReleaseMetrics), (self._alert_path(), self._alerts, Alert)]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f: data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._met_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._metrics.items()}, f, indent=2, default=str)
            with open(self._alert_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._alerts.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def record_metrics(self, org_id: str, pipeline_id: str = "", deployment_id: str = "") -> ReleaseMetrics:
        m = ReleaseMetrics(id=str(uuid.uuid4()), org_id=org_id, pipeline_id=pipeline_id, deployment_id=deployment_id)
        self._metrics[m.id] = m; self._save(); return m

    def create_alert(self, org_id: str, severity: str, title: str, message: str = "", resource_type: str = "", resource_id: str = "") -> Alert:
        a = Alert(id=str(uuid.uuid4()), org_id=org_id, severity=severity, title=title, message=message, resource_type=resource_type, resource_id=resource_id)
        self._alerts[a.id] = a; self._save(); return a

    def acknowledge_alert(self, alert_id: str, user_id: str) -> Optional[Alert]:
        a = self._alerts.get(alert_id)
        if not a: return None
        a.acknowledged = True; a.acknowledged_by = user_id; self._save(); return a

    def get_alert(self, alert_id: str) -> Optional[Alert]: return self._alerts.get(alert_id)
