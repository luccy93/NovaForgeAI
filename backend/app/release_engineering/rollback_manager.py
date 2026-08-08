"""Rollback Manager — safe rollbacks, history, automation, recovery plans."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)

class RollbackStatus(Enum):
    PENDING = "pending"; RUNNING = "running"; SUCCEEDED = "succeeded"; FAILED = "failed"

class RollbackType(Enum):
    FULL = "full"; PARTIAL = "partial"; REVERT_COMMIT = "revert_commit"; RESTORE_DB = "restore_db"

@dataclass
class Rollback:
    id: str; org_id: str; deployment_id: str; release_id: str
    rollback_type: RollbackType = RollbackType.FULL
    status: RollbackStatus = RollbackStatus.PENDING
    reason: str = ""; initiated_by: str = ""; auto_detected: bool = False
    steps: list = field(default_factory=list); metrics: dict = field(default_factory=dict)
    started_at: str = ""; completed_at: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self); d["rollback_type"] = self.rollback_type.value; d["status"] = self.status.value; return d

    @classmethod
    def from_dict(cls, data: dict) -> "Rollback":
        data = data.copy(); data["rollback_type"] = RollbackType(data.get("rollback_type", "full"))
        data["status"] = RollbackStatus(data.get("status", "pending"))
        return cls(**data)

class RollbackManager:
    def __init__(self, storage_dir: str = "release_data/rollbacks"):
        self.storage_dir = storage_dir; self._rollbacks: dict[str, Rollback] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "rollbacks.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r", encoding="utf-8") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._rollbacks[k] = Rollback.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._rollbacks.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create(self, org_id: str, deployment_id: str, release_id: str, reason: str = "", initiated_by: str = "", auto_detected: bool = False, rollback_type: RollbackType = RollbackType.FULL) -> Rollback:
        rb = Rollback(id=str(uuid.uuid4()), org_id=org_id, deployment_id=deployment_id, release_id=release_id, reason=reason, initiated_by=initiated_by, auto_detected=auto_detected, rollback_type=rollback_type)
        self._rollbacks[rb.id] = rb; self._save(); return rb

    def update_status(self, rb_id: str, status: RollbackStatus) -> Optional[Rollback]:
        rb = self._rollbacks.get(rb_id)
        if not rb: return None
        rb.status = status
        if status == RollbackStatus.RUNNING and not rb.started_at: rb.started_at = datetime.now(timezone.utc).isoformat()
        if status == RollbackStatus.SUCCEEDED: rb.completed_at = datetime.now(timezone.utc).isoformat()
        self._save(); return rb

    def get_telemetry(self) -> dict: return dict(self._telemetry)
