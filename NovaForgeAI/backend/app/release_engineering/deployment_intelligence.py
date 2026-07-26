"""Deployment Intelligence — metrics, analysis, scoring, risk, optimization."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class DeploymentAnalytic:
    id: str; org_id: str; deployment_id: str
    success_rate: float = 0.0; avg_duration_seconds: float = 0.0
    rollback_rate: float = 0.0; failure_count: int = 0; total_count: int = 0
    risk_score: float = 0.0; health_score: float = 1.0
    insights: list = field(default_factory=list); recommendations: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "DeploymentAnalytic": return cls(**data)

class DeploymentIntelligence:
    def __init__(self, storage_dir: str = "release_data/intelligence"):
        self.storage_dir = storage_dir; self._analytics: dict[str, DeploymentAnalytic] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "analytics.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r", encoding="utf-8") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._analytics[k] = DeploymentAnalytic.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._analytics.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def record(self, org_id: str, deployment_id: str, success: bool, duration: float = 0.0) -> DeploymentAnalytic:
        existing = next((a for a in self._analytics.values() if a.org_id == org_id and a.deployment_id == deployment_id), None)
        if existing: return existing
        a = DeploymentAnalytic(id=str(uuid.uuid4()), org_id=org_id, deployment_id=deployment_id, total_count=1, success_rate=1.0 if success else 0.0, avg_duration_seconds=duration, failure_count=0 if success else 1)
        self._analytics[a.id] = a; self._save(); return a

    def analyze(self, org_id: str) -> dict:
        deps = [a for a in self._analytics.values() if a.org_id == org_id]
        total = len(deps)
        if total == 0: return {"total": 0}
        success = sum(1 for d in deps if d.success_rate > 0.5)
        return {"total": total, "successful": success, "failed": total - success, "avg_success_rate": sum(d.success_rate for d in deps) / total if total else 0}

    def get_telemetry(self) -> dict: return {"total_analytics": len(self._analytics)}
