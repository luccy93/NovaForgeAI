"""
Global Search — Cross Repository Search, Cross Organization Search, Documentation Search, Architecture Search, Semantic Search, Dependency Search.
"""
import logging
logger = logging.getLogger(__name__)

from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
import json, uuid, hashlib, time, os, threading
from collections import defaultdict


class SearchType(Enum):
    CROSS_REPO = "cross_repo"
    CROSS_ORG = "cross_org"
    DOCUMENTATION = "documentation"
    ARCHITECTURE = "architecture"
    SEMANTIC = "semantic"
    DEPENDENCY = "dependency"
    FULL_TEXT = "full_text"
    CODE = "code"


class SearchScope(Enum):
    ORGANIZATION = "organization"
    WORKSPACE = "workspace"
    PROJECT = "project"
    REPOSITORY = "repository"
    GLOBAL = "global"


class SortOrder(Enum):
    RELEVANCE = "relevance"
    DATE = "date"
    NAME = "name"
    SIZE = "size"
    DEPTH = "depth"
    POPULARITY = "popularity"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SearchQuery:
    id: str
    query_text: str
    search_type: SearchType
    scope: SearchScope
    filters: dict = field(default_factory=dict)
    sort: SortOrder = SortOrder.RELEVANCE
    limit: int = 20
    offset: int = 0
    org_id: Optional[str] = None
    workspace_id: Optional[str] = None
    project_id: Optional[str] = None
    repository_id: Optional[str] = None
    created_at: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["search_type"] = self.search_type.value
        d["scope"] = self.scope.value
        d["sort"] = self.sort.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "SearchQuery":
        data = dict(data)
        data["search_type"] = SearchType(data["search_type"])
        data["scope"] = SearchScope(data["scope"])
        data["sort"] = SortOrder(data["sort"])
        return SearchQuery(**data)


@dataclass
class SearchResult:
    id: str
    query_id: str
    title: str
    snippet: str
    url: str
    score: float
    source_type: str
    source_id: str
    org_id: str
    workspace_id: Optional[str] = None
    repository_id: Optional[str] = None
    matched_terms: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    indexed_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "SearchResult":
        return SearchResult(**data)


@dataclass
class SearchIndex:
    id: str
    source_type: str
    source_id: str
    content: str
    tokens: list[str] = field(default_factory=list)
    embeddings: list[float] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    indexed_at: str = ""
    updated_at: str = ""
    version: int = 1

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "SearchIndex":
        return SearchIndex(**data)


@dataclass
class SearchSuggestion:
    query: str
    score: float = 0.0
    frequency: int = 0
    category: str = "general"

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "SearchSuggestion":
        return SearchSuggestion(**data)


@dataclass
class SearchAnalytics:
    total_searches: int = 0
    unique_users: int = 0
    avg_response_time_ms: float = 0.0
    top_queries: list[tuple] = field(default_factory=list)
    zero_result_queries: list[str] = field(default_factory=list)
    search_type_breakdown: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["top_queries"] = [list(q) for q in self.top_queries]
        return d

    @staticmethod
    def from_dict(data: dict) -> "SearchAnalytics":
        data = dict(data)
        data["top_queries"] = [tuple(q) for q in data.get("top_queries", [])]
        return SearchAnalytics(**data)


# ---------------------------------------------------------------------------
# Managers
# ---------------------------------------------------------------------------

