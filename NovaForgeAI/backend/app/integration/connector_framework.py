"""Connector Framework — plugin framework for authentication, OAuth, API keys, webhooks, polling, GraphQL, REST, gRPC, versioning."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, Callable
from enum import Enum

logger = logging.getLogger(__name__)


class ConnectorAuthType(Enum):
    NONE = "none"
    API_KEY = "api_key"
    OAUTH2 = "oauth2"
    BASIC = "basic"
    JWT = "jwt"
    CERTIFICATE = "certificate"
    CUSTOM = "custom"


class ConnectorProtocol(Enum):
    REST = "rest"
    GRAPHQL = "graphql"
    GRPC = "grpc"
    WEBSOCKET = "websocket"
    WEBHOOK = "webhook"
    POLLING = "polling"
    CUSTOM = "custom"


class ConnectorStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    RATE_LIMITED = "rate_limited"


@dataclass
class ConnectorDefinition:
    id: str
    name: str
    provider: str
    version: str = "1.0.0"
    auth_type: ConnectorAuthType = ConnectorAuthType.API_KEY
    protocol: ConnectorProtocol = ConnectorProtocol.REST
    base_url: str = ""
    description: str = ""
    capabilities: list = field(default_factory=list)
    config_schema: dict = field(default_factory=dict)
    status: ConnectorStatus = ConnectorStatus.ACTIVE
    rate_limit: int = 100
    retry_count: int = 3
    timeout_seconds: int = 30
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["auth_type"] = self.auth_type.value
        d["protocol"] = self.protocol.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ConnectorDefinition":
        data = data.copy()
        data["auth_type"] = ConnectorAuthType(data.get("auth_type", "api_key"))
        data["protocol"] = ConnectorProtocol(data.get("protocol", "rest"))
        data["status"] = ConnectorStatus(data.get("status", "active"))
        return cls(**data)


@dataclass
class ConnectorInstance:
    id: str
    def_id: str
    org_id: str
    name: str
    config: dict = field(default_factory=dict)
    credentials: dict = field(default_factory=dict)
    status: ConnectorStatus = ConnectorStatus.ACTIVE
    last_sync: str = ""
    error_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["credentials"] = {"encrypted": True} if self.credentials else {}
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ConnectorInstance":
        data = data.copy()
        data["status"] = ConnectorStatus(data.get("status", "active"))
        return cls(**data)


class ConnectorFramework:
    def __init__(self, storage_dir: str = "integration_data/framework"):
        self.storage_dir = storage_dir
        self._definitions: dict[str, ConnectorDefinition] = {}
        self._instances: dict[str, ConnectorInstance] = {}
        self._handlers: dict[str, Callable] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _defs_path(self) -> str: return os.path.join(self.storage_dir, "definitions.json")
    def _inst_path(self) -> str: return os.path.join(self.storage_dir, "instances.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._defs_path(), self._definitions, ConnectorDefinition),
            (self._inst_path(), self._instances, ConnectorInstance),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Failed to load connector data: %s", e)

    def _save(self) -> None:
        try:
            with open(self._defs_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._definitions.items()}, f, indent=2, default=str)
            with open(self._inst_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._instances.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save connector data: %s", e)

    def register_definition(self, name: str, provider: str, auth_type: ConnectorAuthType, protocol: ConnectorProtocol, base_url: str = "", capabilities: list = None, config_schema: dict = None) -> ConnectorDefinition:
        defn = ConnectorDefinition(id=str(uuid.uuid4()), name=name, provider=provider, auth_type=auth_type, protocol=protocol, base_url=base_url, capabilities=capabilities or [], config_schema=config_schema or {})
        self._definitions[defn.id] = defn
        self._save()
        return defn

    def create_instance(self, def_id: str, org_id: str, name: str, config: dict = None, credentials: dict = None) -> Optional[ConnectorInstance]:
        if def_id not in self._definitions: return None
        inst = ConnectorInstance(id=str(uuid.uuid4()), def_id=def_id, org_id=org_id, name=name, config=config or {}, credentials=credentials or {})
        self._instances[inst.id] = inst
        self._save()
        return inst

    def get_instance(self, inst_id: str) -> Optional[ConnectorInstance]: return self._instances.get(inst_id)

    def update_instance(self, inst_id: str, updates: dict) -> Optional[ConnectorInstance]:
        inst = self._instances.get(inst_id)
        if not inst: return None
        for k, v in updates.items():
            if hasattr(inst, k) and k not in ("id", "created_at"):
                if k == "status": setattr(inst, k, ConnectorStatus(v) if isinstance(v, str) else v)
                else: setattr(inst, k, v)
        self._save()
        return inst

    def register_handler(self, connector_name: str, handler: Callable) -> None:
        self._handlers[connector_name] = handler

    def execute(self, inst_id: str, action: str, params: dict = None) -> dict:
        inst = self._instances.get(inst_id)
        if not inst: return {"error": "Instance not found"}
        defn = self._definitions.get(inst.def_id)
        if not defn: return {"error": "Definition not found"}
        handler = self._handlers.get(defn.name)
        if handler:
            try:
                result = handler(inst, action, params or {})
                inst.last_sync = datetime.now(timezone.utc).isoformat()
                self._save()
                return result
            except Exception as e:
                inst.error_count += 1
                self._save()
                return {"error": str(e)}
        return {"error": f"No handler for {defn.name}"}

    def list_definitions(self) -> list[ConnectorDefinition]: return list(self._definitions.values())

    def list_instances(self, org_id: str = "") -> list[ConnectorInstance]:
        results = list(self._instances.values())
        if org_id: results = [i for i in results if i.org_id == org_id]
        return results

    def get_telemetry(self) -> dict: return dict(self._telemetry)
