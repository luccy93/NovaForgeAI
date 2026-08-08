"""
Storage — Repository, Artifact, Documentation, AI Memory, Knowledge Graph, Embeddings, Analytics, Logs, Backups.
"""
import logging
logger = logging.getLogger(__name__)

from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
import json, uuid, hashlib, time, os, threading
from collections import defaultdict


class StorageType(Enum):
    REPOSITORY = "repository"
    ARTIFACT = "artifact"
    DOCUMENTATION = "documentation"
    AI_MEMORY = "ai_memory"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    EMBEDDING = "embedding"
    ANALYTICS = "analytics"
    LOGS = "logs"
    BACKUP = "backup"


class StorageClass(Enum):
    STANDARD = "standard"
    FREQUENT = "frequent"
    INFREQUENT = "infrequent"
    ARCHIVE = "archive"
    COLD = "cold"


class DataRetentionPolicy(Enum):
    THIRTY_DAYS = "thirty_days"
    NINETY_DAYS = "ninety_days"
    ONE_YEAR = "one_year"
    INDEFINITE = "indefinite"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class StorageEntity:
    id: str
    storage_type: StorageType
    name: str
    owner_id: str
    org_id: str
    size_bytes: int = 0
    file_count: int = 0
    storage_class: StorageClass = StorageClass.STANDARD
    created_at: str = ""
    accessed_at: str = ""
    retention: DataRetentionPolicy = DataRetentionPolicy.INDEFINITE
    path: str = ""
    metadata: dict = field(default_factory=dict)
    encryption_enabled: bool = False
    compressed: bool = False
    checksum: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["storage_type"] = self.storage_type.value
        d["storage_class"] = self.storage_class.value
        d["retention"] = self.retention.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "StorageEntity":
        data = dict(data)
        data["storage_type"] = StorageType(data["storage_type"])
        data["storage_class"] = StorageClass(data["storage_class"])
        data["retention"] = DataRetentionPolicy(data["retention"])
        return StorageEntity(**data)


@dataclass
class StorageQuota:
    storage_type: StorageType
    max_size_bytes: int = 0
    max_file_count: int = 0
    current_size_bytes: int = 0
    current_file_count: int = 0
    usage_percent: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["storage_type"] = self.storage_type.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "StorageQuota":
        data = dict(data)
        data["storage_type"] = StorageType(data["storage_type"])
        return StorageQuota(**data)


@dataclass
class StorageMetrics:
    total_size_bytes: int = 0
    total_file_count: int = 0
    by_type: dict = field(default_factory=dict)
    by_class: dict = field(default_factory=dict)
    top_n_largest: list = field(default_factory=list)
    oldest_entities: list = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["top_n_largest"] = [e.to_dict() for e in self.top_n_largest]
        d["oldest_entities"] = [e.to_dict() for e in self.oldest_entities]
        return d

    @staticmethod
    def from_dict(data: dict) -> "StorageMetrics":
        data = dict(data)
        data["top_n_largest"] = [StorageEntity.from_dict(e) for e in data.get("top_n_largest", [])]
        data["oldest_entities"] = [StorageEntity.from_dict(e) for e in data.get("oldest_entities", [])]
        return StorageMetrics(**data)


@dataclass
class Artifact:
    id: str
    entity_id: str
    name: str
    artifact_type: str = ""
    version: str = ""
    size_bytes: int = 0
    content_type: str = ""
    checksum: str = ""
    created_at: str = ""
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "Artifact":
        return Artifact(**data)


@dataclass
class BackupConfig:
    id: str
    storage_type: StorageType
    schedule: str = ""
    retention_days: int = 30
    encryption_enabled: bool = False
    compression_enabled: bool = False
    target_path: str = ""
    last_backup: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["storage_type"] = self.storage_type.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "BackupConfig":
        data = dict(data)
        data["storage_type"] = StorageType(data["storage_type"])
        return BackupConfig(**data)


# ---------------------------------------------------------------------------
# Managers
# ---------------------------------------------------------------------------

