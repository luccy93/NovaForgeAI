"""
Distributed Execution — Job Scheduler, Distributed Queue, Worker Pool, Retry, Priority, Checkpoint.
"""
import logging
logger = logging.getLogger(__name__)

from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
import json, uuid, hashlib, time
from collections import defaultdict, deque
import os


class JobStatus(Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"
    TIMEOUT = "timeout"


class JobPriority(Enum):
    LOW = 0
    MEDIUM = 1
    HIGH = 2
    CRITICAL = 3


class QueueType(Enum):
    MAIN = "main"
    RETRY = "retry"
    DELAYED = "delayed"
    DEAD_LETTER = "dead_letter"
    PRIORITY = "priority"


class CheckpointStatus(Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Job:
    id: str
    name: str
    type: str
    priority: JobPriority
    status: JobStatus
    queue: QueueType
    payload: dict
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    worker_id: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    timeout_seconds: int = 300
    progress: float = 0.0
    result: Optional[dict] = None
    error: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["priority"] = self.priority.value
        d["status"] = self.status.value
        d["queue"] = self.queue.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "Job":
        data = dict(data)
        data["priority"] = JobPriority(data["priority"])
        data["status"] = JobStatus(data["status"])
        data["queue"] = QueueType(data["queue"])
        return Job(**data)


@dataclass
class JobBatch:
    id: str
    jobs: list[Job] = field(default_factory=list)
    created_at: str = ""
    status: JobStatus = JobStatus.PENDING

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["jobs"] = [j.to_dict() for j in self.jobs]
        return d

    @staticmethod
    def from_dict(data: dict) -> "JobBatch":
        data = dict(data)
        data["status"] = JobStatus(data["status"])
        data["jobs"] = [Job.from_dict(j) for j in data.get("jobs", [])]
        return JobBatch(**data)


@dataclass
class QueueMetrics:
    queue_name: str
    length: int = 0
    processing: int = 0
    completed: int = 0
    failed: int = 0
    avg_wait_time_ms: float = 0.0
    avg_processing_time_ms: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "QueueMetrics":
        return QueueMetrics(**data)


@dataclass
class WorkerPoolConfig:
    min_workers: int = 2
    max_workers: int = 20
    scale_up_threshold: float = 0.75
    scale_down_threshold: float = 0.25
    cooldown_seconds: int = 60

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "WorkerPoolConfig":
        return WorkerPoolConfig(**data)


@dataclass
class Checkpoint:
    id: str
    job_id: str
    stage: str
    status: CheckpointStatus
    data: dict
    created_at: str
    updated_at: str

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "Checkpoint":
        data = dict(data)
        data["status"] = CheckpointStatus(data["status"])
        return Checkpoint(**data)


# ---------------------------------------------------------------------------
# Pool worker record (lightweight, separate from the full WorkerInstance)
# ---------------------------------------------------------------------------

@dataclass
class PoolWorker:
    id: str
    name: str
    host: str
    port: int
    status: str  # "available", "busy", "offline"
    current_job_id: Optional[str] = None
    last_heartbeat: str = ""
    registered_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "PoolWorker":
        return PoolWorker(**data)


# ---------------------------------------------------------------------------
# Managers
# ---------------------------------------------------------------------------

class DistributedQueue:
    """Distributed job queue with main, retry, delayed, dead-letter, and priority sub-queues."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._queues_file = os.path.join(storage_dir, "distributed_queues.json")
        # Internal deques per queue type
        self._queues: dict[str, deque[Job]] = defaultdict(deque)
        self._metrics_file = os.path.join(storage_dir, "queue_metrics.json")
        self._metrics: dict[str, QueueMetrics] = {}
        self._processing: dict[str, Job] = {}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    # -- persistence --------------------------------------------------------

    def _load(self) -> None:
        try:
            if os.path.exists(self._queues_file):
                with open(self._queues_file, "r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                self._queues = defaultdict(
                    deque,
                    {k: deque(Job.from_dict(j) for j in v) for k, v in raw.get("queues", {}).items()},
                )
                self._processing = {
                    k: Job.from_dict(v) for k, v in raw.get("processing", {}).items()
                }
                logger.info("Loaded distributed queues")
        except Exception:
            logger.exception("Failed to load queues; starting fresh")
            self._queues = defaultdict(deque)
            self._processing = {}

        try:
            if os.path.exists(self._metrics_file):
                with open(self._metrics_file, "r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                self._metrics = {k: QueueMetrics.from_dict(v) for k, v in raw.items()}
        except Exception:
            self._metrics = {}

    def _save(self) -> None:
        try:
            data = {
                "queues": {k: [j.to_dict() for j in q] for k, q in self._queues.items()},
                "processing": {k: v.to_dict() for k, v in self._processing.items()},
            }
            tmp = self._queues_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._queues_file)
        except Exception:
            logger.exception("Failed to save queues")

        try:
            data = {k: v.to_dict() for k, v in self._metrics.items()}
            tmp = self._metrics_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._metrics_file)
        except Exception:
            logger.exception("Failed to save queue metrics")

    # -- core operations ----------------------------------------------------

    def enqueue(self, job: Job, queue_type: QueueType = QueueType.MAIN) -> None:
        try:
            job.queue = queue_type
            job.status = JobStatus.QUEUED
            self._queues[queue_type.value].append(job)
            self._update_metrics(queue_type.value)
            self._save()
            self.telemetry["enqueued"] += 1
            logger.debug("Enqueued job %s to %s", job.id, queue_type.value)
        except Exception:
            logger.exception("Failed to enqueue job %s", job.id)
            raise

    def dequeue(self, queue_type: QueueType = QueueType.MAIN,
                timeout_seconds: Optional[int] = None) -> Optional[Job]:
        try:
            q = self._queues.get(queue_type.value)
            if not q:
                return None

            job = q.popleft()
            now = datetime.now(timezone.utc).isoformat()
            job.started_at = now
            job.status = JobStatus.RUNNING
            self._processing[job.id] = job
            self._update_metrics(queue_type.value)

            # Check timeout
            if timeout_seconds is not None and job.timeout_seconds > 0:
                created = datetime.fromisoformat(job.created_at)
                elapsed = (datetime.now(timezone.utc) - created).total_seconds()
                if elapsed > job.timeout_seconds:
                    job.status = JobStatus.TIMEOUT
                    self.fail(job.id, error="Job timed out")
                    return None

            self._save()
            self.telemetry["dequeued"] += 1
            return job
        except IndexError:
            return None
        except Exception:
            logger.exception("Failed to dequeue from %s", queue_type.value)
            raise

    def peek(self, queue_type: QueueType = QueueType.MAIN) -> Optional[Job]:
        try:
            q = self._queues.get(queue_type.value)
            if q:
                return q[0]
            return None
        except Exception:
            logger.exception("Failed to peek queue %s", queue_type.value)
            raise

    def acknowledge(self, job_id: str) -> None:
        try:
            if job_id in self._processing:
                job = self._processing.pop(job_id)
                job.status = JobStatus.COMPLETED
                job.completed_at = datetime.now(timezone.utc).isoformat()
                m = self._metrics.get(job.queue.value)
                if m:
                    m.completed += 1
                    if job.started_at:
                        start = datetime.fromisoformat(job.started_at)
                        end = datetime.fromisoformat(job.completed_at)
                        m.avg_processing_time_ms = (
                            (m.avg_processing_time_ms * (m.completed - 1) +
                             (end - start).total_seconds() * 1000) / m.completed
                        )
                self._save()
                self.telemetry["acknowledged"] += 1
                logger.debug("Acknowledged job %s", job_id)
        except Exception:
            logger.exception("Failed to acknowledge job %s", job_id)
            raise

    def fail(self, job_id: str, error: str = "Unknown error") -> None:
        try:
            if job_id in self._processing:
                job = self._processing.pop(job_id)
                job.status = JobStatus.FAILED
                job.error = error
                job.completed_at = datetime.now(timezone.utc).isoformat()
                m = self._metrics.get(job.queue.value)
                if m:
                    m.failed += 1
                self._save()
                self.telemetry["failed"] += 1
                logger.warning("Failed job %s: %s", job_id, error)
        except Exception:
            logger.exception("Failed to mark job %s as failed", job_id)
            raise

    def requeue(self, job_id: str, new_queue: Optional[QueueType] = None) -> None:
        try:
            job = self._processing.pop(job_id, None)
            if job is None:
                raise ValueError(f"Job {job_id} not found in processing")

            target = new_queue or QueueType.RETRY
            job.retry_count += 1
            job.status = JobStatus.RETRYING if target == QueueType.RETRY else JobStatus.QUEUED
            self.enqueue(job, target)
            self.telemetry["requeued"] += 1
            logger.info("Requeued job %s to %s (retry %d)", job_id, target.value, job.retry_count)
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to requeue job %s", job_id)
            raise

    def get_metrics(self, queue_type: Optional[QueueType] = None) -> list[QueueMetrics]:
        try:
            if queue_type:
                m = self._metrics.get(queue_type.value)
                return [m] if m else []
            return list(self._metrics.values())
        except Exception:
            logger.exception("Failed to get queue metrics")
            raise

    def get_length(self, queue_type: Optional[QueueType] = None) -> int:
        try:
            if queue_type:
                return len(self._queues.get(queue_type.value, []))
            return sum(len(q) for q in self._queues.values())
        except Exception:
            logger.exception("Failed to get queue length")
            return 0

    def clear(self, queue_type: Optional[QueueType] = None) -> None:
        try:
            if queue_type:
                self._queues[queue_type.value].clear()
            else:
                self._queues.clear()
            self._save()
            self.telemetry["queues_cleared"] += 1
            logger.info("Cleared queues")
        except Exception:
            logger.exception("Failed to clear queues")
            raise

    def batch_enqueue(self, jobs: list[Job], queue_type: QueueType = QueueType.MAIN) -> int:
        try:
            count = 0
            for job in jobs:
                self.enqueue(job, queue_type)
                count += 1
            self.telemetry["batch_enqueued"] += count
            return count
        except Exception:
            logger.exception("Failed to batch enqueue jobs")
            raise

    def get_dead_letter(self) -> list[Job]:
        try:
            return list(self._queues.get(QueueType.DEAD_LETTER.value, []))
        except Exception:
            logger.exception("Failed to get dead letter queue")
            raise

    # -- internal helpers ---------------------------------------------------

    def _update_metrics(self, queue_name: str) -> None:
        if queue_name not in self._metrics:
            self._metrics[queue_name] = QueueMetrics(queue_name=queue_name)
        m = self._metrics[queue_name]
        m.length = len(self._queues.get(queue_name, []))
        m.processing = len(self._processing)


class WorkerPool:
    """Manages a pool of workers for job execution."""

    def __init__(self, storage_dir: str, config: Optional[WorkerPoolConfig] = None):
        self.storage_dir = storage_dir
        self._pool_file = os.path.join(storage_dir, "worker_pool.json")
        self._config_file = os.path.join(storage_dir, "worker_pool_config.json")
        self._workers: dict[str, PoolWorker] = {}
        self.config: WorkerPoolConfig = config or WorkerPoolConfig()
        self._last_scale_time: float = 0.0
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    # -- persistence --------------------------------------------------------

    def _load(self) -> None:
        try:
            if os.path.exists(self._pool_file):
                with open(self._pool_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._workers = {k: PoolWorker.from_dict(v) for k, v in data.items()}
        except Exception:
            self._workers = {}

        try:
            if os.path.exists(self._config_file):
                with open(self._config_file, "r", encoding="utf-8") as fh:
                    self.config = WorkerPoolConfig.from_dict(json.load(fh))
        except Exception:
            pass

        logger.info("Loaded %d pool workers", len(self._workers))

    def _save(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._workers.items()}
            tmp = self._pool_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._pool_file)
        except Exception:
            logger.exception("Failed to save worker pool")

        try:
            tmp = self._config_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.config.to_dict(), fh, indent=2, default=str)
            os.replace(tmp, self._config_file)
        except Exception:
            logger.exception("Failed to save worker pool config")

    # -- CRUD ---------------------------------------------------------------

    def register_worker(self, name: str, host: str, port: int) -> PoolWorker:
        try:
            now = datetime.now(timezone.utc).isoformat()
            w = PoolWorker(
                id=str(uuid.uuid4()),
                name=name,
                host=host,
                port=port,
                status="available",
                last_heartbeat=now,
                registered_at=now,
            )
            self._workers[w.id] = w
            self._save()
            self.telemetry["pool_workers_registered"] += 1
            logger.info("Registered pool worker %s (%s)", w.id, name)
            return w
        except Exception:
            logger.exception("Failed to register pool worker")
            raise

    def unregister_worker(self, worker_id: str) -> None:
        try:
            if worker_id not in self._workers:
                raise ValueError(f"Pool worker not found: {worker_id}")
            del self._workers[worker_id]
            self._save()
            self.telemetry["pool_workers_unregistered"] += 1
            logger.info("Unregistered pool worker %s", worker_id)
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to unregister pool worker %s", worker_id)
            raise

    def get_worker(self, worker_id: str) -> PoolWorker:
        w = self._workers.get(worker_id)
        if w is None:
            raise ValueError(f"Pool worker not found: {worker_id}")
        return w

    def list_workers(self, status: Optional[str] = None) -> list[PoolWorker]:
        try:
            if status:
                return [w for w in self._workers.values() if w.status == status]
            return list(self._workers.values())
        except Exception:
            logger.exception("Failed to list pool workers")
            raise

    def assign_job(self, worker_id: str, job_id: str) -> PoolWorker:
        try:
            w = self.get_worker(worker_id)
            if w.status != "available":
                raise ValueError(f"Worker {worker_id} is not available (status: {w.status})")
            w.status = "busy"
            w.current_job_id = job_id
            w.last_heartbeat = datetime.now(timezone.utc).isoformat()
            self._workers[worker_id] = w
            self._save()
            self.telemetry["pool_jobs_assigned"] += 1
            return w
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to assign job %s to worker %s", job_id, worker_id)
            raise

    def complete_job(self, worker_id: str, success: bool = True) -> PoolWorker:
        try:
            w = self.get_worker(worker_id)
            w.status = "available"
            w.current_job_id = None
            w.last_heartbeat = datetime.now(timezone.utc).isoformat()
            self._workers[worker_id] = w
            self._save()
            self.telemetry["pool_jobs_completed"] += 1
            return w
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to complete job on worker %s", worker_id)
            raise

    def fail_worker(self, worker_id: str) -> PoolWorker:
        try:
            w = self.get_worker(worker_id)
            w.status = "offline"
            w.current_job_id = None
            w.last_heartbeat = datetime.now(timezone.utc).isoformat()
            self._workers[worker_id] = w
            self._save()
            self.telemetry["pool_workers_failed"] += 1
            return w
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to mark worker %s as failed", worker_id)
            raise

    def get_available_count(self) -> int:
        try:
            return sum(1 for w in self._workers.values() if w.status == "available")
        except Exception:
            return 0

    def scale_up(self, count: int = 1) -> list[PoolWorker]:
        try:
            now_time = time.time()
            if now_time - self._last_scale_time < self.config.cooldown_seconds:
                logger.info("Scale cooldown active, skipping scale up")
                return []

            new_workers = []
            for i in range(count):
                w = self.register_worker(
                    name=f"auto-worker-{uuid.uuid4().hex[:6]}",
                    host="localhost",
                    port=9000 + len(self._workers) + i,
                )
                new_workers.append(w)
            self._last_scale_time = now_time
            self.telemetry["pool_scaled_up"] += count
            logger.info("Scaled up %d workers", count)
            return new_workers
        except Exception:
            logger.exception("Failed to scale up workers")
            raise

    def scale_down(self, count: int = 1) -> int:
        try:
            now_time = time.time()
            if now_time - self._last_scale_time < self.config.cooldown_seconds:
                logger.info("Scale cooldown active, skipping scale down")
                return 0

            available = [w for w in self._workers.values() if w.status == "available"]
            to_remove = available[:count]
            for w in to_remove:
                self.unregister_worker(w.id)
            self._last_scale_time = now_time
            self.telemetry["pool_scaled_down"] += len(to_remove)
            logger.info("Scaled down %d workers", len(to_remove))
            return len(to_remove)
        except Exception:
            logger.exception("Failed to scale down workers")
            raise

    def auto_scale(self) -> int:
        try:
            total = len(self._workers)
            available = self.get_available_count()
            if total == 0:
                return self.scale_up(self.config.min_workers)

            utilization = 1.0 - (available / total) if total > 0 else 0.0

            if utilization > self.config.scale_up_threshold and total < self.config.max_workers:
                scale_by = min(
                    int(total * 0.5) + 1,
                    self.config.max_workers - total,
                )
                return len(self.scale_up(scale_by))
            elif utilization < self.config.scale_down_threshold and total > self.config.min_workers:
                scale_by = min(
                    int(total * 0.3) + 1,
                    total - self.config.min_workers,
                )
                return self.scale_down(scale_by)

            return 0
        except Exception:
            logger.exception("Failed to auto-scale workers")
            raise


class JobScheduler:
    """Job scheduler with single and recurring job support."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._jobs_file = os.path.join(storage_dir, "scheduled_jobs.json")
        self._scheduled_jobs: dict[str, Job] = {}
        self._recurring_file = os.path.join(storage_dir, "recurring_jobs.json")
        self._recurring_jobs: dict[str, dict] = {}  # job_id -> {"cron": str, "job": Job}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    # -- persistence --------------------------------------------------------

    def _load(self) -> None:
        try:
            if os.path.exists(self._jobs_file):
                with open(self._jobs_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._scheduled_jobs = {k: Job.from_dict(v) for k, v in data.items()}
        except Exception:
            self._scheduled_jobs = {}

        try:
            if os.path.exists(self._recurring_file):
                with open(self._recurring_file, "r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                self._recurring_jobs = {
                    k: {"cron": v["cron"], "job": Job.from_dict(v["job"])}
                    for k, v in raw.items()
                }
        except Exception:
            self._recurring_jobs = {}

        logger.info("Loaded %d scheduled jobs, %d recurring", len(self._scheduled_jobs), len(self._recurring_jobs))

    def _save(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._scheduled_jobs.items()}
            tmp = self._jobs_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._jobs_file)
        except Exception:
            logger.exception("Failed to save scheduled jobs")

        try:
            data = {
                k: {"cron": v["cron"], "job": v["job"].to_dict()}
                for k, v in self._recurring_jobs.items()
            }
            tmp = self._recurring_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._recurring_file)
        except Exception:
            logger.exception("Failed to save recurring jobs")

    # -- CRUD ---------------------------------------------------------------

    def create_job(self, name: str, type: str, payload: Optional[dict] = None,
                   priority: JobPriority = JobPriority.MEDIUM,
                   max_retries: int = 3, timeout_seconds: int = 300,
                   tags: Optional[list[str]] = None,
                   dependencies: Optional[list[str]] = None) -> Job:
        try:
            now = datetime.now(timezone.utc).isoformat()
            job = Job(
                id=str(uuid.uuid4()),
                name=name,
                type=type,
                priority=priority,
                status=JobStatus.PENDING,
                queue=QueueType.MAIN,
                payload=payload or {},
                created_at=now,
                max_retries=max_retries,
                timeout_seconds=timeout_seconds,
                tags=tags or [],
                dependencies=dependencies or [],
            )
            self._scheduled_jobs[job.id] = job
            self._save()
            self.telemetry["jobs_created"] += 1
            logger.info("Created job %s (%s)", job.id, name)
            return job
        except Exception:
            logger.exception("Failed to create job")
            raise

    def get_job(self, job_id: str) -> Job:
        job = self._scheduled_jobs.get(job_id)
        if job is None:
            raise ValueError(f"Job not found: {job_id}")
        return job

    def update_job(self, job_id: str, **kwargs) -> Job:
        try:
            job = self.get_job(job_id)
            for key, val in kwargs.items():
                if hasattr(job, key) and key not in ("id", "created_at"):
                    setattr(job, key, val)
            self._scheduled_jobs[job_id] = job
            self._save()
            self.telemetry["jobs_updated"] += 1
            return job
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to update job %s", job_id)
            raise

    def cancel_job(self, job_id: str) -> Job:
        return self.update_job(job_id, status=JobStatus.CANCELLED)

    def pause_job(self, job_id: str) -> Job:
        return self.update_job(job_id, status=JobStatus.PAUSED)

    def resume_job(self, job_id: str) -> Job:
        return self.update_job(job_id, status=JobStatus.QUEUED)

    def list_jobs(self, status: Optional[JobStatus] = None,
                  type: Optional[str] = None) -> list[Job]:
        try:
            results = list(self._scheduled_jobs.values())
            if status is not None:
                results = [j for j in results if j.status == status]
            if type is not None:
                results = [j for j in results if j.type == type]
            self.telemetry["jobs_listed"] += 1
            return results
        except Exception:
            logger.exception("Failed to list jobs")
            raise

    def schedule_once(self, job: Job, delay_seconds: int = 0) -> Job:
        try:
            if delay_seconds > 0:
                job.status = JobStatus.PENDING
                scheduled_time = datetime.now(timezone.utc).timestamp() + delay_seconds
                job.payload["_scheduled_at"] = scheduled_time
            else:
                job.status = JobStatus.QUEUED
                job.queue = QueueType.MAIN

            self._scheduled_jobs[job.id] = job
            self._save()
            self.telemetry["jobs_scheduled_once"] += 1
            logger.info("Scheduled job %s once (delay=%ds)", job.id, delay_seconds)
            return job
        except Exception:
            logger.exception("Failed to schedule job once")
            raise

    def schedule_recurring(self, job: Job, cron_expression: str) -> Job:
        try:
            self._recurring_jobs[job.id] = {"cron": cron_expression, "job": job}
            self._save()
            self.telemetry["jobs_scheduled_recurring"] += 1
            logger.info("Scheduled recurring job %s (cron=%s)", job.id, cron_expression)
            return job
        except Exception:
            logger.exception("Failed to schedule recurring job")
            raise

    def get_scheduled_jobs(self) -> list[Job]:
        try:
            return list(self._scheduled_jobs.values())
        except Exception:
            logger.exception("Failed to get scheduled jobs")
            raise

    def process_next(self, queue: DistributedQueue, worker_pool: WorkerPool) -> Optional[str]:
        try:
            job = queue.dequeue(QueueType.MAIN)
            if job is None:
                job = queue.dequeue(QueueType.PRIORITY)
            if job is None:
                return None

            available = worker_pool.get_available_count()
            if available == 0:
                queue.enqueue(job, QueueType.MAIN)
                return None

            workers = worker_pool.list_workers(status="available")
            if not workers:
                queue.enqueue(job, QueueType.MAIN)
                return None

            target = workers[0]
            worker_pool.assign_job(target.id, job.id)
            self.update_job(job.id, status=JobStatus.RUNNING, worker_id=target.id)
            self.telemetry["jobs_processed"] += 1
            return job.id
        except Exception:
            logger.exception("Failed to process next job")
            return None

    def batch_process(self, queue: DistributedQueue, worker_pool: WorkerPool,
                      max_batch: int = 10) -> list[str]:
        try:
            processed = []
            for _ in range(max_batch):
                result = self.process_next(queue, worker_pool)
                if result is None:
                    break
                processed.append(result)
            self.telemetry["batch_processed"] += len(processed)
            return processed
        except Exception:
            logger.exception("Failed to batch process jobs")
            raise


class RetryQueue:
    """Retry queue that handles failed jobs with retry logic."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._retry_file = os.path.join(storage_dir, "retry_queue.json")
        self._retry_jobs: dict[str, Job] = {}
        self._dead_letter_file = os.path.join(storage_dir, "dead_letter_queue.json")
        self._dead_letter: dict[str, Job] = {}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    # -- persistence --------------------------------------------------------

    def _load(self) -> None:
        try:
            if os.path.exists(self._retry_file):
                with open(self._retry_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._retry_jobs = {k: Job.from_dict(v) for k, v in data.items()}
        except Exception:
            self._retry_jobs = {}

        try:
            if os.path.exists(self._dead_letter_file):
                with open(self._dead_letter_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._dead_letter = {k: Job.from_dict(v) for k, v in data.items()}
        except Exception:
            self._dead_letter = {}

    def _save(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._retry_jobs.items()}
            tmp = self._retry_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._retry_file)
        except Exception:
            logger.exception("Failed to save retry queue")

        try:
            data = {k: v.to_dict() for k, v in self._dead_letter.items()}
            tmp = self._dead_letter_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._dead_letter_file)
        except Exception:
            logger.exception("Failed to save dead letter queue")

    # -- operations ---------------------------------------------------------

    def add_to_retry(self, job: Job) -> None:
        try:
            job.status = JobStatus.RETRYING
            job.queue = QueueType.RETRY
            self._retry_jobs[job.id] = job
            self._save()
            self.telemetry["added_to_retry"] += 1
            logger.info("Added job %s to retry queue (attempt %d/%d)", job.id, job.retry_count, job.max_retries)
        except Exception:
            logger.exception("Failed to add job %s to retry queue", job.id)
            raise

    def process_retries(self, queue: DistributedQueue) -> int:
        try:
            processed = 0
            retry_ids = list(self._retry_jobs.keys())
            for jid in retry_ids:
                job = self._retry_jobs[jid]
                if job.retry_count >= job.max_retries:
                    self.move_to_dead_letter(jid)
                    continue

                job.retry_count += 1
                job.status = JobStatus.QUEUED
                job.queue = QueueType.MAIN
                queue.enqueue(job, QueueType.MAIN)
                del self._retry_jobs[jid]
                processed += 1

            if processed:
                self._save()
                self.telemetry["retries_processed"] += processed
                logger.info("Processed %d retry jobs", processed)
            return processed
        except Exception:
            logger.exception("Failed to process retries")
            raise

    def get_retry_count(self, job_id: str) -> int:
        job = self._retry_jobs.get(job_id)
        if job is None:
            return 0
        return job.retry_count

    def max_retries_reached(self, job_id: str) -> bool:
        job = self._retry_jobs.get(job_id)
        if job is None:
            return False
        return job.retry_count >= job.max_retries

    def move_to_dead_letter(self, job_id: str) -> None:
        try:
            if job_id not in self._retry_jobs:
                raise ValueError(f"Job {job_id} not found in retry queue")
            job = self._retry_jobs.pop(job_id)
            job.status = JobStatus.FAILED
            job.queue = QueueType.DEAD_LETTER
            if not job.error:
                job.error = "Max retries exceeded"
            self._dead_letter[job_id] = job
            self._save()
            self.telemetry["moved_to_dead_letter"] += 1
            logger.warning("Moved job %s to dead letter queue (retries exhausted)", job_id)
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to move job %s to dead letter", job_id)
            raise


class PriorityQueue:
    """Priority-based queue where higher-priority jobs are dequeued first."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._priority_file = os.path.join(storage_dir, "priority_queue.json")
        # Buckets by priority value: {0: [], 1: [], 2: [], 3: []}
        self._buckets: dict[int, list[Job]] = defaultdict(list)
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    # -- persistence --------------------------------------------------------

    def _load(self) -> None:
        try:
            if os.path.exists(self._priority_file):
                with open(self._priority_file, "r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                self._buckets = defaultdict(
                    list,
                    {int(k): [Job.from_dict(j) for j in v] for k, v in raw.items()},
                )
                logger.info("Loaded priority queue with %d buckets", len(self._buckets))
        except Exception:
            self._buckets = defaultdict(list)

    def _save(self) -> None:
        try:
            data = {str(k): [j.to_dict() for j in v] for k, v in self._buckets.items()}
            tmp = self._priority_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._priority_file)
        except Exception:
            logger.exception("Failed to save priority queue")

    # -- operations ---------------------------------------------------------

    def enqueue_priority(self, job: Job) -> None:
        try:
            prio = job.priority.value
            self._buckets[prio].append(job)
            self._save()
            self.telemetry["priority_enqueued"] += 1
            logger.debug("Enqueued job %s with priority %s", job.id, job.priority.name)
        except Exception:
            logger.exception("Failed to enqueue priority job")
            raise

    def dequeue_highest_priority(self) -> Optional[Job]:
        try:
            for prio in sorted(self._buckets.keys(), reverse=True):
                bucket = self._buckets[prio]
                if bucket:
                    job = bucket.pop(0)
                    if not self._buckets[prio]:
                        del self._buckets[prio]
                    self._save()
                    self.telemetry["priority_dequeued"] += 1
                    return job
            return None
        except Exception:
            logger.exception("Failed to dequeue highest priority job")
            raise

    def promote_job(self, job_id: str) -> bool:
        try:
            for prio in list(self._buckets.keys()):
                bucket = self._buckets[prio]
                for i, job in enumerate(bucket):
                    if job.id == job_id:
                        current_prio = job.priority.value
                        new_prio = min(current_prio + 1, JobPriority.CRITICAL.value)
                        if new_prio == current_prio:
                            return False
                        bucket.pop(i)
                        job.priority = JobPriority(new_prio)
                        self._buckets[new_prio].append(job)
                        if not bucket:
                            del self._buckets[prio]
                        self._save()
                        self.telemetry["jobs_promoted"] += 1
                        logger.info("Promoted job %s to priority %s", job_id, job.priority.name)
                        return True
            return False
        except Exception:
            logger.exception("Failed to promote job %s", job_id)
            return False

    def demote_job(self, job_id: str) -> bool:
        try:
            for prio in list(self._buckets.keys()):
                bucket = self._buckets[prio]
                for i, job in enumerate(bucket):
                    if job.id == job_id:
                        current_prio = job.priority.value
                        new_prio = max(current_prio - 1, JobPriority.LOW.value)
                        if new_prio == current_prio:
                            return False
                        bucket.pop(i)
                        job.priority = JobPriority(new_prio)
                        self._buckets[new_prio].append(job)
                        if not bucket:
                            del self._buckets[prio]
                        self._save()
                        self.telemetry["jobs_demoted"] += 1
                        logger.info("Demoted job %s to priority %s", job_id, job.priority.name)
                        return True
            return False
        except Exception:
            logger.exception("Failed to demote job %s", job_id)
            return False


