"""
Service Discovery — Automatic Discovery, Health Monitoring, Dynamic Registration, Version Awareness, Service Dependencies.
"""
import logging
logger = logging.getLogger(__name__)

from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
import json, uuid, hashlib, time, os, threading
from collections import defaultdict


class ServiceStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"
    UNKNOWN = "unknown"


class ServiceProtocol(Enum):
    HTTP = "http"
    GRPC = "grpc"
    WS = "ws"
    TCP = "tcp"
    UDP = "udp"


class HealthCheckType(Enum):
    HTTP_GET = "http_get"
    TCP_CONNECT = "tcp_connect"
    GRPC_HEALTH = "grpc_health"
    COMMAND = "command"
    CUSTOM = "custom"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ServiceInstance:
    id: str
    service_name: str
    service_type: str
    version: str
    host: str
    port: int
    protocol: ServiceProtocol
    status: ServiceStatus
    region: str
    metadata: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    health_endpoint: str = ""
    registered_at: str = ""
    last_heartbeat: str = ""
    uptime_seconds: float = 0.0
    capacity: int = 100
    current_load: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["protocol"] = self.protocol.value
        d["status"] = self.status.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "ServiceInstance":
        data = dict(data)
        data["protocol"] = ServiceProtocol(data["protocol"])
        data["status"] = ServiceStatus(data["status"])
        return ServiceInstance(**data)


@dataclass
class ServiceDependency:
    source_service: str
    target_service: str
    dependency_type: str = "hard"
    required: bool = True
    version_constraint: str = ""
    timeout_ms: int = 5000
    retry_count: int = 3

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "ServiceDependency":
        return ServiceDependency(**data)


@dataclass
class HealthCheckResult:
    service_id: str
    check_type: HealthCheckType
    status: ServiceStatus
    latency_ms: float
    checked_at: str
    message: str = ""
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["check_type"] = self.check_type.value
        d["status"] = self.status.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "HealthCheckResult":
        data = dict(data)
        data["check_type"] = HealthCheckType(data["check_type"])
        data["status"] = ServiceStatus(data["status"])
        return HealthCheckResult(**data)


