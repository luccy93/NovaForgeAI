"""
AI Compute — AI Runtime, Inference/Embedding/Search/Security/Doc/Testing/Deployment/Analytics Workers.
"""
import logging
logger = logging.getLogger(__name__)

from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
import json, uuid, hashlib, time
from collections import defaultdict
import os


class WorkerType(Enum):
    INFERENCE = "inference"
    EMBEDDING = "embedding"
    SEARCH = "search"
    SECURITY = "security"
    DOCUMENTATION = "documentation"
    TESTING = "testing"
    DEPLOYMENT = "deployment"
    ANALYTICS = "analytics"


class WorkerStatus(Enum):
    IDLE = "idle"
    BUSY = "busy"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    ERROR = "error"
    BOOTING = "booting"


class RuntimeStatus(Enum):
    CREATED = "created"
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"
    RECOVERING = "recovering"


class ComputeTier(Enum):
    CPU_ONLY = "cpu_only"
    GPU_STANDARD = "gpu_standard"
    GPU_PREMIUM = "gpu_premium"
    TPU = "tpu"
    DISTRIBUTED = "distributed"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class WorkerInstance:
    id: str
    worker_type: WorkerType
    status: WorkerStatus
    host: str
    port: int
    region: str
    version: str
    created_at: str
    last_heartbeat: str
    current_jobs: int = 0
    max_jobs: int = 10
    memory_mb: int = 4096
    cpu_cores: int = 4
    gpu_count: int = 0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["worker_type"] = self.worker_type.value
        d["status"] = self.status.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "WorkerInstance":
        data = dict(data)
        data["worker_type"] = WorkerType(data["worker_type"])
        data["status"] = WorkerStatus(data["status"])
        return WorkerInstance(**data)


@dataclass
class AICapability:
    capability_id: str
    worker_type: WorkerType
    name: str
    description: str
    version: str
    supported_models: list[str] = field(default_factory=list)
    max_concurrency: int = 1
    avg_latency_ms: float = 0.0
    pricing_per_unit: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["worker_type"] = self.worker_type.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "AICapability":
        data = dict(data)
        data["worker_type"] = WorkerType(data["worker_type"])
        return AICapability(**data)


@dataclass
class Runtime:
    id: str
    project_id: str
    name: str
    status: RuntimeStatus
    tier: ComputeTier
    created_at: str
    updated_at: str
    config: dict = field(default_factory=dict)
    workers: list[WorkerInstance] = field(default_factory=list)
    capabilities: list[AICapability] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["tier"] = self.tier.value
        d["workers"] = [w.to_dict() for w in self.workers]
        d["capabilities"] = [c.to_dict() for c in self.capabilities]
        return d

    @staticmethod
    def from_dict(data: dict) -> "Runtime":
        data = dict(data)
        data["status"] = RuntimeStatus(data["status"])
        data["tier"] = ComputeTier(data["tier"])
        data["workers"] = [WorkerInstance.from_dict(w) for w in data.get("workers", [])]
        data["capabilities"] = [AICapability.from_dict(c) for c in data.get("capabilities", [])]
        return Runtime(**data)


@dataclass
class InferenceRequest:
    id: str
    runtime_id: str
    model: str
    input_tokens: int
    output_tokens: int
    max_tokens: int
    temperature: float
    priority: int
    created_at: str
    status: str = "pending"

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "InferenceRequest":
        return InferenceRequest(**data)


@dataclass
class WorkerMetrics:
    worker_id: str
    cpu_usage: float
    memory_usage: float
    gpu_usage: float
    requests_processed: int
    avg_latency_ms: float
    error_rate: float
    timestamp: str

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "WorkerMetrics":
        return WorkerMetrics(**data)


# ---------------------------------------------------------------------------
# Managers
# ---------------------------------------------------------------------------

