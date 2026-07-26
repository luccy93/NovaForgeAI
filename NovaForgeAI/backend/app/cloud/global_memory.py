import logging
import json
import uuid
import hashlib
import os
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class MemoryDomain(Enum):
    REPOSITORY = "repository"
    WORKSPACE = "workspace"
    ORGANIZATION = "organization"
    AI = "ai"
    ARCHITECTURE = "architecture"
    DECISION = "decision"
    ENGINEERING = "engineering"
    KNOWLEDGE = "knowledge"
    HISTORICAL = "historical"


class MemoryVisibility(Enum):
    PRIVATE = "private"
    WORKSPACE = "workspace"
    ORGANIZATION = "organization"
    GLOBAL = "global"


class MemoryImportance(Enum):
    LOW = 1
    MEDIUM = 5
    HIGH = 10
    CRITICAL = 20


def _resolve_enum(val, enum_cls):
    if isinstance(val, enum_cls):
        return val
    if isinstance(val, str):
        for m in enum_cls:
            if m.value == val or m.name == val:
                return m
    if isinstance(val, int):
        for m in enum_cls:
            if m.value == val:
                return m
    return list(enum_cls)[0]


@dataclass
class Memory:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    domain: MemoryDomain = MemoryDomain.KNOWLEDGE
    key: str = ""
    value: Any = None
    summary: str = ""
    importance: MemoryImportance = MemoryImportance.MEDIUM
    visibility: MemoryVisibility = MemoryVisibility.PRIVATE
    org_id: str = ""
    workspace_id: Optional[str] = None
    repository_id: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    accessed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    access_count: int = 0
    ttl_seconds: Optional[int] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["domain"] = self.domain.value
        d["importance"] = self.importance.value
        d["visibility"] = self.visibility.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Memory":
        clean = {}
        for k in cls.__dataclass_fields__:
            if k not in data:
                continue
            clean[k] = data[k]
        if "domain" in data:
            clean["domain"] = _resolve_enum(data["domain"], MemoryDomain)
        if "importance" in data:
            clean["importance"] = _resolve_enum(data["importance"], MemoryImportance)
        if "visibility" in data:
            clean["visibility"] = _resolve_enum(data["visibility"], MemoryVisibility)
        return cls(**clean)

    def touch(self):
        self.accessed_at = datetime.now(timezone.utc).isoformat()
        self.access_count += 1

    def is_expired(self) -> bool:
        if self.ttl_seconds is None:
            return False
        created = datetime.fromisoformat(self.created_at)
        return (datetime.now(timezone.utc) - created).total_seconds() >= self.ttl_seconds


@dataclass
class MemoryQuery:
    domains: list[MemoryDomain] = field(default_factory=list)
    query_text: str = ""
    filters: dict = field(default_factory=dict)
    limit: int = 50
    min_importance: MemoryImportance = MemoryImportance.LOW
    include_expired: bool = False


@dataclass
class MemoryStats:
    domain: MemoryDomain = MemoryDomain.KNOWLEDGE
    total_entries: int = 0
    total_size_bytes: int = 0
    avg_importance: float = 0.0
    most_accessed: list = field(default_factory=list)
    oldest_entries: int = 0
    newest_entries: int = 0


@dataclass
class MemoryLink:
    source_id: str = ""
    target_id: str = ""
    relationship: str = ""
    strength: float = 0.5
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryLink":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class MemorySnapshot:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    domain: MemoryDomain = MemoryDomain.KNOWLEDGE
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    entries: list = field(default_factory=list)
    size_bytes: int = 0
    checksum: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["domain"] = self.domain.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "MemorySnapshot":
        clean = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        if "domain" in data:
            clean["domain"] = _resolve_enum(data["domain"], MemoryDomain)
        return cls(**clean)


