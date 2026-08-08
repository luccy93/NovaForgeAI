"""Knowledge Repository — store, version, search research datasets, findings, and artifacts."""
import json, uuid, os, logging, hashlib
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


class KnowledgeType(Enum):
    DATASET = "dataset"
    FINDING = "finding"
    ARTIFACT = "artifact"
    PAPER = "paper"
    NOTE = "note"
    BENCHMARK = "benchmark"
    MODEL_CARD = "model_card"
    EXPERIMENT_LOG = "experiment_log"


class KnowledgeVisibility(Enum):
    PRIVATE = "private"
    TEAM = "team"
    ORGANIZATION = "organization"
    PUBLIC = "public"


@dataclass
class KnowledgeVersion:
    version: int
    data_hash: str
    size: int
    changes: str = ""
    created_by: str = "system"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)


@dataclass
class KnowledgeEntry:
    id: str
    org_id: str
    title: str
    knowledge_type: KnowledgeType
    visibility: KnowledgeVisibility = KnowledgeVisibility.TEAM
    description: str = ""
    content: Any = None
    metadata: dict = field(default_factory=dict)
    tags: list = field(default_factory=list)
    versions: list = field(default_factory=list)
    current_version: int = 1
    source: str = ""
    authors: list = field(default_factory=list)
    references: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["knowledge_type"] = self.knowledge_type.value
        d["visibility"] = self.visibility.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "KnowledgeEntry":
        data = data.copy()
        data["knowledge_type"] = KnowledgeType(data.get("knowledge_type", "dataset"))
        data["visibility"] = KnowledgeVisibility(data.get("visibility", "team"))
        return cls(**data)


class KnowledgeRepository:
    def __init__(self, storage_dir: str = "research_data/knowledge"):
        self.storage_dir = storage_dir
        self._entries: dict[str, KnowledgeEntry] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "entries.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._entries[k] = KnowledgeEntry.from_dict(v)
                    except Exception as e: logger.warning("Skipping entry %s: %s", k, e)
            except Exception as e: logger.error("Failed to load knowledge repo: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._entries.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save knowledge repo: %s", e)

    def _hash_content(self, content: Any) -> str:
        return hashlib.sha256(json.dumps(content, default=str).encode()).hexdigest()[:16]

    def create_entry(self, title: str, org_id: str, knowledge_type: KnowledgeType = KnowledgeType.FINDING, content: Any = None, description: str = "") -> KnowledgeEntry:
        entry = KnowledgeEntry(id=str(uuid.uuid4()), org_id=org_id, title=title, knowledge_type=knowledge_type, content=content, description=description)
        if content is not None:
            entry.versions.append(KnowledgeVersion(version=1, data_hash=self._hash_content(content), size=len(json.dumps(content, default=str).encode())))
        self._entries[entry.id] = entry
        self._save()
        return entry

    def get_entry(self, entry_id: str) -> Optional[KnowledgeEntry]: return self._entries.get(entry_id)

    def update_entry(self, entry_id: str, updates: dict) -> Optional[KnowledgeEntry]:
        entry = self._entries.get(entry_id)
        if not entry: return None
        for k, v in updates.items():
            if hasattr(entry, k) and k not in ("id", "created_at"):
                if k == "knowledge_type": setattr(entry, k, KnowledgeType(v) if isinstance(v, str) else v)
                elif k == "visibility": setattr(entry, k, KnowledgeVisibility(v) if isinstance(v, str) else v)
                else: setattr(entry, k, v)
        if "content" in updates:
            entry.current_version += 1
            entry.versions.append(KnowledgeVersion(version=entry.current_version, data_hash=self._hash_content(updates["content"]), size=len(json.dumps(updates["content"], default=str).encode()), changes=updates.get("change_description", "")))
        entry.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return entry

    def search(self, query: str, knowledge_type: Optional[KnowledgeType] = None, limit: int = 20) -> list[KnowledgeEntry]:
        q = query.lower()
        results = []
        for entry in self._entries.values():
            if knowledge_type and entry.knowledge_type != knowledge_type: continue
            if q in entry.title.lower() or q in entry.description.lower() or any(q in t.lower() for t in entry.tags):
                results.append(entry)
        return results[:limit]

    def list_entries(self, org_id: str = "", knowledge_type: Optional[KnowledgeType] = None) -> list[KnowledgeEntry]:
        results = list(self._entries.values())
        if org_id: results = [e for e in results if e.org_id == org_id]
        if knowledge_type: results = [e for e in results if e.knowledge_type == knowledge_type]
        return results

    def delete_entry(self, entry_id: str) -> bool:
        if entry_id not in self._entries: return False
        del self._entries[entry_id]
        self._save()
        return True

    def get_entry_version(self, entry_id: str, version: int) -> Optional[dict]:
        entry = self._entries.get(entry_id)
        if not entry: return None
        for v in entry.versions:
            if v.version == version:
                return {"version": v.version, "data_hash": v.data_hash, "created_at": v.created_at, "changes": v.changes}
        return None

    def get_telemetry(self) -> dict: return dict(self._telemetry)
