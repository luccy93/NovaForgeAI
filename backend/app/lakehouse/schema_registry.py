"""Schema Registry - versioned event/table schemas with validation and compatibility checks."""
import json, os, uuid, hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class RegisteredSchema:
    name: str
    version: int
    fields: dict
    registered_at: str = ""
    id: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = uuid.uuid4().hex[:12]
        if not self.registered_at:
            self.registered_at = datetime.now(timezone.utc).isoformat()


class SchemaRegistry:
    """Versioned schema store with JSoN validation and forward/backward compatibility."""

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.schemas: dict[str, list[RegisteredSchema]] = {}

    def _path(self, name: str) -> str:
        return os.path.join(self.data_dir, f"{name}.json")

    def register(self, name: str, fields: dict, version: Optional[int] = None) -> RegisteredSchema:
        versions = self.schemas.get(name, [])
        next_version = (max((s.version for s in versions), default=0) + 1) if version is None else version
        if any(s.version == next_version for s in versions):
            raise ValueError(f"schema {name} version {next_version} already exists")
        if versions:
            prev = versions[-1]
            if not self.compatible(prev.fields, fields, mode="full"):
                raise ValueError(f"schema {name} v{next_version} breaks compatibility with v{prev.version}")
        schema = RegisteredSchema(name=name, version=next_version, fields=fields)
        versions.append(schema)
        self.schemas[name] = versions
        self._persist(name)
        return schema

    def get(self, name: str, version: Optional[int] = None) -> Optional[RegisteredSchema]:
        versions = self.schemas.get(name, [])
        if not versions:
            return None
        if version is None:
            return versions[-1]
        for s in versions:
            if s.version == version:
                return s
        return None

    def versions_of(self, name: str) -> list[int]:
        return [s.version for s in self.schemas.get(name, [])]

    def validate(self, name: str, record: dict, version: Optional[int] = None) -> list[str]:
        schema = self.get(name, version)
        if not schema:
            return ["schema not found"]
        errors = []
        for fname, spec in schema.fields.items():
            required = spec.get("required", False)
            ftype = spec.get("type", "any")
            value = record.get(fname)
            if required and value is None:
                errors.append(f"missing required field: {fname}")
                continue
            if value is not None and ftype != "any" and not self._type_ok(ftype, value):
                errors.append(f"field {fname} expected {ftype}, got {type(value).__name__}")
        return errors

    @staticmethod
    def _type_ok(ftype: str, value) -> bool:
        return {
            "string": isinstance(value, str),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "number": isinstance(value, (int, float)) and not isinstance(value, bool),
            "boolean": isinstance(value, bool),
            "array": isinstance(value, list),
            "object": isinstance(value, dict),
        }.get(ftype, True)

    @staticmethod
    def compatible(old: dict, new: dict, mode: str = "full") -> bool:
        """mode: full | backward (old readers can read new data) | forward."""
        for fname, spec in old.items():
            if mode in ("full", "backward"):
                if fname not in new:
                    return False
        for fname, spec in new.items():
            if mode in ("full", "forward"):
                if fname not in old and spec.get("required"):
                    return False
        return True

    def list_schemas(self) -> list[str]:
        return sorted(self.schemas.keys())

    def _persist(self, name: str) -> None:
        with open(self._path(name), "w", encoding="utf-8") as f:
            json.dump([s.__dict__ for s in self.schemas[name]], f, indent=2, default=str)

    def _load_all(self) -> None:
        for fname in os.listdir(self.data_dir):
            if fname.endswith(".json"):
                name = fname[:-5]
                with open(os.path.join(self.data_dir, fname), encoding="utf-8") as f:
                    raw = json.load(f)
                self.schemas[name] = [RegisteredSchema(**item) for item in raw]

    def health(self) -> dict:
        return {"schemas": len(self.schemas),
                "versions": sum(len(v) for v in self.schemas.values())}