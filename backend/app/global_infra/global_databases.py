"""Global Databases — PostgreSQL, Redis, Neo4j, Qdrant replication, sharding, read replicas, backups."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class DatabaseCluster:
    id: str; org_id: str; name: str; db_type: str  # postgresql, redis, neo4j, qdrant
    region: str = ""; replicas: int = 1; sharding: bool = False
    backup_enabled: bool = True; point_in_time_recovery: bool = True
    status: str = "active"; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class GlobalDatabases:
    def __init__(self, storage_dir: str = "infra_data/databases"):
        self.storage_dir = storage_dir; self._clusters: dict[str, DatabaseCluster] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "clusters.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._clusters[k] = DatabaseCluster(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._clusters.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create(self, org_id: str, name: str, db_type: str, region: str = "") -> DatabaseCluster:
        c = DatabaseCluster(id=str(uuid.uuid4()), org_id=org_id, name=name, db_type=db_type, region=region)
        self._clusters[c.id] = c; self._save(); return c

    def get_telemetry(self) -> dict: return {"clusters": len(self._clusters)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class CacheTier:
    id: str; org_id: str; name: str; cache_type: str  # regional, edge, repo, search, embedding, memory, session
    region: str = ""; size_mb: int = 1024; hit_rate: float = 0.0
    status: str = "active"; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class DistributedCache:
    def __init__(self, storage_dir: str = "infra_data/cache"):
        self.storage_dir = storage_dir; self._tiers: dict[str, CacheTier] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "tiers.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._tiers[k] = CacheTier(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._tiers.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create(self, org_id: str, name: str, cache_type: str, region: str = "") -> CacheTier:
        t = CacheTier(id=str(uuid.uuid4()), org_id=org_id, name=name, cache_type=cache_type, region=region)
        self._tiers[t.id] = t; self._save(); return t

    def get_telemetry(self) -> dict: return {"tiers": len(self._tiers)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class MessageQueue:
    id: str; org_id: str; name: str; queue_type: str  # kafka, redis_streams, rabbitmq, nats, pubsub
    region: str = ""; partitions: int = 3; replication_factor: int = 2
    dead_letter: bool = True; status: str = "active"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class GlobalMessageBus:
    def __init__(self, storage_dir: str = "infra_data/queues"):
        self.storage_dir = storage_dir; self._queues: dict[str, MessageQueue] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "queues.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._queues[k] = MessageQueue(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._queues.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create(self, org_id: str, name: str, queue_type: str = "kafka", region: str = "") -> MessageQueue:
        q = MessageQueue(id=str(uuid.uuid4()), org_id=org_id, name=name, queue_type=queue_type, region=region)
        self._queues[q.id] = q; self._save(); return q

    def get_telemetry(self) -> dict: return {"queues": len(self._queues)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class HighAvailabilityConfig:
    id: str; org_id: str; name: str; target_uptime: float = 99.99
    replicas: int = 3; auto_recovery: bool = True; leader_election: bool = True
    rolling_updates: bool = True; health_interval: int = 10
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class HighAvailability:
    def __init__(self, storage_dir: str = "infra_data/ha"):
        self.storage_dir = storage_dir; self._configs: dict[str, HighAvailabilityConfig] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "configs.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._configs[k] = HighAvailabilityConfig(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._configs.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def configure(self, org_id: str, name: str, uptime: float = 99.99) -> HighAvailabilityConfig:
        c = HighAvailabilityConfig(id=str(uuid.uuid4()), org_id=org_id, name=name, target_uptime=uptime)
        self._configs[c.id] = c; self._save(); return c

    def get_telemetry(self) -> dict: return {"configs": len(self._configs)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class GlobalSecurityConfig:
    id: str; org_id: str; zero_trust: bool = True; waf_enabled: bool = True
    ddos_protection: bool = True; firewall_rules: list = field(default_factory=list)
    secret_rotation_days: int = 90; certificate_rotation_days: int = 30
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class GlobalSecurity:
    def __init__(self, storage_dir: str = "infra_data/security"):
        self.storage_dir = storage_dir; self._configs: dict[str, GlobalSecurityConfig] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "configs.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._configs[k] = GlobalSecurityConfig(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._configs.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def configure(self, org_id: str, name: str = "default") -> GlobalSecurityConfig:
        c = GlobalSecurityConfig(id=str(uuid.uuid4()), org_id=org_id)
        self._configs[c.id] = c; self._save(); return c

    def get_telemetry(self) -> dict: return {"configs": len(self._configs)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class InfraMetric:
    id: str; org_id: str; period: str; region_health: float = 1.0; cluster_health: float = 1.0
    avg_latency_ms: float = 0.0; bandwidth_gbps: float = 0.0
    infra_cost: float = 0.0; storage_growth_gb: float = 0.0
    node_utilization: float = 0.0; gpu_utilization: float = 0.0
    memory_usage: float = 0.0; cpu_usage: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class GlobalObservability:
    def __init__(self, storage_dir: str = "infra_data/observability"):
        self.storage_dir = storage_dir; self._metrics: dict[str, InfraMetric] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "metrics.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._metrics[k] = InfraMetric(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._metrics.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def record(self, org_id: str, metrics: dict) -> InfraMetric:
        period = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H")
        m = InfraMetric(id=str(uuid.uuid4()), org_id=org_id, period=period, **{k: v for k, v in metrics.items() if k in [f.name for f in InfraMetric.__dataclass_fields__]})
        self._metrics[m.id] = m; self._save(); return m

    def get_latest(self, org_id: str) -> Optional[InfraMetric]:
        relevant = [m for m in self._metrics.values() if m.org_id == org_id]
        return sorted(relevant, key=lambda m: m.created_at, reverse=True)[0] if relevant else None

    def get_telemetry(self) -> dict: return {"points": len(self._metrics)}
