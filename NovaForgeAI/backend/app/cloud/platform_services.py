"""
Platform Services — Repository, Search, Embedding, Agent, Chat, Analytics, Security, Deployment, Marketplace, Plugin, Notification.
"""
import logging
logger = logging.getLogger(__name__)

from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
import json, uuid, hashlib, time, os
from collections import defaultdict


class ServiceType(Enum):
    REPOSITORY = "repository"
    SEARCH = "search"
    EMBEDDING = "embedding"
    AGENT = "agent"
    CHAT = "chat"
    ANALYTICS = "analytics"
    SECURITY = "security"
    DEPLOYMENT = "deployment"
    MARKETPLACE = "marketplace"
    PLUGIN = "plugin"
    NOTIFICATION = "notification"


class ServiceTier(Enum):
    FREE = "free"
    BASIC = "basic"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"
    CUSTOM = "custom"


class IntegrationStatus(Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"
    PENDING_CONFIG = "pending_config"
    DEPRECATED = "deprecated"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ServiceConfig:
    id: str
    service_type: ServiceType
    org_id: str
    workspace_id: Optional[str]
    tier: ServiceTier
    enabled: bool
    settings: dict = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    version: str = "1.0.0"
    endpoint: str = ""
    api_key: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["service_type"] = self.service_type.value
        d["tier"] = self.tier.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "ServiceConfig":
        data = dict(data)
        data["service_type"] = ServiceType(data["service_type"])
        data["tier"] = ServiceTier(data["tier"])
        return ServiceConfig(**data)


@dataclass
class ServiceEndpoint:
    id: str
    service_type: ServiceType
    name: str
    url: str
    health_endpoint: str
    status: str = "active"
    version: str = "1.0.0"
    region: str = "us-east-1"
    capacity: int = 100
    current_load: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["service_type"] = self.service_type.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "ServiceEndpoint":
        data = dict(data)
        data["service_type"] = ServiceType(data["service_type"])
        return ServiceEndpoint(**data)


@dataclass
class Integration:
    id: str
    name: str
    service_type: ServiceType
    provider: str
    config: dict = field(default_factory=dict)
    status: IntegrationStatus = IntegrationStatus.PENDING_CONFIG
    created_at: str = ""
    last_sync: str = ""
    sync_frequency: str = "hourly"
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["service_type"] = self.service_type.value
        d["status"] = self.status.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "Integration":
        data = dict(data)
        data["service_type"] = ServiceType(data["service_type"])
        data["status"] = IntegrationStatus(data["status"])
        return Integration(**data)


@dataclass
class ProviderPlugin:
    id: str
    name: str
    plugin_type: str
    version: str
    description: str = ""
    enabled: bool = True
    config_schema: dict = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "ProviderPlugin":
        return ProviderPlugin(**data)


@dataclass
class NotificationChannel:
    id: str
    channel_type: str
    name: str
    config: dict = field(default_factory=dict)
    enabled: bool = True
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "NotificationChannel":
        return NotificationChannel(**data)


# ---------------------------------------------------------------------------
# Managers
# ---------------------------------------------------------------------------

class RepositoryService:
    """Repository service with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._repos_file = os.path.join(storage_dir, "repositories.json")
        self._repos: dict[str, dict] = {}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._repos_file):
                with open(self._repos_file, "r", encoding="utf-8") as fh:
                    self._repos = json.load(fh)
                logger.info("Loaded %d repositories", len(self._repos))
        except Exception:
            logger.exception("Failed to load repositories; starting fresh")
            self._repos = {}

    def _save(self) -> None:
        try:
            tmp = self._repos_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._repos, fh, indent=2, default=str)
            os.replace(tmp, self._repos_file)
        except Exception:
            logger.exception("Failed to save repositories")

    def create_repository(self, name: str, org_id: str, workspace_id: str,
                           project_id: str, description: str = "",
                           is_private: bool = True) -> dict:
        try:
            for r in self._repos.values():
                if r["name"] == name and r["org_id"] == org_id:
                    raise ValueError(f"Repository '{name}' already exists in org '{org_id}'")
            now = datetime.now(timezone.utc).isoformat()
            repo = {
                "id": str(uuid.uuid4()),
                "name": name,
                "org_id": org_id,
                "workspace_id": workspace_id,
                "project_id": project_id,
                "description": description,
                "is_private": is_private,
                "default_branch": "main",
                "created_at": now,
                "updated_at": now,
                "stars": 0,
                "forks": 0,
                "size_bytes": 0,
            }
            self._repos[repo["id"]] = repo
            self._save()
            self.telemetry["repositories_created"] += 1
            logger.info("Created repository %s (%s)", repo["id"], name)
            return repo
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to create repository")
            raise

    def get_repository(self, repo_id: str) -> dict:
        repo = self._repos.get(repo_id)
        if repo is None:
            raise ValueError(f"Repository not found: {repo_id}")
        self.telemetry["repositories_read"] += 1
        return repo

    def fork_repository(self, repo_id: str, target_org_id: str) -> dict:
        try:
            source = self.get_repository(repo_id)
            now = datetime.now(timezone.utc).isoformat()
            fork = dict(source)
            fork["id"] = str(uuid.uuid4())
            fork["org_id"] = target_org_id
            fork["created_at"] = now
            fork["updated_at"] = now
            fork["name"] = f"{source['name']}-fork"
            fork["forks"] = 0
            fork["stars"] = 0
            fork["forked_from"] = repo_id
            self._repos[fork["id"]] = fork
            source["forks"] = source.get("forks", 0) + 1
            self._repos[repo_id] = source
            self._save()
            self.telemetry["repositories_forked"] += 1
            logger.info("Forked repository %s to org %s as %s", repo_id, target_org_id, fork["id"])
            return fork
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to fork repository %s", repo_id)
            raise

    def list_repositories(self, org_id: Optional[str] = None,
                           workspace_id: Optional[str] = None) -> list[dict]:
        try:
            results = list(self._repos.values())
            if org_id is not None:
                results = [r for r in results if r["org_id"] == org_id]
            if workspace_id is not None:
                results = [r for r in results if r["workspace_id"] == workspace_id]
            results.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
            self.telemetry["repositories_listed"] += 1
            return results
        except Exception:
            logger.exception("Failed to list repositories")
            raise

    def search_repositories(self, query: str) -> list[dict]:
        try:
            q = query.lower()
            results = [r for r in self._repos.values()
                       if q in r["name"].lower() or q in r.get("description", "").lower()]
            self.telemetry["repositories_searched"] += 1
            return results
        except Exception:
            logger.exception("Failed to search repositories")
            raise

    def get_repository_stats(self, repo_id: str) -> dict:
        try:
            repo = self.get_repository(repo_id)
            stats = {
                "repo_id": repo_id,
                "name": repo["name"],
                "stars": repo.get("stars", 0),
                "forks": repo.get("forks", 0),
                "size_bytes": repo.get("size_bytes", 0),
                "is_private": repo.get("is_private", True),
                "default_branch": repo.get("default_branch", "main"),
                "created_at": repo.get("created_at"),
                "updated_at": repo.get("updated_at"),
            }
            self.telemetry["repository_stats_read"] += 1
            return stats
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to get repository stats for %s", repo_id)
            raise


class SearchService:
    """Search service with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._index_file = os.path.join(storage_dir, "search_index.json")
        self._index: dict[str, dict] = {}
        self._stats_file = os.path.join(storage_dir, "search_stats.json")
        self._stats: dict = {"total_documents": 0, "total_searches": 0, "last_indexed": ""}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._index_file):
                with open(self._index_file, "r", encoding="utf-8") as fh:
                    self._index = json.load(fh)
                logger.info("Loaded search index with %d documents", len(self._index))
        except Exception:
            logger.exception("Failed to load search index; starting fresh")
            self._index = {}
        try:
            if os.path.exists(self._stats_file):
                with open(self._stats_file, "r", encoding="utf-8") as fh:
                    self._stats = json.load(fh)
        except Exception:
            self._stats = {"total_documents": 0, "total_searches": 0, "last_indexed": ""}

    def _save(self) -> None:
        try:
            tmp = self._index_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._index, fh, indent=2, default=str)
            os.replace(tmp, self._index_file)
        except Exception:
            logger.exception("Failed to save search index")
        try:
            tmp = self._stats_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._stats, fh, indent=2, default=str)
            os.replace(tmp, self._stats_file)
        except Exception:
            logger.exception("Failed to save search stats")

    def index_content(self, doc_id: str, content: str, metadata: Optional[dict] = None) -> dict:
        try:
            now = datetime.now(timezone.utc).isoformat()
            checksum = hashlib.sha256(content.encode()).hexdigest()[:16]
            doc = {
                "doc_id": doc_id,
                "content": content,
                "metadata": metadata or {},
                "checksum": checksum,
                "indexed_at": now,
                "terms": list(set(content.lower().split())),
            }
            self._index[doc_id] = doc
            self._stats["total_documents"] = len(self._index)
            self._stats["last_indexed"] = now
            self._save()
            self.telemetry["content_indexed"] += 1
            logger.info("Indexed document %s (%d terms)", doc_id, len(doc["terms"]))
            return doc
        except Exception:
            logger.exception("Failed to index content")
            raise

    def search(self, query: str, limit: int = 10) -> list[dict]:
        try:
            q_terms = set(query.lower().split())
            scored = []
            for doc_id, doc in self._index.items():
                matches = len(q_terms & set(doc.get("terms", [])))
                if matches > 0:
                    scored.append({
                        "doc_id": doc_id,
                        "score": matches / max(len(q_terms), 1),
                        "content_snippet": doc.get("content", "")[:200],
                        "metadata": doc.get("metadata", {}),
                        "indexed_at": doc.get("indexed_at"),
                    })
            scored.sort(key=lambda x: x["score"], reverse=True)
            self._stats["total_searches"] += 1
            self._save()
            self.telemetry["searches_performed"] += 1
            return scored[:limit]
        except Exception:
            logger.exception("Failed to search")
            raise

    def search_faceted(self, query: str, facet_field: str, limit: int = 10) -> dict:
        try:
            results = self.search(query, limit=100)
            facets = defaultdict(list)
            for r in results:
                facet_val = r.get("metadata", {}).get(facet_field, "unknown")
                facets[facet_val].append(r)
            facet_counts = {k: len(v) for k, v in facets.items()}
            top_facets = dict(sorted(facet_counts.items(), key=lambda x: x[1], reverse=True)[:limit])
            self.telemetry["faceted_searches_performed"] += 1
            return {
                "query": query,
                "total_results": len(results),
                "facet_field": facet_field,
                "facets": top_facets,
                "results": results[:limit],
            }
        except Exception:
            logger.exception("Failed to perform faceted search")
            raise

    def get_search_stats(self) -> dict:
        self.telemetry["search_stats_read"] += 1
        return dict(self._stats)

    def rebuild_index(self) -> int:
        try:
            count = len(self._index)
            self._stats["total_documents"] = count
            self._stats["last_indexed"] = datetime.now(timezone.utc).isoformat()
            self._save()
            self.telemetry["indexes_rebuilt"] += 1
            logger.info("Rebuilt search index (%d documents)", count)
            return count
        except Exception:
            logger.exception("Failed to rebuild search index")
            raise

    def search_fuzzy(self, query: str, limit: int = 10) -> list[dict]:
        try:
            q = query.lower()
            results = []
            for doc_id, doc in self._index.items():
                content = doc.get("content", "").lower()
                if q in content:
                    results.append({
                        "doc_id": doc_id,
                        "score": 1.0,
                        "content_snippet": content[:200],
                        "metadata": doc.get("metadata", {}),
                    })
            results.sort(key=lambda x: x["score"], reverse=True)
            self.telemetry["fuzzy_searches_performed"] += 1
            return results[:limit]
        except Exception:
            logger.exception("Failed to perform fuzzy search")
            raise