class CrossRepositorySearch:
    """Cross-repository search with indexing and language/file-type filters."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._index_file = os.path.join(storage_dir, "cross_repo_index.json")
        self._indices: dict[str, SearchIndex] = {}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._index_file):
                with open(self._index_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._indices = {k: SearchIndex.from_dict(v) for k, v in data.items()}
                logger.info("Loaded %d cross-repo index entries", len(self._indices))
        except Exception:
            logger.exception("Failed to load cross-repo index; starting fresh")
            self._indices = {}

    def _save(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._indices.items()}
            tmp = self._index_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._index_file)
        except Exception:
            logger.exception("Failed to save cross-repo index")

    def index_repository(self, repo_id: str, org_id: str, content: str,
                         language: str = "", file_type: str = "",
                         metadata: Optional[dict] = None) -> SearchIndex:
        try:
            now = datetime.now(timezone.utc).isoformat()
            idx = SearchIndex(
                id=str(uuid.uuid4()),
                source_type="repository",
                source_id=repo_id,
                content=content,
                tokens=content.lower().split(),
                metadata={
                    "org_id": org_id,
                    "language": language,
                    "file_type": file_type,
                    **(metadata or {}),
                },
                indexed_at=now,
                updated_at=now,
            )
            key = f"{repo_id}:{language}:{file_type}"
            self._indices[key] = idx
            self._save()
            self.telemetry["repos_indexed"] += 1
            logger.info("Indexed repository %s (%s)", repo_id, language)
            return idx
        except Exception:
            logger.exception("Failed to index repository %s", repo_id)
            raise

    def search_across_repos(self, query: str, org_id: Optional[str] = None,
                            limit: int = 20) -> list[tuple[SearchIndex, float]]:
        try:
            terms = query.lower().split()
            results: list[tuple[SearchIndex, float]] = []
            for idx in self._indices.values():
                if org_id and idx.metadata.get("org_id") != org_id:
                    continue
                score = sum(1 for t in terms if t in idx.tokens)
                if score > 0:
                    results.append((idx, score / max(len(terms), 1)))
            results.sort(key=lambda x: x[1], reverse=True)
            self.telemetry["cross_repo_searches"] += 1
            return results[:limit]
        except Exception:
            logger.exception("Failed to search across repos")
            raise

    def search_by_language(self, language: str, query: str,
                           limit: int = 20) -> list[tuple[SearchIndex, float]]:
        try:
            terms = query.lower().split()
            results: list[tuple[SearchIndex, float]] = []
            for idx in self._indices.values():
                if idx.metadata.get("language") != language:
                    continue
                score = sum(1 for t in terms if t in idx.tokens)
                if score > 0:
                    results.append((idx, score / max(len(terms), 1)))
            results.sort(key=lambda x: x[1], reverse=True)
            self.telemetry["language_searches"] += 1
            return results[:limit]
        except Exception:
            logger.exception("Failed to search by language")
            raise

    def search_by_file_type(self, file_type: str, query: str,
                            limit: int = 20) -> list[tuple[SearchIndex, float]]:
        try:
            terms = query.lower().split()
            results: list[tuple[SearchIndex, float]] = []
            for idx in self._indices.values():
                if idx.metadata.get("file_type") != file_type:
                    continue
                score = sum(1 for t in terms if t in idx.tokens)
                if score > 0:
                    results.append((idx, score / max(len(terms), 1)))
            results.sort(key=lambda x: x[1], reverse=True)
            self.telemetry["file_type_searches"] += 1
            return results[:limit]
        except Exception:
            logger.exception("Failed to search by file type")
            raise

    def get_repo_search_stats(self) -> dict:
        try:
            return {
                "total_indexed": len(self._indices),
                "repos_indexed": self.telemetry.get("repos_indexed", 0),
                "cross_repo_searches": self.telemetry.get("cross_repo_searches", 0),
                "language_searches": self.telemetry.get("language_searches", 0),
                "file_type_searches": self.telemetry.get("file_type_searches", 0),
                "languages": list(set(
                    idx.metadata.get("language", "")
                    for idx in self._indices.values() if idx.metadata.get("language")
                )),
                "file_types": list(set(
                    idx.metadata.get("file_type", "")
                    for idx in self._indices.values() if idx.metadata.get("file_type")
                )),
            }
        except Exception:
            logger.exception("Failed to get repo search stats")
            raise


class CrossOrganizationSearch:
    """Cross-organization search with tier-based filtering."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._index_file = os.path.join(storage_dir, "cross_org_index.json")
        self._indices: dict[str, SearchIndex] = {}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._index_file):
                with open(self._index_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._indices = {k: SearchIndex.from_dict(v) for k, v in data.items()}
                logger.info("Loaded %d cross-org index entries", len(self._indices))
        except Exception:
            logger.exception("Failed to load cross-org index; starting fresh")
            self._indices = {}

    def _save(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._indices.items()}
            tmp = self._index_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._index_file)
        except Exception:
            logger.exception("Failed to save cross-org index")

    def index_organization(self, org_id: str, content: str,
                           metadata: Optional[dict] = None) -> SearchIndex:
        try:
            now = datetime.now(timezone.utc).isoformat()
            idx = SearchIndex(
                id=str(uuid.uuid4()),
                source_type="organization",
                source_id=org_id,
                content=content,
                tokens=content.lower().split(),
                metadata={"org_id": org_id, **(metadata or {})},
                indexed_at=now,
                updated_at=now,
            )
            self._indices[org_id] = idx
            self._save()
            self.telemetry["orgs_indexed"] += 1
            logger.info("Indexed organization %s", org_id)
            return idx
        except Exception:
            logger.exception("Failed to index organization %s", org_id)
            raise

    def search_across_orgs(self, query: str,
                           limit: int = 20) -> list[tuple[SearchIndex, float]]:
        try:
            terms = query.lower().split()
            results: list[tuple[SearchIndex, float]] = []
            for idx in self._indices.values():
                score = sum(1 for t in terms if t in idx.tokens)
                if score > 0:
                    results.append((idx, score / max(len(terms), 1)))
            results.sort(key=lambda x: x[1], reverse=True)
            self.telemetry["cross_org_searches"] += 1
            return results[:limit]
        except Exception:
            logger.exception("Failed to search across orgs")
            raise

    def search_by_org_tier(self, tier: str, query: str,
                           limit: int = 20) -> list[tuple[SearchIndex, float]]:
        try:
            terms = query.lower().split()
            results: list[tuple[SearchIndex, float]] = []
            for idx in self._indices.values():
                if idx.metadata.get("tier") != tier:
                    continue
                score = sum(1 for t in terms if t in idx.tokens)
                if score > 0:
                    results.append((idx, score / max(len(terms), 1)))
            results.sort(key=lambda x: x[1], reverse=True)
            self.telemetry["org_tier_searches"] += 1
            return results[:limit]
        except Exception:
            logger.exception("Failed to search by org tier")
            raise

    def get_org_search_stats(self) -> dict:
        try:
            return {
                "total_indexed": len(self._indices),
                "orgs_indexed": self.telemetry.get("orgs_indexed", 0),
                "cross_org_searches": self.telemetry.get("cross_org_searches", 0),
                "org_tier_searches": self.telemetry.get("org_tier_searches", 0),
            }
        except Exception:
            logger.exception("Failed to get org search stats")
            raise


