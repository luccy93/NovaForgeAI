import json
import uuid
import hashlib
import time
import math
import os
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class EmbeddingModel(Enum):
    TEXT_EMBEDDING_3_SMALL = "text-embedding-3-small"
    TEXT_EMBEDDING_3_LARGE = "text-embedding-3-large"
    ADA_002 = "ada-002"
    COHERE_EMBED_ENGLISH = "cohere-embed-english"
    COHERE_EMBED_MULTILINGUAL = "cohere-embed-multilingual"
    GECKO = "gecko"
    BGE_SMALL = "bge-small"
    BGE_LARGE = "bge-large"
    CUSTOM = "custom"


class EmbeddingStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CACHED = "cached"


class IndexType(Enum):
    FLAT = "flat"
    IVF = "ivf"
    HNSW = "hnsw"
    PQ = "pq"
    SCANN = "scann"


@dataclass
class EmbeddingRecord:
    id: str
    source_type: str
    source_id: str
    model: EmbeddingModel
    vector: Optional[list[float]] = None
    dimension: int = 0
    text: str = ""
    metadata: dict = field(default_factory=dict)
    status: EmbeddingStatus = EmbeddingStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    token_count: int = 0
    cost: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["model"] = self.model.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "EmbeddingRecord":
        data["model"] = EmbeddingModel(data["model"])
        data["status"] = EmbeddingStatus(data["status"])
        return cls(**data)


@dataclass
class EmbeddingBatch:
    id: str
    records: list[str]
    model: EmbeddingModel
    status: EmbeddingStatus = EmbeddingStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    total_tokens: int = 0
    total_cost: float = 0.0
    progress: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["model"] = self.model.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "EmbeddingBatch":
        data["model"] = EmbeddingModel(data["model"])
        data["status"] = EmbeddingStatus(data["status"])
        return cls(**data)


@dataclass
class EmbeddingModelConfig:
    model: EmbeddingModel
    dimension: int
    max_input_tokens: int
    cost_per_million_tokens: float
    supports_batch: bool = False
    batch_size: int = 1
    provider: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["model"] = self.model.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "EmbeddingModelConfig":
        data["model"] = EmbeddingModel(data["model"])
        return cls(**data)


@dataclass
class EmbeddingCacheEntry:
    id: str
    text_hash: str
    model: EmbeddingModel
    vector: Optional[list[float]] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    access_count: int = 0
    ttl_seconds: int = 86400

    def to_dict(self) -> dict:
        d = asdict(self)
        d["model"] = self.model.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "EmbeddingCacheEntry":
        data["model"] = EmbeddingModel(data["model"])
        return cls(**data)


@dataclass
class MigrationTask:
    id: str
    source_model: EmbeddingModel
    target_model: EmbeddingModel
    status: str = "pending"
    total_records: int = 0
    migrated_records: int = 0
    failed_records: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["source_model"] = self.source_model.value
        d["target_model"] = self.target_model.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "MigrationTask":
        data["source_model"] = EmbeddingModel(data["source_model"])
        data["target_model"] = EmbeddingModel(data["target_model"])
        return cls(**data)


