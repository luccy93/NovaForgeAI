"""Shared Agents — team/org/repo agents with shared memory, context, knowledge, and agent collaboration."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class AgentScope(Enum):
    TEAM = "team"
    ORGANIZATION = "organization"
    REPOSITORY = "repository"
    WORKSPACE = "workspace"


@dataclass
class SharedAgent:
    id: str
    org_id: str
    name: str
    agent_type: str
    scope: AgentScope = AgentScope.TEAM
    description: str = ""
    config: dict = field(default_factory=dict)
    shared_memory: dict = field(default_factory=dict)
    shared_context: dict = field(default_factory=dict)
    knowledge_ids: list = field(default_factory=list)
    owners: list = field(default_factory=list)
    users: list = field(default_factory=list)
    is_active: bool = True
    usage_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["scope"] = self.scope.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "SharedAgent":
        data = data.copy()
        data["scope"] = AgentScope(data.get("scope", "team"))
        return cls(**data)


class SharedAgents:
    def __init__(self, storage_dir: str = "collab_data/agents"):
        self.storage_dir = storage_dir
        self._agents: dict[str, SharedAgent] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "agents.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._agents[k] = SharedAgent.from_dict(v)
                    except Exception as e: logger.warning("Skipping agent %s: %s", k, e)
            except Exception as e: logger.error("Failed to load shared agents: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._agents.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save shared agents: %s", e)

    def register_agent(self, org_id: str, name: str, agent_type: str, scope: AgentScope = AgentScope.TEAM, description: str = "", config: dict = None, owners: list = None) -> SharedAgent:
        agent = SharedAgent(id=str(uuid.uuid4()), org_id=org_id, name=name, agent_type=agent_type, scope=scope, description=description, config=config or {}, owners=owners or [])
        self._agents[agent.id] = agent
        self._save()
        return agent

    def get_agent(self, agent_id: str) -> Optional[SharedAgent]: return self._agents.get(agent_id)

    def update_agent(self, agent_id: str, updates: dict) -> Optional[SharedAgent]:
        agent = self._agents.get(agent_id)
        if not agent: return None
        for k, v in updates.items():
            if hasattr(agent, k) and k not in ("id", "created_at"):
                if k == "scope": setattr(agent, k, AgentScope(v) if isinstance(v, str) else v)
                else: setattr(agent, k, v)
        agent.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return agent

    def update_shared_memory(self, agent_id: str, memory_updates: dict) -> bool:
        agent = self._agents.get(agent_id)
        if not agent: return False
        agent.shared_memory.update(memory_updates)
        agent.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return True

    def update_shared_context(self, agent_id: str, context_updates: dict) -> bool:
        agent = self._agents.get(agent_id)
        if not agent: return False
        agent.shared_context.update(context_updates)
        agent.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return True

    def add_user(self, agent_id: str, user_id: str) -> bool:
        agent = self._agents.get(agent_id)
        if not agent: return False
        if user_id not in agent.users: agent.users.append(user_id)
        self._save()
        return True

    def remove_user(self, agent_id: str, user_id: str) -> bool:
        agent = self._agents.get(agent_id)
        if not agent: return False
        agent.users = [u for u in agent.users if u != user_id]
        self._save()
        return True

    def list_agents(self, org_id: str = "", scope: Optional[AgentScope] = None) -> list[SharedAgent]:
        results = [a for a in self._agents.values() if a.is_active]
        if org_id: results = [a for a in results if a.org_id == org_id]
        if scope: results = [a for a in results if a.scope == scope]
        return results

    def record_usage(self, agent_id: str) -> bool:
        agent = self._agents.get(agent_id)
        if not agent: return False
        agent.usage_count += 1
        self._save()
        return True

    def get_telemetry(self) -> dict: return dict(self._telemetry)
