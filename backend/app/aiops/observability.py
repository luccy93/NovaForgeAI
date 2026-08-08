"""AIOps Observability — system health, service health, recovery time, incident frequency, automation success."""
import json, uuid, os, logging, time
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class AIOpsMetrics:
    id: str; org_id: str; period: str; system_health: float = 1.0
    avg_recovery_time_minutes: float = 0.0; incident_frequency: int = 0
    automation_success_rate: float = 0.0; manual_interventions: int = 0
    prediction_accuracy: float = 0.0; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "AIOpsMetrics": return cls(**data)

class AIOpsObservability:
    def __init__(self, storage_dir: str = "aiops_data/observability"):
        self.storage_dir = storage_dir; self._metrics: dict[str, AIOpsMetrics] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "metrics.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._metrics[k] = AIOpsMetrics.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._metrics.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def record(self, org_id: str, metrics: dict) -> AIOpsMetrics:
        period = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H")
        m = AIOpsMetrics(id=str(uuid.uuid4()), org_id=org_id, period=period, **{k: v for k, v in metrics.items() if k in [f.name for f in AIOpsMetrics.__dataclass_fields__]})
        self._metrics[m.id] = m; self._save(); return m

    def get_latest(self, org_id: str) -> Optional[AIOpsMetrics]:
        relevant = [m for m in self._metrics.values() if m.org_id == org_id]
        return sorted(relevant, key=lambda m: m.created_at, reverse=True)[0] if relevant else None

    def get_telemetry(self) -> dict: return {"metric_points": len(self._metrics)}