class EmbeddingCache:
    def __init__(self, storage_dir: str = "embedding_cache_data"):
        self.storage_dir = storage_dir
        self._cache: dict[str, EmbeddingCacheEntry] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _cache_path(self) -> str:
        return os.path.join(self.storage_dir, "cache.json")

    def _save(self) -> None:
        try:
            data = {cid: e.to_dict() for cid, e in self._cache.items()}
            with open(self._cache_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save embedding cache: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._cache_path()):
                with open(self._cache_path(), "r", encoding="utf-8") as f:
                    data = json.load(f)
                for cid, entry_data in data.items():
                    try:
                        self._cache[cid] = EmbeddingCacheEntry.from_dict(entry_data)
                    except Exception as e:
                        logger.warning("Skipping malformed cache entry %s: %s", cid, e)
        except Exception as e:
            logger.error("Failed to load embedding cache: %s", e, exc_info=True)

    def _hash_text(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _is_expired(self, entry: EmbeddingCacheEntry) -> bool:
        try:
            created = datetime.fromisoformat(entry.created_at)
            elapsed = (datetime.now(timezone.utc) - created).total_seconds()
            return elapsed > entry.ttl_seconds
        except Exception:
            return True

    def get_cached(self, text: str, model: EmbeddingModel) -> Optional[EmbeddingCacheEntry]:
        self._telemetry["get_cached_calls"] += 1
        text_hash = self._hash_text(text)
        for entry in self._cache.values():
            if entry.text_hash == text_hash and entry.model == model:
                if self._is_expired(entry):
                    self.invalidate(entry.id)
                    return None
                entry.access_count += 1
                self._save()
                return entry
        return None

    def set_cache(self, text: str, model: EmbeddingModel, vector: list[float], ttl_seconds: Optional[int] = None) -> EmbeddingCacheEntry:
        self._telemetry["set_cache_calls"] += 1
        text_hash = self._hash_text(text)
        entry = EmbeddingCacheEntry(
            id=str(uuid.uuid4()),
            text_hash=text_hash,
            model=model,
            vector=vector,
            ttl_seconds=ttl_seconds or 86400,
        )
        self._cache[entry.id] = entry
        self._save()
        logger.debug("Cached embedding for model %s (hash=%s)", model.value, text_hash[:12])
        return entry

    def invalidate(self, cache_id: str) -> bool:
        self._telemetry["invalidate_calls"] += 1
        if cache_id in self._cache:
            del self._cache[cache_id]
            self._save()
            return True
        return False

    def clear_model_cache(self, model: EmbeddingModel) -> int:
        self._telemetry["clear_model_cache_calls"] += 1
        removed = 0
        to_delete = [cid for cid, e in self._cache.items() if e.model == model]
        for cid in to_delete:
            del self._cache[cid]
            removed += 1
        if removed:
            self._save()
        logger.info("Cleared %d cache entries for model %s", removed, model.value)
        return removed

    def get_cache_stats(self) -> dict:
        self._telemetry["get_cache_stats_calls"] += 1
        model_counts = defaultdict(int)
        total_access = 0
        expired = 0
        for entry in self._cache.values():
            model_counts[entry.model.value] += 1
            total_access += entry.access_count
            if self._is_expired(entry):
                expired += 1
        return {
            "total_entries": len(self._cache),
            "model_distribution": dict(model_counts),
            "total_access_count": total_access,
            "expired_entries": expired,
            "telemetry": dict(self._telemetry),
        }

    def warmup(self, texts: list[str], model: EmbeddingModel, vectors: list[list[float]]) -> int:
        self._telemetry["warmup_calls"] += 1
        count = 0
        for text, vector in zip(texts, vectors):
            existing = self.get_cached(text, model)
            if not existing:
                self.set_cache(text, model, vector)
                count += 1
        logger.info("Warmed up %d cache entries for model %s", count, model.value)
        return count


class EmbeddingManager:
    def __init__(self, storage_dir: str = "embedding_data"):
        self.storage_dir = storage_dir
        self._records: dict[str, EmbeddingRecord] = {}
        self._batches: dict[str, EmbeddingBatch] = {}
        self._model_configs: dict[EmbeddingModel, EmbeddingModelConfig] = {}
        self._index: dict[str, list[float]] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        self._default_configs: dict[EmbeddingModel, EmbeddingModelConfig] = {
            EmbeddingModel.TEXT_EMBEDDING_3_SMALL: EmbeddingModelConfig(
                model=EmbeddingModel.TEXT_EMBEDDING_3_SMALL, dimension=1536, max_input_tokens=8192,
                cost_per_million_tokens=0.02, supports_batch=True, batch_size=100, provider="openai",
            ),
            EmbeddingModel.TEXT_EMBEDDING_3_LARGE: EmbeddingModelConfig(
                model=EmbeddingModel.TEXT_EMBEDDING_3_LARGE, dimension=3072, max_input_tokens=8192,
                cost_per_million_tokens=0.13, supports_batch=True, batch_size=100, provider="openai",
            ),
            EmbeddingModel.ADA_002: EmbeddingModelConfig(
                model=EmbeddingModel.ADA_002, dimension=1536, max_input_tokens=8191,
                cost_per_million_tokens=0.10, supports_batch=True, batch_size=100, provider="openai",
            ),
            EmbeddingModel.COHERE_EMBED_ENGLISH: EmbeddingModelConfig(
                model=EmbeddingModel.COHERE_EMBED_ENGLISH, dimension=4096, max_input_tokens=512,
                cost_per_million_tokens=0.10, supports_batch=True, batch_size=96, provider="cohere",
            ),
            EmbeddingModel.COHERE_EMBED_MULTILINGUAL: EmbeddingModelConfig(
                model=EmbeddingModel.COHERE_EMBED_MULTILINGUAL, dimension=4096, max_input_tokens=512,
                cost_per_million_tokens=0.10, supports_batch=True, batch_size=96, provider="cohere",
            ),
            EmbeddingModel.GECKO: EmbeddingModelConfig(
                model=EmbeddingModel.GECKO, dimension=768, max_input_tokens=2048,
                cost_per_million_tokens=0.0001, supports_batch=True, batch_size=50, provider="aws",
            ),
            EmbeddingModel.BGE_SMALL: EmbeddingModelConfig(
                model=EmbeddingModel.BGE_SMALL, dimension=384, max_input_tokens=512,
                cost_per_million_tokens=0.0, supports_batch=True, batch_size=64, provider="local",
            ),
            EmbeddingModel.BGE_LARGE: EmbeddingModelConfig(
                model=EmbeddingModel.BGE_LARGE, dimension=1024, max_input_tokens=512,
                cost_per_million_tokens=0.0, supports_batch=True, batch_size=32, provider="local",
            ),
        }
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _records_path(self) -> str:
        return os.path.join(self.storage_dir, "records.json")

    def _batches_path(self) -> str:
        return os.path.join(self.storage_dir, "batches.json")

    def _configs_path(self) -> str:
        return os.path.join(self.storage_dir, "configs.json")

    def _index_path(self) -> str:
        return os.path.join(self.storage_dir, "index.json")

    def _save(self) -> None:
        try:
            records_data = {rid: r.to_dict() for rid, r in self._records.items()}
            with open(self._records_path(), "w", encoding="utf-8") as f:
                json.dump(records_data, f, indent=2, default=str)

            batches_data = {bid: b.to_dict() for bid, b in self._batches.items()}
            with open(self._batches_path(), "w", encoding="utf-8") as f:
                json.dump(batches_data, f, indent=2, default=str)

            configs_data = {k.value: v.to_dict() for k, v in self._model_configs.items()}
            with open(self._configs_path(), "w", encoding="utf-8") as f:
                json.dump(configs_data, f, indent=2, default=str)

            with open(self._index_path(), "w", encoding="utf-8") as f:
                json.dump(self._index, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save embedding data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._records_path()):
                with open(self._records_path(), "r", encoding="utf-8") as f:
                    records_data = json.load(f)
                for rid, data in records_data.items():
                    try:
                        self._records[rid] = EmbeddingRecord.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed record %s: %s", rid, e)

            if os.path.exists(self._batches_path()):
                with open(self._batches_path(), "r", encoding="utf-8") as f:
                    batches_data = json.load(f)
                for bid, data in batches_data.items():
                    try:
                        self._batches[bid] = EmbeddingBatch.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed batch %s: %s", bid, e)

            if os.path.exists(self._configs_path()):
                with open(self._configs_path(), "r", encoding="utf-8") as f:
                    configs_data = json.load(f)
                for k, data in configs_data.items():
                    try:
                        self._model_configs[EmbeddingModel(k)] = EmbeddingModelConfig.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed config %s: %s", k, e)
            else:
                self._model_configs = dict(self._default_configs)

            if os.path.exists(self._index_path()):
                with open(self._index_path(), "r", encoding="utf-8") as f:
                    self._index = json.load(f)
        except Exception as e:
            logger.error("Failed to load embedding data: %s", e, exc_info=True)

    def create_embedding(self, source_type: str, source_id: str, text: str, model: EmbeddingModel = EmbeddingModel.TEXT_EMBEDDING_3_SMALL, metadata: Optional[dict] = None) -> EmbeddingRecord:
        self._telemetry["create_embedding_calls"] += 1
        config = self.get_model_config(model)
        record = EmbeddingRecord(
            id=str(uuid.uuid4()),
            source_type=source_type,
            source_id=source_id,
            model=model,
            dimension=config.dimension,
            text=text,
            metadata=metadata or {},
            status=EmbeddingStatus.PENDING,
        )
        self._records[record.id] = record
        self._save()
        logger.info("Created embedding record %s for %s/%s", record.id, source_type, source_id)
        return record

    def get_embedding(self, record_id: str) -> Optional[EmbeddingRecord]:
        self._telemetry["get_embedding_calls"] += 1
        return self._records.get(record_id)

    def batch_embed(self, texts: list[str], model: EmbeddingModel = EmbeddingModel.TEXT_EMBEDDING_3_SMALL) -> EmbeddingBatch:
        self._telemetry["batch_embed_calls"] += 1
        batch = EmbeddingBatch(
            id=str(uuid.uuid4()),
            records=[],
            model=model,
        )
        for text in texts:
            record = self.create_embedding(
                source_type="batch",
                source_id=batch.id,
                text=text,
                model=model,
            )
            batch.records.append(record.id)
        self._batches[batch.id] = batch
        self._save()
        logger.info("Created batch %s with %d texts", batch.id, len(texts))
        return batch

    def search_similar(self, query_vector: list[float], top_k: int = 10, model: Optional[EmbeddingModel] = None) -> list[dict]:
        self._telemetry["search_similar_calls"] += 1
        scored = []
        for rec_id, record in self._records.items():
            if model and record.model != model:
                continue
            if not record.vector:
                continue
            sim = self._cosine_similarity(query_vector, record.vector)
            scored.append({
                "record_id": rec_id,
                "source_type": record.source_type,
                "source_id": record.source_id,
                "score": sim,
                "text": record.text[:200],
            })
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        if not a or not b:
            return 0.0
        dot = sum(ai * bi for ai, bi in zip(a, b))
        norm_a = math.sqrt(sum(ai * ai for ai in a))
        norm_b = math.sqrt(sum(bi * bi for bi in b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)

    def get_embedding_stats(self) -> dict:
        self._telemetry["get_embedding_stats_calls"] += 1
        status_counts = defaultdict(int)
        model_counts = defaultdict(int)
        total_tokens = 0
        total_cost = 0.0
        for r in self._records.values():
            status_counts[r.status.value] += 1
            model_counts[r.model.value] += 1
            total_tokens += r.token_count
            total_cost += r.cost
        return {
            "total_records": len(self._records),
            "total_batches": len(self._batches),
            "status_distribution": dict(status_counts),
            "model_distribution": dict(model_counts),
            "total_tokens": total_tokens,
            "total_cost": round(total_cost, 6),
            "avg_dimension": round(sum(r.dimension for r in self._records.values()) / max(len(self._records), 1), 1),
            "telemetry": dict(self._telemetry),
        }

    def migrate_embeddings(self, source_model: EmbeddingModel, target_model: EmbeddingModel) -> MigrationTask:
        self._telemetry["migrate_embeddings_calls"] += 1
        task = MigrationTask(
            id=str(uuid.uuid4()),
            source_model=source_model,
            target_model=target_model,
        )
        records_to_migrate = [r for r in self._records.values() if r.model == source_model and r.vector]
        task.total_records = len(records_to_migrate)
        migrated = 0
        failed = 0
        for record in records_to_migrate:
            try:
                record.model = target_model
                record.dimension = self.get_model_config(target_model).dimension
                record.status = EmbeddingStatus.PENDING
                record.vector = None
                migrated += 1
            except Exception as e:
                logger.error("Failed to migrate record %s: %s", record.id, e)
                failed += 1
        task.migrated_records = migrated
        task.failed_records = failed
        task.status = "completed"
        task.completed_at = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Migration %s: %d migrated, %d failed", task.id, migrated, failed)
        return task

    def reindex(self, index_type: IndexType = IndexType.FLAT) -> dict:
        self._telemetry["reindex_calls"] += 1
        start = time.time()
        self._index = {}
        indexed = 0
        for record in self._records.values():
            if record.vector and record.status == EmbeddingStatus.COMPLETED:
                self._index[record.id] = record.vector
                indexed += 1
        elapsed = time.time() - start
        self._save()
        logger.info("Reindexed %d vectors using %s in %.2fs", indexed, index_type.value, elapsed)
        return {
            "indexed_count": indexed,
            "index_type": index_type.value,
            "elapsed_seconds": round(elapsed, 3),
        }

    def list_models(self) -> list[EmbeddingModel]:
        self._telemetry["list_models_calls"] += 1
        return list(self._model_configs.keys())

    def get_model_config(self, model: EmbeddingModel) -> Optional[EmbeddingModelConfig]:
        self._telemetry["get_model_config_calls"] += 1
        return self._model_configs.get(model, self._default_configs.get(model))


class EmbeddingMigration:
    def __init__(self, embedding_manager: EmbeddingManager, storage_dir: str = "migration_data"):
        self.embedding_manager = embedding_manager
        self.storage_dir = storage_dir
        self._tasks: dict[str, MigrationTask] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _tasks_path(self) -> str:
        return os.path.join(self.storage_dir, "migration_tasks.json")

    def _save(self) -> None:
        try:
            data = {tid: t.to_dict() for tid, t in self._tasks.items()}
            with open(self._tasks_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save migration tasks: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._tasks_path()):
                with open(self._tasks_path(), "r", encoding="utf-8") as f:
                    data = json.load(f)
                for tid, tdata in data.items():
                    try:
                        self._tasks[tid] = MigrationTask.from_dict(tdata)
                    except Exception as e:
                        logger.warning("Skipping malformed migration task %s: %s", tid, e)
        except Exception as e:
            logger.error("Failed to load migration tasks: %s", e, exc_info=True)

    def create_migration(self, source_model: EmbeddingModel, target_model: EmbeddingModel) -> MigrationTask:
        self._telemetry["create_migration_calls"] += 1
        task = MigrationTask(
            id=str(uuid.uuid4()),
            source_model=source_model,
            target_model=target_model,
        )
        self._tasks[task.id] = task
        self._save()
        logger.info("Created migration task %s: %s -> %s", task.id, source_model.value, target_model.value)
        return task

    def execute_migration(self, task_id: str) -> Optional[MigrationTask]:
        self._telemetry["execute_migration_calls"] += 1
        task = self._tasks.get(task_id)
        if not task:
            logger.warning("Migration task %s not found", task_id)
            return None
        migration_task = self.embedding_manager.migrate_embeddings(task.source_model, task.target_model)
        task.status = migration_task.status
        task.total_records = migration_task.total_records
        task.migrated_records = migration_task.migrated_records
        task.failed_records = migration_task.failed_records
        task.completed_at = migration_task.completed_at
        self._save()
        return task

    def rollback_migration(self, task_id: str) -> Optional[MigrationTask]:
        self._telemetry["rollback_migration_calls"] += 1
        task = self._tasks.get(task_id)
        if not task:
            return None
        rollback_task = self.embedding_manager.migrate_embeddings(task.target_model, task.source_model)
        task.status = "rolled_back"
        task.completed_at = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Rolled back migration task %s", task_id)
        return task

    def get_migration_status(self, task_id: str) -> Optional[dict]:
        self._telemetry["get_migration_status_calls"] += 1
        task = self._tasks.get(task_id)
        if not task:
            return None
        return {
            "id": task.id,
            "source_model": task.source_model.value,
            "target_model": task.target_model.value,
            "status": task.status,
            "progress": f"{task.migrated_records}/{task.total_records}" if task.total_records else "N/A",
            "failed": task.failed_records,
            "created_at": task.created_at,
            "completed_at": task.completed_at,
        }

    def compare_models(self, model_a: EmbeddingModel, model_b: EmbeddingModel) -> dict:
        self._telemetry["compare_models_calls"] += 1
        config_a = self.embedding_manager.get_model_config(model_a)
        config_b = self.embedding_manager.get_model_config(model_b)
        return {
            "model_a": {"model": model_a.value, "config": config_a.to_dict() if config_a else None},
            "model_b": {"model": model_b.value, "config": config_b.to_dict() if config_b else None},
            "dimension_delta": (config_a.dimension - config_b.dimension) if config_a and config_b else 0,
            "cost_per_million_a": config_a.cost_per_million_tokens if config_a else 0,
            "cost_per_million_b": config_b.cost_per_million_tokens if config_b else 0,
        }
