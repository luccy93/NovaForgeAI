"""Scaling Engine — auto-scale API servers, AI workers, search, embeddings, databases, caches, queues."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class ScalingPolicy:
    id: str; org_id: str; target: str; min_instances: int = 1; max_instances: int = 10
    target_cpu: float = 70.0; target_memory: float = 80.0; cooldown_seconds: int = 300
    is_active: bool = True; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

@dataclass
class ScalingEvent:
    id: str; policy_id: str; direction: str; from_instances: int; to_instances: int
    reason: str = ""; timestamp: float = 0.0

class ScalingEngine:
    def __init__(self, storage_dir: str = "infra_data/scaling"):
        self.storage_dir = storage_dir; self._policies: dict[str, ScalingPolicy] = {}; self._events: list = []
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "policies.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._policies[k] = ScalingPolicy(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try: with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._policies.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create_policy(self, org_id: str, target: str, min_inst: int = 1, max_inst: int = 10) -> ScalingPolicy:
        p = ScalingPolicy(id=str(uuid.uuid4()), org_id=org_id, target=target, min_instances=min_inst, max_instances=max_inst)
        self._policies[p.id] = p; self._save(); return p

    def get_telemetry(self) -> dict: return {"policies": len(self._policies)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class DRPlan:
    id: str; org_id: str; name: str; primary_region: str; dr_region: str
    rpo_minutes: int = 15; rto_minutes: int = 60; auto_failover: bool = True
    last_tested: str = ""; status: str = "active"; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class DisasterRecovery:
    def __init__(self, storage_dir: str = "infra_data/dr"):
        self.storage_dir = storage_dir; self._plans: dict[str, DRPlan] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "plans.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._plans[k] = DRPlan(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try: with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._plans.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create(self, org_id: str, name: str, primary: str, dr: str) -> DRPlan:
        p = DRPlan(id=str(uuid.uuid4()), org_id=org_id, name=name, primary_region=primary, dr_region=dr)
        self._plans[p.id] = p; self._save(); return p

    def get_telemetry(self) -> dict: return {"plans": len(self._plans)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class EdgeNode:
    id: str; org_id: str; name: str; location: str; capabilities: list = field(default_factory=list)
    status: str = "active"; latency_ms: float = 0.0; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class EdgeRuntime:
    def __init__(self, storage_dir: str = "infra_data/edge"):
        self.storage_dir = storage_dir; self._nodes: dict[str, EdgeNode] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "nodes.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._nodes[k] = EdgeNode(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try: with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._nodes.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def deploy(self, org_id: str, name: str, location: str, capabilities: list = None) -> EdgeNode:
        n = EdgeNode(id=str(uuid.uuid4()), org_id=org_id, name=name, location=location, capabilities=capabilities or ["api", "cache", "auth"])
        self._nodes[n.id] = n; self._save(); return n

    def get_telemetry(self) -> dict: return {"nodes": len(self._nodes)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class GlobalSchedule:
    id: str; org_id: str; task_type: str; target: str; cron: str = ""
    region: str = ""; status: str = "active"; last_run: str = ""; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class GlobalScheduler:
    def __init__(self, storage_dir: str = "infra_data/scheduler"):
        self.storage_dir = storage_dir; self._schedules: dict[str, GlobalSchedule] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "schedules.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._schedules[k] = GlobalSchedule(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try: with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._schedules.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def schedule(self, org_id: str, task_type: str, target: str, cron: str = "*/5 * * * *", region: str = "") -> GlobalSchedule:
        s = GlobalSchedule(id=str(uuid.uuid4()), org_id=org_id, task_type=task_type, target=target, cron=cron, region=region)
        self._schedules[s.id] = s; self._save(); return s

    def get_telemetry(self) -> dict: return {"schedules": len(self._schedules)}