@dataclass
class ServiceRegistryEntry:
    instance: ServiceInstance
    last_updated: str = ""
    ttl_seconds: int = 60
    checks: list[HealthCheckResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["instance"] = self.instance.to_dict()
        d["checks"] = [c.to_dict() for c in self.checks]
        return d

    @staticmethod
    def from_dict(data: dict) -> "ServiceRegistryEntry":
        data = dict(data)
        data["instance"] = ServiceInstance.from_dict(data["instance"])
        data["checks"] = [HealthCheckResult.from_dict(c) for c in data.get("checks", [])]
        return ServiceRegistryEntry(**data)


@dataclass
class ServiceTopology:
    name: str
    instances: list[ServiceInstance] = field(default_factory=list)
    dependencies: list[ServiceDependency] = field(default_factory=list)
    health_score: float = 1.0
    instance_count: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["instances"] = [i.to_dict() for i in self.instances]
        d["dependencies"] = [dep.to_dict() for dep in self.dependencies]
        return d

    @staticmethod
    def from_dict(data: dict) -> "ServiceTopology":
        data = dict(data)
        data["instances"] = [ServiceInstance.from_dict(i) for i in data.get("instances", [])]
        data["dependencies"] = [ServiceDependency.from_dict(d) for d in data.get("dependencies", [])]
        return ServiceTopology(**data)


# ---------------------------------------------------------------------------
# Managers
# ---------------------------------------------------------------------------

class ServiceRegistry:
    """Manages service registration with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._registry_file = os.path.join(storage_dir, "service_registry.json")
        self._registry: dict[str, ServiceRegistryEntry] = {}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._registry_file):
                with open(self._registry_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._registry = {k: ServiceRegistryEntry.from_dict(v) for k, v in data.items()}
                logger.info("Loaded %d service registry entries", len(self._registry))
        except Exception:
            logger.exception("Failed to load service registry; starting fresh")
            self._registry = {}

    def _save(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._registry.items()}
            tmp = self._registry_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._registry_file)
        except Exception:
            logger.exception("Failed to save service registry")

    def register(self, service_name: str, service_type: str, version: str,
                  host: str, port: int, protocol: ServiceProtocol = ServiceProtocol.HTTP,
                  region: str = "us-east-1", metadata: Optional[dict] = None,
                  tags: Optional[list[str]] = None,
                  health_endpoint: str = "", capacity: int = 100,
                  ttl_seconds: int = 60) -> ServiceInstance:
        try:
            now = datetime.now(timezone.utc).isoformat()
            inst = ServiceInstance(
                id=str(uuid.uuid4()), service_name=service_name, service_type=service_type,
                version=version, host=host, port=port, protocol=protocol,
                status=ServiceStatus.UNKNOWN, region=region,
                metadata=metadata or {}, tags=tags or [],
                health_endpoint=health_endpoint or f"{protocol.value}://{host}:{port}/health",
                registered_at=now, last_heartbeat=now, uptime_seconds=0.0,
                capacity=capacity, current_load=0,
            )
            entry = ServiceRegistryEntry(instance=inst, last_updated=now, ttl_seconds=ttl_seconds)
            self._registry[inst.id] = entry
            self._save()
            self.telemetry["services_registered"] += 1
            logger.info("Registered service %s (%s v%s) at %s:%d", inst.id, service_name, version, host, port)
            return inst
        except Exception:
            logger.exception("Failed to register service")
            raise

    def unregister(self, service_id: str) -> None:
        try:
            if service_id not in self._registry:
                raise ValueError(f"Service not found: {service_id}")
            del self._registry[service_id]
            self._save()
            self.telemetry["services_unregistered"] += 1
            logger.info("Unregistered service %s", service_id)
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to unregister service %s", service_id)
            raise

    def get_service(self, service_id: str) -> ServiceInstance:
        entry = self._registry.get(service_id)
        if entry is None:
            raise ValueError(f"Service not found: {service_id}")
        self.telemetry["services_read"] += 1
        return entry.instance

    def list_services(self) -> list[ServiceInstance]:
        try:
            instances = [e.instance for e in self._registry.values()]
            self.telemetry["services_listed"] += 1
            return instances
        except Exception:
            logger.exception("Failed to list services")
            raise

    def list_by_type(self, service_type: str) -> list[ServiceInstance]:
        try:
            return [e.instance for e in self._registry.values() if e.instance.service_type == service_type]
        except Exception:
            logger.exception("Failed to list services by type")
            raise

    def list_by_region(self, region: str) -> list[ServiceInstance]:
        try:
            return [e.instance for e in self._registry.values() if e.instance.region == region]
        except Exception:
            logger.exception("Failed to list services by region")
            raise

    def list_by_status(self, status: ServiceStatus) -> list[ServiceInstance]:
        try:
            return [e.instance for e in self._registry.values() if e.instance.status == status]
        except Exception:
            logger.exception("Failed to list services by status")
            raise

    def find_healthy(self) -> list[ServiceInstance]:
        try:
            return [e.instance for e in self._registry.values() if e.instance.status == ServiceStatus.HEALTHY]
        except Exception:
            logger.exception("Failed to find healthy services")
            raise

    def find_healthy_in_region(self, region: str) -> list[ServiceInstance]:
        try:
            return [e.instance for e in self._registry.values()
                    if e.instance.status == ServiceStatus.HEALTHY and e.instance.region == region]
        except Exception:
            logger.exception("Failed to find healthy services in region %s", region)
            raise

    def search_services(self, query: str) -> list[ServiceInstance]:
        try:
            q = query.lower()
            results = []
            for e in self._registry.values():
                inst = e.instance
                if (q in inst.service_name.lower() or q in inst.service_type.lower()
                        or q in inst.host.lower() or q in inst.version.lower()
                        or q in str(inst.tags).lower() or q in inst.region.lower()):
                    results.append(inst)
            self.telemetry["services_searched"] += 1
            return results
        except Exception:
            logger.exception("Failed to search services")
            raise

    def update_metadata(self, service_id: str, metadata: dict) -> ServiceInstance:
        try:
            entry = self._registry.get(service_id)
            if entry is None:
                raise ValueError(f"Service not found: {service_id}")
            entry.instance.metadata.update(metadata)
            entry.last_updated = datetime.now(timezone.utc).isoformat()
            self._registry[service_id] = entry
            self._save()
            self.telemetry["services_metadata_updated"] += 1
            return entry.instance
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to update metadata for service %s", service_id)
            raise

    def update_status(self, service_id: str, status: ServiceStatus) -> ServiceInstance:
        try:
            entry = self._registry.get(service_id)
            if entry is None:
                raise ValueError(f"Service not found: {service_id}")
            entry.instance.status = status
            entry.last_updated = datetime.now(timezone.utc).isoformat()
            self._registry[service_id] = entry
            self._save()
            self.telemetry["services_status_updated"] += 1
            logger.info("Updated service %s status to %s", service_id, status.value)
            return entry.instance
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to update status for service %s", service_id)
            raise


class HealthMonitor:
    """Monitors service health with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._history_file = os.path.join(storage_dir, "health_history.json")
        self._history: dict[str, list[HealthCheckResult]] = defaultdict(list)
        self._thresholds_file = os.path.join(storage_dir, "health_thresholds.json")
        self._thresholds: dict[str, dict] = {}
        self._monitoring: dict[str, bool] = {}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._history_file):
                with open(self._history_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._history = defaultdict(list, {k: [HealthCheckResult.from_dict(c) for c in v]
                                                     for k, v in data.items()})
                logger.info("Loaded health history for %d services", len(self._history))
        except Exception:
            logger.exception("Failed to load health history; starting fresh")
            self._history = defaultdict(list)
        try:
            if os.path.exists(self._thresholds_file):
                with open(self._thresholds_file, "r", encoding="utf-8") as fh:
                    self._thresholds = json.load(fh)
        except Exception:
            self._thresholds = {}

    def _save(self) -> None:
        try:
            data = {k: [c.to_dict() for c in v] for k, v in self._history.items()}
            tmp = self._history_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._history_file)
        except Exception:
            logger.exception("Failed to save health history")
        try:
            tmp = self._thresholds_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._thresholds, fh, indent=2, default=str)
            os.replace(tmp, self._thresholds_file)
        except Exception:
            logger.exception("Failed to save health thresholds")

    def check_health(self, service_id: str, host: str, port: int,
                      check_type: HealthCheckType = HealthCheckType.HTTP_GET,
                      endpoint: str = "") -> HealthCheckResult:
        try:
            start = time.time()
            simulated_latency = int(hashlib.sha256(f"{service_id}:{time.time()}".encode()).hexdigest()[:4], 16) % 200
            latency = float(int(simulated_latency[0], 16) % 200) if isinstance(simulated_latency, tuple) else float(abs(hash(simulated_latency)) % 200)
            elapsed = max(1, latency)
            healthy = elapsed < 100
            status = ServiceStatus.HEALTHY if healthy else ServiceStatus.DEGRADED
            now = datetime.now(timezone.utc).isoformat()
            result = HealthCheckResult(
                service_id=service_id, check_type=check_type, status=status,
                latency_ms=elapsed, checked_at=now,
                message="Health check passed" if healthy else "Health check degraded",
                details={"host": host, "port": port, "endpoint": endpoint},
            )
            self._history[service_id].append(result)
            if len(self._history[service_id]) > 1000:
                self._history[service_id] = self._history[service_id][-1000:]
            self._save()
            self.telemetry["health_checks_performed"] += 1
            return result
        except Exception:
            logger.exception("Failed to check health for service %s", service_id)
            raise

    def start_monitoring(self, service_id: str) -> None:
        self._monitoring[service_id] = True
        self.telemetry["monitoring_started"] += 1
        logger.info("Started monitoring service %s", service_id)

    def stop_monitoring(self, service_id: str) -> None:
        self._monitoring[service_id] = False
        self.telemetry["monitoring_stopped"] += 1
        logger.info("Stopped monitoring service %s", service_id)

    def get_health_status(self, service_id: str) -> Optional[HealthCheckResult]:
        checks = self._history.get(service_id, [])
        if not checks:
            return None
        self.telemetry["health_status_read"] += 1
        return checks[-1]

    def get_health_history(self, service_id: str, limit: int = 50) -> list[HealthCheckResult]:
        checks = self._history.get(service_id, [])
        self.telemetry["health_history_read"] += 1
        return checks[-limit:]

    def get_uptime(self, service_id: str) -> dict:
        try:
            checks = self._history.get(service_id, [])
            if not checks:
                return {"service_id": service_id, "uptime_percent": 0, "total_checks": 0}
            healthy = sum(1 for c in checks if c.status == ServiceStatus.HEALTHY)
            total = len(checks)
            uptime_pct = round((healthy / total * 100), 2) if total > 0 else 0
            self.telemetry["uptime_read"] += 1
            return {"service_id": service_id, "uptime_percent": uptime_pct,
                    "healthy_checks": healthy, "total_checks": total}
        except Exception:
            logger.exception("Failed to get uptime for service %s", service_id)
            raise

    def get_health_score(self, service_id: str) -> float:
        try:
            uptime = self.get_uptime(service_id)
            score = uptime["uptime_percent"] / 100.0
            self.telemetry["health_scores_read"] += 1
            return score
        except Exception:
            logger.exception("Failed to get health score for service %s", service_id)
            return 0.0

    def check_dependency_health(self, dependencies: list[ServiceDependency],
                                 registry: ServiceRegistry) -> dict:
        try:
            results = {}
            for dep in dependencies:
                services = registry.search_services(dep.target_service)
                dep_healthy = any(s.status == ServiceStatus.HEALTHY for s in services) if services else False
                results[dep.target_service] = {
                    "healthy": dep_healthy,
                    "required": dep.required,
                    "found": len(services) > 0,
                }
            self.telemetry["dependency_health_checked"] += 1
            return results
        except Exception:
            logger.exception("Failed to check dependency health")
            raise

    def set_health_threshold(self, service_id: str, threshold_key: str, value: Any) -> None:
        try:
            if service_id not in self._thresholds:
                self._thresholds[service_id] = {}
            self._thresholds[service_id][threshold_key] = value
            self._save()
            self.telemetry["health_thresholds_set"] += 1
            logger.info("Set health threshold %s=%s for service %s", threshold_key, value, service_id)
        except Exception:
            logger.exception("Failed to set health threshold for %s", service_id)
            raise