class DocumentationSearch:
    """Documentation search with section and tag filtering."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._index_file = os.path.join(storage_dir, "doc_index.json")
        self._indices: dict[str, SearchIndex] = {}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._index_file):
                with open(self._index_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._indices = {k: SearchIndex.from_dict(v) for k, v in data.items()}
                logger.info("Loaded %d doc index entries", len(self._indices))
        except Exception:
            logger.exception("Failed to load doc index; starting fresh")
            self._indices = {}

    def _save(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._indices.items()}
            tmp = self._index_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._index_file)
        except Exception:
            logger.exception("Failed to save doc index")

    def index_document(self, doc_id: str, content: str, section: str = "",
                       tags: Optional[list[str]] = None,
                       metadata: Optional[dict] = None) -> SearchIndex:
        try:
            now = datetime.now(timezone.utc).isoformat()
            idx = SearchIndex(
                id=str(uuid.uuid4()),
                source_type="documentation",
                source_id=doc_id,
                content=content,
                tokens=content.lower().split(),
                metadata={
                    "section": section,
                    "tags": tags or [],
                    **(metadata or {}),
                },
                indexed_at=now,
                updated_at=now,
            )
            self._indices[doc_id] = idx
            self._save()
            self.telemetry["docs_indexed"] += 1
            logger.info("Indexed document %s", doc_id)
            return idx
        except Exception:
            logger.exception("Failed to index document %s", doc_id)
            raise

    def search_docs(self, query: str, limit: int = 20) -> list[tuple[SearchIndex, float]]:
        try:
            terms = query.lower().split()
            results: list[tuple[SearchIndex, float]] = []
            for idx in self._indices.values():
                if idx.source_type != "documentation":
                    continue
                score = sum(1 for t in terms if t in idx.tokens)
                if score > 0:
                    results.append((idx, score / max(len(terms), 1)))
            results.sort(key=lambda x: x[1], reverse=True)
            self.telemetry["doc_searches"] += 1
            return results[:limit]
        except Exception:
            logger.exception("Failed to search docs")
            raise

    def search_by_section(self, section: str, query: str,
                          limit: int = 20) -> list[tuple[SearchIndex, float]]:
        try:
            terms = query.lower().split()
            results: list[tuple[SearchIndex, float]] = []
            for idx in self._indices.values():
                if idx.metadata.get("section") != section:
                    continue
                score = sum(1 for t in terms if t in idx.tokens)
                if score > 0:
                    results.append((idx, score / max(len(terms), 1)))
            results.sort(key=lambda x: x[1], reverse=True)
            self.telemetry["section_searches"] += 1
            return results[:limit]
        except Exception:
            logger.exception("Failed to search by section")
            raise

    def search_by_tag(self, tag: str, query: str,
                      limit: int = 20) -> list[tuple[SearchIndex, float]]:
        try:
            terms = query.lower().split()
            results: list[tuple[SearchIndex, float]] = []
            for idx in self._indices.values():
                if tag not in idx.metadata.get("tags", []):
                    continue
                score = sum(1 for t in terms if t in idx.tokens)
                if score > 0:
                    results.append((idx, score / max(len(terms), 1)))
            results.sort(key=lambda x: x[1], reverse=True)
            self.telemetry["tag_searches"] += 1
            return results[:limit]
        except Exception:
            logger.exception("Failed to search by tag")
            raise

    def get_doc_search_stats(self) -> dict:
        try:
            return {
                "total_indexed": len(self._indices),
                "docs_indexed": self.telemetry.get("docs_indexed", 0),
                "doc_searches": self.telemetry.get("doc_searches", 0),
                "section_searches": self.telemetry.get("section_searches", 0),
                "tag_searches": self.telemetry.get("tag_searches", 0),
                "sections": list(set(
                    idx.metadata.get("section", "")
                    for idx in self._indices.values() if idx.metadata.get("section")
                )),
                "tags": list(set(
                    t for idx in self._indices.values()
                    for t in idx.metadata.get("tags", [])
                )),
            }
        except Exception:
            logger.exception("Failed to get doc search stats")
            raise


class ArchitectureSearch:
    """Architecture pattern and component search."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._index_file = os.path.join(storage_dir, "arch_index.json")
        self._indices: dict[str, SearchIndex] = {}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._index_file):
                with open(self._index_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._indices = {k: SearchIndex.from_dict(v) for k, v in data.items()}
                logger.info("Loaded %d arch index entries", len(self._indices))
        except Exception:
            logger.exception("Failed to load arch index; starting fresh")
            self._indices = {}

    def _save(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._indices.items()}
            tmp = self._index_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._index_file)
        except Exception:
            logger.exception("Failed to save arch index")

    def index_architecture(self, arch_id: str, content: str,
                           pattern: str = "", component: str = "",
                           metadata: Optional[dict] = None) -> SearchIndex:
        try:
            now = datetime.now(timezone.utc).isoformat()
            idx = SearchIndex(
                id=str(uuid.uuid4()),
                source_type="architecture",
                source_id=arch_id,
                content=content,
                tokens=content.lower().split(),
                metadata={
                    "pattern": pattern,
                    "component": component,
                    **(metadata or {}),
                },
                indexed_at=now,
                updated_at=now,
            )
            self._indices[arch_id] = idx
            self._save()
            self.telemetry["arch_indexed"] += 1
            logger.info("Indexed architecture %s", arch_id)
            return idx
        except Exception:
            logger.exception("Failed to index architecture %s", arch_id)
            raise

    def search_architecture(self, query: str,
                            limit: int = 20) -> list[tuple[SearchIndex, float]]:
        try:
            terms = query.lower().split()
            results: list[tuple[SearchIndex, float]] = []
            for idx in self._indices.values():
                if idx.source_type != "architecture":
                    continue
                score = sum(1 for t in terms if t in idx.tokens)
                if score > 0:
                    results.append((idx, score / max(len(terms), 1)))
            results.sort(key=lambda x: x[1], reverse=True)
            self.telemetry["arch_searches"] += 1
            return results[:limit]
        except Exception:
            logger.exception("Failed to search architecture")
            raise

    def search_by_pattern(self, pattern: str, query: str,
                          limit: int = 20) -> list[tuple[SearchIndex, float]]:
        try:
            terms = query.lower().split()
            results: list[tuple[SearchIndex, float]] = []
            for idx in self._indices.values():
                if idx.metadata.get("pattern") != pattern:
                    continue
                score = sum(1 for t in terms if t in idx.tokens)
                if score > 0:
                    results.append((idx, score / max(len(terms), 1)))
            results.sort(key=lambda x: x[1], reverse=True)
            self.telemetry["pattern_searches"] += 1
            return results[:limit]
        except Exception:
            logger.exception("Failed to search by pattern")
            raise

    def search_by_component(self, component: str, query: str,
                            limit: int = 20) -> list[tuple[SearchIndex, float]]:
        try:
            terms = query.lower().split()
            results: list[tuple[SearchIndex, float]] = []
            for idx in self._indices.values():
                if idx.metadata.get("component") != component:
                    continue
                score = sum(1 for t in terms if t in idx.tokens)
                if score > 0:
                    results.append((idx, score / max(len(terms), 1)))
            results.sort(key=lambda x: x[1], reverse=True)
            self.telemetry["component_searches"] += 1
            return results[:limit]
        except Exception:
            logger.exception("Failed to search by component")
            raise

    def get_architecture_search_stats(self) -> dict:
        try:
            return {
                "total_indexed": len(self._indices),
                "arch_indexed": self.telemetry.get("arch_indexed", 0),
                "arch_searches": self.telemetry.get("arch_searches", 0),
                "pattern_searches": self.telemetry.get("pattern_searches", 0),
                "component_searches": self.telemetry.get("component_searches", 0),
                "patterns": list(set(
                    idx.metadata.get("pattern", "")
                    for idx in self._indices.values() if idx.metadata.get("pattern")
                )),
                "components": list(set(
                    idx.metadata.get("component", "")
                    for idx in self._indices.values() if idx.metadata.get("component")
                )),
            }
        except Exception:
            logger.exception("Failed to get arch search stats")
            raise