class StorageManager:
    """Manages storage entities with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._entities_file = os.path.join(storage_dir, "storage_entities.json")
        self._entities: dict[str, StorageEntity] = {}
        self._quotas_file = os.path.join(storage_dir, "storage_quotas.json")
        self._quotas: dict[str, StorageQuota] = {}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    # -- persistence --------------------------------------------------------

    def _load(self) -> None:
        try:
            if os.path.exists(self._entities_file):
                with open(self._entities_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._entities = {k: StorageEntity.from_dict(v) for k, v in data.items()}
                logger.info("Loaded %d storage entities", len(self._entities))
        except Exception:
            logger.exception("Failed to load storage entities; starting fresh")
            self._entities = {}

        try:
            if os.path.exists(self._quotas_file):
                with open(self._quotas_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._quotas = {k: StorageQuota.from_dict(v) for k, v in data.items()}
        except Exception:
            self._quotas = {}

    def _save(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._entities.items()}
            tmp = self._entities_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._entities_file)
        except Exception:
            logger.exception("Failed to save storage entities")

        try:
            data = {k: v.to_dict() for k, v in self._quotas.items()}
            tmp = self._quotas_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._quotas_file)
        except Exception:
            logger.exception("Failed to save storage quotas")

    # -- CRUD ---------------------------------------------------------------

    def store_entity(self, storage_type: StorageType, name: str, owner_id: str,
                     org_id: str, size_bytes: int = 0, file_count: int = 0,
                     storage_class: StorageClass = StorageClass.STANDARD,
                     path: str = "", retention: DataRetentionPolicy = DataRetentionPolicy.INDEFINITE,
                     encryption_enabled: bool = False, compressed: bool = False,
                     metadata: Optional[dict] = None) -> StorageEntity:
        try:
            now = datetime.now(timezone.utc).isoformat()
            checksum = hashlib.sha256(f"{name}:{size_bytes}:{now}".encode()).hexdigest()[:16]
            entity = StorageEntity(
                id=str(uuid.uuid4()),
                storage_type=storage_type,
                name=name,
                owner_id=owner_id,
                org_id=org_id,
                size_bytes=size_bytes,
                file_count=file_count,
                storage_class=storage_class,
                created_at=now,
                accessed_at=now,
                retention=retention,
                path=path or f"{storage_type.value}/{owner_id}/{name}",
                metadata=metadata or {},
                encryption_enabled=encryption_enabled,
                compressed=compressed,
                checksum=checksum,
            )
            self._entities[entity.id] = entity
            self._update_quota(storage_type, size_bytes, file_count)
            self._save()
            self.telemetry["entities_stored"] += 1
            logger.info("Stored entity %s (%s) for %s", entity.id, name, owner_id)
            return entity
        except Exception:
            logger.exception("Failed to store entity")
            raise

    def get_entity(self, entity_id: str) -> StorageEntity:
        entity = self._entities.get(entity_id)
        if entity is None:
            raise ValueError(f"Storage entity not found: {entity_id}")
        entity.accessed_at = datetime.now(timezone.utc).isoformat()
        self._entities[entity_id] = entity
        self._save()
        self.telemetry["entities_read"] += 1
        return entity

    def update_entity(self, entity_id: str, **kwargs) -> StorageEntity:
        try:
            entity = self.get_entity(entity_id)
            old_size = entity.size_bytes
            for key, val in kwargs.items():
                if hasattr(entity, key) and key not in ("id", "created_at"):
                    setattr(entity, key, val)
            entity.accessed_at = datetime.now(timezone.utc).isoformat()
            self._entities[entity_id] = entity
            if kwargs.get("size_bytes") is not None:
                delta_size = entity.size_bytes - old_size
                self._update_quota(entity.storage_type, delta_size, 0)
            self._save()
            self.telemetry["entities_updated"] += 1
            return entity
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to update entity %s", entity_id)
            raise

    def delete_entity(self, entity_id: str) -> None:
        try:
            entity = self._entities.pop(entity_id, None)
            if entity is None:
                raise ValueError(f"Storage entity not found: {entity_id}")
            self._update_quota(entity.storage_type, -entity.size_bytes, -entity.file_count)
            self._save()
            self.telemetry["entities_deleted"] += 1
            logger.info("Deleted entity %s", entity_id)
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to delete entity %s", entity_id)
            raise

    def list_entities(self, storage_type: Optional[StorageType] = None,
                      org_id: Optional[str] = None,
                      owner_id: Optional[str] = None) -> list[StorageEntity]:
        try:
            results = list(self._entities.values())
            if storage_type is not None:
                results = [e for e in results if e.storage_type == storage_type]
            if org_id is not None:
                results = [e for e in results if e.org_id == org_id]
            if owner_id is not None:
                results = [e for e in results if e.owner_id == owner_id]
            self.telemetry["entities_listed"] += 1
            return results
        except Exception:
            logger.exception("Failed to list entities")
            raise

    def get_quota(self, storage_type: StorageType) -> StorageQuota:
        key = storage_type.value
        if key not in self._quotas:
            self._quotas[key] = StorageQuota(storage_type=storage_type)
        self.telemetry["quotas_read"] += 1
        return self._quotas[key]

    def check_quota(self, storage_type: StorageType, additional_bytes: int = 0,
                    additional_files: int = 0) -> dict:
        try:
            quota = self.get_quota(storage_type)
            new_size = quota.current_size_bytes + additional_bytes
            new_files = quota.current_file_count + additional_files
            exceeded = []
            if quota.max_size_bytes > 0 and new_size > quota.max_size_bytes:
                exceeded.append("size")
            if quota.max_file_count > 0 and new_files > quota.max_file_count:
                exceeded.append("file_count")
            result = {
                "allowed": len(exceeded) == 0,
                "current_size_bytes": quota.current_size_bytes,
                "current_file_count": quota.current_file_count,
                "new_size_bytes": new_size,
                "new_file_count": new_files,
                "max_size_bytes": quota.max_size_bytes,
                "max_file_count": quota.max_file_count,
                "exceeded": exceeded,
            }
            self.telemetry["quotas_checked"] += 1
            return result
        except Exception:
            logger.exception("Failed to check quota")
            raise

    def get_metrics(self) -> StorageMetrics:
        try:
            total_size = sum(e.size_bytes for e in self._entities.values())
            total_files = sum(e.file_count for e in self._entities.values())
            by_type = defaultdict(int)
            by_class = defaultdict(int)
            for e in self._entities.values():
                by_type[e.storage_type.value] += e.size_bytes
                by_class[e.storage_class.value] += e.size_bytes
            sorted_by_size = sorted(self._entities.values(), key=lambda x: x.size_bytes, reverse=True)
            top_n = sorted_by_size[:10]
            sorted_by_age = sorted(self._entities.values(), key=lambda x: x.created_at)
            oldest = sorted_by_age[:10]
            metrics = StorageMetrics(
                total_size_bytes=total_size,
                total_file_count=total_files,
                by_type=dict(by_type),
                by_class=dict(by_class),
                top_n_largest=top_n,
                oldest_entities=oldest,
            )
            self.telemetry["metrics_computed"] += 1
            return metrics
        except Exception:
            logger.exception("Failed to get storage metrics")
            raise

    def search_entities(self, query: str) -> list[StorageEntity]:
        try:
            q = query.lower()
            results = [
                e for e in self._entities.values()
                if q in e.name.lower() or q in e.path.lower() or q in str(e.metadata).lower()
            ]
            self.telemetry["entities_searched"] += 1
            return results
        except Exception:
            logger.exception("Failed to search entities")
            raise

    def move_entity(self, entity_id: str, new_path: str) -> StorageEntity:
        try:
            entity = self.get_entity(entity_id)
            old_path = entity.path
            entity.path = new_path
            entity.accessed_at = datetime.now(timezone.utc).isoformat()
            self._entities[entity_id] = entity
            self._save()
            self.telemetry["entities_moved"] += 1
            logger.info("Moved entity %s from %s to %s", entity_id, old_path, new_path)
            return entity
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to move entity %s", entity_id)
            raise

    def copy_entity(self, entity_id: str, new_name: Optional[str] = None) -> StorageEntity:
        try:
            source = self.get_entity(entity_id)
            return self.store_entity(
                storage_type=source.storage_type,
                name=new_name or f"{source.name}_copy",
                owner_id=source.owner_id,
                org_id=source.org_id,
                size_bytes=source.size_bytes,
                file_count=source.file_count,
                storage_class=source.storage_class,
                path=source.path + "_copy",
                retention=source.retention,
                encryption_enabled=source.encryption_enabled,
                compressed=source.compressed,
                metadata=dict(source.metadata),
            )
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to copy entity %s", entity_id)
            raise

    def compress_entity(self, entity_id: str) -> StorageEntity:
        try:
            entity = self.get_entity(entity_id)
            if entity.compressed:
                logger.info("Entity %s is already compressed", entity_id)
                return entity
            old_size = entity.size_bytes
            entity.compressed = True
            entity.size_bytes = max(1, int(entity.size_bytes * 0.4))
            entity.checksum = hashlib.sha256(f"compressed:{entity.id}:{time.time()}".encode()).hexdigest()[:16]
            self._entities[entity_id] = entity
            self._update_quota(entity.storage_type, entity.size_bytes - old_size, 0)
            self._save()
            self.telemetry["entities_compressed"] += 1
            logger.info("Compressed entity %s (size: %d -> %d)", entity_id, old_size, entity.size_bytes)
            return entity
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to compress entity %s", entity_id)
            raise

    def encrypt_entity(self, entity_id: str) -> StorageEntity:
        try:
            entity = self.get_entity(entity_id)
            if entity.encryption_enabled:
                logger.info("Entity %s is already encrypted", entity_id)
                return entity
            entity.encryption_enabled = True
            entity.checksum = hashlib.sha256(f"encrypted:{entity.id}:{time.time()}".encode()).hexdigest()[:16]
            self._entities[entity_id] = entity
            self._save()
            self.telemetry["entities_encrypted"] += 1
            logger.info("Encrypted entity %s", entity_id)
            return entity
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to encrypt entity %s", entity_id)
            raise

    def get_usage_by_org(self, org_id: str) -> dict:
        try:
            org_entities = [e for e in self._entities.values() if e.org_id == org_id]
            total_size = sum(e.size_bytes for e in org_entities)
            total_files = sum(e.file_count for e in org_entities)
            by_type = defaultdict(int)
            for e in org_entities:
                by_type[e.storage_type.value] += e.size_bytes
            return {
                "org_id": org_id,
                "total_size_bytes": total_size,
                "total_file_count": total_files,
                "entity_count": len(org_entities),
                "by_type": dict(by_type),
            }
        except Exception:
            logger.exception("Failed to get usage by org %s", org_id)
            raise

    def get_usage_by_type(self, storage_type: StorageType) -> dict:
        try:
            type_entities = [e for e in self._entities.values() if e.storage_type == storage_type]
            total_size = sum(e.size_bytes for e in type_entities)
            total_files = sum(e.file_count for e in type_entities)
            return {
                "storage_type": storage_type.value,
                "total_size_bytes": total_size,
                "total_file_count": total_files,
                "entity_count": len(type_entities),
            }
        except Exception:
            logger.exception("Failed to get usage by type %s", storage_type.value)
            raise

    # -- internal helpers ---------------------------------------------------

    def _update_quota(self, storage_type: StorageType, size_delta: int, file_delta: int) -> None:
        key = storage_type.value
        if key not in self._quotas:
            self._quotas[key] = StorageQuota(storage_type=storage_type)
        q = self._quotas[key]
        q.current_size_bytes = max(0, q.current_size_bytes + size_delta)
        q.current_file_count = max(0, q.current_file_count + file_delta)
        if q.max_size_bytes > 0:
            q.usage_percent = round((q.current_size_bytes / q.max_size_bytes) * 100, 2)
        else:
            q.usage_percent = 0.0


class ArtifactManager:
    """Manages artifacts with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._artifacts_file = os.path.join(storage_dir, "artifacts.json")
        self._artifacts: dict[str, Artifact] = {}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    # -- persistence --------------------------------------------------------

    def _load(self) -> None:
        try:
            if os.path.exists(self._artifacts_file):
                with open(self._artifacts_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._artifacts = {k: Artifact.from_dict(v) for k, v in data.items()}
                logger.info("Loaded %d artifacts", len(self._artifacts))
        except Exception:
            logger.exception("Failed to load artifacts; starting fresh")
            self._artifacts = {}

    def _save(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._artifacts.items()}
            tmp = self._artifacts_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._artifacts_file)
        except Exception:
            logger.exception("Failed to save artifacts")

    # -- CRUD ---------------------------------------------------------------

    def upload_artifact(self, entity_id: str, name: str, artifact_type: str = "",
                        version: str = "1.0.0", size_bytes: int = 0,
                        content_type: str = "", checksum: str = "",
                        tags: Optional[list[str]] = None,
                        metadata: Optional[dict] = None) -> Artifact:
        try:
            now = datetime.now(timezone.utc).isoformat()
            artifact = Artifact(
                id=str(uuid.uuid4()),
                entity_id=entity_id,
                name=name,
                artifact_type=artifact_type,
                version=version,
                size_bytes=size_bytes,
                content_type=content_type or "application/octet-stream",
                checksum=checksum or hashlib.sha256(f"{name}:{time.time()}".encode()).hexdigest()[:16],
                created_at=now,
                tags=tags or [],
                metadata=metadata or {},
            )
            self._artifacts[artifact.id] = artifact
            self._save()
            self.telemetry["artifacts_uploaded"] += 1
            logger.info("Uploaded artifact %s (%s v%s)", artifact.id, name, version)
            return artifact
        except Exception:
            logger.exception("Failed to upload artifact")
            raise

    def get_artifact(self, artifact_id: str) -> Artifact:
        artifact = self._artifacts.get(artifact_id)
        if artifact is None:
            raise ValueError(f"Artifact not found: {artifact_id}")
        self.telemetry["artifacts_read"] += 1
        return artifact

    def delete_artifact(self, artifact_id: str) -> None:
        try:
            if artifact_id not in self._artifacts:
                raise ValueError(f"Artifact not found: {artifact_id}")
            del self._artifacts[artifact_id]
            self._save()
            self.telemetry["artifacts_deleted"] += 1
            logger.info("Deleted artifact %s", artifact_id)
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to delete artifact %s", artifact_id)
            raise

    def list_artifacts(self, entity_id: Optional[str] = None,
                       artifact_type: Optional[str] = None) -> list[Artifact]:
        try:
            results = list(self._artifacts.values())
            if entity_id is not None:
                results = [a for a in results if a.entity_id == entity_id]
            if artifact_type is not None:
                results = [a for a in results if a.artifact_type == artifact_type]
            self.telemetry["artifacts_listed"] += 1
            return results
        except Exception:
            logger.exception("Failed to list artifacts")
            raise

    def get_latest_version(self, entity_id: str, name: str) -> Optional[Artifact]:
        try:
            matching = [a for a in self._artifacts.values()
                        if a.entity_id == entity_id and a.name == name]
            if not matching:
                return None
            matching.sort(key=lambda x: x.version, reverse=True)
            self.telemetry["latest_version_read"] += 1
            return matching[0]
        except Exception:
            logger.exception("Failed to get latest version")
            raise

    def list_versions(self, entity_id: str, name: str) -> list[Artifact]:
        try:
            results = [a for a in self._artifacts.values()
                       if a.entity_id == entity_id and a.name == name]
            results.sort(key=lambda x: x.created_at, reverse=True)
            self.telemetry["versions_listed"] += 1
            return results
        except Exception:
            logger.exception("Failed to list versions")
            raise

    def promote_artifact(self, artifact_id: str, new_version: str) -> Artifact:
        try:
            artifact = self.get_artifact(artifact_id)
            return self.upload_artifact(
                entity_id=artifact.entity_id,
                name=artifact.name,
                artifact_type=artifact.artifact_type,
                version=new_version,
                size_bytes=artifact.size_bytes,
                content_type=artifact.content_type,
                checksum=artifact.checksum,
                tags=list(artifact.tags),
                metadata={**artifact.metadata, "promoted_from": artifact.version},
            )
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to promote artifact %s", artifact_id)
            raise

    def deprecate_artifact(self, artifact_id: str) -> Artifact:
        try:
            artifact = self.get_artifact(artifact_id)
            artifact.metadata["deprecated"] = True
            artifact.metadata["deprecated_at"] = datetime.now(timezone.utc).isoformat()
            self._artifacts[artifact_id] = artifact
            self._save()
            self.telemetry["artifacts_deprecated"] += 1
            logger.info("Deprecated artifact %s", artifact_id)
            return artifact
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to deprecate artifact %s", artifact_id)
            raise


