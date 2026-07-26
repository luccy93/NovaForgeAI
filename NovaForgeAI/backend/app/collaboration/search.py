"""Collaboration Search — search across conversations, knowledge, repositories, projects, teams, architecture, reports, tasks, documentation."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class SearchEntity(Enum):
    CONVERSATION = "conversation"
    KNOWLEDGE = "knowledge"
    REPOSITORY = "repository"
    PROJECT = "project"
    TEAM = "team"
    ARCHITECTURE = "architecture"
    REPORT = "report"
    TASK = "task"
    DOCUMENTATION = "documentation"
    USER = "user"
    WORKSPACE = "workspace"
    DISCUSSION = "discussion"


@dataclass
class SearchResult:
    id: str
    entity_type: SearchEntity
    entity_id: str
    title: str
    description: str = ""
    score: float = 0.0
    url: str = ""
    highlights: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["entity_type"] = self.entity_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "SearchResult":
        data = data.copy()
        data["entity_type"] = SearchEntity(data.get("entity_type", "documentation"))
        return cls(**data)


@dataclass
class SearchQuery:
    id: str
    org_id: str
    user_id: str
    query: str
    entity_types: list = field(default_factory=list)
    result_count: int = 0
    duration_ms: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "SearchQuery": return cls(**data)


class CollaborationSearch:
    def __init__(self, storage_dir: str = "collab_data/search"):
        self.storage_dir = storage_dir
        self._results_cache: dict[str, dict] = {}
        self._queries: dict[str, SearchQuery] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _results_path(self) -> str: return os.path.join(self.storage_dir, "results.json")
    def _queries_path(self) -> str: return os.path.join(self.storage_dir, "queries.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._results_path(), None, None),
            (self._queries_path(), self._queries, SearchQuery),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if cls:
                        for k, v in data.items():
                            try: store[k] = cls.from_dict(v)
                            except Exception as e: logger.warning("Skipping %s: %s", k, e)
                    else:
                        self._results_cache = data
                except Exception as e: logger.error("Failed to load search data: %s", e)

    def _save(self) -> None:
        try:
            with open(self._results_path(), "w", encoding="utf-8") as f:
                json.dump(self._results_cache, f, indent=2, default=str)
            with open(self._queries_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._queries.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save search data: %s", e)

    def index(self, entity_type: SearchEntity, entity_id: str, title: str, description: str = "", url: str = "", content: str = "") -> None:
        key = f"{entity_type.value}:{entity_id}"
        self._results_cache[key] = {
            "entity_type": entity_type.value, "entity_id": entity_id, "title": title,
            "description": description, "url": url, "content": content[:1000] if content else "",
            "indexed_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save()

    def search(self, org_id: str, user_id: str, query: str, entity_types: list[SearchEntity] = None, limit: int = 20) -> list[SearchResult]:
        q = query.lower()
        results = []
        for key, data in self._results_cache.items():
            if entity_types and data.get("entity_type") not in [e.value for e in entity_types]:
                continue
            if q in data.get("title", "").lower() or q in data.get("description", "").lower() or q in data.get("content", "").lower():
                score = 0.0
                if q in data.get("title", "").lower(): score += 0.5
                if q in data.get("description", "").lower(): score += 0.3
                if q in data.get("content", "").lower(): score += 0.2
                results.append({"data": data, "score": score})
        results.sort(key=lambda r: r["score"], reverse=True)
        search_result = SearchQuery(id=str(uuid.uuid4()), org_id=org_id, user_id=user_id, query=query, entity_types=[e.value for e in (entity_types or [])], result_count=len(results))
        self._queries[search_result.id] = search_result
        self._save()
        return [
            SearchResult(id=str(uuid.uuid4()), entity_type=SearchEntity(r["data"]["entity_type"]), entity_id=r["data"]["entity_id"], title=r["data"]["title"], description=r["data"].get("description", ""), score=r["score"], url=r["data"].get("url", ""))
            for r in results[:limit]
        ]

    def get_popular_queries(self, org_id: str, limit: int = 20) -> list[dict]:
        queries = [q for q in self._queries.values() if q.org_id == org_id]
        query_counts = {}
        for q in queries:
            query_counts[q.query] = query_counts.get(q.query, 0) + 1
        sorted_queries = sorted(query_counts.items(), key=lambda x: x[1], reverse=True)
        return [{"query": q, "count": c} for q, c in sorted_queries[:limit]]

    def remove_index(self, entity_type: SearchEntity, entity_id: str) -> bool:
        key = f"{entity_type.value}:{entity_id}"
        if key in self._results_cache:
            del self._results_cache[key]
            self._save()
            return True
        return False

    def get_telemetry(self) -> dict: return dict(self._telemetry)
