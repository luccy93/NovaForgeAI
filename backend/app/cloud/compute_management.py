"""
Compute Management — CPU Scheduling, GPU Scheduling, Worker Scheduling, Resource Quotas, Organization/Workspace Limits.
"""
import logging
logger = logging.getLogger(__name__)

from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
import json, uuid, hashlib, time, os, threading
from collections import defaultdict


class ResourceType(Enum):
    CPU = "cpu"
    GPU = "gpu"
    MEMORY = "memory"
    STORAGE = "storage"
    NETWORK = "network"
    TOKENS = "tokens"
    EMBEDDINGS = "embeddings"


class AllocationStrategy(Enum):
    ROUND_ROBIN = "round_robin"
    LEAST_LOADED = "least_loaded"
    MOST_LOADED = "most_loaded"
    PRIORITY_BASED = "priority_based"
    RANDOM = "random"


class SchedulingPolicy(Enum):
    FIRST_COME_FIRST_SERVED = "fcfs"
    SHORTEST_JOB_FIRST = "sjf"
    PRIORITY = "priority"
    FAIR_SHARE = "fair_share"
    PREEMPTIVE = "preemptive"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ResourceQuota:
    id: str
    org_id: str
    workspace_id: Optional[str] = None
    resource_type: ResourceType = ResourceType.CPU
    total: float = 0.0
    used: float = 0.0
    reserved: float = 0.0
    available: float = 0.0
    limit: float = 0.0
    burst_limit: float = 0.0
    unit: str = "cores"
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["resource_type"] = self.resource_type.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "ResourceQuota":
        data = dict(data)
        data["resource_type"] = ResourceType(data["resource_type"])
        return ResourceQuota(**data)


@dataclass
class ResourceAllocation:
    id: str
    requester_id: str
    resource_type: ResourceType
    amount: float = 0.0
    unit: str = "cores"
    job_id: str = ""
    started_at: str = ""
    completed_at: Optional[str] = None
    status: str = "active"
    priority: int = 5

    def to_dict(self) -> dict:
        d = asdict(self)
        d["resource_type"] = self.resource_type.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "ResourceAllocation":
        data = dict(data)
        data["resource_type"] = ResourceType(data["resource_type"])
        return ResourceAllocation(**data)


@dataclass
class SchedulingRequest:
    id: str
    job_id: str
    resource_type: ResourceType
    required_amount: float = 0.0
    priority: int = 5
    max_wait_time_seconds: int = 300
    strategy: AllocationStrategy = AllocationStrategy.ROUND_ROBIN
    created_at: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["resource_type"] = self.resource_type.value
        d["strategy"] = self.strategy.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "SchedulingRequest":
        data = dict(data)
        data["resource_type"] = ResourceType(data["resource_type"])
        data["strategy"] = AllocationStrategy(data["strategy"])
        return SchedulingRequest(**data)


@dataclass
class WorkerAllocation:
    worker_id: str
    job_id: str
    resource_type: ResourceType
    amount: float = 0.0
    allocated_at: str = ""
    released_at: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["resource_type"] = self.resource_type.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "WorkerAllocation":
        data = dict(data)
        data["resource_type"] = ResourceType(data["resource_type"])
        return WorkerAllocation(**data)


@dataclass
class ResourceUsage:
    timestamp: str
    resource_type: ResourceType
    total: float = 0.0
    used: float = 0.0
    available: float = 0.0
    utilization_percent: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["resource_type"] = self.resource_type.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "ResourceUsage":
        data = dict(data)
        data["resource_type"] = ResourceType(data["resource_type"])
        return ResourceUsage(**data)


@dataclass
class OrganizationLimit:
    org_id: str
    max_cpu_cores: int = 64
    max_gpu_count: int = 8
    max_memory_gb: int = 256
    max_storage_gb: int = 1024
    max_workers: int = 50
    max_concurrent_jobs: int = 100
    max_tokens_per_day: int = 10000000
    max_embeddings_per_day: int = 500000

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "OrganizationLimit":
        return OrganizationLimit(**data)


@dataclass
class WorkspaceLimit:
    workspace_id: str
    org_id: str
    max_cpu_cores: int = 16
    max_gpu_count: int = 4
    max_memory_gb: int = 64
    max_storage_gb: int = 256
    max_workers: int = 10
    max_concurrent_jobs: int = 20

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "WorkspaceLimit":
        return WorkspaceLimit(**data)


# ---------------------------------------------------------------------------
# Managers
# ---------------------------------------------------------------------------