class EmbeddingService:
    """Embedding service with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._embeddings_file = os.path.join(storage_dir, "embeddings.json")
        self._embeddings: dict[str, dict] = {}
        self._stats_file = os.path.join(storage_dir, "embedding_stats.json")
        self._stats: dict = {"total_embeddings": 0, "dimension": 0, "last_updated": ""}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._embeddings_file):
                with open(self._embeddings_file, "r", encoding="utf-8") as fh:
                    self._embeddings = json.load(fh)
                logger.info("Loaded %d embeddings", len(self._embeddings))
        except Exception:
            logger.exception("Failed to load embeddings; starting fresh")
            self._embeddings = {}
        try:
            if os.path.exists(self._stats_file):
                with open(self._stats_file, "r", encoding="utf-8") as fh:
                    self._stats = json.load(fh)
        except Exception:
            self._stats = {"total_embeddings": 0, "dimension": 0, "last_updated": ""}

    def _save(self) -> None:
        try:
            tmp = self._embeddings_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._embeddings, fh, indent=2, default=str)
            os.replace(tmp, self._embeddings_file)
        except Exception:
            logger.exception("Failed to save embeddings")
        try:
            tmp = self._stats_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._stats, fh, indent=2, default=str)
            os.replace(tmp, self._stats_file)
        except Exception:
            logger.exception("Failed to save embedding stats")

    def _simulate_vector(self, dimension: int = 128) -> list[float]:
        seed = str(time.time())
        h = hashlib.sha256(seed.encode()).hexdigest()
        return [round((int(h[i:i+2], 16) / 255.0 - 0.5) * 2, 6) for i in range(0, min(dimension * 2, len(h)), 2)]

    def _cosine_similarity(self, vec_a: list[float], vec_b: list[float]) -> float:
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = sum(a * a for a in vec_a) ** 0.5
        norm_b = sum(b * b for b in vec_b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def create_embedding(self, content: str, dimension: int = 128,
                          metadata: Optional[dict] = None) -> dict:
        try:
            now = datetime.now(timezone.utc).isoformat()
            emb_id = str(uuid.uuid4())
            vector = self._simulate_vector(dimension)
            embedding = {
                "id": emb_id,
                "content": content[:500],
                "vector": vector,
                "dimension": dimension,
                "metadata": metadata or {},
                "created_at": now,
            }
            self._embeddings[emb_id] = embedding
            self._stats["total_embeddings"] = len(self._embeddings)
            self._stats["dimension"] = dimension
            self._stats["last_updated"] = now
            self._save()
            self.telemetry["embeddings_created"] += 1
            logger.info("Created embedding %s (dim=%d)", emb_id, dimension)
            return {"id": emb_id, "dimension": dimension, "created_at": now}
        except Exception:
            logger.exception("Failed to create embedding")
            raise

    def search_similar(self, query_vector: list[float], top_k: int = 10) -> list[dict]:
        try:
            scored = []
            for emb_id, emb in self._embeddings.items():
                sim = self._cosine_similarity(query_vector, emb["vector"])
                scored.append({
                    "id": emb_id,
                    "score": round(sim, 6),
                    "content": emb.get("content", "")[:200],
                    "metadata": emb.get("metadata", {}),
                })
            scored.sort(key=lambda x: x["score"], reverse=True)
            self.telemetry["similarity_searches_performed"] += 1
            return scored[:top_k]
        except Exception:
            logger.exception("Failed to search similar embeddings")
            raise

    def get_embedding_stats(self) -> dict:
        self.telemetry["embedding_stats_read"] += 1
        return dict(self._stats)

    def rebuild_embeddings(self) -> int:
        try:
            count = len(self._embeddings)
            for emb in self._embeddings.values():
                emb["vector"] = self._simulate_vector(emb.get("dimension", 128))
            self._stats["last_updated"] = datetime.now(timezone.utc).isoformat()
            self._save()
            self.telemetry["embeddings_rebuilt"] += 1
            logger.info("Rebuilt %d embeddings", count)
            return count
        except Exception:
            logger.exception("Failed to rebuild embeddings")
            raise

    def batch_create_embeddings(self, items: list[dict]) -> list[dict]:
        try:
            results = []
            for item in items:
                result = self.create_embedding(
                    content=item.get("content", ""),
                    dimension=item.get("dimension", 128),
                    metadata=item.get("metadata"),
                )
                results.append(result)
            self.telemetry["batch_embeddings_created"] += len(results)
            logger.info("Batch created %d embeddings", len(results))
            return results
        except Exception:
            logger.exception("Failed to batch create embeddings")
            raise


class AgentService:
    """Agent service with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._agents_file = os.path.join(storage_dir, "agents.json")
        self._agents: dict[str, dict] = {}
        self._logs_file = os.path.join(storage_dir, "agent_logs.json")
        self._logs: dict[str, list[dict]] = defaultdict(list)
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._agents_file):
                with open(self._agents_file, "r", encoding="utf-8") as fh:
                    self._agents = json.load(fh)
                logger.info("Loaded %d agents", len(self._agents))
        except Exception:
            logger.exception("Failed to load agents; starting fresh")
            self._agents = {}
        try:
            if os.path.exists(self._logs_file):
                with open(self._logs_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._logs = defaultdict(list, data)
        except Exception:
            self._logs = defaultdict(list)

    def _save(self) -> None:
        try:
            tmp = self._agents_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._agents, fh, indent=2, default=str)
            os.replace(tmp, self._agents_file)
        except Exception:
            logger.exception("Failed to save agents")
        try:
            tmp = self._logs_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(dict(self._logs), fh, indent=2, default=str)
            os.replace(tmp, self._logs_file)
        except Exception:
            logger.exception("Failed to save agent logs")

    def create_agent(self, name: str, agent_type: str, org_id: str,
                      workspace_id: str, config: Optional[dict] = None) -> dict:
        try:
            now = datetime.now(timezone.utc).isoformat()
            agent = {
                "id": str(uuid.uuid4()),
                "name": name,
                "agent_type": agent_type,
                "org_id": org_id,
                "workspace_id": workspace_id,
                "config": config or {},
                "status": "idle",
                "created_at": now,
                "updated_at": now,
                "last_executed": "",
                "execution_count": 0,
            }
            self._agents[agent["id"]] = agent
            self._save()
            self.telemetry["agents_created"] += 1
            logger.info("Created agent %s (%s)", agent["id"], name)
            return agent
        except Exception:
            logger.exception("Failed to create agent")
            raise

    def get_agent(self, agent_id: str) -> dict:
        agent = self._agents.get(agent_id)
        if agent is None:
            raise ValueError(f"Agent not found: {agent_id}")
        self.telemetry["agents_read"] += 1
        return agent

    def list_agents(self, org_id: Optional[str] = None,
                     workspace_id: Optional[str] = None,
                     status: Optional[str] = None) -> list[dict]:
        try:
            results = list(self._agents.values())
            if org_id is not None:
                results = [a for a in results if a["org_id"] == org_id]
            if workspace_id is not None:
                results = [a for a in results if a["workspace_id"] == workspace_id]
            if status is not None:
                results = [a for a in results if a["status"] == status]
            self.telemetry["agents_listed"] += 1
            return results
        except Exception:
            logger.exception("Failed to list agents")
            raise

    def execute_agent(self, agent_id: str, input_data: Optional[dict] = None) -> dict:
        try:
            agent = self.get_agent(agent_id)
            now = datetime.now(timezone.utc).isoformat()
            execution_id = str(uuid.uuid4())
            result = {
                "execution_id": execution_id,
                "agent_id": agent_id,
                "status": "completed",
                "input": input_data or {},
                "output": {"result": f"Executed {agent['name']} successfully"},
                "started_at": now,
                "completed_at": now,
                "duration_ms": abs(hash(execution_id)) % 5000 + 100,
            }
            agent["status"] = "idle"
            agent["last_executed"] = now
            agent["execution_count"] = agent.get("execution_count", 0) + 1
            agent["updated_at"] = now
            self._agents[agent_id] = agent
            log_entry = {**result, "agent_name": agent["name"]}
            self._logs[agent_id].append(log_entry)
            if len(self._logs[agent_id]) > 500:
                self._logs[agent_id] = self._logs[agent_id][-500:]
            self._save()
            self.telemetry["agents_executed"] += 1
            logger.info("Executed agent %s (%s)", agent_id, agent["name"])
            return result
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to execute agent %s", agent_id)
            raise

    def pause_agent(self, agent_id: str) -> dict:
        try:
            agent = self.get_agent(agent_id)
            agent["status"] = "paused"
            agent["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._agents[agent_id] = agent
            self._save()
            self.telemetry["agents_paused"] += 1
            logger.info("Paused agent %s", agent_id)
            return agent
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to pause agent %s", agent_id)
            raise

    def resume_agent(self, agent_id: str) -> dict:
        try:
            agent = self.get_agent(agent_id)
            agent["status"] = "idle"
            agent["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._agents[agent_id] = agent
            self._save()
            self.telemetry["agents_resumed"] += 1
            logger.info("Resumed agent %s", agent_id)
            return agent
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to resume agent %s", agent_id)
            raise

    def get_agent_logs(self, agent_id: str, limit: int = 50) -> list[dict]:
        logs = self._logs.get(agent_id, [])
        self.telemetry["agent_logs_read"] += 1
        return logs[-limit:]


class ChatService:
    """Chat service with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._sessions_file = os.path.join(storage_dir, "chat_sessions.json")
        self._sessions: dict[str, dict] = {}
        self._messages_file = os.path.join(storage_dir, "chat_messages.json")
        self._messages: dict[str, list[dict]] = defaultdict(list)
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._sessions_file):
                with open(self._sessions_file, "r", encoding="utf-8") as fh:
                    self._sessions = json.load(fh)
                logger.info("Loaded %d chat sessions", len(self._sessions))
        except Exception:
            logger.exception("Failed to load chat sessions; starting fresh")
            self._sessions = {}
        try:
            if os.path.exists(self._messages_file):
                with open(self._messages_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._messages = defaultdict(list, data)
        except Exception:
            self._messages = defaultdict(list)

    def _save(self) -> None:
        try:
            tmp = self._sessions_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._sessions, fh, indent=2, default=str)
            os.replace(tmp, self._sessions_file)
        except Exception:
            logger.exception("Failed to save chat sessions")
        try:
            tmp = self._messages_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(dict(self._messages), fh, indent=2, default=str)
            os.replace(tmp, self._messages_file)
        except Exception:
            logger.exception("Failed to save chat messages")

    def create_session(self, org_id: str, workspace_id: str,
                        user_id: str, title: str = "") -> dict:
        try:
            now = datetime.now(timezone.utc).isoformat()
            session = {
                "id": str(uuid.uuid4()),
                "org_id": org_id,
                "workspace_id": workspace_id,
                "user_id": user_id,
                "title": title or f"Chat {now[:10]}",
                "status": "active",
                "created_at": now,
                "updated_at": now,
                "message_count": 0,
            }
            self._sessions[session["id"]] = session
            self._save()
            self.telemetry["chat_sessions_created"] += 1
            logger.info("Created chat session %s for user %s", session["id"], user_id)
            return session
        except Exception:
            logger.exception("Failed to create chat session")
            raise

    def send_message(self, session_id: str, role: str, content: str,
                      metadata: Optional[dict] = None) -> dict:
        try:
            session = self._sessions.get(session_id)
            if session is None:
                raise ValueError(f"Chat session not found: {session_id}")
            now = datetime.now(timezone.utc).isoformat()
            msg = {
                "id": str(uuid.uuid4()),
                "session_id": session_id,
                "role": role,
                "content": content,
                "metadata": metadata or {},
                "timestamp": now,
            }
            self._messages[session_id].append(msg)
            session["message_count"] = session.get("message_count", 0) + 1
            session["updated_at"] = now
            self._sessions[session_id] = session
            if len(self._messages[session_id]) > 1000:
                self._messages[session_id] = self._messages[session_id][-1000:]
            self._save()
            self.telemetry["chat_messages_sent"] += 1
            return msg
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to send message")
            raise

    def get_history(self, session_id: str, limit: int = 100) -> list[dict]:
        messages = self._messages.get(session_id, [])
        self.telemetry["chat_history_read"] += 1
        return messages[-limit:]

    def get_active_sessions(self, org_id: Optional[str] = None,
                             user_id: Optional[str] = None) -> list[dict]:
        try:
            results = [s for s in self._sessions.values() if s.get("status") == "active"]
            if org_id is not None:
                results = [s for s in results if s["org_id"] == org_id]
            if user_id is not None:
                results = [s for s in results if s["user_id"] == user_id]
            results.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
            self.telemetry["active_sessions_listed"] += 1
            return results
        except Exception:
            logger.exception("Failed to get active sessions")
            raise

    def close_session(self, session_id: str) -> dict:
        try:
            session = self._sessions.get(session_id)
            if session is None:
                raise ValueError(f"Chat session not found: {session_id}")
            session["status"] = "closed"
            session["updated_at"] = datetime.now(timezone.utc).isoformat()
            self._sessions[session_id] = session
            self._save()
            self.telemetry["chat_sessions_closed"] += 1
            logger.info("Closed chat session %s", session_id)
            return session
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to close chat session %s", session_id)
            raise


class AnalyticsService:
    """Analytics service with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._events_file = os.path.join(storage_dir, "analytics_events.json")
        self._events: list[dict] = []
        self._reports_file = os.path.join(storage_dir, "analytics_reports.json")
        self._reports: dict[str, dict] = {}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._events_file):
                with open(self._events_file, "r", encoding="utf-8") as fh:
                    self._events = json.load(fh)
                logger.info("Loaded %d analytics events", len(self._events))
        except Exception:
            logger.exception("Failed to load analytics events; starting fresh")
            self._events = []
        try:
            if os.path.exists(self._reports_file):
                with open(self._reports_file, "r", encoding="utf-8") as fh:
                    self._reports = json.load(fh)
        except Exception:
            self._reports = {}

    def _save(self) -> None:
        try:
            tmp = self._events_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._events, fh, indent=2, default=str)
            os.replace(tmp, self._events_file)
        except Exception:
            logger.exception("Failed to save analytics events")
        try:
            tmp = self._reports_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._reports, fh, indent=2, default=str)
            os.replace(tmp, self._reports_file)
        except Exception:
            logger.exception("Failed to save analytics reports")

    def track_event(self, event_type: str, org_id: str, user_id: str = "",
                     properties: Optional[dict] = None) -> dict:
        try:
            now = datetime.now(timezone.utc).isoformat()
            event = {
                "id": str(uuid.uuid4()),
                "event_type": event_type,
                "org_id": org_id,
                "user_id": user_id,
                "properties": properties or {},
                "timestamp": now,
            }
            self._events.append(event)
            if len(self._events) > 10000:
                self._events = self._events[-10000:]
            self._save()
            self.telemetry["events_tracked"] += 1
            return event
        except Exception:
            logger.exception("Failed to track event")
            raise

    def get_analytics(self, org_id: str, event_type: Optional[str] = None,
                       start_date: Optional[str] = None,
                       end_date: Optional[str] = None) -> list[dict]:
        try:
            results = [e for e in self._events if e["org_id"] == org_id]
            if event_type is not None:
                results = [e for e in results if e["event_type"] == event_type]
            if start_date is not None:
                results = [e for e in results if e["timestamp"] >= start_date]
            if end_date is not None:
                results = [e for e in results if e["timestamp"] <= end_date]
            results.sort(key=lambda x: x["timestamp"], reverse=True)
            self.telemetry["analytics_read"] += 1
            return results
        except Exception:
            logger.exception("Failed to get analytics")
            raise

    def generate_report(self, org_id: str, report_type: str,
                         period: str = "daily") -> dict:
        try:
            events = self.get_analytics(org_id)
            by_type = defaultdict(int)
            by_user = defaultdict(int)
            for e in events:
                by_type[e["event_type"]] += 1
                if e.get("user_id"):
                    by_user[e["user_id"]] += 1
            report = {
                "id": str(uuid.uuid4()),
                "org_id": org_id,
                "report_type": report_type,
                "period": period,
                "total_events": len(events),
                "unique_users": len(by_user),
                "events_by_type": dict(by_type),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            self._reports[report["id"]] = report
            self._save()
            self.telemetry["reports_generated"] += 1
            return report
        except Exception:
            logger.exception("Failed to generate report")
            raise

    def get_dashboard_data(self, org_id: str) -> dict:
        try:
            events = self.get_analytics(org_id)
            by_type = defaultdict(int)
            by_day = defaultdict(int)
            for e in events:
                by_type[e["event_type"]] += 1
                day = e["timestamp"][:10]
                by_day[day] += 1
            today_events = sum(1 for e in events if e["timestamp"][:10] == datetime.now(timezone.utc).isoformat()[:10])
            dashboard = {
                "org_id": org_id,
                "total_events": len(events),
                "today_events": today_events,
                "events_by_type": dict(by_type),
                "events_by_day": dict(sorted(by_day.items())),
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }
            self.telemetry["dashboard_data_read"] += 1
            return dashboard
        except Exception:
            logger.exception("Failed to get dashboard data")
            raise

    def get_trends(self, org_id: str, metric: str, days: int = 30) -> dict:
        try:
            events = self.get_analytics(org_id)
            cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
            filtered = [e for e in events if e["event_type"] == metric or not metric]
            daily_counts = defaultdict(int)
            for e in filtered:
                try:
                    ts = datetime.fromisoformat(e["timestamp"]).timestamp()
                    if ts >= cutoff:
                        daily_counts[e["timestamp"][:10]] += 1
                except (ValueError, TypeError):
                    continue
            trend_data = dict(sorted(daily_counts.items()))
            values = list(trend_data.values())
            avg = round(sum(values) / len(values), 2) if values else 0
            trend = {
                "org_id": org_id,
                "metric": metric or "all",
                "days": days,
                "daily_counts": trend_data,
                "average": avg,
                "total": sum(values),
            }
            self.telemetry["trends_read"] += 1
            return trend
        except Exception:
            logger.exception("Failed to get trends")
            raise


class SecurityService:
    """Security service with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._scans_file = os.path.join(storage_dir, "security_scans.json")
        self._scans: dict[str, dict] = {}
        self._vulns_file = os.path.join(storage_dir, "vulnerabilities.json")
        self._vulnerabilities: dict[str, dict] = {}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._scans_file):
                with open(self._scans_file, "r", encoding="utf-8") as fh:
                    self._scans = json.load(fh)
                logger.info("Loaded %d security scans", len(self._scans))
        except Exception:
            logger.exception("Failed to load security scans; starting fresh")
            self._scans = {}
        try:
            if os.path.exists(self._vulns_file):
                with open(self._vulns_file, "r", encoding="utf-8") as fh:
                    self._vulnerabilities = json.load(fh)
        except Exception:
            self._vulnerabilities = {}

    def _save(self) -> None:
        try:
            tmp = self._scans_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._scans, fh, indent=2, default=str)
            os.replace(tmp, self._scans_file)
        except Exception:
            logger.exception("Failed to save security scans")
        try:
            tmp = self._vulns_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._vulnerabilities, fh, indent=2, default=str)
            os.replace(tmp, self._vulns_file)
        except Exception:
            logger.exception("Failed to save vulnerabilities")

    def scan_repository(self, repo_id: str, scan_type: str = "full") -> dict:
        try:
            now = datetime.now(timezone.utc).isoformat()
            scan_id = str(uuid.uuid4())
            vuln_count = abs(hash(scan_id)) % 20
            scan = {
                "id": scan_id,
                "repo_id": repo_id,
                "scan_type": scan_type,
                "status": "completed",
                "vulnerabilities_found": vuln_count,
                "critical": vuln_count // 4,
                "high": vuln_count // 3,
                "medium": vuln_count // 3,
                "low": max(0, vuln_count - (vuln_count // 4 + vuln_count // 3 + vuln_count // 3)),
                "started_at": now,
                "completed_at": now,
                "duration_ms": abs(hash(scan_id)) % 30000 + 5000,
            }
            self._scans[scan_id] = scan
            for i in range(vuln_count):
                vid = str(uuid.uuid4())
                severity = ["critical", "high", "medium", "low"][i % 4]
                self._vulnerabilities[vid] = {
                    "id": vid, "scan_id": scan_id, "repo_id": repo_id,
                    "severity": severity,
                    "title": f"Vulnerability {i+1}",
                    "description": f"Simulated {severity} vulnerability found",
                    "status": "open",
                    "found_at": now,
                }
            self._save()
            self.telemetry["scans_performed"] += 1
            logger.info("Scanned repository %s (%d vulns found)", repo_id, vuln_count)
            return scan
        except Exception:
            logger.exception("Failed to scan repository")
            raise

    def get_scan_results(self, scan_id: str) -> dict:
        scan = self._scans.get(scan_id)
        if scan is None:
            raise ValueError(f"Scan not found: {scan_id}")
        vulns = [v for v in self._vulnerabilities.values() if v["scan_id"] == scan_id]
        self.telemetry["scan_results_read"] += 1
        return {"scan": scan, "vulnerabilities": vulns}

    def get_security_score(self, repo_id: str) -> dict:
        try:
            repo_scans = [s for s in self._scans.values() if s["repo_id"] == repo_id]
            repo_vulns = [v for v in self._vulnerabilities.values() if v["repo_id"] == repo_id]
            open_vulns = [v for v in repo_vulns if v["status"] == "open"]
            critical_count = sum(1 for v in open_vulns if v["severity"] == "critical")
            high_count = sum(1 for v in open_vulns if v["severity"] == "high")
            score = max(0, 100 - (critical_count * 25 + high_count * 10 + len(open_vulns) * 2))
            result = {
                "repo_id": repo_id,
                "security_score": min(100, score),
                "total_scans": len(repo_scans),
                "open_vulnerabilities": len(open_vulns),
                "critical": critical_count,
                "high": high_count,
                "last_scan": repo_scans[-1]["completed_at"] if repo_scans else None,
            }
            self.telemetry["security_scores_read"] += 1
            return result
        except Exception:
            logger.exception("Failed to get security score for %s", repo_id)
            raise

    def list_vulnerabilities(self, repo_id: Optional[str] = None,
                              severity: Optional[str] = None,
                              status: Optional[str] = None) -> list[dict]:
        try:
            results = list(self._vulnerabilities.values())
            if repo_id is not None:
                results = [v for v in results if v["repo_id"] == repo_id]
            if severity is not None:
                results = [v for v in results if v["severity"] == severity]
            if status is not None:
                results = [v for v in results if v["status"] == status]
            results.sort(key=lambda x: x.get("found_at", ""), reverse=True)
            self.telemetry["vulnerabilities_listed"] += 1
            return results
        except Exception:
            logger.exception("Failed to list vulnerabilities")
            raise

    def get_compliance_report(self, org_id: str) -> dict:
        try:
            org_scans = [s for s in self._scans.values()]
            org_vulns = [v for v in self._vulnerabilities.values()]
            open_vulns = [v for v in org_vulns if v["status"] == "open"]
            report = {
                "org_id": org_id,
                "total_scans": len(org_scans),
                "total_vulnerabilities": len(org_vulns),
                "open_vulnerabilities": len(open_vulns),
                "critical": sum(1 for v in open_vulns if v["severity"] == "critical"),
                "high": sum(1 for v in open_vulns if v["severity"] == "high"),
                "medium": sum(1 for v in open_vulns if v["severity"] == "medium"),
                "low": sum(1 for v in open_vulns if v["severity"] == "low"),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            self.telemetry["compliance_reports_generated"] += 1
            return report
        except Exception:
            logger.exception("Failed to get compliance report")
            raise


class DeploymentService:
    """Deployment service with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._deployments_file = os.path.join(storage_dir, "deployments.json")
        self._deployments: dict[str, dict] = {}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._deployments_file):
                with open(self._deployments_file, "r", encoding="utf-8") as fh:
                    self._deployments = json.load(fh)
                logger.info("Loaded %d deployments", len(self._deployments))
        except Exception:
            logger.exception("Failed to load deployments; starting fresh")
            self._deployments = {}

    def _save(self) -> None:
        try:
            tmp = self._deployments_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._deployments, fh, indent=2, default=str)
            os.replace(tmp, self._deployments_file)
        except Exception:
            logger.exception("Failed to save deployments")

    def create_deployment(self, repo_id: str, org_id: str, workspace_id: str,
                           environment: str = "production",
                           version: str = "1.0.0",
                           config: Optional[dict] = None) -> dict:
        try:
            now = datetime.now(timezone.utc).isoformat()
            deployment = {
                "id": str(uuid.uuid4()),
                "repo_id": repo_id,
                "org_id": org_id,
                "workspace_id": workspace_id,
                "environment": environment,
                "version": version,
                "config": config or {},
                "status": "pending",
                "created_at": now,
                "updated_at": now,
                "deployed_at": None,
                "rollback_version": None,
            }
            self._deployments[deployment["id"]] = deployment
            self._save()
            self.telemetry["deployments_created"] += 1
            logger.info("Created deployment %s for repo %s (%s)", deployment["id"], repo_id, environment)
            return deployment
        except Exception:
            logger.exception("Failed to create deployment")
            raise

    def get_deployment(self, deployment_id: str) -> dict:
        dep = self._deployments.get(deployment_id)
        if dep is None:
            raise ValueError(f"Deployment not found: {deployment_id}")
        self.telemetry["deployments_read"] += 1
        return dep

    def list_deployments(self, org_id: Optional[str] = None,
                          repo_id: Optional[str] = None,
                          environment: Optional[str] = None) -> list[dict]:
        try:
            results = list(self._deployments.values())
            if org_id is not None:
                results = [d for d in results if d["org_id"] == org_id]
            if repo_id is not None:
                results = [d for d in results if d["repo_id"] == repo_id]
            if environment is not None:
                results = [d for d in results if d["environment"] == environment]
            results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            self.telemetry["deployments_listed"] += 1
            return results
        except Exception:
            logger.exception("Failed to list deployments")
            raise

    def rollback_deployment(self, deployment_id: str) -> dict:
        try:
            dep = self.get_deployment(deployment_id)
            now = datetime.now(timezone.utc).isoformat()
            rollback = self.create_deployment(
                repo_id=dep["repo_id"], org_id=dep["org_id"],
                workspace_id=dep["workspace_id"],
                environment=dep["environment"],
                version=dep.get("rollback_version", dep["version"]),
                config=dep.get("config"),
            )
            rollback["status"] = "rolling_back"
            rollback["rollback_from"] = deployment_id
            rollback["updated_at"] = now
            self._deployments[rollback["id"]] = rollback
            dep["status"] = "rolled_back"
            dep["updated_at"] = now
            self._deployments[deployment_id] = dep
            self._save()
            self.telemetry["deployments_rolled_back"] += 1
            logger.info("Rolled back deployment %s to new deployment %s", deployment_id, rollback["id"])
            return rollback
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to rollback deployment %s", deployment_id)
            raise

    def get_deployment_status(self, deployment_id: str) -> dict:
        try:
            dep = self.get_deployment(deployment_id)
            status = {
                "deployment_id": deployment_id,
                "status": dep["status"],
                "environment": dep["environment"],
                "version": dep["version"],
                "created_at": dep.get("created_at"),
                "deployed_at": dep.get("deployed_at"),
            }
            self.telemetry["deployment_status_read"] += 1
            return status
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to get deployment status for %s", deployment_id)
            raise

    def promote_deployment(self, deployment_id: str, target_environment: str) -> dict:
        try:
            dep = self.get_deployment(deployment_id)
            now = datetime.now(timezone.utc).isoformat()
            promoted = self.create_deployment(
                repo_id=dep["repo_id"], org_id=dep["org_id"],
                workspace_id=dep["workspace_id"],
                environment=target_environment,
                version=dep["version"],
                config=dep.get("config"),
            )
            promoted["status"] = "promoted"
            promoted["promoted_from"] = deployment_id
            promoted["deployed_at"] = now
            promoted["updated_at"] = now
            self._deployments[promoted["id"]] = promoted
            dep["status"] = "promoted"
            dep["updated_at"] = now
            self._deployments[deployment_id] = dep
            self._save()
            self.telemetry["deployments_promoted"] += 1
            logger.info("Promoted deployment %s to %s", deployment_id, target_environment)
            return promoted
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to promote deployment %s", deployment_id)
            raise