class WorkerManager:
    """Manages AI worker instances with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._workers_file = os.path.join(storage_dir, "workers.json")
        self._workers: dict[str, WorkerInstance] = {}
        self._metrics_file = os.path.join(storage_dir, "worker_metrics.json")
        self._metrics_store: dict[str, list[WorkerMetrics]] = defaultdict(list)
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    # -- persistence --------------------------------------------------------

    def _load(self) -> None:
        try:
            if os.path.exists(self._workers_file):
                with open(self._workers_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._workers = {k: WorkerInstance.from_dict(v) for k, v in data.items()}
                logger.info("Loaded %d workers", len(self._workers))
        except Exception:
            logger.exception("Failed to load workers; starting fresh")
            self._workers = {}

        try:
            if os.path.exists(self._metrics_file):
                with open(self._metrics_file, "r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                self._metrics_store = defaultdict(
                    list,
                    {k: [WorkerMetrics.from_dict(m) for m in v] for k, v in raw.items()},
                )
        except Exception:
            self._metrics_store = defaultdict(list)

    def _save(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._workers.items()}
            tmp = self._workers_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._workers_file)
        except Exception:
            logger.exception("Failed to save workers")

        try:
            data = {k: [m.to_dict() for m in v] for k, v in self._metrics_store.items()}
            tmp = self._metrics_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._metrics_file)
        except Exception:
            logger.exception("Failed to save worker metrics")

    # -- CRUD ---------------------------------------------------------------

    def register_worker(self, worker_type: WorkerType, host: str, port: int,
                        region: str, version: str, max_jobs: int = 10,
                        memory_mb: int = 4096, cpu_cores: int = 4,
                        gpu_count: int = 0,
                        metadata: Optional[dict] = None) -> WorkerInstance:
        try:
            now = datetime.now(timezone.utc).isoformat()
            worker = WorkerInstance(
                id=str(uuid.uuid4()),
                worker_type=worker_type,
                status=WorkerStatus.BOOTING,
                host=host,
                port=port,
                region=region,
                version=version,
                created_at=now,
                last_heartbeat=now,
                max_jobs=max_jobs,
                memory_mb=memory_mb,
                cpu_cores=cpu_cores,
                gpu_count=gpu_count,
                metadata=metadata or {},
            )
            self._workers[worker.id] = worker
            self._save()
            self.telemetry["workers_registered"] += 1
            logger.info("Registered worker %s (%s) at %s:%d", worker.id, worker_type.value, host, port)
            return worker
        except Exception:
            logger.exception("Failed to register worker")
            raise

    def unregister_worker(self, worker_id: str) -> None:
        try:
            if worker_id not in self._workers:
                raise ValueError(f"Worker not found: {worker_id}")
            del self._workers[worker_id]
            self._save()
            self.telemetry["workers_unregistered"] += 1
            logger.info("Unregistered worker %s", worker_id)
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to unregister worker %s", worker_id)
            raise

    def get_worker(self, worker_id: str) -> WorkerInstance:
        w = self._workers.get(worker_id)
        if w is None:
            raise ValueError(f"Worker not found: {worker_id}")
        self.telemetry["workers_read"] += 1
        return w

    def list_workers(self, worker_type: Optional[WorkerType] = None,
                     status: Optional[WorkerStatus] = None,
                     region: Optional[str] = None) -> list[WorkerInstance]:
        try:
            results = list(self._workers.values())
            if worker_type is not None:
                results = [w for w in results if w.worker_type == worker_type]
            if status is not None:
                results = [w for w in results if w.status == status]
            if region is not None:
                results = [w for w in results if w.region == region]
            self.telemetry["workers_listed"] += 1
            return results
        except Exception:
            logger.exception("Failed to list workers")
            raise

    def update_heartbeat(self, worker_id: str) -> WorkerInstance:
        try:
            w = self.get_worker(worker_id)
            w.last_heartbeat = datetime.now(timezone.utc).isoformat()
            if w.status == WorkerStatus.BOOTING:
                w.status = WorkerStatus.IDLE
            self._workers[worker_id] = w
            self._save()
            self.telemetry["heartbeats_updated"] += 1
            return w
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to update heartbeat for %s", worker_id)
            raise

    def assign_job(self, worker_id: str) -> WorkerInstance:
        try:
            w = self.get_worker(worker_id)
            if w.current_jobs >= w.max_jobs:
                raise ValueError(f"Worker {worker_id} at max capacity ({w.max_jobs})")
            if w.status not in (WorkerStatus.IDLE, WorkerStatus.BUSY):
                raise ValueError(f"Worker {worker_id} cannot accept jobs (status: {w.status.value})")
            w.current_jobs += 1
            w.status = WorkerStatus.BUSY
            self._workers[worker_id] = w
            self._save()
            self.telemetry["jobs_assigned"] += 1
            return w
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to assign job to %s", worker_id)
            raise

    def complete_job(self, worker_id: str) -> WorkerInstance:
        try:
            w = self.get_worker(worker_id)
            w.current_jobs = max(0, w.current_jobs - 1)
            w.status = WorkerStatus.IDLE if w.current_jobs == 0 else WorkerStatus.BUSY
            self._workers[worker_id] = w
            self._save()
            self.telemetry["jobs_completed"] += 1
            return w
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to complete job on %s", worker_id)
            raise

    def fail_job(self, worker_id: str) -> WorkerInstance:
        try:
            w = self.get_worker(worker_id)
            w.current_jobs = max(0, w.current_jobs - 1)
            w.status = WorkerStatus.ERROR
            self._workers[worker_id] = w
            self._save()
            self.telemetry["jobs_failed"] += 1
            return w
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to mark job failed on %s", worker_id)
            raise

    def get_worker_metrics(self, worker_id: str) -> list[WorkerMetrics]:
        if worker_id not in self._workers and worker_id not in self._metrics_store:
            raise ValueError(f"No metrics found for worker: {worker_id}")
        return list(self._metrics_store.get(worker_id, []))

    def get_available_workers(self, worker_type: Optional[WorkerType] = None) -> list[WorkerInstance]:
        try:
            results = [
                w for w in self._workers.values()
                if w.status in (WorkerStatus.IDLE, WorkerStatus.BUSY)
                and w.current_jobs < w.max_jobs
            ]
            if worker_type is not None:
                results = [w for w in results if w.worker_type == worker_type]
            self.telemetry["available_workers_checked"] += 1
            return results
        except Exception:
            logger.exception("Failed to get available workers")
            raise

    def record_metrics(self, metrics: WorkerMetrics) -> None:
        try:
            self._metrics_store[metrics.worker_id].append(metrics)
            # keep last 1000 entries per worker
            if len(self._metrics_store[metrics.worker_id]) > 1000:
                self._metrics_store[metrics.worker_id] = self._metrics_store[metrics.worker_id][-1000:]
            self._save()
            self.telemetry["metrics_recorded"] += 1
        except Exception:
            logger.exception("Failed to record metrics")


class ComputeManager:
    """Manages AI runtimes with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._runtimes_file = os.path.join(storage_dir, "runtimes.json")
        self._runtimes: dict[str, Runtime] = {}
        self._requests_file = os.path.join(storage_dir, "inference_requests.json")
        self._inference_requests: dict[str, InferenceRequest] = {}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    # -- persistence --------------------------------------------------------

    def _load(self) -> None:
        try:
            if os.path.exists(self._runtimes_file):
                with open(self._runtimes_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._runtimes = {k: Runtime.from_dict(v) for k, v in data.items()}
                logger.info("Loaded %d runtimes", len(self._runtimes))
        except Exception:
            logger.exception("Failed to load runtimes; starting fresh")
            self._runtimes = {}

        try:
            if os.path.exists(self._requests_file):
                with open(self._requests_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._inference_requests = {k: InferenceRequest.from_dict(v) for k, v in data.items()}
        except Exception:
            self._inference_requests = {}

    def _save(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._runtimes.items()}
            tmp = self._runtimes_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._runtimes_file)
        except Exception:
            logger.exception("Failed to save runtimes")

        try:
            data = {k: v.to_dict() for k, v in self._inference_requests.items()}
            tmp = self._requests_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._requests_file)
        except Exception:
            logger.exception("Failed to save inference requests")

    # -- Runtime CRUD -------------------------------------------------------

    def create_runtime(self, project_id: str, name: str, tier: ComputeTier,
                       config: Optional[dict] = None) -> Runtime:
        try:
            now = datetime.now(timezone.utc).isoformat()
            runtime = Runtime(
                id=str(uuid.uuid4()),
                project_id=project_id,
                name=name,
                status=RuntimeStatus.CREATED,
                tier=tier,
                created_at=now,
                updated_at=now,
                config=config or {},
            )
            self._runtimes[runtime.id] = runtime
            self._save()
            self.telemetry["runtimes_created"] += 1
            logger.info("Created runtime %s (%s) for project %s", runtime.id, name, project_id)
            return runtime
        except Exception:
            logger.exception("Failed to create runtime")
            raise

    def get_runtime(self, runtime_id: str) -> Runtime:
        rt = self._runtimes.get(runtime_id)
        if rt is None:
            raise ValueError(f"Runtime not found: {runtime_id}")
        self.telemetry["runtimes_read"] += 1
        return rt

    def update_runtime(self, runtime_id: str, **kwargs) -> Runtime:
        try:
            rt = self.get_runtime(runtime_id)
            for key, val in kwargs.items():
                if hasattr(rt, key) and key not in ("id", "project_id", "created_at"):
                    setattr(rt, key, val)
            rt.updated_at = datetime.now(timezone.utc).isoformat()
            self._runtimes[runtime_id] = rt
            self._save()
            self.telemetry["runtimes_updated"] += 1
            return rt
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to update runtime %s", runtime_id)
            raise

    def delete_runtime(self, runtime_id: str) -> None:
        try:
            if runtime_id not in self._runtimes:
                raise ValueError(f"Runtime not found: {runtime_id}")
            del self._runtimes[runtime_id]
            self._save()
            self.telemetry["runtimes_deleted"] += 1
            logger.info("Deleted runtime %s", runtime_id)
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to delete runtime %s", runtime_id)
            raise

    def list_runtimes(self, project_id: Optional[str] = None,
                      status: Optional[RuntimeStatus] = None) -> list[Runtime]:
        try:
            results = list(self._runtimes.values())
            if project_id is not None:
                results = [r for r in results if r.project_id == project_id]
            if status is not None:
                results = [r for r in results if r.status == status]
            self.telemetry["runtimes_listed"] += 1
            return results
        except Exception:
            logger.exception("Failed to list runtimes")
            raise

    def start_runtime(self, runtime_id: str) -> Runtime:
        return self.update_runtime(runtime_id, status=RuntimeStatus.RUNNING)

    def stop_runtime(self, runtime_id: str) -> Runtime:
        return self.update_runtime(runtime_id, status=RuntimeStatus.STOPPED)

    def pause_runtime(self, runtime_id: str) -> Runtime:
        return self.update_runtime(runtime_id, status=RuntimeStatus.PAUSED)

    def resume_runtime(self, runtime_id: str) -> Runtime:
        return self.update_runtime(runtime_id, status=RuntimeStatus.RUNNING)

    def get_runtime_status(self, runtime_id: str) -> dict:
        try:
            rt = self.get_runtime(runtime_id)
            return {
                "runtime_id": rt.id,
                "name": rt.name,
                "status": rt.status.value,
                "tier": rt.tier.value,
                "worker_count": len(rt.workers),
                "capability_count": len(rt.capabilities),
                "uptime": (datetime.now(timezone.utc) - datetime.fromisoformat(rt.created_at)).total_seconds(),
            }
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to get runtime status")
            raise

    def allocate_worker(self, runtime_id: str, worker: WorkerInstance) -> Runtime:
        try:
            rt = self.get_runtime(runtime_id)
            for existing in rt.workers:
                if existing.id == worker.id:
                    raise ValueError(f"Worker {worker.id} already allocated to runtime {runtime_id}")
            rt.workers.append(worker)
            rt.updated_at = datetime.now(timezone.utc).isoformat()
            self._runtimes[runtime_id] = rt
            self._save()
            self.telemetry["workers_allocated"] += 1
            return rt
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to allocate worker to runtime %s", runtime_id)
            raise

    def release_worker(self, runtime_id: str, worker_id: str) -> Runtime:
        try:
            rt = self.get_runtime(runtime_id)
            before = len(rt.workers)
            rt.workers = [w for w in rt.workers if w.id != worker_id]
            if len(rt.workers) == before:
                raise ValueError(f"Worker {worker_id} not found in runtime {runtime_id}")
            rt.updated_at = datetime.now(timezone.utc).isoformat()
            self._runtimes[runtime_id] = rt
            self._save()
            self.telemetry["workers_released"] += 1
            return rt
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to release worker from runtime %s", runtime_id)
            raise

    def get_compute_metrics(self, runtime_id: str) -> dict:
        try:
            rt = self.get_runtime(runtime_id)
            total_workers = len(rt.workers)
            busy = sum(1 for w in rt.workers if w.status == WorkerStatus.BUSY)
            idle = sum(1 for w in rt.workers if w.status == WorkerStatus.IDLE)
            total_jobs = sum(w.current_jobs for w in rt.workers)
            max_jobs = sum(w.max_jobs for w in rt.workers)

            return {
                "runtime_id": rt.id,
                "runtime_name": rt.name,
                "status": rt.status.value,
                "total_workers": total_workers,
                "busy_workers": busy,
                "idle_workers": idle,
                "current_jobs": total_jobs,
                "max_jobs_capacity": max_jobs,
                "utilization_pct": round((total_jobs / max_jobs * 100), 2) if max_jobs > 0 else 0.0,
                "tier": rt.tier.value,
            }
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to get compute metrics for %s", runtime_id)
            raise