class SemanticSearch:
    """Semantic search with embedding similarity and concept matching."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._index_file = os.path.join(storage_dir, "semantic_index.json")
        self._indices: dict[str, SearchIndex] = {}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._index_file):
                with open(self._index_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._indices = {k: SearchIndex.from_dict(v) for k, v in data.items()}
                logger.info("Loaded %d semantic index entries", len(self._indices))
        except Exception:
            logger.exception("Failed to load semantic index; starting fresh")
            self._indices = {}

    def _save(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._indices.items()}
            tmp = self._index_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._index_file)
        except Exception:
            logger.exception("Failed to save semantic index")

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(av * bv for av, bv in zip(a, b))
        na = sum(av * av for av in a) ** 0.5
        nb = sum(bv * bv for bv in b) ** 0.5
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def create_embedding(self, source_type: str, source_id: str, content: str,
                         embeddings: Optional[list[float]] = None,
                         metadata: Optional[dict] = None) -> SearchIndex:
        try:
            now = datetime.now(timezone.utc).isoformat()
            idx = SearchIndex(
                id=str(uuid.uuid4()),
                source_type=source_type,
                source_id=source_id,
                content=content,
                tokens=content.lower().split(),
                embeddings=embeddings or [],
                metadata=metadata or {},
                indexed_at=now,
                updated_at=now,
            )
            key = f"{source_type}:{source_id}"
            self._indices[key] = idx
            self._save()
            self.telemetry["embeddings_created"] += 1
            logger.info("Created embedding for %s %s", source_type, source_id)
            return idx
        except Exception:
            logger.exception("Failed to create embedding")
            raise

    def search_semantic(self, query_embedding: list[float],
                        limit: int = 20) -> list[tuple[SearchIndex, float]]:
        try:
            scored: list[tuple[SearchIndex, float]] = []
            for idx in self._indices.values():
                if not idx.embeddings:
                    continue
                sim = self._cosine_similarity(query_embedding, idx.embeddings)
                if sim > 0:
                    scored.append((idx, sim))
            scored.sort(key=lambda x: x[1], reverse=True)
            self.telemetry["semantic_searches"] += 1
            return scored[:limit]
        except Exception:
            logger.exception("Failed to search semantic")
            raise

    def find_similar(self, source_type: str, source_id: str,
                     limit: int = 20) -> list[tuple[SearchIndex, float]]:
        try:
            key = f"{source_type}:{source_id}"
            target = self._indices.get(key)
            if target is None or not target.embeddings:
                return []
            return self.search_semantic(target.embeddings, limit=limit + 1)[1:limit + 1]
        except Exception:
            logger.exception("Failed to find similar")
            raise

    def search_by_concept(self, concept: str,
                          limit: int = 20) -> list[tuple[SearchIndex, float]]:
        try:
            terms = concept.lower().split()
            results: list[tuple[SearchIndex, float]] = []
            for idx in self._indices.values():
                score = sum(1 for t in terms if t in idx.tokens)
                if score > 0:
                    results.append((idx, score / max(len(terms), 1)))
            results.sort(key=lambda x: x[1], reverse=True)
            self.telemetry["concept_searches"] += 1
            return results[:limit]
        except Exception:
            logger.exception("Failed to search by concept")
            raise

    def get_semantic_search_stats(self) -> dict:
        try:
            return {
                "total_embeddings": sum(1 for idx in self._indices.values() if idx.embeddings),
                "total_indexed": len(self._indices),
                "embeddings_created": self.telemetry.get("embeddings_created", 0),
                "semantic_searches": self.telemetry.get("semantic_searches", 0),
                "concept_searches": self.telemetry.get("concept_searches", 0),
            }
        except Exception:
            logger.exception("Failed to get semantic search stats")
            raise


class DependencySearch:
    """Dependency search with usage analysis and vulnerability detection."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._index_file = os.path.join(storage_dir, "dep_index.json")
        self._indices: dict[str, SearchIndex] = {}
        self._dependents_map: dict[str, list[str]] = defaultdict(list)
        self._dependencies_map: dict[str, list[str]] = defaultdict(list)
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._index_file):
                with open(self._index_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._indices = {k: SearchIndex.from_dict(v) for k, v in data.get("indices", {}).items()}
                self._dependents_map = defaultdict(list, data.get("dependents_map", {}))
                self._dependencies_map = defaultdict(list, data.get("dependencies_map", {}))
                logger.info("Loaded %d dependency index entries", len(self._indices))
        except Exception:
            logger.exception("Failed to load dependency index; starting fresh")
            self._indices = {}
            self._dependents_map = defaultdict(list)
            self._dependencies_map = defaultdict(list)

    def _save(self) -> None:
        try:
            data = {
                "indices": {k: v.to_dict() for k, v in self._indices.items()},
                "dependents_map": dict(self._dependents_map),
                "dependencies_map": dict(self._dependencies_map),
            }
            tmp = self._index_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._index_file)
        except Exception:
            logger.exception("Failed to save dependency index")

    def index_dependencies(self, source_id: str, dependencies: list[str],
                           content: str = "",
                           metadata: Optional[dict] = None) -> list[SearchIndex]:
        try:
            now = datetime.now(timezone.utc).isoformat()
            indices = []
            for dep in dependencies:
                key = f"{source_id}:{dep}"
                idx = SearchIndex(
                    id=str(uuid.uuid4()),
                    source_type="dependency",
                    source_id=dep,
                    content=content or dep,
                    tokens=dep.lower().replace("-", " ").replace(".", " ").split(),
                    metadata={"source": source_id, **(metadata or {})},
                    indexed_at=now,
                    updated_at=now,
                )
                self._indices[key] = idx
                self._dependencies_map[source_id].append(dep)
                self._dependents_map[dep].append(source_id)
                indices.append(idx)
            self._save()
            self.telemetry["deps_indexed"] += len(dependencies)
            logger.info("Indexed %d dependencies for %s", len(dependencies), source_id)
            return indices
        except Exception:
            logger.exception("Failed to index dependencies for %s", source_id)
            raise

    def search_dependencies(self, query: str,
                            limit: int = 20) -> list[tuple[SearchIndex, float]]:
        try:
            terms = query.lower().split()
            results: list[tuple[SearchIndex, float]] = []
            for idx in self._indices.values():
                if idx.source_type != "dependency":
                    continue
                score = sum(1 for t in terms if t in idx.tokens)
                if score > 0:
                    results.append((idx, score / max(len(terms), 1)))
            results.sort(key=lambda x: x[1], reverse=True)
            self.telemetry["dep_searches"] += 1
            return results[:limit]
        except Exception:
            logger.exception("Failed to search dependencies")
            raise

    def find_usage(self, dependency: str) -> list[str]:
        try:
            usages = list(self._dependents_map.get(dependency, []))
            self.telemetry["usage_lookups"] += 1
            return usages
        except Exception:
            logger.exception("Failed to find usage for %s", dependency)
            raise

    def find_dependents(self, source_id: str) -> list[str]:
        try:
            deps = list(self._dependencies_map.get(source_id, []))
            self.telemetry["dependent_lookups"] += 1
            return deps
        except Exception:
            logger.exception("Failed to find dependents for %s", source_id)
            raise

    def find_vulnerable_dependencies(self, vulnerability_keywords: Optional[list[str]] = None) -> list[tuple[SearchIndex, float]]:
        try:
            keywords = vulnerability_keywords or ["cve", "critical", "high", "vulnerability", "security"]
            results: list[tuple[SearchIndex, float]] = []
            for idx in self._indices.values():
                score = sum(1 for kw in keywords if kw in idx.content.lower() or kw in str(idx.metadata).lower())
                if score > 0:
                    results.append((idx, score / max(len(keywords), 1)))
            results.sort(key=lambda x: x[1], reverse=True)
            self.telemetry["vulnerability_checks"] += 1
            return results
        except Exception:
            logger.exception("Failed to find vulnerable dependencies")
            raise


