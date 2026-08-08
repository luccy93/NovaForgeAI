"""Connector SDK — build, test, and deploy custom connectors with plugin framework, auth templates, and protocol adapters."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


class SDKComponentType(Enum):
    AUTH = "auth"
    PROTOCOL = "protocol"
    TRANSFORM = "transform"
    VALIDATOR = "validator"
    CACHE = "cache"
    RATE_LIMITER = "rate_limiter"


@dataclass
class SDKTemplate:
    id: str
    name: str
    component_type: SDKComponentType
    code_template: str = ""
    config_schema: dict = field(default_factory=dict)
    dependencies: list = field(default_factory=list)
    version: str = "1.0.0"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["component_type"] = self.component_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "SDKTemplate":
        data = data.copy()
        data["component_type"] = SDKComponentType(data.get("component_type", "auth"))
        return cls(**data)


@dataclass
class ConnectorExtension:
    id: str
    org_id: str
    name: str
    version: str = "1.0.0"
    components: list = field(default_factory=list)
    config: dict = field(default_factory=dict)
    is_published: bool = False
    install_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "ConnectorExtension": return cls(**data)


class ConnectorSDK:
    def __init__(self, storage_dir: str = "integration_data/sdk"):
        self.storage_dir = storage_dir
        self._templates: dict[str, SDKTemplate] = {}
        self._extensions: dict[str, ConnectorExtension] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _tmpl_path(self) -> str: return os.path.join(self.storage_dir, "templates.json")
    def _ext_path(self) -> str: return os.path.join(self.storage_dir, "extensions.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._tmpl_path(), self._templates, SDKTemplate),
            (self._ext_path(), self._extensions, ConnectorExtension),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Failed to load SDK data: %s", e)

    def _save(self) -> None:
        try:
            with open(self._tmpl_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._templates.items()}, f, indent=2, default=str)
            with open(self._ext_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._extensions.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save SDK data: %s", e)

    def add_template(self, name: str, component_type: SDKComponentType, code_template: str = "", config_schema: dict = None, dependencies: list = None) -> SDKTemplate:
        tmpl = SDKTemplate(id=str(uuid.uuid4()), name=name, component_type=component_type, code_template=code_template, config_schema=config_schema or {}, dependencies=dependencies or [])
        self._templates[tmpl.id] = tmpl
        self._save()
        return tmpl

    def create_extension(self, org_id: str, name: str, components: list = None, config: dict = None) -> ConnectorExtension:
        ext = ConnectorExtension(id=str(uuid.uuid4()), org_id=org_id, name=name, components=components or [], config=config or {})
        self._extensions[ext.id] = ext
        self._save()
        return ext

    def publish_extension(self, ext_id: str) -> bool:
        ext = self._extensions.get(ext_id)
        if not ext: return False
        ext.is_published = True
        ext.version = "1.0.0"
        self._save()
        return True

    def list_templates(self, component_type: Optional[SDKComponentType] = None) -> list[SDKTemplate]:
        results = list(self._templates.values())
        if component_type: results = [t for t in results if t.component_type == component_type]
        return results

    def list_extensions(self, org_id: str = "") -> list[ConnectorExtension]:
        results = list(self._extensions.values())
        if org_id: results = [e for e in results if e.org_id == org_id]
        return results

    def get_telemetry(self) -> dict: return dict(self._telemetry)