class DynamicRegistration:
    """Handles dynamic service registration with heartbeat."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._pending_file = os.path.join(storage_dir, "pending_registrations.json")
        self._pending: dict[str, dict] = {}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._pending_file):
                with open(self._pending_file, "r", encoding="utf-8") as fh:
                    self._pending = json.load(fh)
                logger.info("Loaded %d pending registrations", len(self._pending))
        except Exception:
            logger.exception("Failed to load pending registrations; starting fresh")
            self._pending = {}

    def _save(self) -> None:
        try:
            tmp = self._pending_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._pending, fh, indent=2, default=str)
            os.replace(tmp, self._pending_file)
        except Exception:
            logger.exception("Failed to save pending registrations")

    def auto_register(self, service_name: str, service_type: str, version: str,
                       host: str, port: int, protocol: str = "http",
                       region: str = "us-east-1",
                       metadata: Optional[dict] = None) -> dict:
        try:
            reg_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()
            entry = {
                "id": reg_id, "service_name": service_name, "service_type": service_type,
                "version": version, "host": host, "port": port, "protocol": protocol,
                "region": region, "metadata": metadata or {},
                "registered_at": now, "last_heartbeat": now, "status": "pending",
            }
            self._pending[reg_id] = entry
            self._save()
            self.telemetry["auto_registrations"] += 1
            logger.info("Auto-registered service %s (%s) at %s:%d", reg_id, service_name, host, port)
            return entry
        except Exception:
            logger.exception("Failed to auto-register service")
            raise

    def auto_unregister(self, registration_id: str) -> None:
        try:
            if registration_id not in self._pending:
                raise ValueError(f"Pending registration not found: {registration_id}")
            del self._pending[registration_id]
            self._save()
            self.telemetry["auto_unregistrations"] += 1
            logger.info("Auto-unregistered service %s", registration_id)
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to auto-unregister service %s", registration_id)
            raise

    def discover_services(self, service_type: Optional[str] = None,
                           region: Optional[str] = None) -> list[dict]:
        try:
            results = list(self._pending.values())
            if service_type is not None:
                results = [r for r in results if r.get("service_type") == service_type]
            if region is not None:
                results = [r for r in results if r.get("region") == region]
            self.telemetry["discovered_services"] += 1
            return results
        except Exception:
            logger.exception("Failed to discover services")
            raise

    def get_registration_status(self, registration_id: str) -> dict:
        entry = self._pending.get(registration_id)
        if entry is None:
            raise ValueError(f"Pending registration not found: {registration_id}")
        self.telemetry["registration_status_read"] += 1
        return entry

    def set_heartbeat(self, registration_id: str) -> dict:
        try:
            entry = self._pending.get(registration_id)
            if entry is None:
                raise ValueError(f"Pending registration not found: {registration_id}")
            entry["last_heartbeat"] = datetime.now(timezone.utc).isoformat()
            entry["status"] = "active"
            self._pending[registration_id] = entry
            self._save()
            self.telemetry["heartbeats_set"] += 1
            return entry
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to set heartbeat for %s", registration_id)
            raise


class VersionAwareness:
    """Manages version awareness with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._versions_file = os.path.join(storage_dir, "service_versions.json")
        self._versions: dict[str, list[dict]] = defaultdict(list)
        self._deprecation_file = os.path.join(storage_dir, "deprecation_schedule.json")
        self._deprecation: dict[str, dict] = {}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._versions_file):
                with open(self._versions_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._versions = defaultdict(list, {k: list(v) for k, v in data.items()})
                logger.info("Loaded version info for %d services", len(self._versions))
        except Exception:
            logger.exception("Failed to load service versions; starting fresh")
            self._versions = defaultdict(list)
        try:
            if os.path.exists(self._deprecation_file):
                with open(self._deprecation_file, "r", encoding="utf-8") as fh:
                    self._deprecation = json.load(fh)
        except Exception:
            self._deprecation = {}

    def _save(self) -> None:
        try:
            data = dict(self._versions)
            tmp = self._versions_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._versions_file)
        except Exception:
            logger.exception("Failed to save service versions")
        try:
            tmp = self._deprecation_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._deprecation, fh, indent=2, default=str)
            os.replace(tmp, self._deprecation_file)
        except Exception:
            logger.exception("Failed to save deprecation schedule")

    def register_version(self, service_name: str, version: str,
                          release_notes: str = "", is_latest: bool = True) -> dict:
        try:
            now = datetime.now(timezone.utc).isoformat()
            entry = {
                "service_name": service_name, "version": version,
                "release_notes": release_notes, "registered_at": now,
                "is_latest": is_latest,
            }
            if is_latest:
                for v in self._versions.get(service_name, []):
                    v["is_latest"] = False
            self._versions[service_name].append(entry)
            self._save()
            self.telemetry["versions_registered"] += 1
            logger.info("Registered version %s for service %s", version, service_name)
            return entry
        except Exception:
            logger.exception("Failed to register version")
            raise

    def get_version(self, service_name: str, version: str) -> Optional[dict]:
        for v in self._versions.get(service_name, []):
            if v["version"] == version:
                self.telemetry["versions_read"] += 1
                return v
        return None

    def list_versions(self, service_name: str) -> list[dict]:
        versions = self._versions.get(service_name, [])
        versions.sort(key=lambda x: x.get("registered_at", ""), reverse=True)
        self.telemetry["versions_listed"] += 1
        return versions

    def get_latest_version(self, service_name: str) -> Optional[dict]:
        for v in self._versions.get(service_name, []):
            if v.get("is_latest"):
                self.telemetry["latest_version_read"] += 1
                return v
        versions = self.list_versions(service_name)
        return versions[0] if versions else None

    def check_deprecated(self, service_name: str, version: str) -> bool:
        dep_key = f"{service_name}:{version}"
        entry = self._deprecation.get(dep_key)
        if entry is None:
            return False
        if entry.get("deprecated_at"):
            self.telemetry["deprecation_checks"] += 1
            return True
        return False

    def check_compatible_version(self, service_name: str, version: str,
                                  constraint: str) -> bool:
        try:
            if not constraint:
                return True
            parts = version.split(".")
            constraint_parts = constraint.replace(">=", "").replace("<=", "").replace("==", "").replace(">", "").replace("<", "").strip().split(".")
            for i, cp in enumerate(constraint_parts):
                if i < len(parts):
                    try:
                        vp = int(parts[i])
                        cpv = int(cp)
                        if ">=" in constraint and vp < cpv:
                            return False
                        if "<=" in constraint and vp > cpv:
                            return False
                        if "==" in constraint and vp != cpv:
                            return False
                        if ">" in constraint and vp <= cpv:
                            return False
                        if "<" in constraint and vp >= cpv:
                            return False
                    except (ValueError, IndexError):
                        continue
            self.telemetry["compatibility_checks"] += 1
            return True
        except Exception:
            logger.exception("Failed to check compatible version")
            return False

    def get_deprecation_schedule(self, service_name: Optional[str] = None) -> dict:
        try:
            if service_name:
                relevant = {k: v for k, v in self._deprecation.items() if k.startswith(service_name)}
            else:
                relevant = dict(self._deprecation)
            self.telemetry["deprecation_schedules_read"] += 1
            return relevant
        except Exception:
            logger.exception("Failed to get deprecation schedule")
            raise


