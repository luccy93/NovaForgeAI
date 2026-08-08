"""Environment Manager — environments, configurations, secrets, parity tracking."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class Environment:
    id: str; org_id: str; name: str; type: str  # development, staging, production
    description: str = ""; is_protected: bool = False
    variables: dict = field(default_factory=dict); secrets: list = field(default_factory=list)
    approval_required: bool = False; auto_deploy: bool = False
    config: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "Environment": return cls(**data)

class EnvironmentManager:
    def __init__(self, storage_dir: str = "release_data/environments"):
        self.storage_dir = storage_dir; self._environments: dict[str, Environment] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "environments.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r", encoding="utf-8") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._environments[k] = Environment.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._environments.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create(self, org_id: str, name: str, env_type: str, is_protected: bool = False) -> Environment:
        env = Environment(id=str(uuid.uuid4()), org_id=org_id, name=name, type=env_type, is_protected=is_protected)
        self._environments[env.id] = env; self._save(); return env

    def get(self, env_id: str) -> Optional[Environment]: return self._environments.get(env_id)

    def list_by_org(self, org_id: str) -> list[Environment]:
        return sorted([e for e in self._environments.values() if e.org_id == org_id], key=lambda e: e.name)

    def set_variable(self, env_id: str, key: str, value: str) -> bool:
        env = self._environments.get(env_id)
        if not env: return False
        env.variables[key] = value; env.updated_at = datetime.now(timezone.utc).isoformat(); self._save(); return True

    def get_telemetry(self) -> dict: return dict(self._telemetry)
