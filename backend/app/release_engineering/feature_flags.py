"""Feature Flags — toggles, rollout, targeting, experimentation, safe deployment."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)

class FlagStatus(Enum):
    DEVELOPMENT = "development"; TESTING = "testing"; RELEASED = "released"; REMOVED = "removed"

@dataclass
class FeatureFlag:
    id: str; org_id: str; name: str; key: str; description: str = ""
    enabled: bool = False; status: FlagStatus = FlagStatus.DEVELOPMENT
    rollout_percentage: int = 0; targets: dict = field(default_factory=dict)
    conditions: dict = field(default_factory=dict)
    owner_id: str = ""; tags: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def is_active(self, user_context: dict = None) -> bool:
        if not self.enabled: return False
        import random
        return random.randint(1, 100) <= self.rollout_percentage

    def to_dict(self) -> dict:
        d = asdict(self); d["status"] = self.status.value; return d
    @classmethod
    def from_dict(cls, data: dict) -> "FeatureFlag":
        data = data.copy(); data["status"] = FlagStatus(data.get("status", "development")); return cls(**data)

class FeatureFlags:
    def __init__(self, storage_dir: str = "release_data/flags"):
        self.storage_dir = storage_dir; self._flags: dict[str, FeatureFlag] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "flags.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r", encoding="utf-8") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._flags[k] = FeatureFlag.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._flags.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create(self, org_id: str, name: str, key: str, enabled: bool = False, rollout: int = 0) -> FeatureFlag:
        f = FeatureFlag(id=str(uuid.uuid4()), org_id=org_id, name=name, key=key, enabled=enabled, rollout_percentage=rollout)
        self._flags[f.id] = f; self._save(); return f

    def get(self, flag_id: str) -> Optional[FeatureFlag]: return self._flags.get(flag_id)

    def enable(self, flag_id: str) -> Optional[FeatureFlag]:
        f = self._flags.get(flag_id)
        if not f: return None
        f.enabled = True; f.updated_at = datetime.now(timezone.utc).isoformat(); self._save(); return f

    def disable(self, flag_id: str) -> Optional[FeatureFlag]:
        f = self._flags.get(flag_id)
        if not f: return None
        f.enabled = False; f.updated_at = datetime.now(timezone.utc).isoformat(); self._save(); return f

    def set_rollout(self, flag_id: str, percentage: int) -> Optional[FeatureFlag]:
        f = self._flags.get(flag_id)
        if not f: return None
        f.rollout_percentage = min(max(percentage, 0), 100); f.updated_at = datetime.now(timezone.utc).isoformat(); self._save(); return f

    def evaluate(self, org_id: str, key: str, user_context: dict = None) -> bool:
        for f in self._flags.values():
            if f.org_id == org_id and f.key == key: return f.is_active(user_context)
        return False