class GlobalSearchEngine(
    CrossRepositorySearch, CrossOrganizationSearch, DocumentationSearch,
    ArchitectureSearch, SemanticSearch, DependencySearch
):
    """Unified global search engine combining all search domains."""

    def __init__(self, storage_dir: str):
        CrossRepositorySearch.__init__(self, storage_dir)
        CrossOrganizationSearch.__init__(self, storage_dir)
        DocumentationSearch.__init__(self, storage_dir)
        ArchitectureSearch.__init__(self, storage_dir)
        SemanticSearch.__init__(self, storage_dir)
        DependencySearch.__init__(self, storage_dir)
        self._queries_file = os.path.join(storage_dir, "search_queries.json")
        self._results_file = os.path.join(storage_dir, "search_results.json")
        self._suggestions_file = os.path.join(storage_dir, "search_suggestions.json")
        self._queries: dict[str, SearchQuery] = {}
        self._results: dict[str, SearchResult] = {}
        self._suggestions: dict[str, SearchSuggestion] = {}
        self._analytics: SearchAnalytics = SearchAnalytics()
        self.telemetry: dict = defaultdict(int)
        self._lock = threading.Lock()
        self._load_queries()
        self._load_results()
        self._load_suggestions()
        self._load_analytics()
        logger.info("GlobalSearchEngine initialized at %s", storage_dir)

    def _load_queries(self) -> None:
        try:
            if os.path.exists(self._queries_file):
                with open(self._queries_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._queries = {k: SearchQuery.from_dict(v) for k, v in data.items()}
        except Exception:
            logger.exception("Failed to load search queries; starting fresh")
            self._queries = {}

    def _save_queries(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._queries.items()}
            tmp = self._queries_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._queries_file)
        except Exception:
            logger.exception("Failed to save search queries")

    def _load_results(self) -> None:
        try:
            if os.path.exists(self._results_file):
                with open(self._results_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._results = {k: SearchResult.from_dict(v) for k, v in data.items()}
        except Exception:
            logger.exception("Failed to load search results; starting fresh")
            self._results = {}

    def _save_results(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._results.items()}
            tmp = self._results_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._results_file)
        except Exception:
            logger.exception("Failed to save search results")

    def _load_suggestions(self) -> None:
        try:
            if os.path.exists(self._suggestions_file):
                with open(self._suggestions_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._suggestions = {k: SearchSuggestion.from_dict(v) for k, v in data.items()}
        except Exception:
            logger.exception("Failed to load suggestions; starting fresh")
            self._suggestions = {}

    def _save_suggestions(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._suggestions.items()}
            tmp = self._suggestions_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._suggestions_file)
        except Exception:
            logger.exception("Failed to save suggestions")

    def _load_analytics(self) -> None:
        try:
            analytics_file = os.path.join(self.storage_dir, "search_analytics.json")
            if os.path.exists(analytics_file):
                with open(analytics_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._analytics = SearchAnalytics.from_dict(data)
        except Exception:
            logger.exception("Failed to load search analytics; starting fresh")
            self._analytics = SearchAnalytics()

    def _save_analytics(self) -> None:
        try:
            analytics_file = os.path.join(self.storage_dir, "search_analytics.json")
            tmp = analytics_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._analytics.to_dict(), fh, indent=2, default=str)
            os.replace(tmp, analytics_file)
        except Exception:
            logger.exception("Failed to save search analytics")

    def search_all(self, query_text: str,
                   org_id: Optional[str] = None,
                   workspace_id: Optional[str] = None,
                   project_id: Optional[str] = None,
                   repository_id: Optional[str] = None,
                   limit: int = 20) -> dict[str, list[tuple[SearchIndex, float]]]:
        try:
            start = time.time()
            with self._lock:
                q = SearchQuery(
                    id=str(uuid.uuid4()),
                    query_text=query_text,
                    search_type=SearchType.FULL_TEXT,
                    scope=SearchScope.GLOBAL,
                    org_id=org_id,
                    workspace_id=workspace_id,
                    project_id=project_id,
                    repository_id=repository_id,
                    limit=limit,
                    created_at=datetime.now(timezone.utc).isoformat(),
                )
                self._queries[q.id] = q
                self._save_queries()

            results = {
                "cross_repo": self.search_across_repos(query_text, org_id=org_id, limit=limit),
                "cross_org": self.search_across_orgs(query_text, limit=limit),
                "documentation": self.search_docs(query_text, limit=limit),
                "architecture": self.search_architecture(query_text, limit=limit),
                "semantic": self.search_by_concept(query_text, limit=limit),
                "dependencies": self.search_dependencies(query_text, limit=limit),
            }
            elapsed = (time.time() - start) * 1000
            with self._lock:
                self._analytics.total_searches += 1
                self._analytics.avg_response_time_ms = (
                    (self._analytics.avg_response_time_ms * (self._analytics.total_searches - 1) + elapsed)
                    / self._analytics.total_searches
                )
                self._analytics.search_type_breakdown["full_text"] = self._analytics.search_type_breakdown.get("full_text", 0) + 1
                top = [(q.query_text, 1) for q in self._queries.values()]
                query_counts: dict[str, int] = defaultdict(int)
                for q in self._queries.values():
                    query_counts[q.query_text] += 1
                self._analytics.top_queries = sorted(query_counts.items(), key=lambda x: x[1], reverse=True)[:10]
                total_results = sum(len(v) for v in results.values())
                if total_results == 0:
                    self._analytics.zero_result_queries.append(query_text)
                self._save_analytics()

            self.telemetry["searches_performed"] += 1
            logger.info("Global search '%s' returned %d total results in %.0fms",
                        query_text, total_results, elapsed)
            return results
        except Exception:
            logger.exception("Failed to perform global search")
            raise

    def search_multi_type(self, query_text: str, search_types: list[SearchType],
                          limit: int = 20) -> dict[str, list[tuple[SearchIndex, float]]]:
        try:
            results = {}
            for st in search_types:
                if st == SearchType.CROSS_REPO:
                    results["cross_repo"] = self.search_across_repos(query_text, limit=limit)
                elif st == SearchType.CROSS_ORG:
                    results["cross_org"] = self.search_across_orgs(query_text, limit=limit)
                elif st == SearchType.DOCUMENTATION:
                    results["documentation"] = self.search_docs(query_text, limit=limit)
                elif st == SearchType.ARCHITECTURE:
                    results["architecture"] = self.search_architecture(query_text, limit=limit)
                elif st == SearchType.SEMANTIC:
                    results["semantic"] = self.search_by_concept(query_text, limit=limit)
                elif st == SearchType.DEPENDENCY:
                    results["dependencies"] = self.search_dependencies(query_text, limit=limit)
                elif st == SearchType.CODE:
                    results["code"] = self.search_across_repos(query_text, limit=limit)
                else:
                    results[st.value] = self.search_across_repos(query_text, limit=limit)
            self.telemetry["multi_type_searches"] += 1
            return results
        except Exception:
            logger.exception("Failed to perform multi-type search")
            raise

    def get_search_analytics(self) -> SearchAnalytics:
        try:
            self.telemetry["analytics_requests"] += 1
            return self._analytics
        except Exception:
            logger.exception("Failed to get search analytics")
            raise

    def rebuild_index(self) -> dict[str, int]:
        try:
            counts: dict[str, int] = defaultdict(int)
            for idx in self._indices.values():
                counts[idx.source_type] += 1
            logger.info("Rebuild index: %s", dict(counts))
            self.telemetry["index_rebuilds"] += 1
            return dict(counts)
        except Exception:
            logger.exception("Failed to rebuild index")
            raise

    def get_trending_searches(self, top_n: int = 10) -> list[tuple[str, int]]:
        try:
            query_counts: dict[str, int] = defaultdict(int)
            for q in self._queries.values():
                query_counts[q.query_text] += 1
            trending = sorted(query_counts.items(), key=lambda x: x[1], reverse=True)[:top_n]
            self.telemetry["trending_requests"] += 1
            return trending
        except Exception:
            logger.exception("Failed to get trending searches")
            raise

    def get_search_suggestions(self, prefix: str, limit: int = 5) -> list[SearchSuggestion]:
        try:
            matching: list[SearchSuggestion] = []
            for s in self._suggestions.values():
                if s.query.lower().startswith(prefix.lower()):
                    matching.append(s)
            suggestions = sorted(matching, key=lambda x: (x.score, x.frequency), reverse=True)[:limit]
            if not suggestions:
                query_matches = [q.query_text for q in self._queries.values()
                                 if q.query_text.lower().startswith(prefix.lower())]
                seen: set[str] = set()
                for qm in query_matches:
                    if qm not in seen:
                        suggestions.append(SearchSuggestion(query=qm, score=0.5, frequency=1, category="query"))
                        seen.add(qm)
                        if len(suggestions) >= limit:
                            break
            self.telemetry["suggestion_requests"] += 1
            return suggestions
        except Exception:
            logger.exception("Failed to get search suggestions")
            raise