class AIComputeManager(ComputeManager, WorkerManager):
    """Unified AI compute manager combining runtime and worker management."""

    def __init__(self, storage_dir: str):
        ComputeManager.__init__(self, storage_dir)
        WorkerManager.__init__(self, storage_dir)
        self.telemetry: dict = defaultdict(int)
        logger.info("AIComputeManager initialized at %s", storage_dir)

    def schedule_inference(self, runtime_id: str, model: str,
                           input_tokens: int = 0, output_tokens: int = 0,
                           max_tokens: int = 2048, temperature: float = 0.7,
                           priority: int = 5) -> InferenceRequest:
        try:
            rt = self.get_runtime(runtime_id)
            if rt.status != RuntimeStatus.RUNNING:
                raise ValueError(f"Runtime {runtime_id} is not running (status: {rt.status.value})")

            available = self.get_available_workers(WorkerType.INFERENCE)
            if not available:
                raise ValueError(f"No available inference workers for runtime {runtime_id}")

            now = datetime.now(timezone.utc).isoformat()
            req = InferenceRequest(
                id=str(uuid.uuid4()),
                runtime_id=runtime_id,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                max_tokens=max_tokens,
                temperature=temperature,
                priority=priority,
                created_at=now,
                status="scheduled",
            )
            self._inference_requests[req.id] = req
            self._save()
            self.telemetry["inferences_scheduled"] += 1
            logger.info("Scheduled inference %s on runtime %s (model=%s)", req.id, runtime_id, model)
            return req
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to schedule inference")
            raise

    def create_embedding_workers(self, runtime_id: str, count: int = 1,
                                 region: str = "us-east-1") -> list[WorkerInstance]:
        try:
            rt = self.get_runtime(runtime_id)
            workers = []
            for _ in range(count):
                w = self.register_worker(
                    worker_type=WorkerType.EMBEDDING,
                    host=f"embed-{rt.name}-{uuid.uuid4().hex[:8]}",
                    port=8001,
                    region=region,
                    version="1.0.0",
                    max_jobs=20,
                )
                w.status = WorkerStatus.IDLE
                self._workers[w.id] = w
                rt.workers.append(w)
                workers.append(w)
            rt.updated_at = datetime.now(timezone.utc).isoformat()
            self._runtimes[runtime_id] = rt
            self._save()
            self.telemetry["embedding_workers_created"] += count
            return workers
        except Exception:
            logger.exception("Failed to create embedding workers")
            raise

    def create_search_workers(self, runtime_id: str, count: int = 1,
                              region: str = "us-east-1") -> list[WorkerInstance]:
        try:
            rt = self.get_runtime(runtime_id)
            workers = []
            for _ in range(count):
                w = self.register_worker(
                    worker_type=WorkerType.SEARCH,
                    host=f"search-{rt.name}-{uuid.uuid4().hex[:8]}",
                    port=8002,
                    region=region,
                    version="1.0.0",
                    max_jobs=15,
                )
                w.status = WorkerStatus.IDLE
                self._workers[w.id] = w
                rt.workers.append(w)
                workers.append(w)
            rt.updated_at = datetime.now(timezone.utc).isoformat()
            self._runtimes[runtime_id] = rt
            self._save()
            self.telemetry["search_workers_created"] += count
            return workers
        except Exception:
            logger.exception("Failed to create search workers")
            raise

    def get_cluster_health(self) -> dict:
        try:
            all_workers = self.list_workers()
            total = len(all_workers)
            idle = sum(1 for w in all_workers if w.status == WorkerStatus.IDLE)
            busy = sum(1 for w in all_workers if w.status == WorkerStatus.BUSY)
            offline = sum(1 for w in all_workers if w.status == WorkerStatus.OFFLINE)
            error = sum(1 for w in all_workers if w.status == WorkerStatus.ERROR)
            booting = sum(1 for w in all_workers if w.status == WorkerStatus.BOOTING)
            degraded = sum(1 for w in all_workers if w.status == WorkerStatus.DEGRADED)

            total_capacity = sum(w.max_jobs for w in all_workers)
            total_current = sum(w.current_jobs for w in all_workers)

            runtimes = self.list_runtimes()
            running_runtimes = sum(1 for r in runtimes if r.status == RuntimeStatus.RUNNING)
            errored_runtimes = sum(1 for r in runtimes if r.status == RuntimeStatus.ERROR)

            health = {
                "status": "healthy" if error == 0 and errored_runtimes == 0 else "degraded",
                "total_workers": total,
                "idle_workers": idle,
                "busy_workers": busy,
                "offline_workers": offline,
                "error_workers": error,
                "booting_workers": booting,
                "degraded_workers": degraded,
                "total_runtimes": len(runtimes),
                "running_runtimes": running_runtimes,
                "errored_runtimes": errored_runtimes,
                "cluster_capacity": total_capacity,
                "cluster_load": total_current,
                "utilization_pct": round((total_current / total_capacity * 100), 2) if total_capacity > 0 else 0.0,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
            self.telemetry["health_checks"] += 1
            return health
        except Exception:
            logger.exception("Failed to get cluster health")
            raise

    def scale_workers(self, runtime_id: str, worker_type: WorkerType,
                      target_count: int) -> list[WorkerInstance]:
        try:
            rt = self.get_runtime(runtime_id)
            current = [w for w in rt.workers if w.worker_type == worker_type]
            delta = target_count - len(current)

            if delta > 0:
                new_workers = []
                for _ in range(delta):
                    w = self.register_worker(
                        worker_type=worker_type,
                        host=f"scale-{worker_type.value}-{uuid.uuid4().hex[:8]}",
                        port=8000,
                        region="auto",
                        version="1.0.0",
                    )
                    w.status = WorkerStatus.IDLE
                    self._workers[w.id] = w
                    rt.workers.append(w)
                    new_workers.append(w)
                self.telemetry["workers_scaled_up"] += delta
                logger.info("Scaled up %d %s workers for runtime %s", delta, worker_type.value, runtime_id)
                self._runtimes[runtime_id] = rt
                self._save()
                return new_workers
            elif delta < 0:
                remove_count = abs(delta)
                to_remove = [w for w in current if w.status == WorkerStatus.IDLE][:remove_count]
                for w in to_remove:
                    rt.workers = [x for x in rt.workers if x.id != w.id]
                    self.unregister_worker(w.id)
                self.telemetry["workers_scaled_down"] += len(to_remove)
                logger.info("Scaled down %d %s workers for runtime %s", len(to_remove), worker_type.value, runtime_id)
                self._runtimes[runtime_id] = rt
                self._save()
                return []
            return []
        except Exception:
            logger.exception("Failed to scale workers for runtime %s", runtime_id)
            raise
