"""Metadata Catalog module for NovaForge Data Platform & Knowledge Fabric."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class MetadataEntityType(Enum):
    REPOSITORY = "repository"
    API = "api"
    FUNCTION = "function"
    CLASS = "class"
    MODULE = "module"
    ARCHITECTURE = "architecture"
    DEPENDENCY = "dependency"
    DATABASE = "database"
    PROMPT = "prompt"
    MODEL = "model"
    AGENT = "agent"
    WORKSPACE = "workspace"
    SERVICE = "service"
    DATASET = "dataset"
    PIPELINE = "pipeline"
    DASHBOARD = "dashboard"
    CONFIGURATION = "configuration"
    INTEGRATION = "integration"


class MetadataSource(Enum):
    SCANNER = "scanner"
    PARSER = "parser"
    INGESTION = "ingestion"
    MANUAL = "manual"
    INFERRED = "inferred"
    CI_CD = "ci_cd"
    REGISTRY = "registry"
    API = "api"


class MetadataStatus(Enum):
    CURRENT = "current"
    STALE = "stale"
    DEPRECATED = "deprecated"
    PENDING_REVIEW = "pending_review"
    ERROR = "error"


class MetadataVisibility(Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    PRIVATE = "private"
    RESTRICTED = "restricted"


@dataclass
class MetadataEntry:
    id: str
    org_id: str
    workspace_id: str = ""
    entity_type: MetadataEntityType = MetadataEntityType.REPOSITORY
    entity_id: str = ""
    name: str = ""
    qualified_name: str = ""
    description: str = ""
    source: MetadataSource = MetadataSource.MANUAL
    status: MetadataStatus = MetadataStatus.CURRENT
    visibility: MetadataVisibility = MetadataVisibility.INTERNAL
    version: str = "1.0.0"
    schema_version: str = "1.0"
    attributes: dict = field(default_factory=dict)
    tags: list = field(default_factory=list)
    owner: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["entity_type"] = self.entity_type.value
        d["source"] = self.source.value
        d["status"] = self.status.value
        d["visibility"] = self.visibility.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "MetadataEntry":
        data = data.copy()
        data["entity_type"] = MetadataEntityType(data.get("entity_type", "repository"))
        data["source"] = MetadataSource(data.get("source", "manual"))
        data["status"] = MetadataStatus(data.get("status", "current"))
        data["visibility"] = MetadataVisibility(data.get("visibility", "internal"))
        return cls(**data)


@dataclass
class MetadataSchema:
    id: str
    entity_type: MetadataEntityType
    name: str = ""
    version: str = "1.0"
    fields: list = field(default_factory=list)
    required_fields: list = field(default_factory=list)
    constraints: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["entity_type"] = self.entity_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "MetadataSchema":
        data = data.copy()
        data["entity_type"] = MetadataEntityType(data.get("entity_type", "repository"))
        return cls(**data)


@dataclass
class MetadataChange:
    id: str
    entry_id: str
    field_name: str = ""
    old_value: Any = None
    new_value: Any = None
    changed_by: str = ""
    changed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    change_type: str = "update"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "MetadataChange":
        return cls(**data)


@dataclass
class MetadataRelationship:
    id: str
    source_entry_id: str
    target_entry_id: str
    relationship_type: str = "related_to"
    properties: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "MetadataRelationship":
        return cls(**data)


class MetadataCatalog:
    def __init__(self, storage_dir: str = "metadata_catalog_data"):
        self.storage_dir = storage_dir
        self._entries: dict[str, MetadataEntry] = {}
        self._schemas: dict[str, MetadataSchema] = {}
        self._changes: dict[str, MetadataChange] = {}
        self._relationships: dict[str, MetadataRelationship] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _entries_path(self) -> str: return os.path.join(self.storage_dir, "entries.json")
    def _schemas_path(self) -> str: return os.path.join(self.storage_dir, "schemas.json")
    def _changes_path(self) -> str: return os.path.join(self.storage_dir, "changes.json")
    def _relationships_path(self) -> str: return os.path.join(self.storage_dir, "relationships.json")

    def _save(self) -> None:
        try:
            with open(self._entries_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._entries.items()}, f, indent=2, default=str)
            with open(self._schemas_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._schemas.items()}, f, indent=2, default=str)
            with open(self._changes_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._changes.items()}, f, indent=2, default=str)
            with open(self._relationships_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._relationships.items()}, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save metadata catalog: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            for path, store, cls in [
                (self._entries_path(), self._entries, MetadataEntry),
                (self._schemas_path(), self._schemas, MetadataSchema),
                (self._changes_path(), self._changes, MetadataChange),
                (self._relationships_path(), self._relationships, MetadataRelationship),
            ]:
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for k, v in data.items():
                        try:
                            store[k] = cls.from_dict(v)
                        except Exception as e:
                            logger.warning("Skipping malformed entry %s: %s", k, e)
        except Exception as e:
            logger.error("Failed to load metadata catalog: %s", e, exc_info=True)

    def register_entry(self, entry: MetadataEntry) -> MetadataEntry:
        self._telemetry["register_entry_calls"] += 1
        self._entries[entry.id] = entry
        self._save()
        return entry

    def get_entry(self, entry_id: str) -> Optional[MetadataEntry]:
        return self._entries.get(entry_id)

    def get_entry_by_entity(self, entity_type: MetadataEntityType, entity_id: str) -> Optional[MetadataEntry]:
        for e in self._entries.values():
            if e.entity_type == entity_type and e.entity_id == entity_id:
                return e
        return None

    def update_entry(self, entry_id: str, updates: dict) -> Optional[MetadataEntry]:
        self._telemetry["update_entry_calls"] += 1
        entry = self._entries.get(entry_id)
        if not entry:
            return None
        for key, value in updates.items():
            if hasattr(entry, key) and key not in ("id", "created_at"):
                if key == "entity_type":
                    setattr(entry, key, MetadataEntityType(value) if isinstance(value, str) else value)
                elif key == "source":
                    setattr(entry, key, MetadataSource(value) if isinstance(value, str) else value)
                elif key == "status":
                    setattr(entry, key, MetadataStatus(value) if isinstance(value, str) else value)
                elif key == "visibility":
                    setattr(entry, key, MetadataVisibility(value) if isinstance(value, str) else value)
                else:
                    setattr(entry, key, value)
        entry.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return entry

    def delete_entry(self, entry_id: str) -> bool:
        if entry_id in self._entries:
            del self._entries[entry_id]
            self._save()
            return True
        return False

    def search_entries(self, query: str, entity_type: Optional[MetadataEntityType] = None) -> list[MetadataEntry]:
        q = query.lower()
        results = []
        for e in self._entries.values():
            if entity_type and e.entity_type != entity_type:
                continue
            if q in e.name.lower() or q in e.qualified_name.lower() or q in e.description.lower() or q in e.owner.lower():
                results.append(e)
        return results

    def list_entries(self, org_id: str, entity_type: Optional[MetadataEntityType] = None, status: Optional[MetadataStatus] = None) -> list[MetadataEntry]:
        results = [e for e in self._entries.values() if e.org_id == org_id]
        if entity_type:
            results = [e for e in results if e.entity_type == entity_type]
        if status:
            results = [e for e in results if e.status == status]
        return results

    def register_schema(self, schema: MetadataSchema) -> MetadataSchema:
        self._telemetry["register_schema_calls"] += 1
        self._schemas[schema.id] = schema
        self._save()
        return schema

    def get_schema(self, entity_type: MetadataEntityType, version: Optional[str] = None) -> Optional[MetadataSchema]:
        candidates = [s for s in self._schemas.values() if s.entity_type == entity_type]
        if version:
            candidates = [s for s in candidates if s.version == version]
        return max(candidates, key=lambda s: s.version) if candidates else None

    def validate_entry(self, entry: MetadataEntry) -> dict:
        self._telemetry["validate_entry_calls"] += 1
        schema = self.get_schema(entry.entity_type)
        if not schema:
            return {"valid": True, "errors": [], "warnings": ["No schema registered for this entity type"]}
        errors = []
        for field_name in schema.required_fields:
            if not hasattr(entry, field_name) or getattr(entry, field_name) in (None, ""):
                errors.append(f"Required field '{field_name}' is missing")
        warnings = []
        for field_def in schema.fields:
            if isinstance(field_def, dict) and field_def.get("name") and field_def.get("type"):
                fn = field_def["name"]
                ft = field_def["type"]
                if hasattr(entry, fn):
                    val = getattr(entry, fn)
                    if ft == "str" and not isinstance(val, str):
                        warnings.append(f"Field '{fn}' expected str, got {type(val).__name__}")
                    elif ft == "int" and not isinstance(val, int):
                        warnings.append(f"Field '{fn}' expected int, got {type(val).__name__}")
        return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}

    def register_relationship(self, rel: MetadataRelationship) -> MetadataRelationship:
        self._telemetry["register_relationship_calls"] += 1
        self._relationships[rel.id] = rel
        self._save()
        return rel

    def get_entity_relationships(self, entry_id: str) -> list[MetadataRelationship]:
        return [r for r in self._relationships.values() if r.source_entry_id == entry_id or r.target_entry_id == entry_id]

    def get_catalog_stats(self, org_id: str) -> dict:
        entries = [e for e in self._entries.values() if e.org_id == org_id]
        type_counts = defaultdict(int)
        for e in entries:
            type_counts[e.entity_type.value] += 1
        return {
            "total_entries": len(entries),
            "by_type": dict(type_counts),
            "total_schemas": len(self._schemas),
            "total_relationships": len(self._relationships),
            "total_changes": len(self._changes),
            "telemetry": dict(self._telemetry),
        }

    def get_telemetry(self) -> dict:
        return dict(self._telemetry)