class MarketplaceService:
    """Marketplace service with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._plugins_file = os.path.join(storage_dir, "marketplace_plugins.json")
        self._plugins: dict[str, dict] = {}
        self._stats_file = os.path.join(storage_dir, "marketplace_stats.json")
        self._stats: dict = {"total_installs": 0, "total_plugins": 0}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._plugins_file):
                with open(self._plugins_file, "r", encoding="utf-8") as fh:
                    self._plugins = json.load(fh)
                logger.info("Loaded %d marketplace plugins", len(self._plugins))
        except Exception:
            logger.exception("Failed to load marketplace plugins; starting fresh")
            self._plugins = {}
        try:
            if os.path.exists(self._stats_file):
                with open(self._stats_file, "r", encoding="utf-8") as fh:
                    self._stats = json.load(fh)
        except Exception:
            self._stats = {"total_installs": 0, "total_plugins": 0}

    def _save(self) -> None:
        try:
            tmp = self._plugins_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._plugins, fh, indent=2, default=str)
            os.replace(tmp, self._plugins_file)
        except Exception:
            logger.exception("Failed to save marketplace plugins")
        try:
            tmp = self._stats_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._stats, fh, indent=2, default=str)
            os.replace(tmp, self._stats_file)
        except Exception:
            logger.exception("Failed to save marketplace stats")

    def list_plugins(self, category: Optional[str] = None) -> list[dict]:
        try:
            results = list(self._plugins.values())
            if category is not None:
                results = [p for p in results if p.get("category") == category]
            results.sort(key=lambda x: x.get("name", ""))
            self.telemetry["marketplace_plugins_listed"] += 1
            return results
        except Exception:
            logger.exception("Failed to list marketplace plugins")
            raise

    def get_plugin(self, plugin_id: str) -> dict:
        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            raise ValueError(f"Marketplace plugin not found: {plugin_id}")
        self.telemetry["marketplace_plugins_read"] += 1
        return plugin

    def install_plugin(self, plugin_id: str, org_id: str) -> dict:
        try:
            plugin = self.get_plugin(plugin_id)
            now = datetime.now(timezone.utc).isoformat()
            install = {
                "install_id": str(uuid.uuid4()),
                "plugin_id": plugin_id,
                "org_id": org_id,
                "plugin_name": plugin["name"],
                "installed_at": now,
                "status": "installed",
            }
            plugin["installs"] = plugin.get("installs", 0) + 1
            self._plugins[plugin_id] = plugin
            self._stats["total_installs"] += 1
            self._save()
            self.telemetry["plugins_installed"] += 1
            logger.info("Installed plugin %s for org %s", plugin_id, org_id)
            return install
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to install plugin %s", plugin_id)
            raise

    def uninstall_plugin(self, plugin_id: str, org_id: str) -> None:
        try:
            plugin = self.get_plugin(plugin_id)
            plugin["installs"] = max(0, plugin.get("installs", 1) - 1)
            self._plugins[plugin_id] = plugin
            self._stats["total_installs"] = max(0, self._stats["total_installs"] - 1)
            self._save()
            self.telemetry["plugins_uninstalled"] += 1
            logger.info("Uninstalled plugin %s for org %s", plugin_id, org_id)
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to uninstall plugin %s", plugin_id)
            raise

    def search_plugins(self, query: str) -> list[dict]:
        try:
            q = query.lower()
            results = [p for p in self._plugins.values()
                       if q in p.get("name", "").lower()
                       or q in p.get("description", "").lower()
                       or q in p.get("category", "").lower()]
            self.telemetry["marketplace_plugins_searched"] += 1
            return results
        except Exception:
            logger.exception("Failed to search marketplace plugins")
            raise

    def get_plugin_stats(self) -> dict:
        self.telemetry["marketplace_stats_read"] += 1
        return dict(self._stats)


class PluginService:
    """Plugin service with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._plugins_file = os.path.join(storage_dir, "plugins.json")
        self._plugins: dict[str, ProviderPlugin] = {}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._plugins_file):
                with open(self._plugins_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._plugins = {k: ProviderPlugin.from_dict(v) for k, v in data.items()}
                logger.info("Loaded %d plugins", len(self._plugins))
        except Exception:
            logger.exception("Failed to load plugins; starting fresh")
            self._plugins = {}

    def _save(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._plugins.items()}
            tmp = self._plugins_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._plugins_file)
        except Exception:
            logger.exception("Failed to save plugins")

    def register_plugin(self, name: str, plugin_type: str, version: str,
                         description: str = "",
                         config_schema: Optional[dict] = None) -> ProviderPlugin:
        try:
            now = datetime.now(timezone.utc).isoformat()
            plugin = ProviderPlugin(
                id=str(uuid.uuid4()), name=name, plugin_type=plugin_type,
                version=version, description=description, enabled=True,
                config_schema=config_schema or {}, created_at=now, updated_at=now,
            )
            self._plugins[plugin.id] = plugin
            self._save()
            self.telemetry["plugins_registered"] += 1
            logger.info("Registered plugin %s (%s v%s)", plugin.id, name, version)
            return plugin
        except Exception:
            logger.exception("Failed to register plugin")
            raise

    def enable_plugin(self, plugin_id: str) -> ProviderPlugin:
        try:
            plugin = self._plugins.get(plugin_id)
            if plugin is None:
                raise ValueError(f"Plugin not found: {plugin_id}")
            plugin.enabled = True
            plugin.updated_at = datetime.now(timezone.utc).isoformat()
            self._plugins[plugin_id] = plugin
            self._save()
            self.telemetry["plugins_enabled"] += 1
            logger.info("Enabled plugin %s", plugin_id)
            return plugin
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to enable plugin %s", plugin_id)
            raise

    def disable_plugin(self, plugin_id: str) -> ProviderPlugin:
        try:
            plugin = self._plugins.get(plugin_id)
            if plugin is None:
                raise ValueError(f"Plugin not found: {plugin_id}")
            plugin.enabled = False
            plugin.updated_at = datetime.now(timezone.utc).isoformat()
            self._plugins[plugin_id] = plugin
            self._save()
            self.telemetry["plugins_disabled"] += 1
            logger.info("Disabled plugin %s", plugin_id)
            return plugin
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to disable plugin %s", plugin_id)
            raise

    def list_plugins(self, plugin_type: Optional[str] = None,
                      enabled_only: bool = False) -> list[ProviderPlugin]:
        try:
            results = list(self._plugins.values())
            if plugin_type is not None:
                results = [p for p in results if p.plugin_type == plugin_type]
            if enabled_only:
                results = [p for p in results if p.enabled]
            self.telemetry["plugins_listed"] += 1
            return results
        except Exception:
            logger.exception("Failed to list plugins")
            raise

    def get_plugin_config(self, plugin_id: str) -> dict:
        try:
            plugin = self._plugins.get(plugin_id)
            if plugin is None:
                raise ValueError(f"Plugin not found: {plugin_id}")
            self.telemetry["plugin_configs_read"] += 1
            return {"id": plugin.id, "name": plugin.name, "config_schema": plugin.config_schema,
                    "enabled": plugin.enabled, "version": plugin.version}
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to get plugin config for %s", plugin_id)
            raise

    def update_plugin_config(self, plugin_id: str, config_schema: dict) -> ProviderPlugin:
        try:
            plugin = self._plugins.get(plugin_id)
            if plugin is None:
                raise ValueError(f"Plugin not found: {plugin_id}")
            plugin.config_schema = config_schema
            plugin.updated_at = datetime.now(timezone.utc).isoformat()
            self._plugins[plugin_id] = plugin
            self._save()
            self.telemetry["plugin_configs_updated"] += 1
            logger.info("Updated plugin config for %s", plugin_id)
            return plugin
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to update plugin config for %s", plugin_id)
            raise


