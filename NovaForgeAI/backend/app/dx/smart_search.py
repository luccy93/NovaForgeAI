"""Smart Search — universal search across repos, files, functions, classes, commits, issues, PRs, documentation, agents, prompts, settings, analytics, architecture, security reports."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class SearchDomain(Enum):
    REPOSITORY = "repository"
    FILE = "file"
    FUNCTION = "function"
    CLASS = "class"
    COMMIT = "commit"
    ISSUE = "issue"
    PULL_REQUEST = "pull_request"
    DOCUMENTATION = "documentation"
    AGENT = "agent"
    PROMPT = "prompt"
    SETTINGS = "settings"
    ANALYTICS = "analytics"
    ARCHITECTURE = "architecture"
    SECURITY = "security"


@dataclass
class SmartSearchResult:
    id: str
    domain: SearchDomain
    title: str
    description: str = ""
    url: str = ""
    score: float = 0.0
    metadata: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["domain"] = self.domain.value
        return d


@dataclass
class IndexedEntity:
    id: str
    domain: SearchDomain
    entity_id: str
    title: str
    content: str = ""
    tags: list = field(default_factory=list)
    indexed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["domain"] = self.domain.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "IndexedEntity":
        data = data.copy()
        data["domain"] = SearchDomain(data.get("domain", "file"))
        return cls(**data)


class SmartSearch:
    def __init__(self, storage_dir: str = "dx_data/search"):
        self.storage_dir = storage_dir
        self._index: dict[str, IndexedEntity] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "index.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._index[k] = IndexedEntity.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Failed to load search index: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._index.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save search index: %s", e)

    def index_entity(self, domain: SearchDomain, entity_id: str, title: str, content: str = "", tags: list = None) -> IndexedEntity:
        key = f"{domain.value}:{entity_id}"
        entity = IndexedEntity(id=key, domain=domain, entity_id=entity_id, title=title, content=content, tags=tags or [])
        self._index[key] = entity
        self._save()
        return entity

    def search(self, query: str, domains: list[SearchDomain] = None, limit: int = 20) -> list[SmartSearchResult]:
        q = query.lower()
        results = []
        for entity in self._index.values():
            if domains and entity.domain not in domains: continue
            score = 0.0
            if q in entity.title.lower(): score += 10
            if q in entity.content.lower(): score += 5
            if entity.tags and any(q in t.lower() for t in entity.tags): score += 3
            if score > 0:
                results.append(SmartSearchResult(id=str(uuid.uuid4()), domain=entity.domain, title=entity.title, description=entity.content[:200], score=score))
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    def get_domain_index(self, domain: SearchDomain) -> list[IndexedEntity]:
        return [e for e in self._index.values() if e.domain == domain]

    def remove_entity(self, domain: SearchDomain, entity_id: str) -> bool:
        key = f"{domain.value}:{entity_id}"
        if key in self._index:
            del self._index[key]
            self._save()
            return True
        return False

    def get_telemetry(self) -> dict: return dict(self._telemetry)