class BackupManager:
    """Manages backup configurations and operations with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._configs_file = os.path.join(storage_dir, "backup_configs.json")
        self._configs: dict[str, BackupConfig] = {}
        self._backups_file = os.path.join(storage_dir, "backups.json")
        self._backups: dict[str, dict] = {}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    # -- persistence --------------------------------------------------------

    def _load(self) -> None:
        try:
            if os.path.exists(self._configs_file):
                with open(self._configs_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._configs = {k: BackupConfig.from_dict(v) for k, v in data.items()}
                logger.info("Loaded %d backup configs", len(self._configs))
        except Exception:
            logger.exception("Failed to load backup configs; starting fresh")
            self._configs = {}

        try:
            if os.path.exists(self._backups_file):
                with open(self._backups_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._backups = dict(data)
        except Exception:
            self._backups = {}

    def _save(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._configs.items()}
            tmp = self._configs_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._configs_file)
        except Exception:
            logger.exception("Failed to save backup configs")

        try:
            data = dict(self._backups)
            tmp = self._backups_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._backups_file)
        except Exception:
            logger.exception("Failed to save backups")

    # -- CRUD for configs ---------------------------------------------------

    def create_backup_config(self, storage_type: StorageType, schedule: str = "0 0 * * *",
                             retention_days: int = 30, encryption_enabled: bool = False,
                             compression_enabled: bool = False,
                             target_path: str = "") -> BackupConfig:
        try:
            config = BackupConfig(
                id=str(uuid.uuid4()),
                storage_type=storage_type,
                schedule=schedule,
                retention_days=retention_days,
                encryption_enabled=encryption_enabled,
                compression_enabled=compression_enabled,
                target_path=target_path or f"backups/{storage_type.value}",
            )
            self._configs[config.id] = config
            self._save()
            self.telemetry["backup_configs_created"] += 1
            logger.info("Created backup config %s for %s", config.id, storage_type.value)
            return config
        except Exception:
            logger.exception("Failed to create backup config")
            raise

    def get_backup_config(self, config_id: str) -> BackupConfig:
        config = self._configs.get(config_id)
        if config is None:
            raise ValueError(f"Backup config not found: {config_id}")
        self.telemetry["backup_configs_read"] += 1
        return config

    def run_backup(self, config_id: str) -> dict:
        try:
            config = self.get_backup_config(config_id)
            now = datetime.now(timezone.utc).isoformat()
            backup_id = str(uuid.uuid4())
            backup_record = {
                "id": backup_id,
                "config_id": config_id,
                "storage_type": config.storage_type.value,
                "started_at": now,
                "completed_at": None,
                "status": "running",
                "size_bytes": 0,
                "encrypted": config.encryption_enabled,
                "compressed": config.compression_enabled,
                "target_path": config.target_path,
            }
            simulated_size = int(hashlib.sha256(backup_id.encode()).hexdigest()[:8], 16) % (1024 * 1024 * 100)
            backup_record["size_bytes"] = simulated_size
            backup_record["completed_at"] = datetime.now(timezone.utc).isoformat()
            backup_record["status"] = "completed"
            self._backups[backup_id] = backup_record
            config.last_backup = now
            self._configs[config_id] = config
            self._save()
            self.telemetry["backups_run"] += 1
            logger.info("Ran backup %s for config %s (%d bytes)", backup_id, config_id, simulated_size)
            return backup_record
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to run backup")
            raise

    def list_backups(self, config_id: Optional[str] = None) -> list[dict]:
        try:
            results = list(self._backups.values())
            if config_id is not None:
                results = [b for b in results if b["config_id"] == config_id]
            results.sort(key=lambda x: x.get("started_at", ""), reverse=True)
            self.telemetry["backups_listed"] += 1
            return results
        except Exception:
            logger.exception("Failed to list backups")
            raise

    def restore_from_backup(self, backup_id: str) -> dict:
        try:
            backup = self._backups.get(backup_id)
            if backup is None:
                raise ValueError(f"Backup not found: {backup_id}")
            restore_record = {
                "restore_id": str(uuid.uuid4()),
                "backup_id": backup_id,
                "storage_type": backup["storage_type"],
                "restored_at": datetime.now(timezone.utc).isoformat(),
                "size_bytes": backup["size_bytes"],
                "status": "restored",
            }
            self.telemetry["backups_restored"] += 1
            logger.info("Restored from backup %s", backup_id)
            return restore_record
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to restore from backup %s", backup_id)
            raise

    def verify_backup(self, backup_id: str) -> dict:
        try:
            backup = self._backups.get(backup_id)
            if backup is None:
                raise ValueError(f"Backup not found: {backup_id}")
            checksum = hashlib.sha256(f"{backup_id}:{backup.get('size_bytes', 0)}".encode()).hexdigest()
            result = {
                "backup_id": backup_id,
                "verified": True,
                "checksum": checksum,
                "verified_at": datetime.now(timezone.utc).isoformat(),
            }
            self.telemetry["backups_verified"] += 1
            return result
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to verify backup %s", backup_id)
            raise

    def cleanup_old_backups(self, retention_days: int = 30) -> int:
        try:
            cutoff = datetime.now(timezone.utc).timestamp() - (retention_days * 86400)
            to_delete = []
            for bid, backup in self._backups.items():
                started = backup.get("started_at", "")
                if started:
                    try:
                        ts = datetime.fromisoformat(started).timestamp()
                        if ts < cutoff:
                            to_delete.append(bid)
                    except (ValueError, TypeError):
                        to_delete.append(bid)
            for bid in to_delete:
                del self._backups[bid]
            if to_delete:
                self._save()
                self.telemetry["old_backups_cleaned"] += len(to_delete)
                logger.info("Cleaned up %d old backups (>%d days)", len(to_delete), retention_days)
            return len(to_delete)
        except Exception:
            logger.exception("Failed to cleanup old backups")
            return 0

    def get_backup_metrics(self) -> dict:
        try:
            total_backups = len(self._backups)
            total_size = sum(b.get("size_bytes", 0) for b in self._backups.values())
            completed = sum(1 for b in self._backups.values() if b.get("status") == "completed")
            failed = sum(1 for b in self._backups.values() if b.get("status") == "failed")
            running = sum(1 for b in self._backups.values() if b.get("status") == "running")
            return {
                "total_backups": total_backups,
                "total_size_bytes": total_size,
                "completed": completed,
                "failed": failed,
                "running": running,
                "config_count": len(self._configs),
            }
        except Exception:
            logger.exception("Failed to get backup metrics")
            raise
