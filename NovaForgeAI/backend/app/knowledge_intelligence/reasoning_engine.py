"""Knowledge Reasoning — historical context, repository graph, architecture, developer history, cross-context."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, Any

logger = logging.getLogger(__name__)

@dataclass
class ReasoningQuery:
    id: str; org_id: str; query: str; context_type: str; result: Any = None
    sources: list = field(default_factory=list); confidence: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class KnowledgeReasoning:
    def __init__(self, storage_dir: str = "knowledge_data/reasoning"):
        self.storage_dir = storage_dir; self._queries: dict[str, ReasoningQuery] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "queries.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._queries[k] = ReasoningQuery(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._queries.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def reason(self, org_id: str, query: str, context_type: str, sources: list = None) -> ReasoningQuery:
        q = ReasoningQuery(id=str(uuid.uuid4()), org_id=org_id, query=query, context_type=context_type, sources=sources or [], result=f"Reasoned across {len(sources or [])} sources", confidence=0.75)
        self._queries[q.id] = q; self._save(); return q

    def get_telemetry(self) -> dict: return {"queries": len(self._queries)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class MemoryEntry:
    id: str; org_id: str; memory_type: str; key: str; value: Any
    scope: str = "organization"; ttl_days: int = 365; tags: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class KnowledgeMemory:
    def __init__(self, storage_dir: str = "knowledge_data/memory"):
        self.storage_dir = storage_dir; self._memory: dict[str, MemoryEntry] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "memory.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._memory[k] = MemoryEntry(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._memory.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def remember(self, org_id: str, memory_type: str, key: str, value: Any, scope: str = "organization") -> MemoryEntry:
        m = MemoryEntry(id=str(uuid.uuid4()), org_id=org_id, memory_type=memory_type, key=key, value=value, scope=scope)
        self._memory[m.id] = m; self._save(); return m

    def recall(self, org_id: str, key: str) -> Optional[Any]:
        for m in self._memory.values():
            if m.org_id == org_id and m.key == key: return m.value
        return None

    def search(self, org_id: str, memory_type: str = "") -> list[MemoryEntry]:
        results = [m for m in self._memory.values() if m.org_id == org_id]
        if memory_type: results = [m for m in results if m.memory_type == memory_type]
        return sorted(results, key=lambda m: m.updated_at, reverse=True)

    def get_telemetry(self) -> dict: return {"entries": len(self._memory)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class SearchIndex:
    id: str; org_id: str; resource_type: str; resource_id: str; title: str = ""; content: str = ""; score: float = 0.0; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class KnowledgeSearch:
    def __init__(self, storage_dir: str = "knowledge_data/search"):
        self.storage_dir = storage_dir; self._index: dict[str, SearchIndex] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "index.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._index[k] = SearchIndex(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._index.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def index(self, org_id: str, resource_type: str, resource_id: str, title: str = "", content: str = "") -> SearchIndex:
        si = SearchIndex(id=str(uuid.uuid4()), org_id=org_id, resource_type=resource_type, resource_id=resource_id, title=title, content=content)
        self._index[si.id] = si; self._save(); return si

    def query(self, org_id: str, q: str, resource_type: str = "") -> list[SearchIndex]:
        query = q.lower()
        results = [i for i in self._index.values() if i.org_id == org_id]
        if resource_type: results = [i for i in results if i.resource_type == resource_type]
        return [i for i in results if query in i.title.lower() or query in i.content.lower()]

    def get_telemetry(self) -> dict: return {"indexed": len(self._index)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class KnowledgeAnalytic:
    id: str; org_id: str; period: str; knowledge_growth: int = 0; knowledge_coverage: float = 0.0
    knowledge_usage: int = 0; freshness: float = 0.0; doc_health: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class KnowledgeAnalytics:
    def __init__(self, storage_dir: str = "knowledge_data/analytics"):
        self.storage_dir = storage_dir; self._analytics: dict[str, KnowledgeAnalytic] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "analytics.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._analytics[k] = KnowledgeAnalytic(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._analytics.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def record(self, org_id: str, growth: int = 0, coverage: float = 0.0, usage: int = 0) -> KnowledgeAnalytic:
        period = datetime.now(timezone.utc).strftime("%Y-%m")
        ka = KnowledgeAnalytic(id=str(uuid.uuid4()), org_id=org_id, period=period, knowledge_growth=growth, knowledge_coverage=coverage, knowledge_usage=usage)
        self._analytics[ka.id] = ka; self._save(); return ka

    def get_latest(self, org_id: str) -> Optional[KnowledgeAnalytic]:
        relevant = [a for a in self._analytics.values() if a.org_id == org_id]
        return sorted(relevant, key=lambda a: a.created_at, reverse=True)[0] if relevant else None

    def get_telemetry(self) -> dict: return {"points": len(self._analytics)}