class CPUScheduler:
    """Manages CPU resource scheduling with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._allocations_file = os.path.join(storage_dir, "cpu_allocations.json")
        self._allocations: dict[str, ResourceAllocation] = {}
        self._cpu_pool_file = os.path.join(storage_dir, "cpu_pool.json")
        self._cpu_pool: dict[str, dict] = {}  # core_id -> {"total": float, "available": float}
        self._rr_index: int = 0
        self._lock = threading.Lock()
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    # -- persistence --------------------------------------------------------

    def _load(self) -> None:
        try:
            if os.path.exists(self._allocations_file):
                with open(self._allocations_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._allocations = {k: ResourceAllocation.from_dict(v) for k, v in data.items()}
                logger.info("Loaded %d CPU allocations", len(self._allocations))
        except Exception:
            logger.exception("Failed to load CPU allocations; starting fresh")
            self._allocations = {}

        try:
            if os.path.exists(self._cpu_pool_file):
                with open(self._cpu_pool_file, "r", encoding="utf-8") as fh:
                    self._cpu_pool = json.load(fh)
        except Exception:
            self._cpu_pool = {}

    def _save(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._allocations.items()}
            tmp = self._allocations_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._allocations_file)
        except Exception:
            logger.exception("Failed to save CPU allocations")

        try:
            tmp = self._cpu_pool_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._cpu_pool, fh, indent=2, default=str)
            os.replace(tmp, self._cpu_pool_file)
        except Exception:
            logger.exception("Failed to save CPU pool")

    # -- core operations ----------------------------------------------------

    def allocate_cpu(self, requester_id: str, amount: float,
                     job_id: str, priority: int = 5) -> ResourceAllocation:
        try:
            available = self.get_available_cpus()
            if available < amount:
                raise ValueError(f"Insufficient CPU cores: requested {amount}, available {available}")

            now = datetime.now(timezone.utc).isoformat()
            alloc = ResourceAllocation(
                id=str(uuid.uuid4()),
                requester_id=requester_id,
                resource_type=ResourceType.CPU,
                amount=amount,
                unit="cores",
                job_id=job_id,
                started_at=now,
                status="active",
                priority=priority,
            )
            with self._lock:
                self._allocations[alloc.id] = alloc
                self._update_cpu_pool(-amount)
            self._save()
            self.telemetry["cpu_allocated"] += 1
            logger.info("Allocated %.1f CPU cores to %s (job=%s)", amount, requester_id, job_id)
            return alloc
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to allocate CPU")
            raise

    def release_cpu(self, allocation_id: str) -> ResourceAllocation:
        try:
            with self._lock:
                alloc = self._allocations.pop(allocation_id, None)
                if alloc is None:
                    raise ValueError(f"CPU allocation not found: {allocation_id}")
                alloc.completed_at = datetime.now(timezone.utc).isoformat()
                alloc.status = "released"
                self._update_cpu_pool(alloc.amount)
            self._save()
            self.telemetry["cpu_released"] += 1
            logger.info("Released %.1f CPU cores (allocation=%s)", alloc.amount, allocation_id)
            return alloc
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to release CPU")
            raise

    def get_cpu_usage(self) -> dict:
        try:
            total_allocated = sum(a.amount for a in self._allocations.values() if a.status == "active")
            total_cores = sum(pool.get("total", 0) for pool in self._cpu_pool.values())
            available = self.get_available_cpus()
            return {
                "total_cores": total_cores,
                "allocated": total_allocated,
                "available": available,
                "utilization_pct": round((total_allocated / total_cores * 100), 2) if total_cores > 0 else 0.0,
                "active_allocations": sum(1 for a in self._allocations.values() if a.status == "active"),
            }
        except Exception:
            logger.exception("Failed to get CPU usage")
            raise

    def get_available_cpus(self) -> float:
        try:
            total = sum(pool.get("total", 0) for pool in self._cpu_pool.values())
            allocated = sum(a.amount for a in self._allocations.values() if a.status == "active")
            return max(0.0, total - allocated)
        except Exception:
            return 0.0

    def reserve_cpu(self, amount: float, job_id: str) -> ResourceAllocation:
        try:
            available = self.get_available_cpus()
            if available < amount:
                raise ValueError(f"Cannot reserve {amount} CPU cores (available: {available})")
            now = datetime.now(timezone.utc).isoformat()
            alloc = ResourceAllocation(
                id=str(uuid.uuid4()),
                requester_id="reserved",
                resource_type=ResourceType.CPU,
                amount=amount,
                unit="cores",
                job_id=job_id,
                started_at=now,
                status="reserved",
                priority=10,
            )
            with self._lock:
                self._allocations[alloc.id] = alloc
                self._update_cpu_pool(-amount)
            self._save()
            self.telemetry["cpu_reserved"] += 1
            logger.info("Reserved %.1f CPU cores for job %s", amount, job_id)
            return alloc
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to reserve CPU")
            raise

    def set_cpu_quota(self, total_cores: float) -> None:
        try:
            self._cpu_pool["default"] = {"total": total_cores, "available": total_cores}
            allocated = sum(a.amount for a in self._allocations.values() if a.status == "active")
            self._cpu_pool["default"]["available"] = max(0.0, total_cores - allocated)
            self._save()
            self.telemetry["cpu_quotas_set"] += 1
            logger.info("Set CPU quota to %.1f cores", total_cores)
        except Exception:
            logger.exception("Failed to set CPU quota")
            raise

    # -- internal helpers ---------------------------------------------------

    def _update_cpu_pool(self, delta: float) -> None:
        for pool in self._cpu_pool.values():
            pool["available"] = max(0.0, pool.get("available", 0) + delta)
            break


class GPUScheduler:
    """Manages GPU resource scheduling with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._allocations_file = os.path.join(storage_dir, "gpu_allocations.json")
        self._allocations: dict[str, ResourceAllocation] = {}
        self._gpu_pool_file = os.path.join(storage_dir, "gpu_pool.json")
        self._gpu_pool: dict[str, dict] = {}
        self._capabilities_file = os.path.join(storage_dir, "gpu_capabilities.json")
        self._capabilities: dict[str, dict] = {}
        self._lock = threading.Lock()
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    # -- persistence --------------------------------------------------------

    def _load(self) -> None:
        try:
            if os.path.exists(self._allocations_file):
                with open(self._allocations_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._allocations = {k: ResourceAllocation.from_dict(v) for k, v in data.items()}
                logger.info("Loaded %d GPU allocations", len(self._allocations))
        except Exception:
            logger.exception("Failed to load GPU allocations; starting fresh")
            self._allocations = {}

        try:
            if os.path.exists(self._gpu_pool_file):
                with open(self._gpu_pool_file, "r", encoding="utf-8") as fh:
                    self._gpu_pool = json.load(fh)
        except Exception:
            self._gpu_pool = {}

        try:
            if os.path.exists(self._capabilities_file):
                with open(self._capabilities_file, "r", encoding="utf-8") as fh:
                    self._capabilities = json.load(fh)
        except Exception:
            self._capabilities = {}

    def _save(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._allocations.items()}
            tmp = self._allocations_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._allocations_file)
        except Exception:
            logger.exception("Failed to save GPU allocations")

        try:
            tmp = self._gpu_pool_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._gpu_pool, fh, indent=2, default=str)
            os.replace(tmp, self._gpu_pool_file)
        except Exception:
            logger.exception("Failed to save GPU pool")

        try:
            tmp = self._capabilities_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._capabilities, fh, indent=2, default=str)
            os.replace(tmp, self._capabilities_file)
        except Exception:
            logger.exception("Failed to save GPU capabilities")

    # -- core operations ----------------------------------------------------

    def allocate_gpu(self, requester_id: str, amount: float,
                     job_id: str, priority: int = 5) -> ResourceAllocation:
        try:
            available = self.get_available_gpus()
            if available < amount:
                raise ValueError(f"Insufficient GPUs: requested {amount}, available {available}")

            now = datetime.now(timezone.utc).isoformat()
            alloc = ResourceAllocation(
                id=str(uuid.uuid4()),
                requester_id=requester_id,
                resource_type=ResourceType.GPU,
                amount=amount,
                unit="gpus",
                job_id=job_id,
                started_at=now,
                status="active",
                priority=priority,
            )
            with self._lock:
                self._allocations[alloc.id] = alloc
                self._update_gpu_pool(-amount)
            self._save()
            self.telemetry["gpu_allocated"] += 1
            logger.info("Allocated %.1f GPUs to %s (job=%s)", amount, requester_id, job_id)
            return alloc
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to allocate GPU")
            raise

    def release_gpu(self, allocation_id: str) -> ResourceAllocation:
        try:
            with self._lock:
                alloc = self._allocations.pop(allocation_id, None)
                if alloc is None:
                    raise ValueError(f"GPU allocation not found: {allocation_id}")
                alloc.completed_at = datetime.now(timezone.utc).isoformat()
                alloc.status = "released"
                self._update_gpu_pool(alloc.amount)
            self._save()
            self.telemetry["gpu_released"] += 1
            logger.info("Released %.1f GPUs (allocation=%s)", alloc.amount, allocation_id)
            return alloc
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to release GPU")
            raise

    def get_gpu_usage(self) -> dict:
        try:
            total_allocated = sum(a.amount for a in self._allocations.values() if a.status == "active")
            total_gpus = sum(pool.get("total", 0) for pool in self._gpu_pool.values())
            available = self.get_available_gpus()
            return {
                "total_gpus": total_gpus,
                "allocated": total_allocated,
                "available": available,
                "utilization_pct": round((total_allocated / total_gpus * 100), 2) if total_gpus > 0 else 0.0,
                "active_allocations": sum(1 for a in self._allocations.values() if a.status == "active"),
            }
        except Exception:
            logger.exception("Failed to get GPU usage")
            raise

    def get_available_gpus(self) -> float:
        try:
            total = sum(pool.get("total", 0) for pool in self._gpu_pool.values())
            allocated = sum(a.amount for a in self._allocations.values() if a.status == "active")
            return max(0.0, total - allocated)
        except Exception:
            return 0.0

    def reserve_gpu(self, amount: float, job_id: str) -> ResourceAllocation:
        try:
            available = self.get_available_gpus()
            if available < amount:
                raise ValueError(f"Cannot reserve {amount} GPUs (available: {available})")
            now = datetime.now(timezone.utc).isoformat()
            alloc = ResourceAllocation(
                id=str(uuid.uuid4()),
                requester_id="reserved",
                resource_type=ResourceType.GPU,
                amount=amount,
                unit="gpus",
                job_id=job_id,
                started_at=now,
                status="reserved",
                priority=10,
            )
            with self._lock:
                self._allocations[alloc.id] = alloc
                self._update_gpu_pool(-amount)
            self._save()
            self.telemetry["gpu_reserved"] += 1
            logger.info("Reserved %.1f GPUs for job %s", amount, job_id)
            return alloc
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to reserve GPU")
            raise

    def set_gpu_quota(self, total_gpus: float) -> None:
        try:
            self._gpu_pool["default"] = {"total": total_gpus, "available": total_gpus}
            allocated = sum(a.amount for a in self._allocations.values() if a.status == "active")
            self._gpu_pool["default"]["available"] = max(0.0, total_gpus - allocated)
            self._save()
            self.telemetry["gpu_quotas_set"] += 1
            logger.info("Set GPU quota to %.1f GPUs", total_gpus)
        except Exception:
            logger.exception("Failed to set GPU quota")
            raise

    def list_gpu_capabilities(self) -> list[dict]:
        try:
            return list(self._capabilities.values())
        except Exception:
            logger.exception("Failed to list GPU capabilities")
            raise

    # -- internal helpers ---------------------------------------------------

    def _update_gpu_pool(self, delta: float) -> None:
        for pool in self._gpu_pool.values():
            pool["available"] = max(0.0, pool.get("available", 0) + delta)
            break


