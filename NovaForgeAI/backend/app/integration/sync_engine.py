"""Integration Sync Engine — one-way/two-way sync with conflict detection, resolution, retry, scheduling, priority, batch, streaming sync for all integrated services."""
import json, uuid, os, logging, hashlib
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


class SyncMode(Enum):
    ONE_WAY = "one_way"
    TWO_WAY = "two_way"


class SyncPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SyncSchedule(Enum):
    REALTIME = "realtime"
    BATCH = "batch"
    SCHEDULED = "scheduled"
    MANUAL = "manual"


@dataclass
class IntegrationSyncJob:
    id: str
    org_id: str
    connector_id: str
    entity_type: str
    mode: SyncMode
    priority: SyncPriority = SyncPriority.MEDIUM
    schedule: SyncSchedule = SyncSchedule.BATCH
    status: str = "pending"
    source_data: Any = None
    target_data: Any = None
    conflict: bool = False
    conflict_resolution: str = ""
    retry_count: int = 0
    max_retries: int = 3
    batch_id: str = ""
    started_at: str = ""
    completed_at: str = ""
    error: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["mode"] = self.mode.value
        d["priority"] = self.priority.value
        d["schedule"] = self.schedule.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "IntegrationSyncJob":
        data = data.copy()
        data["mode"] = SyncMode(data.get("mode", "one_way"))
        data["priority"] = SyncPriority(data.get("priority", "medium"))
        data["schedule"] = SyncSchedule(data.get("schedule", "batch"))
        return cls(**data)


@dataclass
class SyncBatch:
    id: str
    org_id: str
    status: str = "pending"
    total_jobs: int = 0
    completed_jobs: int = 0
    failed_jobs: int = 0
    started_at: str = ""
    completed_at: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "SyncBatch": return cls(**data)


class IntegrationSyncEngine:
    def __init__(self, storage_dir: str = "integration_data/sync"):
        self.storage_dir = storage_dir
        self._jobs: dict[str, IntegrationSyncJob] = {}
        self._batches: dict[str, SyncBatch] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _jobs_path(self) -> str: return os.path.join(self.storage_dir, "jobs.json")
    def _batches_path(self) -> str: return os.path.join(self.storage_dir, "batches.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._jobs_path(), self._jobs, IntegrationSyncJob),
            (self._batches_path(), self._batches, SyncBatch),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Failed to load sync engine data: %s", e)

    def _save(self) -> None:
        try:
            with open(self._jobs_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._jobs.items()}, f, indent=2, default=str)
            with open(self._batches_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._batches.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save sync engine data: %s", e)

    def create_job(self, org_id: str, connector_id: str, entity_type: str, mode: SyncMode = SyncMode.ONE_WAY, priority: SyncPriority = SyncPriority.MEDIUM, schedule: SyncSchedule = SyncSchedule.BATCH, batch_id: str = "") -> IntegrationSyncJob:
        job = IntegrationSyncJob(id=str(uuid.uuid4()), org_id=org_id, connector_id=connector_id, entity_type=entity_type, mode=mode, priority=priority, schedule=schedule, batch_id=batch_id)
        self._jobs[job.id] = job
        self._telemetry["jobs_created"] = self._telemetry.get("jobs_created", 0) + 1
        self._save()
        return job

    def start_job(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if not job: return False
        job.status = "running"
        job.started_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return True

    def complete_job(self, job_id: str, source_data: Any = None, target_data: Any = None) -> bool:
        job = self._jobs.get(job_id)
        if not job: return False
        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc).isoformat()
        job.source_data = source_data
        job.target_data = target_data
        self._save()
        return True

    def fail_job(self, job_id: str, error: str) -> bool:
        job = self._jobs.get(job_id)
        if not job: return False
        job.status = "failed"
        job.error = error
        job.retry_count += 1
        job.completed_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return True

    def detect_conflict(self, job_id: str, source_hash: str, target_hash: str) -> bool:
        job = self._jobs.get(job_id)
        if not job: return False
        if source_hash != target_hash:
            job.conflict = True
            job.status = "conflict"
            self._save()
            return True
        return False

    def resolve_conflict(self, job_id: str, resolution: str) -> bool:
        job = self._jobs.get(job_id)
        if not job: return False
        job.conflict = False
        job.conflict_resolution = resolution
        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return True

    def create_batch(self, org_id: str) -> SyncBatch:
        batch = SyncBatch(id=str(uuid.uuid4()), org_id=org_id)
        self._batches[batch.id] = batch
        self._save()
        return batch

    def list_jobs(self, org_id: str = "", status: str = "", connector_id: str = "", limit: int = 100) -> list[IntegrationSyncJob]:
        results = list(self._jobs.values())
        if org_id: results = [j for j in results if j.org_id == org_id]
        if status: results = [j for j in results if j.status == status]
        if connector_id: results = [j for j in results if j.connector_id == connector_id]
        return sorted(results, key=lambda j: ({"critical": 0, "high": 1, "medium": 2, "low": 3}.get(j.priority.value, 99), j.created_at))[:limit]

    def get_telemetry(self) -> dict: return dict(self._telemetry)
