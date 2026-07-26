"""Observation Engine — monitor repos, workers, APIs, DB, Redis, Neo4j, Qdrant, Docker, K8s, AI."""
import json, uuid, os, logging, time
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, Any

logger = logging.getLogger(__name__)

@dataclass
class Observation:
    id: str; org_id: str; target: str; metric: str; value: Any; status: str = "healthy"
    timestamp: float = field(default_factory=time.time); metadata: dict = field(default_factory=dict)

@dataclass
class ObservationTarget:
    name: str; target_type: str; endpoint: str = ""; interval_seconds: int = 60
    last_observed: float = 0.0; health: str = "unknown"; is_active: bool = True

class ObservationEngine:
    def __init__(self, storage_dir: str = "aiops_data/observations"):
        self.storage_dir = storage_dir; self._observations: dict[str, Observation] = {}
        self._targets: dict[str, ObservationTarget] = {}
        self._telemetry: dict = {"observations": 0, "targets": 0}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _obs_path(self) -> str: return os.path.join(self.storage_dir, "observations.json")
    def _tgt_path(self) -> str: return os.path.join(self.storage_dir, "targets.json")

    def _load(self) -> None:
        for path, store, cls in [(self._obs_path(), self._observations, Observation), (self._tgt_path(), self._targets, ObservationTarget)]:
            if os.path.exists(path):
                try:
                    with open(path, "r") as f: data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls(**v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Load error: %s", e)
        self._telemetry["observations"] = len(self._observations)
        self._telemetry["targets"] = len(self._targets)

    def _save(self) -> None:
        try:
            with open(self._obs_path(), "w") as f:
                json.dump({k: asdict(v) for k, v in self._observations.items()}, f, indent=2, default=str)
            with open(self._tgt_path(), "w") as f:
                json.dump({k: asdict(v) for k, v in self._targets.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def register_target(self, name: str, target_type: str, endpoint: str = "", interval: int = 60) -> ObservationTarget:
        t = ObservationTarget(name=name, target_type=target_type, endpoint=endpoint, interval_seconds=interval)
        self._targets[name] = t; self._telemetry["targets"] += 1; self._save(); return t

    def record(self, org_id: str, target: str, metric: str, value: Any, status: str = "healthy") -> Observation:
        obs = Observation(id=str(uuid.uuid4()), org_id=org_id, target=target, metric=metric, value=value, status=status)
        self._observations[obs.id] = obs; self._telemetry["observations"] += 1
        if target in self._targets: self._targets[target].last_observed = time.time(); self._targets[target].health = status
        self._save(); return obs

    def get_recent(self, org_id: str, target: str = "", limit: int = 100) -> list[Observation]:
        results = [o for o in self._observations.values() if o.org_id == org_id]
        if target: results = [o for o in results if o.target == target]
        return sorted(results, key=lambda o: o.timestamp, reverse=True)[:limit]

    def get_telemetry(self) -> dict: return dict(self._telemetry)
