"""Health Engine — repository, system, API, DB, infra, worker, search, embedding, LLM health."""
import json, uuid, os, logging, time
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class HealthStatus:
    id: str; org_id: str; component: str; status: str = "unknown"
    score: float = 0.0; latency_ms: float = 0.0
    last_checked: float = field(default_factory=time.time)
    details: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "HealthStatus": return cls(**data)

class HealthEngine:
    def __init__(self, storage_dir: str = "aiops_data/health"):
        self.storage_dir = storage_dir; self._health: dict[str, HealthStatus] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "health.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._health[k] = HealthStatus.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._health.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def check(self, org_id: str, component: str, status: str = "healthy", score: float = 1.0, latency: float = 0.0) -> HealthStatus:
        h = HealthStatus(id=str(uuid.uuid4()), org_id=org_id, component=component, status=status, score=score, latency_ms=latency)
        self._health[h.id] = h; self._save(); return h

    def get_component_health(self, org_id: str, component: str) -> list[HealthStatus]:
        return sorted([h for h in self._health.values() if h.org_id == org_id and h.component == component], key=lambda h: h.last_checked, reverse=True)

    def get_overall(self, org_id: str) -> dict:
        components = [h for h in self._health.values() if h.org_id == org_id]
        if not components: return {"org_id": org_id, "overall_health": "unknown"}
        latest = {}
        for h in components:
            if h.component not in latest or h.last_checked > latest[h.component].last_checked: latest[h.component] = h
        scores = [v.score for v in latest.values()]
        return {"org_id": org_id, "overall_health": "healthy" if all(s >= 0.7 for s in scores) else "degraded", "avg_score": sum(scores) / len(scores) if scores else 0}

    def get_telemetry(self) -> dict: return {"checks": len(self._health)}