class WorkerScheduler:
    """Manages worker scheduling with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._workers_file = os.path.join(storage_dir, "scheduled_workers.json")
        self._workers: dict[str, dict] = {}
        self._assignments_file = os.path.join(storage_dir, "worker_assignments.json")
        self._assignments: dict[str, WorkerAllocation] = {}
        self._lock = threading.Lock()
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    # -- persistence --------------------------------------------------------

    def _load(self) -> None:
        try:
            if os.path.exists(self._workers_file):
                with open(self._workers_file, "r", encoding="utf-8") as fh:
                    self._workers = json.load(fh)
                logger.info("Loaded %d scheduled workers", len(self._workers))
        except Exception:
            logger.exception("Failed to load scheduled workers; starting fresh")
            self._workers = {}

        try:
            if os.path.exists(self._assignments_file):
                with open(self._assignments_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._assignments = {k: WorkerAllocation.from_dict(v) for k, v in data.items()}
        except Exception:
            self._assignments = {}

    def _save(self) -> None:
        try:
            tmp = self._workers_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._workers, fh, indent=2, default=str)
            os.replace(tmp, self._workers_file)
        except Exception:
            logger.exception("Failed to save scheduled workers")

        try:
            data = {k: v.to_dict() for k, v in self._assignments.items()}
            tmp = self._assignments_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._assignments_file)
        except Exception:
            logger.exception("Failed to save worker assignments")

    # -- core operations ----------------------------------------------------

    def schedule_worker(self, worker_id: str, worker_type: str = "generic",
                        capacity: float = 1.0, region: str = "default") -> dict:
        try:
            now = datetime.now(timezone.utc).isoformat()
            worker = {
                "worker_id": worker_id,
                "worker_type": worker_type,
                "capacity": capacity,
                "region": region,
                "status": "available",
                "current_load": 0.0,
                "scheduled_at": now,
                "last_heartbeat": now,
            }
            self._workers[worker_id] = worker
            self._save()
            self.telemetry["workers_scheduled"] += 1
            logger.info("Scheduled worker %s (%s)", worker_id, worker_type)
            return worker
        except Exception:
            logger.exception("Failed to schedule worker")
            raise

    def deschedule_worker(self, worker_id: str) -> None:
        try:
            if worker_id not in self._workers:
                raise ValueError(f"Scheduled worker not found: {worker_id}")
            del self._workers[worker_id]
            self._save()
            self.telemetry["workers_descheduled"] += 1
            logger.info("Descheduled worker %s", worker_id)
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to deschedule worker")
            raise

    def get_available_workers(self, worker_type: Optional[str] = None) -> list[dict]:
        try:
            results = [w for w in self._workers.values() if w.get("status") == "available"]
            if worker_type is not None:
                results = [w for w in results if w.get("worker_type") == worker_type]
            self.telemetry["available_workers_checked"] += 1
            return results
        except Exception:
            logger.exception("Failed to get available workers")
            raise

    def assign_worker_to_job(self, worker_id: str, job_id: str,
                             resource_type: ResourceType = ResourceType.CPU,
                             amount: float = 1.0) -> WorkerAllocation:
        try:
            worker = self._workers.get(worker_id)
            if worker is None:
                raise ValueError(f"Worker not found: {worker_id}")
            if worker.get("status") != "available":
                raise ValueError(f"Worker {worker_id} is not available (status: {worker.get('status')})")

            now = datetime.now(timezone.utc).isoformat()
            assignment = WorkerAllocation(
                worker_id=worker_id,
                job_id=job_id,
                resource_type=resource_type,
                amount=amount,
                allocated_at=now,
            )
            with self._lock:
                worker["status"] = "busy"
                worker["current_load"] = worker.get("current_load", 0) + amount
                worker["last_heartbeat"] = now
                self._workers[worker_id] = worker
                self._assignments[assignment.worker_id] = assignment
            self._save()
            self.telemetry["worker_jobs_assigned"] += 1
            logger.info("Assigned worker %s to job %s", worker_id, job_id)
            return assignment
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to assign worker to job")
            raise

    def release_worker(self, worker_id: str) -> WorkerAllocation:
        try:
            with self._lock:
                assignment = self._assignments.pop(worker_id, None)
                if assignment is None:
                    raise ValueError(f"No active assignment for worker {worker_id}")
                worker = self._workers.get(worker_id)
                if worker:
                    worker["status"] = "available"
                    worker["current_load"] = max(0.0, worker.get("current_load", 0) - assignment.amount)
                    worker["last_heartbeat"] = datetime.now(timezone.utc).isoformat()
                    self._workers[worker_id] = worker
                assignment.released_at = datetime.now(timezone.utc).isoformat()
            self._save()
            self.telemetry["workers_released"] += 1
            logger.info("Released worker %s from job %s", worker_id, assignment.job_id)
            return assignment
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to release worker")
            raise

    def get_worker_utilization(self) -> dict:
        try:
            total = len(self._workers)
            available = sum(1 for w in self._workers.values() if w.get("status") == "available")
            busy = total - available
            total_capacity = sum(w.get("capacity", 1.0) for w in self._workers.values())
            total_load = sum(w.get("current_load", 0) for w in self._workers.values())
            return {
                "total_workers": total,
                "available": available,
                "busy": busy,
                "utilization_pct": round((total_load / total_capacity * 100), 2) if total_capacity > 0 else 0.0,
                "active_assignments": len(self._assignments),
            }
        except Exception:
            logger.exception("Failed to get worker utilization")
            raise

    def auto_scale_workers(self, target_count: int, worker_type: str = "generic",
                           capacity: float = 1.0, region: str = "default") -> int:
        try:
            current = len(self._workers)
            delta = target_count - current
            scaled = 0
            if delta > 0:
                for _ in range(delta):
                    wid = f"auto-{worker_type}-{uuid.uuid4().hex[:8]}"
                    self.schedule_worker(wid, worker_type, capacity, region)
                    scaled += 1
                logger.info("Auto-scaled up %d %s workers", scaled, worker_type)
            elif delta < 0:
                to_remove = abs(delta)
                available = [w for w in self._workers.values() if w.get("status") == "available"]
                for w in available[:to_remove]:
                    self.deschedule_worker(w["worker_id"])
                    scaled += 1
                logger.info("Auto-scaled down %d workers", scaled)
            self.telemetry["workers_auto_scaled"] += scaled
            return scaled
        except Exception:
            logger.exception("Failed to auto-scale workers")
            raise


class ResourceQuotaManager:
    """Manages resource quotas with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._quotas_file = os.path.join(storage_dir, "resource_quotas.json")
        self._quotas: dict[str, ResourceQuota] = {}
        self._org_limits_file = os.path.join(storage_dir, "org_limits.json")
        self._org_limits: dict[str, OrganizationLimit] = {}
        self._ws_limits_file = os.path.join(storage_dir, "workspace_limits.json")
        self._ws_limits: dict[str, WorkspaceLimit] = {}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    # -- persistence --------------------------------------------------------

    def _load(self) -> None:
        try:
            if os.path.exists(self._quotas_file):
                with open(self._quotas_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._quotas = {k: ResourceQuota.from_dict(v) for k, v in data.items()}
                logger.info("Loaded %d resource quotas", len(self._quotas))
        except Exception:
            logger.exception("Failed to load resource quotas; starting fresh")
            self._quotas = {}

        try:
            if os.path.exists(self._org_limits_file):
                with open(self._org_limits_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._org_limits = {k: OrganizationLimit.from_dict(v) for k, v in data.items()}
        except Exception:
            self._org_limits = {}

        try:
            if os.path.exists(self._ws_limits_file):
                with open(self._ws_limits_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._ws_limits = {k: WorkspaceLimit.from_dict(v) for k, v in data.items()}
        except Exception:
            self._ws_limits = {}

    def _save(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._quotas.items()}
            tmp = self._quotas_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._quotas_file)
        except Exception:
            logger.exception("Failed to save resource quotas")

        try:
            data = {k: v.to_dict() for k, v in self._org_limits.items()}
            tmp = self._org_limits_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._org_limits_file)
        except Exception:
            logger.exception("Failed to save org limits")

        try:
            data = {k: v.to_dict() for k, v in self._ws_limits.items()}
            tmp = self._ws_limits_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._ws_limits_file)
        except Exception:
            logger.exception("Failed to save workspace limits")

    # -- quota operations ---------------------------------------------------

    def set_quota(self, org_id: str, resource_type: ResourceType, total: float,
                  limit: float, burst_limit: float = 0.0, unit: str = "cores",
                  workspace_id: Optional[str] = None) -> ResourceQuota:
        try:
            qid = f"{org_id}_{workspace_id or 'org'}_{resource_type.value}"
            now = datetime.now(timezone.utc).isoformat()
            quota = ResourceQuota(
                id=qid,
                org_id=org_id,
                workspace_id=workspace_id,
                resource_type=resource_type,
                total=total,
                limit=limit,
                burst_limit=burst_limit or limit * 1.2,
                unit=unit,
                available=total,
                created_at=self._quotas[qid].created_at if qid in self._quotas else now,
                updated_at=now,
            )
            self._quotas[qid] = quota
            self._save()
            self.telemetry["quotas_set"] += 1
            logger.info("Set quota %s for org %s (total=%.1f %s)", resource_type.value, org_id, total, unit)
            return quota
        except Exception:
            logger.exception("Failed to set quota")
            raise

    def get_quota(self, org_id: str, resource_type: ResourceType,
                  workspace_id: Optional[str] = None) -> ResourceQuota:
        qid = f"{org_id}_{workspace_id or 'org'}_{resource_type.value}"
        quota = self._quotas.get(qid)
        if quota is None:
            raise ValueError(f"Quota not found: {qid}")
        self.telemetry["quotas_read"] += 1
        return quota

    def update_quota(self, org_id: str, resource_type: ResourceType,
                     used_delta: float = 0.0, workspace_id: Optional[str] = None) -> ResourceQuota:
        try:
            qid = f"{org_id}_{workspace_id or 'org'}_{resource_type.value}"
            quota = self.get_quota(org_id, resource_type, workspace_id)
            quota.used = max(0.0, quota.used + used_delta)
            quota.available = max(0.0, quota.total - quota.used - quota.reserved)
            quota.updated_at = datetime.now(timezone.utc).isoformat()
            self._quotas[qid] = quota
            self._save()
            self.telemetry["quotas_updated"] += 1
            return quota
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to update quota")
            raise

    def check_quota(self, org_id: str, resource_type: ResourceType,
                    requested: float = 0.0,
                    workspace_id: Optional[str] = None) -> dict:
        try:
            qid = f"{org_id}_{workspace_id or 'org'}_{resource_type.value}"
            quota = self._quotas.get(qid)
            if quota is None:
                return {"allowed": True, "reason": "no_quota_set"}
            exceeded = []
            if quota.limit > 0 and quota.used + requested > quota.limit:
                exceeded.append("limit")
            if quota.total > 0 and quota.used + requested > quota.total:
                exceeded.append("total")
            allowed = len(exceeded) == 0
            return {
                "allowed": allowed,
                "reason": exceeded if not allowed else "ok",
                "quota_id": qid,
                "current_used": quota.used,
                "requested": requested,
                "limit": quota.limit,
                "total": quota.total,
                "available": quota.available,
            }
        except Exception:
            logger.exception("Failed to check quota")
            raise

    def get_usage(self, org_id: str, resource_type: ResourceType,
                  workspace_id: Optional[str] = None) -> dict:
        try:
            quota = self.get_quota(org_id, resource_type, workspace_id)
            return {
                "org_id": org_id,
                "resource_type": resource_type.value,
                "used": quota.used,
                "reserved": quota.reserved,
                "available": quota.available,
                "total": quota.total,
                "utilization_pct": round((quota.used / quota.total * 100), 2) if quota.total > 0 else 0.0,
            }
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to get usage")
            raise

    def get_available(self, org_id: str, resource_type: ResourceType,
                      workspace_id: Optional[str] = None) -> float:
        try:
            quota = self.get_quota(org_id, resource_type, workspace_id)
            return quota.available
        except ValueError:
            return 0.0
        except Exception:
            return 0.0

    def get_all_quotas(self, org_id: Optional[str] = None) -> list[ResourceQuota]:
        try:
            results = list(self._quotas.values())
            if org_id is not None:
                results = [q for q in results if q.org_id == org_id]
            self.telemetry["all_quotas_listed"] += 1
            return results
        except Exception:
            logger.exception("Failed to get all quotas")
            raise

    def generate_quota_report(self, org_id: str) -> dict:
        try:
            org_quotas = [q for q in self._quotas.values() if q.org_id == org_id]
            org_limit = self._org_limits.get(org_id)
            report = {
                "org_id": org_id,
                "quotas": [q.to_dict() for q in org_quotas],
                "limits": org_limit.to_dict() if org_limit else None,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            self.telemetry["quota_reports_generated"] += 1
            return report
        except Exception:
            logger.exception("Failed to generate quota report")
            raise

    # -- limit operations ---------------------------------------------------

    def set_org_limit(self, org_id: str, max_cpu_cores: int = 64,
                      max_gpu_count: int = 8, max_memory_gb: int = 256,
                      max_storage_gb: int = 1024, max_workers: int = 50,
                      max_concurrent_jobs: int = 100,
                      max_tokens_per_day: int = 10000000,
                      max_embeddings_per_day: int = 500000) -> OrganizationLimit:
        try:
            limit = OrganizationLimit(
                org_id=org_id,
                max_cpu_cores=max_cpu_cores,
                max_gpu_count=max_gpu_count,
                max_memory_gb=max_memory_gb,
                max_storage_gb=max_storage_gb,
                max_workers=max_workers,
                max_concurrent_jobs=max_concurrent_jobs,
                max_tokens_per_day=max_tokens_per_day,
                max_embeddings_per_day=max_embeddings_per_day,
            )
            self._org_limits[org_id] = limit
            self._save()
            self.telemetry["org_limits_set"] += 1
            logger.info("Set org limits for %s", org_id)
            return limit
        except Exception:
            logger.exception("Failed to set org limit")
            raise

    def get_org_limit(self, org_id: str) -> OrganizationLimit:
        limit = self._org_limits.get(org_id)
        if limit is None:
            raise ValueError(f"Org limit not found: {org_id}")
        return limit

    def set_workspace_limit(self, workspace_id: str, org_id: str,
                            max_cpu_cores: int = 16, max_gpu_count: int = 4,
                            max_memory_gb: int = 64, max_storage_gb: int = 256,
                            max_workers: int = 10,
                            max_concurrent_jobs: int = 20) -> WorkspaceLimit:
        try:
            limit = WorkspaceLimit(
                workspace_id=workspace_id,
                org_id=org_id,
                max_cpu_cores=max_cpu_cores,
                max_gpu_count=max_gpu_count,
                max_memory_gb=max_memory_gb,
                max_storage_gb=max_storage_gb,
                max_workers=max_workers,
                max_concurrent_jobs=max_concurrent_jobs,
            )
            self._ws_limits[workspace_id] = limit
            self._save()
            self.telemetry["workspace_limits_set"] += 1
            logger.info("Set workspace limits for %s", workspace_id)
            return limit
        except Exception:
            logger.exception("Failed to set workspace limit")
            raise

    def get_workspace_limit(self, workspace_id: str) -> WorkspaceLimit:
        limit = self._ws_limits.get(workspace_id)
        if limit is None:
            raise ValueError(f"Workspace limit not found: {workspace_id}")
        return limit


class ComputeManagement(CPUScheduler, GPUScheduler, WorkerScheduler, ResourceQuotaManager):
    """Unified compute management combining CPU, GPU, worker scheduling and resource quotas."""

    def __init__(self, storage_dir: str):
        CPUScheduler.__init__(self, storage_dir)
        GPUScheduler.__init__(self, storage_dir)
        WorkerScheduler.__init__(self, storage_dir)
        ResourceQuotaManager.__init__(self, storage_dir)
        self.telemetry: dict = defaultdict(int)
        logger.info("ComputeManagement initialized at %s", storage_dir)

    def get_cluster_utilization(self) -> dict:
        try:
            cpu_usage = self.get_cpu_usage()
            gpu_usage = self.get_gpu_usage()
            worker_util = self.get_worker_utilization()
            return {
                "cpu": cpu_usage,
                "gpu": gpu_usage,
                "workers": worker_util,
                "overall_utilization_pct": round(
                    (cpu_usage.get("utilization_pct", 0) +
                     gpu_usage.get("utilization_pct", 0) +
                     worker_util.get("utilization_pct", 0)) / 3, 2
                ),
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception:
            logger.exception("Failed to get cluster utilization")
            raise

    def get_org_usage(self, org_id: str) -> dict:
        try:
            quotas = self.get_all_quotas(org_id=org_id)
            usage = {}
            for q in quotas:
                usage[q.resource_type.value] = {
                    "used": q.used,
                    "total": q.total,
                    "available": q.available,
                    "utilization_pct": round((q.used / q.total * 100), 2) if q.total > 0 else 0.0,
                }
            return {
                "org_id": org_id,
                "resources": usage,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception:
            logger.exception("Failed to get org usage for %s", org_id)
            raise

    def get_workspace_usage(self, workspace_id: str) -> dict:
        try:
            ws_quotas = [q for q in self._quotas.values() if q.workspace_id == workspace_id]
            usage = {}
            for q in ws_quotas:
                usage[q.resource_type.value] = {
                    "used": q.used,
                    "total": q.total,
                    "available": q.available,
                    "utilization_pct": round((q.used / q.total * 100), 2) if q.total > 0 else 0.0,
                }
            return {
                "workspace_id": workspace_id,
                "resources": usage,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception:
            logger.exception("Failed to get workspace usage for %s", workspace_id)
            raise

    def enforce_limits(self, org_id: str, workspace_id: Optional[str] = None) -> dict:
        try:
            org_limit = self._org_limits.get(org_id)
            ws_limit = self._ws_limits.get(workspace_id) if workspace_id else None
            violations = []
            if org_limit:
                cpu_allocated = sum(a.amount for a in self._allocations.values() if a.status == "active")
                if cpu_allocated > org_limit.max_cpu_cores:
                    violations.append(f"CPU cores ({cpu_allocated}) exceeds org limit ({org_limit.max_cpu_cores})")
                active_jobs = sum(1 for a in self._allocations.values() if a.status == "active")
                if active_jobs > org_limit.max_concurrent_jobs:
                    violations.append(f"Active jobs ({active_jobs}) exceeds org limit ({org_limit.max_concurrent_jobs})")
            return {
                "org_id": org_id,
                "workspace_id": workspace_id,
                "violations": violations,
                "enforced": len(violations) == 0,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception:
            logger.exception("Failed to enforce limits")
            raise

    def allocate_for_job(self, job_id: str, org_id: str,
                         cpu_needed: float = 1.0, gpu_needed: float = 0.0,
                         workspace_id: Optional[str] = None) -> dict:
        try:
            results = {"job_id": job_id, "allocations": [], "errors": []}
            if cpu_needed > 0:
                cpu_check = self.check_quota(org_id, ResourceType.CPU, cpu_needed, workspace_id)
                if cpu_check.get("allowed"):
                    alloc = self.allocate_cpu(f"job:{job_id}", cpu_needed, job_id)
                    self.update_quota(org_id, ResourceType.CPU, cpu_needed, workspace_id)
                    results["allocations"].append({"type": "cpu", "id": alloc.id, "amount": cpu_needed})
                else:
                    results["errors"].append(f"CPU quota exceeded: {cpu_check}")
            if gpu_needed > 0:
                gpu_check = self.check_quota(org_id, ResourceType.GPU, gpu_needed, workspace_id)
                if gpu_check.get("allowed"):
                    alloc = self.allocate_gpu(f"job:{job_id}", gpu_needed, job_id)
                    self.update_quota(org_id, ResourceType.GPU, gpu_needed, workspace_id)
                    results["allocations"].append({"type": "gpu", "id": alloc.id, "amount": gpu_needed})
                else:
                    results["errors"].append(f"GPU quota exceeded: {gpu_check}")
            self.telemetry["job_allocations"] += 1
            logger.info("Allocated resources for job %s: %s", job_id, results)
            return results
        except Exception:
            logger.exception("Failed to allocate for job %s", job_id)
            raise
