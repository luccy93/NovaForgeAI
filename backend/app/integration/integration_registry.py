"""Integration Registry — catalog of all available integrations, their capabilities, statuses, and health."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class IntegrationCategory(Enum):
    SOURCE_CONTROL = "source_control"
    PROJECT_MANAGEMENT = "project_management"
    DOCUMENTATION = "documentation"
    COMMUNICATION = "communication"
    CI_CD = "ci_cd"
    CLOUD = "cloud"
    CONTAINER = "container"
    DATABASE = "database"
    MONITORING = "monitoring"
    IDENTITY = "identity"
    AI_PROVIDER = "ai_provider"
    DEV_TOOL = "dev_tool"


class IntegrationStatus(Enum):
    AVAILABLE = "available"
    CONFIGURED = "configured"
    ACTIVE = "active"
    ERROR = "error"
    DEPRECATED = "deprecated"


@dataclass
class IntegrationEntry:
    id: str
    name: str
    provider: str
    category: IntegrationCategory
    status: IntegrationStatus = IntegrationStatus.AVAILABLE
    description: str = ""
    version: str = "1.0.0"
    docs_url: str = ""
    capabilities: list = field(default_factory=list)
    config_example: dict = field(default_factory=dict)
    instances_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["category"] = self.category.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "IntegrationEntry":
        data = data.copy()
        data["category"] = IntegrationCategory(data.get("category", "source_control"))
        data["status"] = IntegrationStatus(data.get("status", "available"))
        return cls(**data)


class IntegrationRegistry:
    def __init__(self, storage_dir: str = "integration_data/registry"):
        self.storage_dir = storage_dir
        self._entries: dict[str, IntegrationEntry] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "registry.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._entries[k] = IntegrationEntry.from_dict(v)
                    except Exception as e: logger.warning("Skipping entry %s: %s", k, e)
            except Exception as e: logger.error("Failed to load registry: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._entries.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save registry: %s", e)

    def register(self, name: str, provider: str, category: IntegrationCategory, description: str = "", capabilities: list = None, config_example: dict = None) -> IntegrationEntry:
        entry = IntegrationEntry(id=str(uuid.uuid4()), name=name, provider=provider, category=category, description=description, capabilities=capabilities or [], config_example=config_example or {})
        self._entries[entry.id] = entry
        self._save()
        return entry

    def get(self, entry_id: str) -> Optional[IntegrationEntry]: return self._entries.get(entry_id)

    def update_status(self, entry_id: str, status: IntegrationStatus) -> bool:
        entry = self._entries.get(entry_id)
        if not entry: return False
        entry.status = status
        entry.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return True

    def list_by_category(self, category: IntegrationCategory) -> list[IntegrationEntry]:
        return [e for e in self._entries.values() if e.category == category]

    def list_all(self) -> list[IntegrationEntry]:
        return list(self._entries.values())

    def search(self, query: str) -> list[IntegrationEntry]:
        q = query.lower()
        return [e for e in self._entries.values() if q in e.name.lower() or q in e.provider.lower() or q in e.description.lower()]

    def get_health_summary(self) -> dict:
        entries = list(self._entries.values())
        return {
            "total": len(entries),
            "by_category": {c.value: len([e for e in entries if e.category == c]) for c in IntegrationCategory},
            "by_status": {s.value: len([e for e in entries if e.status == s]) for s in IntegrationStatus},
            "active": len([e for e in entries if e.status == IntegrationStatus.ACTIVE]),
        }

    def get_telemetry(self) -> dict: return dict(self._telemetry)