class CheckpointManager:
    """Manages checkpoints for job progress tracking and rollback."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._cp_file = os.path.join(storage_dir, "checkpoints.json")
        self._checkpoints: dict[str, Checkpoint] = {}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    # -- persistence --------------------------------------------------------

    def _load(self) -> None:
        try:
            if os.path.exists(self._cp_file):
                with open(self._cp_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._checkpoints = {k: Checkpoint.from_dict(v) for k, v in data.items()}
                logger.info("Loaded %d checkpoints", len(self._checkpoints))
        except Exception:
            self._checkpoints = {}

    def _save(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._checkpoints.items()}
            tmp = self._cp_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._cp_file)
        except Exception:
            logger.exception("Failed to save checkpoints")

    # -- CRUD ---------------------------------------------------------------

    def create_checkpoint(self, job_id: str, stage: str,
                          data: Optional[dict] = None) -> Checkpoint:
        try:
            now = datetime.now(timezone.utc).isoformat()
            cp = Checkpoint(
                id=str(uuid.uuid4()),
                job_id=job_id,
                stage=stage,
                status=CheckpointStatus.RUNNING,
                data=data or {},
                created_at=now,
                updated_at=now,
            )
            self._checkpoints[cp.id] = cp
            self._save()
            self.telemetry["checkpoints_created"] += 1
            logger.info("Created checkpoint %s for job %s (stage=%s)", cp.id, job_id, stage)
            return cp
        except Exception:
            logger.exception("Failed to create checkpoint")
            raise

    def update_checkpoint(self, checkpoint_id: str, status: Optional[CheckpointStatus] = None,
                          data: Optional[dict] = None) -> Checkpoint:
        try:
            cp = self.get_checkpoint(checkpoint_id)
            if status is not None:
                cp.status = status
            if data is not None:
                cp.data.update(data)
            cp.updated_at = datetime.now(timezone.utc).isoformat()
            self._checkpoints[checkpoint_id] = cp
            self._save()
            self.telemetry["checkpoints_updated"] += 1
            return cp
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to update checkpoint %s", checkpoint_id)
            raise

    def get_checkpoint(self, checkpoint_id: str) -> Checkpoint:
        cp = self._checkpoints.get(checkpoint_id)
        if cp is None:
            raise ValueError(f"Checkpoint not found: {checkpoint_id}")
        return cp

    def list_checkpoints(self, job_id: Optional[str] = None) -> list[Checkpoint]:
        try:
            results = list(self._checkpoints.values())
            if job_id is not None:
                results = [c for c in results if c.job_id == job_id]
            self.telemetry["checkpoints_listed"] += 1
            return results
        except Exception:
            logger.exception("Failed to list checkpoints")
            raise

    def rollback_to_checkpoint(self, checkpoint_id: str) -> dict:
        try:
            cp = self.get_checkpoint(checkpoint_id)
            rollback_data = {
                "checkpoint_id": cp.id,
                "job_id": cp.job_id,
                "stage": cp.stage,
                "snapshot_data": dict(cp.data),
                "rolled_back_at": datetime.now(timezone.utc).isoformat(),
            }
            self.telemetry["checkpoints_rolled_back"] += 1
            logger.info("Rolled back to checkpoint %s (job=%s, stage=%s)", cp.id, cp.job_id, cp.stage)
            return rollback_data
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to rollback to checkpoint %s", checkpoint_id)
            raise

    def cleanup_old_checkpoints(self, max_age_hours: int = 24) -> int:
        try:
            now = datetime.now(timezone.utc)
            cutoff = now.timestamp() - (max_age_hours * 3600)
            to_delete = []
            for cid, cp in self._checkpoints.items():
                try:
                    ctime = datetime.fromisoformat(cp.created_at).timestamp()
                    if ctime < cutoff:
                        to_delete.append(cid)
                except (ValueError, TypeError):
                    to_delete.append(cid)

            for cid in to_delete:
                del self._checkpoints[cid]

            if to_delete:
                self._save()
                self.telemetry["checkpoints_cleaned"] += len(to_delete)
                logger.info("Cleaned up %d old checkpoints (>%dh)", len(to_delete), max_age_hours)
            return len(to_delete)
        except Exception:
            logger.exception("Failed to cleanup old checkpoints")
            return 0


class ExecutionManager(JobScheduler, WorkerPool, DistributedQueue, RetryQueue, PriorityQueue, CheckpointManager):
    """Unified execution manager combining all scheduling, queue, pool, retry, priority, and checkpoint subsystems."""

    def __init__(self, storage_dir: str,
                 pool_config: Optional[WorkerPoolConfig] = None):
        JobScheduler.__init__(self, storage_dir)
        WorkerPool.__init__(self, storage_dir, config=pool_config)
        DistributedQueue.__init__(self, storage_dir)
        RetryQueue.__init__(self, storage_dir)
        PriorityQueue.__init__(self, storage_dir)
        CheckpointManager.__init__(self, storage_dir)
        self.telemetry: dict = defaultdict(int)
        logger.info("ExecutionManager initialized at %s", storage_dir)

    def execute_pipeline(self, job_names: list[str],
                         payloads: Optional[list[dict]] = None,
                         job_type: str = "pipeline") -> list[Job]:
        try:
            jobs = []
            for i, name in enumerate(job_names):
                pl = payloads[i] if payloads and i < len(payloads) else {}
                job = self.create_job(
                    name=name,
                    type=job_type,
                    payload=pl,
                    priority=JobPriority.MEDIUM,
                )
                if i > 0:
                    job.dependencies = [jobs[-1].id]
                self.schedule_once(job)
                jobs.append(job)

            self.telemetry["pipelines_executed"] += 1
            logger.info("Executed pipeline with %d jobs", len(jobs))
            return jobs
        except Exception:
            logger.exception("Failed to execute pipeline")
            raise

    def get_system_health(self) -> dict:
        try:
            queue_total = self.get_length()
            queue_metrics = self.get_metrics()
            pool_workers = self.list_workers()
            available = self.get_available_count()
            scheduled = len(self._scheduled_jobs)
            checkpoints = len(self._checkpoints)

            health = {
                "status": "healthy",
                "queues": {
                    "total_pending": queue_total,
                    "processing": len(self._processing),
                },
                "worker_pool": {
                    "total": len(pool_workers),
                    "available": available,
                    "busy": sum(1 for w in pool_workers if w.status == "busy"),
                    "offline": sum(1 for w in pool_workers if w.status == "offline"),
                },
                "scheduler": {
                    "scheduled_jobs": scheduled,
                    "recurring_jobs": len(self._recurring_jobs),
                },
                "retry_queue": {
                    "pending_retries": len(self._retry_jobs),
                    "dead_letter": len(self._dead_letter),
                },
                "checkpoints": {
                    "total": checkpoints,
                },
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }

            # Degrade health if too many dead letters or offline workers
            if health["retry_queue"]["dead_letter"] > 100 or health["worker_pool"]["offline"] > 3:
                health["status"] = "degraded"

            self.telemetry["health_checks"] += 1
            return health
        except Exception:
            logger.exception("Failed to get system health")
            raise

    def get_throughput(self, window_minutes: int = 5) -> dict:
        try:
            total_enqueued = self.telemetry.get("enqueued", 0)
            total_processed = self.telemetry.get("jobs_processed", 0)
            total_completed = self.telemetry.get("acknowledged", 0)
            total_failed = self.telemetry.get("failed", 0)

            throughput = {
                "total_enqueued": total_enqueued,
                "total_processed": total_processed,
                "total_completed": total_completed,
                "total_failed": total_failed,
                "success_rate_pct": round(
                    (total_completed / total_processed * 100), 2
                ) if total_processed > 0 else 0.0,
                "failure_rate_pct": round(
                    (total_failed / total_processed * 100), 2
                ) if total_processed > 0 else 0.0,
                "window_minutes": window_minutes,
                "calculated_at": datetime.now(timezone.utc).isoformat(),
            }

            self.telemetry["throughput_checks"] += 1
            return throughput
        except Exception:
            logger.exception("Failed to get throughput")
            raise

    def get_error_rate(self) -> dict:
        try:
            total_processed = self.telemetry.get("jobs_processed", 0)
            total_failed = self.telemetry.get("failed", 0)
            total_retries = self.telemetry.get("added_to_retry", 0)

            error_rate = {
                "total_processed": total_processed,
                "total_failed": total_failed,
                "total_retried": total_retries,
                "error_rate_pct": round(
                    (total_failed / total_processed * 100), 2
                ) if total_processed > 0 else 0.0,
                "retry_rate_pct": round(
                    (total_retries / total_processed * 100), 2
                ) if total_processed > 0 else 0.0,
                "dead_letter_count": len(self._dead_letter),
                "calculated_at": datetime.now(timezone.utc).isoformat(),
            }

            self.telemetry["error_rates_checked"] += 1
            return error_rate
        except Exception:
            logger.exception("Failed to get error rate")
            raise
