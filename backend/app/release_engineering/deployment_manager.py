"""Deployment Manager — strategies, rollback, canary, blue-green, progressive delivery."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)

class DeploymentStrategy(Enum):
    IMMEDIATE = "immediate"; ROLLING = "rolling"; BLUE_GREEN = "blue_green"
    CANARY = "canary"; REVERSED_CANARY = "reversed_canary"; RAMPED = "ramped"

class DeploymentStatus(Enum):
    PENDING = "pending"; RUNNING = "running"; SUCCEEDED = "succeeded"
    FAILED = "failed"; ROLLING_BACK = "rolling_back"; ROLLED_BACK = "rolled_back"

@dataclass
class Deployment:
    id: str; org_id: str; release_id: str; environment: str
    strategy: DeploymentStrategy = DeploymentStrategy.ROLLING
    status: DeploymentStatus = DeploymentStatus.PENDING
    version: str = ""; target_percentage: int = 100
    current_percentage: int = 0; auto_promote: bool = False
    rollback_plan: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    started_at: str = ""; completed_at: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self); d["strategy"] = self.strategy.value; d["status"] = self.status.value; return d

    @classmethod
    def from_dict(cls, data: dict) -> "Deployment":
        data = data.copy(); data["strategy"] = DeploymentStrategy(data.get("strategy", "rolling"))
        data["status"] = DeploymentStatus(data.get("status", "pending"))
        return cls(**data)

class DeploymentManager:
    def __init__(self, storage_dir: str = "release_data/deployments"):
        self.storage_dir = storage_dir; self._deployments: dict[str, Deployment] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "deployments.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r", encoding="utf-8") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._deployments[k] = Deployment.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._deployments.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create(self, org_id: str, release_id: str, environment: str, strategy: DeploymentStrategy = DeploymentStrategy.ROLLING, version: str = "") -> Deployment:
        dep = Deployment(id=str(uuid.uuid4()), org_id=org_id, release_id=release_id, environment=environment, strategy=strategy, version=version)
        self._deployments[dep.id] = dep; self._save(); return dep

    def update_status(self, dep_id: str, status: DeploymentStatus) -> Optional[Deployment]:
        dep = self._deployments.get(dep_id)
        if not dep: return None
        dep.status = status
        if status == DeploymentStatus.RUNNING and not dep.started_at: dep.started_at = datetime.now(timezone.utc).isoformat()
        if status == DeploymentStatus.SUCCEEDED: dep.completed_at = datetime.now(timezone.utc).isoformat()
        self._save(); return dep

    def promote(self, dep_id: str, percentage: int) -> Optional[Deployment]:
        dep = self._deployments.get(dep_id)
        if not dep: return None
        dep.current_percentage = min(percentage, 100)
        if dep.current_percentage >= 100: dep.status = DeploymentStatus.SUCCEEDED
        self._save(); return dep

    def list_by_env(self, org_id: str, environment: str) -> list[Deployment]:
        return sorted([d for d in self._deployments.values() if d.org_id == org_id and d.environment == environment], key=lambda d: d.created_at, reverse=True)
