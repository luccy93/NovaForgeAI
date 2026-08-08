"""Resource Optimization — CPU, memory, GPU, network, storage, DB, cache, container optimization."""
import json, uuid, os, logging, time
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class ResourceMetrics:
    id: str; org_id: str; resource_type: str; name: str; usage_percent: float = 0.0
    limit: float = 0.0; current: float = 0.0; recommendation: str = ""
    collected_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "ResourceMetrics": return cls(**data)

class ResourceOptimization:
    def __init__(self, storage_dir: str = "aiops_data/resources"):
        self.storage_dir = storage_dir; self._metrics: dict[str, ResourceMetrics] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "metrics.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._metrics[k] = ResourceMetrics.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._metrics.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def record(self, org_id: str, resource_type: str, name: str, usage: float, limit: float = 0.0, current: float = 0.0) -> ResourceMetrics:
        rec = usage / limit if limit > 0 else usage
        recommendation = "scale up" if rec > 0.8 else "scale down" if rec < 0.2 else "optimal"
        m = ResourceMetrics(id=str(uuid.uuid4()), org_id=org_id, resource_type=resource_type, name=name, usage_percent=rec * 100, limit=limit, current=current, recommendation=recommendation)
        self._metrics[m.id] = m; self._save(); return m

    def get_recommendations(self, org_id: str) -> list[ResourceMetrics]:
        return [m for m in self._metrics.values() if m.org_id == org_id and m.recommendation != "optimal"]
