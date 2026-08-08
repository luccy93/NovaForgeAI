"""Shared Agents — org, repo, team, project agents; collaboration, coordination, ownership."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class SharedAgent:
    id: str; org_id: str; name: str; agent_type: str = "general"  # org, repo, team, project, department
    scope_id: str = ""; owner_id: str = ""; capabilities: list = field(default_factory=list)
    participants: list = field(default_factory=list); config: dict = field(default_factory=dict)
    is_active: bool = True; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "SharedAgent": return cls(**data)

class SharedAgents:
    def __init__(self, storage_dir: str = "rtc_data/agents"):
        self.storage_dir = storage_dir; self._agents: dict[str, SharedAgent] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "agents.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._agents[k] = SharedAgent.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._agents.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def register(self, org_id: str, name: str, agent_type: str = "general", scope_id: str = "", owner_id: str = "") -> SharedAgent:
        a = SharedAgent(id=str(uuid.uuid4()), org_id=org_id, name=name, agent_type=agent_type, scope_id=scope_id, owner_id=owner_id)
        self._agents[a.id] = a; self._save(); return a

    def get_agents_by_scope(self, org_id: str, scope_id: str) -> list[SharedAgent]:
        return [a for a in self._agents.values() if a.org_id == org_id and a.scope_id == scope_id]
