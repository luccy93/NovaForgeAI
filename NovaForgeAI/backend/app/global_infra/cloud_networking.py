"""Cloud Networking — VPC, private networking, DNS, VPN, private endpoints, load balancers, API gateway."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class NetworkConfig:
    id: str; org_id: str; name: str; vpc_cidr: str = "10.0.0.0/16"
    private_subnets: list = field(default_factory=list); public_subnets: list = field(default_factory=list)
    dns_enabled: bool = True; vpn_enabled: bool = False
    private_endpoints: list = field(default_factory=list); load_balancers: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class CloudNetworking:
    def __init__(self, storage_dir: str = "infra_data/networking"):
        self.storage_dir = storage_dir; self._networks: dict[str, NetworkConfig] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "networks.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._networks[k] = NetworkConfig(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try: with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._networks.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create(self, org_id: str, name: str) -> NetworkConfig:
        n = NetworkConfig(id=str(uuid.uuid4()), org_id=org_id, name=name)
        self._networks[n.id] = n; self._save(); return n

    def get_telemetry(self) -> dict: return {"networks": len(self._networks)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class GPUCluster:
    id: str; org_id: str; name: str; gpu_type: str = "A100"; count: int = 4
    region: str = ""; usage_percent: float = 0.0; autoscaling: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class GPUInfrastructure:
    def __init__(self, storage_dir: str = "infra_data/gpu"):
        self.storage_dir = storage_dir; self._clusters: dict[str, GPUCluster] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "clusters.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._clusters[k] = GPUCluster(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try: with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._clusters.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create(self, org_id: str, name: str, gpu_type: str = "A100", count: int = 4) -> GPUCluster:
        c = GPUCluster(id=str(uuid.uuid4()), org_id=org_id, name=name, gpu_type=gpu_type, count=count)
        self._clusters[c.id] = c; self._save(); return c

    def get_telemetry(self) -> dict: return {"clusters": len(self._clusters)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class CostReport:
    id: str; org_id: str; period: str; total_cost: float = 0.0
    compute_cost: float = 0.0; gpu_cost: float = 0.0; storage_cost: float = 0.0
    bandwidth_cost: float = 0.0; savings: float = 0.0; recommendations: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class CostOptimization:
    def __init__(self, storage_dir: str = "infra_data/cost"):
        self.storage_dir = storage_dir; self._reports: dict[str, CostReport] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "reports.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._reports[k] = CostReport(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try: with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._reports.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def generate(self, org_id: str, total: float = 0.0, savings: float = 0.0) -> CostReport:
        period = datetime.now(timezone.utc).strftime("%Y-%m")
        r = CostReport(id=str(uuid.uuid4()), org_id=org_id, period=period, total_cost=total, savings=savings)
        self._reports[r.id] = r; self._save(); return r

    def get_telemetry(self) -> dict: return {"reports": len(self._reports)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class GlobalAnalytic:
    id: str; org_id: str; period: str; report_type: str; data: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class GlobalAnalytics:
    def __init__(self, storage_dir: str = "infra_data/analytics"):
        self.storage_dir = storage_dir; self._analytics: dict[str, GlobalAnalytic] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "analytics.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._analytics[k] = GlobalAnalytic(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try: with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._analytics.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def generate(self, org_id: str, report_type: str, data: dict = None) -> GlobalAnalytic:
        period = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        a = GlobalAnalytic(id=str(uuid.uuid4()), org_id=org_id, period=period, report_type=report_type, data=data or {})
        self._analytics[a.id] = a; self._save(); return a

    def get_telemetry(self) -> dict: return {"analytics": len(self._analytics)}
