"""Extensibility — custom commands, custom shortcuts, workspace extensions, developer scripts, macros, automation rules."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class ExtensionType(Enum):
    COMMAND = "command"
    SHORTCUT = "shortcut"
    SCRIPT = "script"
    MACRO = "macro"
    AUTOMATION_RULE = "automation_rule"
    WORKSPACE_EXTENSION = "workspace_extension"


@dataclass
class Extension:
    id: str
    user_id: str
    org_id: str
    name: str
    extension_type: ExtensionType
    description: str = ""
    code: str = ""
    config: dict = field(default_factory=dict)
    version: str = "1.0.0"
    is_active: bool = True
    usage_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["extension_type"] = self.extension_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Extension":
        data = data.copy()
        data["extension_type"] = ExtensionType(data.get("extension_type", "command"))
        return cls(**data)


class Extensibility:
    def __init__(self, storage_dir: str = "dx_data/extensions"):
        self.storage_dir = storage_dir
        self._extensions: dict[str, Extension] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "extensions.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._extensions[k] = Extension.from_dict(v)
                    except Exception as e: logger.warning("Skipping extension %s: %s", k, e)
            except Exception as e: logger.error("Failed to load extensions: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._extensions.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save extensions: %s", e)

    def install(self, user_id: str, org_id: str, name: str, extension_type: ExtensionType, code: str = "", config: dict = None, description: str = "") -> Extension:
        ext = Extension(id=str(uuid.uuid4()), user_id=user_id, org_id=org_id, name=name, extension_type=extension_type, description=description, code=code, config=config or {})
        self._extensions[ext.id] = ext
        self._save()
        return ext

    def uninstall(self, ext_id: str) -> bool:
        if ext_id not in self._extensions: return False
        del self._extensions[ext_id]
        self._save()
        return True

    def list_by_user(self, user_id: str, ext_type: Optional[ExtensionType] = None) -> list[Extension]:
        results = [e for e in self._extensions.values() if e.user_id == user_id and e.is_active]
        if ext_type: results = [e for e in results if e.extension_type == ext_type]
        return results

    def execute(self, ext_id: str) -> dict:
        ext = self._extensions.get(ext_id)
        if not ext: return {"error": "Extension not found"}
        ext.usage_count += 1
        self._save()
        return {"extension": ext.name, "type": ext.extension_type.value, "executed": True}

    def get_telemetry(self) -> dict: return dict(self._telemetry)