class _DomainStore:
    def __init__(self, domain: MemoryDomain, storage_dir: str):
        self.domain = domain
        self.storage_dir = storage_dir
        self.memories: dict[str, Memory] = {}
        self.links: dict[str, list[MemoryLink]] = defaultdict(list)
        self.telemetry: dict = defaultdict(int)
        os.makedirs(storage_dir, exist_ok=True)

    @property
    def store_path(self) -> str:
        return os.path.join(self.storage_dir, f"{self.domain.value}_memories.json")

    @property
    def links_path(self) -> str:
        return os.path.join(self.storage_dir, f"{self.domain.value}_links.json")

    def save(self):
        try:
            data = {mid: mem.to_dict() for mid, mem in self.memories.items()}
            with open(self.store_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
            links_data = {sid: [lnk.to_dict() for lnk in lnks] for sid, lnks in self.links.items()}
            with open(self.links_path, "w", encoding="utf-8") as f:
                json.dump(links_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save domain store %s: %s", self.domain.value, e)

    def load(self):
        try:
            if os.path.exists(self.store_path):
                with open(self.store_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for mid, mem_dict in data.items():
                    try:
                        self.memories[mid] = Memory.from_dict(mem_dict)
                    except Exception as e:
                        logger.warning("Skipping corrupted memory %s: %s", mid, e)
        except Exception as e:
            logger.error("Failed to load domain store %s: %s", self.domain.value, e)


class _MemoryBase:
    def __init__(self, storage_dir: str, domain: MemoryDomain):
        if not hasattr(self, "_domain_stores"):
            self._domain_stores: dict[str, _DomainStore] = {}
            self._base_storage_dir = storage_dir
            os.makedirs(storage_dir, exist_ok=True)
        if domain.value not in self._domain_stores:
            domain_dir = os.path.join(storage_dir, domain.value)
            store = _DomainStore(domain, domain_dir)
            store.load()
            self._domain_stores[domain.value] = store

    @property
    def _store(self) -> _DomainStore:
        return self._domain_stores.get(self._current_domain.value)
    
    def _store_memory(self, memory: Memory) -> Memory:
        memory.updated_at = datetime.now(timezone.utc).isoformat()
        store = self._domain_stores[memory.domain.value]
        store.memories[memory.id] = memory
        store.save()
        store.telemetry["stored"] += 1
        return memory

    def _recall(self, memory_id: str, domain: Optional[MemoryDomain] = None) -> Optional[Memory]:
        for d, store in self._domain_stores.items():
            if domain and d != domain.value:
                continue
            mem = store.memories.get(memory_id)
            if mem and not mem.is_expired():
                mem.touch()
                store.telemetry["recalled"] += 1
                return mem
            if mem and mem.is_expired():
                store.telemetry["expired_hits"] += 1
        return None

    def _forget(self, memory_id: str, domain: Optional[MemoryDomain] = None) -> bool:
        for d, store in self._domain_stores.items():
            if domain and d != domain.value:
                continue
            if memory_id in store.memories:
                del store.memories[memory_id]
                store.links.pop(memory_id, None)
                store.save()
                store.telemetry["forgotten"] += 1
                return True
        return False

    def _list(self, domain: Optional[MemoryDomain] = None, limit: int = 100, offset: int = 0) -> list[Memory]:
        items = []
        for d, store in self._domain_stores.items():
            if domain and d != domain.value:
                continue
            for mem in store.memories.values():
                if not mem.is_expired():
                    items.append(mem)
        items.sort(key=lambda x: x.updated_at, reverse=True)
        return items[offset:offset + limit]

    def _search(self, query: MemoryQuery) -> list[Memory]:
        results = []
        for d, store in self._domain_stores.items():
            if query.domains and d not in [dm.value for dm in query.domains]:
                continue
            for mem in store.memories.values():
                if mem.is_expired() and not query.include_expired:
                    continue
                if mem.importance.value < query.min_importance.value:
                    continue
                if query.query_text:
                    ql = query.query_text.lower()
                    if ql not in mem.summary.lower() and ql not in mem.key.lower():
                        if isinstance(mem.value, str) and ql not in mem.value.lower():
                            continue
                if query.filters:
                    match = True
                    for k, v in query.filters.items():
                        if k == "tags" and isinstance(v, list):
                            if not all(tag in mem.tags for tag in v):
                                match = False
                                break
                        elif k == "visibility":
                            vis = _resolve_enum(v, MemoryVisibility)
                            if mem.visibility != vis:
                                match = False
                                break
                        elif k == "org_id" and mem.org_id != v:
                            match = False
                            break
                        elif k == "workspace_id" and mem.workspace_id != v:
                            match = False
                            break
                        elif k == "repository_id" and mem.repository_id != v:
                            match = False
                            break
                    if not match:
                        continue
                results.append(mem)
        results.sort(key=lambda x: (x.importance.value, x.access_count), reverse=True)
        return results[:query.limit]

    def _get_stats(self, domain: MemoryDomain) -> MemoryStats:
        store = self._domain_stores.get(domain.value)
        if not store:
            return MemoryStats(domain=domain)
        active = [m for m in store.memories.values() if not m.is_expired()]
        total_bytes = sum(len(json.dumps(m.to_dict(), default=str)) for m in active)
        avg_imp = sum(m.importance.value for m in active) / len(active) if active else 0.0
        sorted_by_access = sorted(active, key=lambda x: x.access_count, reverse=True)
        now = datetime.now(timezone.utc)
        oldest = sum(1 for m in active if (now - datetime.fromisoformat(m.created_at)).days > 30)
        newest = sum(1 for m in active if (now - datetime.fromisoformat(m.created_at)).days < 7)
        return MemoryStats(
            domain=domain, total_entries=len(active), total_size_bytes=int(total_bytes),
            avg_importance=round(avg_imp, 2),
            most_accessed=[m.to_dict() for m in sorted_by_access[:10]],
            oldest_entries=oldest, newest_entries=newest,
        )

    def _get_telemetry(self, domain: MemoryDomain) -> dict:
        store = self._domain_stores.get(domain.value)
        return dict(store.telemetry) if store else {}


class RepositoryMemory(_MemoryBase):
    def __init__(self, storage_dir: str):
        _MemoryBase.__init__(self, storage_dir, MemoryDomain.REPOSITORY)

    def remember_repo(self, key: str, value: Any, summary: str = "", repo_id: str = "", org_id: str = "",
                      importance: MemoryImportance = MemoryImportance.MEDIUM,
                      visibility: MemoryVisibility = MemoryVisibility.WORKSPACE,
                      tags: Optional[list[str]] = None, ttl: Optional[int] = None,
                      metadata: Optional[dict] = None) -> Memory:
        mem = Memory(
            domain=MemoryDomain.REPOSITORY, key=key, value=value, summary=summary or key,
            importance=importance, visibility=visibility,
            org_id=org_id, repository_id=repo_id, tags=tags or [],
            ttl_seconds=ttl, metadata=metadata or {},
        )
        return self._store_memory(mem)

    def recall_repo(self, memory_id: str) -> Optional[Memory]:
        return self._recall(memory_id, domain=MemoryDomain.REPOSITORY)

    def forget_repo(self, memory_id: str) -> bool:
        return self._forget(memory_id, domain=MemoryDomain.REPOSITORY)

    def list_repo_memories(self, repo_id: str, limit: int = 100, offset: int = 0) -> list[Memory]:
        store = self._domain_stores.get(MemoryDomain.REPOSITORY.value)
        if not store:
            return []
        items = [m for m in store.memories.values() if m.repository_id == repo_id and not m.is_expired()]
        items.sort(key=lambda x: x.updated_at, reverse=True)
        return items[offset:offset + limit]

    def search_repo_memories(self, repo_id: str, query_text: str = "", limit: int = 50) -> list[Memory]:
        q = MemoryQuery(domains=[MemoryDomain.REPOSITORY], query_text=query_text, limit=limit, filters={"repository_id": repo_id})
        return self._search(q)

    def get_repo_memory_stats(self, repo_id: str) -> MemoryStats:
        store = self._domain_stores.get(MemoryDomain.REPOSITORY.value)
        if not store:
            return MemoryStats(domain=MemoryDomain.REPOSITORY)
        repo_mems = [m for m in store.memories.values() if m.repository_id == repo_id and not m.is_expired()]
        total_bytes = sum(len(json.dumps(m.to_dict(), default=str)) for m in repo_mems)
        avg_imp = sum(m.importance.value for m in repo_mems) / len(repo_mems) if repo_mems else 0.0
        return MemoryStats(
            domain=MemoryDomain.REPOSITORY, total_entries=len(repo_mems), total_size_bytes=int(total_bytes),
            avg_importance=round(avg_imp, 2),
            most_accessed=sorted((m.to_dict() for m in repo_mems), key=lambda x: x["access_count"], reverse=True)[:10],
            oldest_entries=sum(1 for m in repo_mems if (datetime.now(timezone.utc) - datetime.fromisoformat(m.created_at)).days > 30),
            newest_entries=sum(1 for m in repo_mems if (datetime.now(timezone.utc) - datetime.fromisoformat(m.created_at)).days < 7),
        )


class WorkspaceMemory(_MemoryBase):
    def __init__(self, storage_dir: str):
        _MemoryBase.__init__(self, storage_dir, MemoryDomain.WORKSPACE)

    def remember_workspace(self, key: str, value: Any, summary: str = "", workspace_id: str = "", org_id: str = "",
                           importance: MemoryImportance = MemoryImportance.MEDIUM,
                           visibility: MemoryVisibility = MemoryVisibility.WORKSPACE,
                           tags: Optional[list[str]] = None, ttl: Optional[int] = None,
                           metadata: Optional[dict] = None) -> Memory:
        mem = Memory(
            domain=MemoryDomain.WORKSPACE, key=key, value=value, summary=summary or key,
            importance=importance, visibility=visibility,
            org_id=org_id, workspace_id=workspace_id, tags=tags or [],
            ttl_seconds=ttl, metadata=metadata or {},
        )
        return self._store_memory(mem)

    def recall_workspace(self, memory_id: str) -> Optional[Memory]:
        return self._recall(memory_id, domain=MemoryDomain.WORKSPACE)

    def forget_workspace(self, memory_id: str) -> bool:
        return self._forget(memory_id, domain=MemoryDomain.WORKSPACE)

    def list_workspace_memories(self, workspace_id: str, limit: int = 100, offset: int = 0) -> list[Memory]:
        store = self._domain_stores.get(MemoryDomain.WORKSPACE.value)
        if not store:
            return []
        items = [m for m in store.memories.values() if m.workspace_id == workspace_id and not m.is_expired()]
        items.sort(key=lambda x: x.updated_at, reverse=True)
        return items[offset:offset + limit]

    def search_workspace_memories(self, workspace_id: str, query_text: str = "", limit: int = 50) -> list[Memory]:
        q = MemoryQuery(domains=[MemoryDomain.WORKSPACE], query_text=query_text, limit=limit, filters={"workspace_id": workspace_id})
        return self._search(q)

    def get_workspace_memory_stats(self, workspace_id: str) -> MemoryStats:
        store = self._domain_stores.get(MemoryDomain.WORKSPACE.value)
        if not store:
            return MemoryStats(domain=MemoryDomain.WORKSPACE)
        mems = [m for m in store.memories.values() if m.workspace_id == workspace_id and not m.is_expired()]
        total_bytes = sum(len(json.dumps(m.to_dict(), default=str)) for m in mems)
        avg_imp = sum(m.importance.value for m in mems) / len(mems) if mems else 0.0
        return MemoryStats(
            domain=MemoryDomain.WORKSPACE, total_entries=len(mems), total_size_bytes=int(total_bytes),
            avg_importance=round(avg_imp, 2),
            most_accessed=sorted((m.to_dict() for m in mems), key=lambda x: x["access_count"], reverse=True)[:10],
            oldest_entries=sum(1 for m in mems if (datetime.now(timezone.utc) - datetime.fromisoformat(m.created_at)).days > 30),
            newest_entries=sum(1 for m in mems if (datetime.now(timezone.utc) - datetime.fromisoformat(m.created_at)).days < 7),
        )


class OrganizationMemory(_MemoryBase):
    def __init__(self, storage_dir: str):
        _MemoryBase.__init__(self, storage_dir, MemoryDomain.ORGANIZATION)

    def remember_org(self, key: str, value: Any, summary: str = "", org_id: str = "",
                     importance: MemoryImportance = MemoryImportance.HIGH,
                     visibility: MemoryVisibility = MemoryVisibility.ORGANIZATION,
                     tags: Optional[list[str]] = None, ttl: Optional[int] = None,
                     metadata: Optional[dict] = None) -> Memory:
        mem = Memory(
            domain=MemoryDomain.ORGANIZATION, key=key, value=value, summary=summary or key,
            importance=importance, visibility=visibility,
            org_id=org_id, tags=tags or [], ttl_seconds=ttl, metadata=metadata or {},
        )
        return self._store_memory(mem)

    def recall_org(self, memory_id: str) -> Optional[Memory]:
        return self._recall(memory_id, domain=MemoryDomain.ORGANIZATION)

    def forget_org(self, memory_id: str) -> bool:
        return self._forget(memory_id, domain=MemoryDomain.ORGANIZATION)

    def list_org_memories(self, org_id: str, limit: int = 100, offset: int = 0) -> list[Memory]:
        store = self._domain_stores.get(MemoryDomain.ORGANIZATION.value)
        if not store:
            return []
        items = [m for m in store.memories.values() if m.org_id == org_id and not m.is_expired()]
        items.sort(key=lambda x: x.updated_at, reverse=True)
        return items[offset:offset + limit]

    def search_org_memories(self, org_id: str, query_text: str = "", limit: int = 50) -> list[Memory]:
        q = MemoryQuery(domains=[MemoryDomain.ORGANIZATION], query_text=query_text, limit=limit, filters={"org_id": org_id})
        return self._search(q)

    def get_org_memory_stats(self, org_id: str) -> MemoryStats:
        store = self._domain_stores.get(MemoryDomain.ORGANIZATION.value)
        if not store:
            return MemoryStats(domain=MemoryDomain.ORGANIZATION)
        mems = [m for m in store.memories.values() if m.org_id == org_id and not m.is_expired()]
        total_bytes = sum(len(json.dumps(m.to_dict(), default=str)) for m in mems)
        avg_imp = sum(m.importance.value for m in mems) / len(mems) if mems else 0.0
        return MemoryStats(
            domain=MemoryDomain.ORGANIZATION, total_entries=len(mems), total_size_bytes=int(total_bytes),
            avg_importance=round(avg_imp, 2),
            most_accessed=sorted((m.to_dict() for m in mems), key=lambda x: x["access_count"], reverse=True)[:10],
            oldest_entries=sum(1 for m in mems if (datetime.now(timezone.utc) - datetime.fromisoformat(m.created_at)).days > 30),
            newest_entries=sum(1 for m in mems if (datetime.now(timezone.utc) - datetime.fromisoformat(m.created_at)).days < 7),
        )


class AIMemory(_MemoryBase):
    def __init__(self, storage_dir: str):
        _MemoryBase.__init__(self, storage_dir, MemoryDomain.AI)

    def remember_ai(self, key: str, value: Any, summary: str = "", org_id: str = "",
                    importance: MemoryImportance = MemoryImportance.MEDIUM,
                    visibility: MemoryVisibility = MemoryVisibility.WORKSPACE,
                    tags: Optional[list[str]] = None, ttl: Optional[int] = None,
                    metadata: Optional[dict] = None) -> Memory:
        mem = Memory(
            domain=MemoryDomain.AI, key=key, value=value, summary=summary or key,
            importance=importance, visibility=visibility,
            org_id=org_id, tags=tags or [], ttl_seconds=ttl, metadata=metadata or {},
        )
        return self._store_memory(mem)

    def recall_ai(self, memory_id: str) -> Optional[Memory]:
        return self._recall(memory_id, domain=MemoryDomain.AI)

    def forget_ai(self, memory_id: str) -> bool:
        return self._forget(memory_id, domain=MemoryDomain.AI)

    def list_ai_memories(self, org_id: str = "", limit: int = 100, offset: int = 0) -> list[Memory]:
        store = self._domain_stores.get(MemoryDomain.AI.value)
        if not store:
            return []
        items = [m for m in store.memories.values() if not m.is_expired()]
        if org_id:
            items = [m for m in items if m.org_id == org_id]
        items.sort(key=lambda x: x.importance.value, reverse=True)
        return items[offset:offset + limit]

    def search_ai_memories(self, query_text: str = "", org_id: str = "", limit: int = 50) -> list[Memory]:
        filters = {}
        if org_id:
            filters["org_id"] = org_id
        q = MemoryQuery(domains=[MemoryDomain.AI], query_text=query_text, limit=limit, filters=filters)
        return self._search(q)

    def reinforce_memory(self, memory_id: str) -> Optional[Memory]:
        store = self._domain_stores.get(MemoryDomain.AI.value)
        if not store:
            return None
        mem = store.memories.get(memory_id)
        if mem and not mem.is_expired():
            levels = sorted([m.value for m in MemoryImportance])
            current_val = mem.importance.value
            idx = levels.index(current_val)
            if idx < len(levels) - 1:
                next_val = levels[idx + 1]
                for imp in MemoryImportance:
                    if imp.value == next_val:
                        mem.importance = imp
                        break
            mem.touch()
            store.save()
            store.telemetry["reinforced"] += 1
            return mem
        return None


class ArchitectureMemory(_MemoryBase):
    def __init__(self, storage_dir: str):
        _MemoryBase.__init__(self, storage_dir, MemoryDomain.ARCHITECTURE)

    def remember_architecture(self, key: str, value: Any, summary: str = "", org_id: str = "",
                              workspace_id: Optional[str] = None,
                              importance: MemoryImportance = MemoryImportance.HIGH,
                              visibility: MemoryVisibility = MemoryVisibility.WORKSPACE,
                              tags: Optional[list[str]] = None, ttl: Optional[int] = None,
                              metadata: Optional[dict] = None) -> Memory:
        mem = Memory(
            domain=MemoryDomain.ARCHITECTURE, key=key, value=value, summary=summary or key,
            importance=importance, visibility=visibility,
            org_id=org_id, workspace_id=workspace_id, tags=tags or [],
            ttl_seconds=ttl, metadata=metadata or {},
        )
        return self._store_memory(mem)

    def recall_architecture(self, memory_id: str) -> Optional[Memory]:
        return self._recall(memory_id, domain=MemoryDomain.ARCHITECTURE)

    def forget_architecture(self, memory_id: str) -> bool:
        return self._forget(memory_id, domain=MemoryDomain.ARCHITECTURE)

    def list_architecture_memories(self, org_id: str = "", workspace_id: Optional[str] = None,
                                   limit: int = 100, offset: int = 0) -> list[Memory]:
        store = self._domain_stores.get(MemoryDomain.ARCHITECTURE.value)
        if not store:
            return []
        items = [m for m in store.memories.values() if not m.is_expired()]
        if org_id:
            items = [m for m in items if m.org_id == org_id]
        if workspace_id:
            items = [m for m in items if m.workspace_id == workspace_id]
        items.sort(key=lambda x: x.updated_at, reverse=True)
        return items[offset:offset + limit]

    def search_architecture(self, query_text: str = "", org_id: str = "", limit: int = 50) -> list[Memory]:
        filters = {}
        if org_id:
            filters["org_id"] = org_id
        q = MemoryQuery(domains=[MemoryDomain.ARCHITECTURE], query_text=query_text, limit=limit, filters=filters)
        return self._search(q)


class DecisionMemory(_MemoryBase):
    def __init__(self, storage_dir: str):
        _MemoryBase.__init__(self, storage_dir, MemoryDomain.DECISION)

    def remember_decision(self, key: str, value: Any, summary: str = "", org_id: str = "",
                          workspace_id: Optional[str] = None,
                          importance: MemoryImportance = MemoryImportance.HIGH,
                          visibility: MemoryVisibility = MemoryVisibility.WORKSPACE,
                          tags: Optional[list[str]] = None, ttl: Optional[int] = None,
                          metadata: Optional[dict] = None) -> Memory:
        mem = Memory(
            domain=MemoryDomain.DECISION, key=key, value=value, summary=summary or key,
            importance=importance, visibility=visibility,
            org_id=org_id, workspace_id=workspace_id, tags=tags or [],
            ttl_seconds=ttl, metadata=metadata or {},
        )
        return self._store_memory(mem)

    def recall_decision(self, memory_id: str) -> Optional[Memory]:
        return self._recall(memory_id, domain=MemoryDomain.DECISION)

    def forget_decision(self, memory_id: str) -> bool:
        return self._forget(memory_id, domain=MemoryDomain.DECISION)

    def list_decisions(self, org_id: str = "", workspace_id: Optional[str] = None,
                       limit: int = 100, offset: int = 0) -> list[Memory]:
        store = self._domain_stores.get(MemoryDomain.DECISION.value)
        if not store:
            return []
        items = [m for m in store.memories.values() if not m.is_expired()]
        if org_id:
            items = [m for m in items if m.org_id == org_id]
        if workspace_id:
            items = [m for m in items if m.workspace_id == workspace_id]
        items.sort(key=lambda x: x.created_at, reverse=True)
        return items[offset:offset + limit]

    def search_decisions(self, query_text: str = "", org_id: str = "", limit: int = 50) -> list[Memory]:
        filters = {}
        if org_id:
            filters["org_id"] = org_id
        q = MemoryQuery(domains=[MemoryDomain.DECISION], query_text=query_text, limit=limit, filters=filters)
        return self._search(q)

    def get_decision_timeline(self, org_id: str = "", workspace_id: Optional[str] = None,
                              limit: int = 200) -> list[dict]:
        store = self._domain_stores.get(MemoryDomain.DECISION.value)
        if not store:
            return []
        items = [m for m in store.memories.values() if not m.is_expired()]
        if org_id:
            items = [m for m in items if m.org_id == org_id]
        if workspace_id:
            items = [m for m in items if m.workspace_id == workspace_id]
        items.sort(key=lambda x: x.created_at)
        return [
            {
                "id": m.id, "key": m.key, "summary": m.summary,
                "timestamp": m.created_at, "importance": m.importance.value,
                "tags": m.tags, "metadata": m.metadata,
            }
            for m in items[-limit:]
        ]


class GlobalMemoryManager(RepositoryMemory, WorkspaceMemory, OrganizationMemory,
                          AIMemory, ArchitectureMemory, DecisionMemory):
    def __init__(self, storage_dir: str):
        os.makedirs(storage_dir, exist_ok=True)
        RepositoryMemory.__init__(self, storage_dir)
        WorkspaceMemory.__init__(self, storage_dir)
        OrganizationMemory.__init__(self, storage_dir)
        AIMemory.__init__(self, storage_dir)
        ArchitectureMemory.__init__(self, storage_dir)
        DecisionMemory.__init__(self, storage_dir)
        self._snapshots: dict[str, MemorySnapshot] = {}
        self._all_links: dict[str, list[MemoryLink]] = defaultdict(list)
        self._global_telemetry: dict = defaultdict(int)
        self._snapshots_path = os.path.join(storage_dir, "snapshots.json")
        self._links_global_path = os.path.join(storage_dir, "global_links.json")
        self._load_snapshots()
        self._load_global_links()

    def _load_snapshots(self):
        try:
            if os.path.exists(self._snapshots_path):
                with open(self._snapshots_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for sid, sd in data.items():
                    try:
                        self._snapshots[sid] = MemorySnapshot.from_dict(sd)
                    except Exception:
                        pass
        except Exception as e:
            logger.error("Failed to load snapshots: %s", e)

    def _save_snapshots(self):
        try:
            data = {sid: snap.to_dict() for sid, snap in self._snapshots.items()}
            with open(self._snapshots_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save snapshots: %s", e)

    def _save_global_links(self):
        try:
            data = {sid: [lnk.to_dict() for lnk in lnks] for sid, lnks in self._all_links.items()}
            with open(self._links_global_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save global links: %s", e)

    def _load_global_links(self):
        try:
            if os.path.exists(self._links_global_path):
                with open(self._links_global_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for sid, lnks in data.items():
                    self._all_links[sid] = [MemoryLink.from_dict(ld) for ld in lnks]
        except Exception as e:
            logger.error("Failed to load global links: %s", e)

    def store(self, memory: Memory) -> Memory:
        return self._store_memory(memory)

    def recall(self, memory_id: str, domain: Optional[MemoryDomain] = None) -> Optional[Memory]:
        return self._recall(memory_id, domain=domain)

    def search(self, query: MemoryQuery) -> list[Memory]:
        return self._search(query)

    def forget(self, memory_id: str) -> bool:
        return self._forget(memory_id)

    def get_all_stats(self) -> dict[str, MemoryStats]:
        stats = {}
        for d in MemoryDomain:
            s = self._get_stats(d)
            if s.total_entries > 0 or d in (MemoryDomain.REPOSITORY, MemoryDomain.WORKSPACE,
                                             MemoryDomain.ORGANIZATION, MemoryDomain.AI,
                                             MemoryDomain.ARCHITECTURE, MemoryDomain.DECISION):
                stats[d.value] = s
        return stats

    def link_memories(self, source_id: str, target_id: str, relationship: str,
                      strength: float = 0.5) -> Optional[MemoryLink]:
        source = self.recall(source_id)
        target = self.recall(target_id)
        if not source or not target:
            logger.warning("Cannot link: one or both memories not found (%s, %s)", source_id, target_id)
            return None
        link = MemoryLink(source_id=source_id, target_id=target_id, relationship=relationship, strength=strength)
        self._all_links[source_id].append(link)
        self._save_global_links()
        self._global_telemetry["links_created"] += 1
        return link

    def consolidate_memories(self, target_domain: MemoryDomain = MemoryDomain.KNOWLEDGE,
                             min_importance: MemoryImportance = MemoryImportance.MEDIUM,
                             max_age_hours: int = 24) -> int:
        consolidated = 0
        cutoff_ts = datetime.now(timezone.utc).timestamp() - (max_age_hours * 3600)
        target_store = self._domain_stores.get(target_domain.value)
        if not target_store:
            target_store = _DomainStore(target_domain, os.path.join(self._base_storage_dir, target_domain.value))
            self._domain_stores[target_domain.value] = target_store
        for d, store in self._domain_stores.items():
            if d == target_domain.value:
                continue
            for mem in list(store.memories.values()):
                if mem.importance.value < min_importance.value:
                    continue
                created_ts = datetime.fromisoformat(mem.created_at).timestamp()
                if created_ts < cutoff_ts:
                    continue
                knowledge_mem = Memory(
                    domain=target_domain, key=mem.key, value=mem.value, summary=mem.summary,
                    importance=mem.importance, visibility=mem.visibility,
                    org_id=mem.org_id, workspace_id=mem.workspace_id, repository_id=mem.repository_id,
                    tags=list(set(mem.tags + ["consolidated"])), ttl_seconds=mem.ttl_seconds,
                    metadata={**mem.metadata, "source_id": mem.id, "source_domain": mem.domain.value,
                              "consolidated_at": datetime.now(timezone.utc).isoformat()},
                )
                target_store.memories[knowledge_mem.id] = knowledge_mem
                consolidated += 1
                self._global_telemetry["consolidated"] += 1
        if consolidated:
            target_store.save()
        return consolidated

    def create_snapshot(self, domain: Optional[MemoryDomain] = None) -> MemorySnapshot:
        entries = []
        for d, store in self._domain_stores.items():
            if domain and d != domain.value:
                continue
            for mem in store.memories.values():
                if not mem.is_expired():
                    entries.append(mem.to_dict())
        serialized = json.dumps(entries, default=str, sort_keys=True)
        snapshot = MemorySnapshot(
            domain=domain or MemoryDomain.KNOWLEDGE,
            entries=entries,
            size_bytes=len(serialized.encode("utf-8")),
            checksum=hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        )
        self._snapshots[snapshot.id] = snapshot
        self._save_snapshots()
        self._global_telemetry["snapshots_created"] += 1
        return snapshot

    def get_global_telemetry(self) -> dict:
        telem = dict(self._global_telemetry)
        for d, store in self._domain_stores.items():
            for k, v in store.telemetry.items():
                telem[f"{d}_{k}"] = telem.get(f"{d}_{k}", 0) + v
        return telem
