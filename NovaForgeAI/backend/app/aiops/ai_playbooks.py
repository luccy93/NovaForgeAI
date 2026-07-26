"""AI Playbooks — recovery, deployment, security, incident, scaling, database, AI provider playbooks."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class Playbook:
    id: str; org_id: str; name: str; playbook_type: str; description: str = ""
    steps: list = field(default_factory=list); triggers: list = field(default_factory=list)
    is_active: bool = True; version: int = 1; tags: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "Playbook": return cls(**data)

@dataclass
class PlaybookStep:
    id: str; playbook_id: str; order: int; action: str; target: str; params: dict = field(default_factory=dict)
    timeout_seconds: int = 60; is_automated: bool = True

class AIPlaybooks:
    def __init__(self, storage_dir: str = "aiops_data/playbooks"):
        self.storage_dir = storage_dir; self._playbooks: dict[str, Playbook] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "playbooks.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._playbooks[k] = Playbook.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._playbooks.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create(self, org_id: str, name: str, playbook_type: str, steps: list = None) -> Playbook:
        p = Playbook(id=str(uuid.uuid4()), org_id=org_id, name=name, playbook_type=playbook_type, steps=steps or [])
        self._playbooks[p.id] = p; self._save(); return p

    def get_by_type(self, org_id: str, playbook_type: str) -> list[Playbook]:
        return [p for p in self._playbooks.values() if p.org_id == org_id and p.playbook_type == playbook_type]

    def get_telemetry(self) -> dict: return {"playbooks": len(self._playbooks)}