class NotificationService:
    """Notification service with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._channels_file = os.path.join(storage_dir, "notification_channels.json")
        self._channels: dict[str, NotificationChannel] = {}
        self._history_file = os.path.join(storage_dir, "notification_history.json")
        self._history: list[dict] = []
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._channels_file):
                with open(self._channels_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._channels = {k: NotificationChannel.from_dict(v) for k, v in data.items()}
                logger.info("Loaded %d notification channels", len(self._channels))
        except Exception:
            logger.exception("Failed to load notification channels; starting fresh")
            self._channels = {}
        try:
            if os.path.exists(self._history_file):
                with open(self._history_file, "r", encoding="utf-8") as fh:
                    self._history = json.load(fh)
        except Exception:
            self._history = []

    def _save(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._channels.items()}
            tmp = self._channels_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._channels_file)
        except Exception:
            logger.exception("Failed to save notification channels")
        try:
            tmp = self._history_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._history, fh, indent=2, default=str)
            os.replace(tmp, self._history_file)
        except Exception:
            logger.exception("Failed to save notification history")

    def send_notification(self, channel_id: str, title: str, message: str,
                           severity: str = "info",
                           metadata: Optional[dict] = None) -> dict:
        try:
            channel = self._channels.get(channel_id)
            if channel is None:
                raise ValueError(f"Notification channel not found: {channel_id}")
            if not channel.enabled:
                raise ValueError(f"Notification channel '{channel.name}' is disabled")
            now = datetime.now(timezone.utc).isoformat()
            notification = {
                "id": str(uuid.uuid4()),
                "channel_id": channel_id,
                "channel_name": channel.name,
                "channel_type": channel.channel_type,
                "title": title,
                "message": message,
                "severity": severity,
                "metadata": metadata or {},
                "sent_at": now,
                "status": "sent",
            }
            self._history.append(notification)
            if len(self._history) > 5000:
                self._history = self._history[-5000:]
            self._save()
            self.telemetry["notifications_sent"] += 1
            logger.info("Sent notification '%s' via %s (%s)", title, channel.name, channel.channel_type)
            return notification
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to send notification")
            raise

    def create_channel(self, channel_type: str, name: str,
                        config: Optional[dict] = None) -> NotificationChannel:
        try:
            now = datetime.now(timezone.utc).isoformat()
            channel = NotificationChannel(
                id=str(uuid.uuid4()), channel_type=channel_type, name=name,
                config=config or {}, enabled=True, created_at=now,
            )
            self._channels[channel.id] = channel
            self._save()
            self.telemetry["channels_created"] += 1
            logger.info("Created notification channel %s (%s)", channel.id, name)
            return channel
        except Exception:
            logger.exception("Failed to create notification channel")
            raise

    def list_channels(self, channel_type: Optional[str] = None) -> list[NotificationChannel]:
        try:
            results = list(self._channels.values())
            if channel_type is not None:
                results = [c for c in results if c.channel_type == channel_type]
            self.telemetry["channels_listed"] += 1
            return results
        except Exception:
            logger.exception("Failed to list notification channels")
            raise

    def get_notification_history(self, channel_id: Optional[str] = None,
                                   limit: int = 100) -> list[dict]:
        try:
            results = list(self._history)
            if channel_id is not None:
                results = [n for n in results if n["channel_id"] == channel_id]
            results.sort(key=lambda x: x.get("sent_at", ""), reverse=True)
            self.telemetry["notification_history_read"] += 1
            return results[:limit]
        except Exception:
            logger.exception("Failed to get notification history")
            raise

    def send_bulk_notification(self, channel_ids: list[str], title: str,
                                message: str, severity: str = "info") -> list[dict]:
        try:
            results = []
            for cid in channel_ids:
                try:
                    result = self.send_notification(cid, title, message, severity)
                    results.append(result)
                except ValueError as e:
                    logger.warning("Skipping channel %s: %s", cid, e)
                    continue
            self.telemetry["bulk_notifications_sent"] += len(results)
            logger.info("Sent bulk notification to %d/%d channels", len(results), len(channel_ids))
            return results
        except Exception:
            logger.exception("Failed to send bulk notification")
            raise


class PlatformServiceManager(RepositoryService, SearchService, EmbeddingService,
                              AgentService, ChatService, AnalyticsService,
                              SecurityService, DeploymentService, MarketplaceService,
                              PluginService, NotificationService):
    """Unified platform service manager combining all sub-services."""

    def __init__(self, storage_dir: str):
        RepositoryService.__init__(self, storage_dir)
        SearchService.__init__(self, storage_dir)
        EmbeddingService.__init__(self, storage_dir)
        AgentService.__init__(self, storage_dir)
        ChatService.__init__(self, storage_dir)
        AnalyticsService.__init__(self, storage_dir)
        SecurityService.__init__(self, storage_dir)
        DeploymentService.__init__(self, storage_dir)
        MarketplaceService.__init__(self, storage_dir)
        PluginService.__init__(self, storage_dir)
        NotificationService.__init__(self, storage_dir)
        self.telemetry: dict = defaultdict(int)
        logger.info("PlatformServiceManager initialized at %s", storage_dir)

    def get_service_health(self) -> dict:
        try:
            health = {
                "repositories": len(self._repos),
                "search_index_size": len(self._index),
                "embeddings": len(self._embeddings),
                "agents": len(self._agents),
                "active_chat_sessions": len([s for s in self._sessions.values() if s.get("status") == "active"]),
                "analytics_events": len(self._events),
                "security_scans": len(self._scans),
                "deployments": len(self._deployments),
                "marketplace_plugins": len(self._plugins),
                "notification_channels": len(self._channels),
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
            self.telemetry["service_health_read"] += 1
            return health
        except Exception:
            logger.exception("Failed to get service health")
            raise

    def get_all_metrics(self) -> dict:
        try:
            metrics = {}
            for attr, label in [
                ("repositories_created", "repos"),
                ("searches_performed", "searches"),
                ("embeddings_created", "embeddings"),
                ("agents_created", "agents"),
                ("chat_sessions_created", "chat_sessions"),
                ("events_tracked", "events"),
                ("scans_performed", "scans"),
                ("deployments_created", "deployments"),
                ("plugins_installed", "plugin_installs"),
                ("notifications_sent", "notifications"),
            ]:
                metrics[label] = self.telemetry.get(attr, 0)
            metrics["total"] = sum(metrics.values())
            return metrics
        except Exception:
            logger.exception("Failed to get all metrics")
            raise

    def enable_service(self, service_type: ServiceType, org_id: str,
                        workspace_id: Optional[str] = None,
                        tier: ServiceTier = ServiceTier.FREE) -> ServiceConfig:
        try:
            now = datetime.now(timezone.utc).isoformat()
            cfg = ServiceConfig(
                id=str(uuid.uuid4()), service_type=service_type, org_id=org_id,
                workspace_id=workspace_id, tier=tier, enabled=True,
                created_at=now, updated_at=now,
            )
            cfg_file = os.path.join(self.storage_dir, "service_configs.json")
            configs = {}
            try:
                if os.path.exists(cfg_file):
                    with open(cfg_file, "r", encoding="utf-8") as fh:
                        configs = json.load(fh)
            except Exception:
                configs = {}
            configs[cfg.id] = cfg.to_dict()
            tmp = cfg_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(configs, fh, indent=2, default=str)
            os.replace(tmp, cfg_file)
            self.telemetry["services_enabled"] += 1
            logger.info("Enabled service %s for org %s", service_type.value, org_id)
            return cfg
        except Exception:
            logger.exception("Failed to enable service")
            raise

    def disable_service(self, service_type: ServiceType, org_id: str) -> None:
        try:
            cfg_file = os.path.join(self.storage_dir, "service_configs.json")
            configs = {}
            try:
                if os.path.exists(cfg_file):
                    with open(cfg_file, "r", encoding="utf-8") as fh:
                        configs = json.load(fh)
            except Exception:
                configs = {}
            to_remove = [k for k, v in configs.items()
                         if v.get("service_type") == service_type.value and v.get("org_id") == org_id]
            for k in to_remove:
                configs[k]["enabled"] = False
                configs[k]["updated_at"] = datetime.now(timezone.utc).isoformat()
            tmp = cfg_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(configs, fh, indent=2, default=str)
            os.replace(tmp, cfg_file)
            self.telemetry["services_disabled"] += 1
            logger.info("Disabled service %s for org %s", service_type.value, org_id)
        except Exception:
            logger.exception("Failed to disable service")
            raise
