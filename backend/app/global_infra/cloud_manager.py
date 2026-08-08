"""Cloud Manager — multi-cloud discovery, registration, sync, inventory, networking, health, cost, governance."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class CloudProvider:
    id: str; org_id: str; name: str; provider_type: str  # aws, azure, gcp, oci, ibm, digitalocean, cloudflare, hetzner, vultr, linode, self_hosted, hybrid, private
    region: str = ""; endpoint: str = ""; credentials: dict = field(default_factory=dict)
    health: str = "unknown"; is_active: bool = True; cost_tracking: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "CloudProvider": return cls(**data)

@dataclass
class CloudResource:
    id: str; provider_id: str; resource_type: str; name: str; status: str = "running"
    region: str = ""; cost_per_hour: float = 0.0; tags: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class CloudManager:
    def __init__(self, storage_dir: str = "infra_data/cloud"):
        self.storage_dir = storage_dir; self._providers: dict[str, CloudProvider] = {}; self._resources: dict[str, CloudResource] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _prov_path(self) -> str: return os.path.join(self.storage_dir, "providers.json")
    def _res_path(self) -> str: return os.path.join(self.storage_dir, "resources.json")

    def _load(self) -> None:
        for path, store, cls in [(self._prov_path(), self._providers, CloudProvider), (self._res_path(), self._resources, CloudResource)]:
            if os.path.exists(path):
                try:
                    with open(path, "r") as f: data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._prov_path(), "w") as f: json.dump({k: v.to_dict() for k, v in self._providers.items()}, f, indent=2, default=str)
            with open(self._res_path(), "w") as f: json.dump({k: asdict(v) for k, v in self._resources.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def register(self, org_id: str, name: str, provider_type: str, region: str = "") -> CloudProvider:
        p = CloudProvider(id=str(uuid.uuid4()), org_id=org_id, name=name, provider_type=provider_type, region=region)
        self._providers[p.id] = p; self._save(); return p

    def list_by_org(self, org_id: str) -> list[CloudProvider]: return [p for p in self._providers.values() if p.org_id == org_id]

    def get_telemetry(self) -> dict: return {"providers": len(self._providers), "resources": len(self._resources)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class Region:
    id: str; org_id: str; name: str; region_type: str  # primary, secondary, dr, edge
    cloud_provider: str = ""; location: str = ""; status: str = "active"
    health_score: float = 1.0; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class RegionManager:
    def __init__(self, storage_dir: str = "infra_data/regions"):
        self.storage_dir = storage_dir; self._regions: dict[str, Region] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "regions.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._regions[k] = Region(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try: with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._regions.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def register(self, org_id: str, name: str, region_type: str, cloud_provider: str = "") -> Region:
        r = Region(id=str(uuid.uuid4()), org_id=org_id, name=name, region_type=region_type, cloud_provider=cloud_provider)
        self._regions[r.id] = r; self._save(); return r

    def get_by_type(self, org_id: str, region_type: str) -> list[Region]: return [r for r in self._regions.values() if r.org_id == org_id and r.region_type == region_type]

    def get_telemetry(self) -> dict: return {"regions": len(self._regions)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class K8sCluster:
    id: str; org_id: str; name: str; provider: str = ""; region: str = ""
    version: str = "1.28"; status: str = "active"; node_count: int = 3
    gpu_nodes: int = 0; autoscaling: bool = True; namespace_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class ClusterManager:
    def __init__(self, storage_dir: str = "infra_data/clusters"):
        self.storage_dir = storage_dir; self._clusters: dict[str, K8sCluster] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "clusters.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._clusters[k] = K8sCluster(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try: with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._clusters.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def register(self, org_id: str, name: str, provider: str = "", region: str = "") -> K8sCluster:
        c = K8sCluster(id=str(uuid.uuid4()), org_id=org_id, name=name, provider=provider, region=region)
        self._clusters[c.id] = c; self._save(); return c

    def list_by_org(self, org_id: str) -> list[K8sCluster]: return [c for c in self._clusters.values() if c.org_id == org_id]

    def get_telemetry(self) -> dict: return {"clusters": len(self._clusters)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class InfraStack:
    id: str; org_id: str; name: str; stack_type: str  # terraform, pulumi, helm, kustomize, ansible, cloudformation, crossplane
    config: dict = field(default_factory=dict); status: str = "deployed"
    version: int = 1; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class InfrastructureManager:
    def __init__(self, storage_dir: str = "infra_data/stacks"):
        self.storage_dir = storage_dir; self._stacks: dict[str, InfraStack] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "stacks.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._stacks[k] = InfraStack(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try: with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._stacks.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create(self, org_id: str, name: str, stack_type: str, config: dict = None) -> InfraStack:
        s = InfraStack(id=str(uuid.uuid4()), org_id=org_id, name=name, stack_type=stack_type, config=config or {})
        self._stacks[s.id] = s; self._save(); return s

    def get_telemetry(self) -> dict: return {"stacks": len(self._stacks)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class TrafficPolicy:
    id: str; org_id: str; name: str; routing_type: str  # geo, latency, weighted, regional
    rules: list = field(default_factory=list); health_checks: bool = True
    fallback_region: str = ""; is_active: bool = True; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class TrafficManager:
    def __init__(self, storage_dir: str = "infra_data/traffic"):
        self.storage_dir = storage_dir; self._policies: dict[str, TrafficPolicy] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "policies.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._policies[k] = TrafficPolicy(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try: with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._policies.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create_policy(self, org_id: str, name: str, routing_type: str = "latency") -> TrafficPolicy:
        p = TrafficPolicy(id=str(uuid.uuid4()), org_id=org_id, name=name, routing_type=routing_type)
        self._policies[p.id] = p; self._save(); return p

    def get_telemetry(self) -> dict: return {"policies": len(self._policies)}