class ServiceDependencyGraph:
    """Manages service dependency graph with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._deps_file = os.path.join(storage_dir, "service_dependencies.json")
        self._dependencies: dict[str, list[ServiceDependency]] = defaultdict(list)
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._deps_file):
                with open(self._deps_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._dependencies = defaultdict(
                    list,
                    {k: [ServiceDependency.from_dict(d) for d in v] for k, v in data.items()},
                )
                logger.info("Loaded dependencies for %d services", len(self._dependencies))
        except Exception:
            logger.exception("Failed to load service dependencies; starting fresh")
            self._dependencies = defaultdict(list)

    def _save(self) -> None:
        try:
            data = {k: [d.to_dict() for d in v] for k, v in self._dependencies.items()}
            tmp = self._deps_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._deps_file)
        except Exception:
            logger.exception("Failed to save service dependencies")

    def add_dependency(self, source_service: str, target_service: str,
                        dependency_type: str = "hard", required: bool = True,
                        version_constraint: str = "", timeout_ms: int = 5000,
                        retry_count: int = 3) -> ServiceDependency:
        try:
            dep = ServiceDependency(
                source_service=source_service, target_service=target_service,
                dependency_type=dependency_type, required=required,
                version_constraint=version_constraint, timeout_ms=timeout_ms,
                retry_count=retry_count,
            )
            existing = [d for d in self._dependencies[source_service]
                        if d.target_service == target_service]
            if not existing:
                self._dependencies[source_service].append(dep)
                self._save()
                self.telemetry["dependencies_added"] += 1
                logger.info("Added dependency %s -> %s", source_service, target_service)
            return dep
        except Exception:
            logger.exception("Failed to add dependency")
            raise

    def remove_dependency(self, source_service: str, target_service: str) -> None:
        try:
            self._dependencies[source_service] = [
                d for d in self._dependencies[source_service]
                if d.target_service != target_service
            ]
            self._save()
            self.telemetry["dependencies_removed"] += 1
            logger.info("Removed dependency %s -> %s", source_service, target_service)
        except Exception:
            logger.exception("Failed to remove dependency")
            raise

    def get_dependencies(self, service_name: str) -> list[ServiceDependency]:
        deps = self._dependencies.get(service_name, [])
        self.telemetry["dependencies_read"] += 1
        return list(deps)

    def get_dependents(self, service_name: str) -> list[str]:
        try:
            dependents = []
            for src, deps in self._dependencies.items():
                for d in deps:
                    if d.target_service == service_name:
                        dependents.append(src)
            self.telemetry["dependents_read"] += 1
            return dependents
        except Exception:
            logger.exception("Failed to get dependents for %s", service_name)
            raise

    def find_critical_path(self, source_service: str, target_service: str) -> list[str]:
        try:
            visited = set()
            path = []
            found = False

            def dfs(current: str, target: str, path_so_far: list[str]):
                nonlocal found
                if current in visited or found:
                    return
                visited.add(current)
                path_so_far.append(current)
                if current == target:
                    path.extend(path_so_far)
                    found = True
                    return
                for dep in self._dependencies.get(current, []):
                    dfs(dep.target_service, target, path_so_far)
                path_so_far.pop()

            dfs(source_service, target_service, [])
            self.telemetry["critical_paths_found"] += 1
            return path
        except Exception:
            logger.exception("Failed to find critical path")
            raise

    def get_impact_analysis(self, service_name: str) -> dict:
        try:
            affected = set()
            dependents = self.get_dependents(service_name)
            queue = list(dependents)
            while queue:
                current = queue.pop(0)
                if current not in affected:
                    affected.add(current)
                    queue.extend(self.get_dependents(current))
            deps = self.get_dependencies(service_name)
            result = {
                "service": service_name,
                "dependencies": [d.target_service for d in deps],
                "dependents": dependents,
                "all_affected": list(affected),
                "impact_count": len(affected),
            }
            self.telemetry["impact_analyses_performed"] += 1
            return result
        except Exception:
            logger.exception("Failed to get impact analysis for %s", service_name)
            raise

    def get_service_graph(self) -> dict:
        try:
            graph = {}
            for src, deps in self._dependencies.items():
                graph[src] = [d.target_service for d in deps]
            self.telemetry["service_graphs_read"] += 1
            return graph
        except Exception:
            logger.exception("Failed to get service graph")
            raise

    def detect_cycles(self) -> list[list[str]]:
        try:
            all_services = set(self._dependencies.keys())
            for deps in self._dependencies.values():
                for d in deps:
                    all_services.add(d.target_service)

            cycles = []
            visited = set()
            rec_stack = set()

            def dfs(node: str, path: list[str]):
                visited.add(node)
                rec_stack.add(node)
                path.append(node)
                for dep in self._dependencies.get(node, []):
                    if dep.target_service not in visited:
                        dfs(dep.target_service, path)
                    elif dep.target_service in rec_stack:
                        cycle_start = path.index(dep.target_service)
                        cycle = path[cycle_start:] + [dep.target_service]
                        cycles.append(cycle)
                path.pop()
                rec_stack.discard(node)

            for svc in all_services:
                if svc not in visited:
                    dfs(svc, [])

            self.telemetry["cycle_detections"] += 1
            return cycles
        except Exception:
            logger.exception("Failed to detect cycles")
            raise


class ServiceDiscoveryManager(ServiceRegistry, HealthMonitor, DynamicRegistration,
                               VersionAwareness, ServiceDependencyGraph):
    """Unified service discovery manager combining all sub-managers."""

    def __init__(self, storage_dir: str):
        ServiceRegistry.__init__(self, storage_dir)
        HealthMonitor.__init__(self, storage_dir)
        DynamicRegistration.__init__(self, storage_dir)
        VersionAwareness.__init__(self, storage_dir)
        ServiceDependencyGraph.__init__(self, storage_dir)
        self.telemetry: dict = defaultdict(int)
        logger.info("ServiceDiscoveryManager initialized at %s", storage_dir)

    def get_topology(self, service_name: str) -> ServiceTopology:
        try:
            instances = self.list_by_type(service_name) or []
            deps = self.get_dependencies(service_name)
            healthy_count = sum(1 for i in instances if i.status == ServiceStatus.HEALTHY)
            total = len(instances)
            health_score = round(healthy_count / total, 2) if total > 0 else 1.0
            topology = ServiceTopology(
                name=service_name,
                instances=instances,
                dependencies=deps,
                health_score=health_score,
                instance_count=total,
            )
            self.telemetry["topologies_generated"] += 1
            return topology
        except Exception:
            logger.exception("Failed to get topology for %s", service_name)
            raise

    def get_system_health(self) -> dict:
        try:
            all_instances = self.list_services()
            total = len(all_instances)
            healthy = sum(1 for i in all_instances if i.status == ServiceStatus.HEALTHY)
            degraded = sum(1 for i in all_instances if i.status == ServiceStatus.DEGRADED)
            unhealthy = sum(1 for i in all_instances if i.status == ServiceStatus.UNHEALTHY)
            offline = sum(1 for i in all_instances if i.status == ServiceStatus.OFFLINE)
            by_type = defaultdict(int)
            for i in all_instances:
                by_type[i.service_type] += 1
            health_score = round(healthy / total, 2) if total > 0 else 0
            result = {
                "total_services": total,
                "healthy": healthy,
                "degraded": degraded,
                "unhealthy": unhealthy,
                "offline": offline,
                "health_score": health_score,
                "by_type": dict(by_type),
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
            self.telemetry["system_health_read"] += 1
            return result
        except Exception:
            logger.exception("Failed to get system health")
            raise

    def get_service_map(self) -> dict:
        try:
            instances = self.list_services()
            graph = self.get_service_graph()
            service_map = {}
            for inst in instances:
                if inst.service_name not in service_map:
                    service_map[inst.service_name] = {
                        "instances": [],
                        "dependencies": graph.get(inst.service_name, []),
                        "dependents": self.get_dependents(inst.service_name),
                    }
                service_map[inst.service_name]["instances"].append(inst.to_dict())
            self.telemetry["service_maps_generated"] += 1
            return service_map
        except Exception:
            logger.exception("Failed to get service map")
            raise
