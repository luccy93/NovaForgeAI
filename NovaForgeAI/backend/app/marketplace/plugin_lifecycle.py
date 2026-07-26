"""Plugin Lifecycle — install, enable, disable, update, pause, deprecate, archive, remove + SDK + security."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class PluginInstance:
    id: str; plugin_id: str; org_id: str; name: str; status: str = "installed"
    config: dict = field(default_factory=dict); version: str = "1.0.0"
    installed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class PluginLifecycle:
    def __init__(self, storage_dir: str = "marketplace_data/lifecycle"):
        self.storage_dir = storage_dir; self._instances: dict[str, PluginInstance] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "instances.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._instances[k] = PluginInstance(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try: with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._instances.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def install(self, plugin_id: str, org_id: str, name: str) -> PluginInstance:
        pi = PluginInstance(id=str(uuid.uuid4()), plugin_id=plugin_id, org_id=org_id, name=name)
        self._instances[pi.id] = pi; self._save(); return pi

    def update_status(self, instance_id: str, status: str) -> Optional[PluginInstance]:
        pi = self._instances.get(instance_id)
        if not pi: return None
        pi.status = status; pi.updated_at = datetime.now(timezone.utc).isoformat(); self._save(); return pi

    def get_by_org(self, org_id: str) -> list[PluginInstance]: return [p for p in self._instances.values() if p.org_id == org_id]

    def get_telemetry(self) -> dict: return {"instances": len(self._instances)}

class PluginSDK:
    """Plugin SDK metadata and validation utilities."""
    @staticmethod
    def validate_permissions(permissions: list, required: list) -> bool:
        return all(p in permissions for p in required)

    @staticmethod
    def get_sdk_version() -> str: return "1.0.0"

    @staticmethod
    def get_supported_hooks() -> list:
        return ["on_install", "on_enable", "on_disable", "on_update", "on_uninstall", "health_check", "on_config_change"]

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class PromptPack:
    id: str; org_id: str; name: str; description: str = ""
    prompts: list = field(default_factory=list); version: str = "1.0.0"
    author: str = ""; rating: float = 0.0; downloads: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class PromptMarketplace:
    def __init__(self, storage_dir: str = "marketplace_data/prompts"):
        self.storage_dir = storage_dir; self._packs: dict[str, PromptPack] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "packs.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._packs[k] = PromptPack(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try: with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._packs.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def publish(self, org_id: str, name: str, prompts: list = None) -> PromptPack:
        p = PromptPack(id=str(uuid.uuid4()), org_id=org_id, name=name, prompts=prompts or [])
        self._packs[p.id] = p; self._save(); return p

    def get_telemetry(self) -> dict: return {"packs": len(self._packs)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class MarketplaceAgent:
    id: str; org_id: str; name: str; agent_type: str; description: str = ""
    capabilities: list = field(default_factory=list); price: float = 0.0
    rating: float = 0.0; downloads: int = 0; is_verified: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class AgentMarketplace:
    def __init__(self, storage_dir: str = "marketplace_data/agents"):
        self.storage_dir = storage_dir; self._agents: dict[str, MarketplaceAgent] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "agents.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._agents[k] = MarketplaceAgent(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try: with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._agents.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def publish(self, org_id: str, name: str, agent_type: str, capabilities: list = None, price: float = 0.0) -> MarketplaceAgent:
        a = MarketplaceAgent(id=str(uuid.uuid4()), org_id=org_id, name=name, agent_type=agent_type, capabilities=capabilities or [], price=price)
        self._agents[a.id] = a; self._save(); return a

    def get_telemetry(self) -> dict: return {"agents": len(self._agents)}
