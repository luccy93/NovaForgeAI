"""Future AI — prototype autonomous coding, debugging, refactoring, architecture design, deployment, security review, testing, documentation, repository maintenance."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class AutonomousCapability(Enum):
    CODING = "autonomous_coding"
    DEBUGGING = "autonomous_debugging"
    REFACTORING = "autonomous_refactoring"
    ARCHITECTURE = "autonomous_architecture"
    DEPLOYMENT = "autonomous_deployment"
    SECURITY_REVIEW = "autonomous_security_review"
    TESTING = "autonomous_testing"
    DOCUMENTATION = "autonomous_documentation"
    REPO_MAINTENANCE = "autonomous_repo_maintenance"


class CapabilityStatus(Enum):
    PROTOTYPE = "prototype"
    EXPERIMENTAL = "experimental"
    BETA = "beta"
    STABLE = "stable"
    DEPRECATED = "deprecated"


@dataclass
class AutonomousCapabilityRecord:
    id: str
    name: str
    capability: AutonomousCapability
    status: CapabilityStatus = CapabilityStatus.PROTOTYPE
    description: str = ""
    version: str = "0.1.0"
    success_rate: float = 0.0
    total_runs: int = 0
    successful_runs: int = 0
    metrics: dict = field(default_factory=dict)
    tags: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["capability"] = self.capability.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AutonomousCapabilityRecord":
        data = data.copy()
        data["capability"] = AutonomousCapability(data.get("capability", "autonomous_coding"))
        data["status"] = CapabilityStatus(data.get("status", "prototype"))
        return cls(**data)


@dataclass
class CapabilityExecution:
    id: str
    capability_id: str
    input_data: dict = field(default_factory=dict)
    output_data: dict = field(default_factory=dict)
    success: bool = False
    duration_ms: float = 0.0
    tokens_used: int = 0
    error: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "CapabilityExecution": return cls(**data)


class FutureAI:
    def __init__(self, storage_dir: str = "research_data/future_ai"):
        self.storage_dir = storage_dir
        self._capabilities: dict[str, AutonomousCapabilityRecord] = {}
        self._executions: dict[str, CapabilityExecution] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _caps_path(self) -> str: return os.path.join(self.storage_dir, "capabilities.json")
    def _execs_path(self) -> str: return os.path.join(self.storage_dir, "executions.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._caps_path(), self._capabilities, AutonomousCapabilityRecord),
            (self._execs_path(), self._executions, CapabilityExecution),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Failed to load future AI data: %s", e)

    def _save(self) -> None:
        try:
            with open(self._caps_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._capabilities.items()}, f, indent=2, default=str)
            with open(self._execs_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._executions.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save future AI data: %s", e)

    def register_capability(self, name: str, capability: AutonomousCapability, description: str = "") -> AutonomousCapabilityRecord:
        cap = AutonomousCapabilityRecord(id=str(uuid.uuid4()), name=name, capability=capability, description=description)
        self._capabilities[cap.id] = cap
        self._save()
        return cap

    def get_capability(self, cap_id: str) -> Optional[AutonomousCapabilityRecord]: return self._capabilities.get(cap_id)

    def update_capability(self, cap_id: str, updates: dict) -> Optional[AutonomousCapabilityRecord]:
        cap = self._capabilities.get(cap_id)
        if not cap: return None
        for k, v in updates.items():
            if hasattr(cap, k) and k not in ("id", "created_at"):
                if k == "capability": setattr(cap, k, AutonomousCapability(v) if isinstance(v, str) else v)
                elif k == "status": setattr(cap, k, CapabilityStatus(v) if isinstance(v, str) else v)
                else: setattr(cap, k, v)
        cap.updated_at = datetime.now(timezone.utc).isoformat()
        if "success" in updates:
            cap.total_runs += 1
            if updates["success"]: cap.successful_runs += 1
            cap.success_rate = round(cap.successful_runs / max(cap.total_runs, 1), 4)
        self._save()
        return cap

    def record_execution(self, capability_id: str, input_data: dict, output_data: dict, success: bool, duration_ms: float = 0.0, tokens_used: int = 0, error: str = "") -> CapabilityExecution:
        exec = CapabilityExecution(id=str(uuid.uuid4()), capability_id=capability_id, input_data=input_data, output_data=output_data, success=success, duration_ms=duration_ms, tokens_used=tokens_used, error=error)
        self._executions[exec.id] = exec
        cap = self._capabilities.get(capability_id)
        if cap:
            cap.total_runs += 1
            if success: cap.successful_runs += 1
            cap.success_rate = round(cap.successful_runs / max(cap.total_runs, 1), 4)
            cap.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return exec

    def list_capabilities(self, capability: Optional[AutonomousCapability] = None, status: Optional[CapabilityStatus] = None) -> list[AutonomousCapabilityRecord]:
        results = list(self._capabilities.values())
        if capability: results = [c for c in results if c.capability == capability]
        if status: results = [c for c in results if c.status == status]
        return results

    def get_executions(self, capability_id: str = "", limit: int = 50) -> list[CapabilityExecution]:
        results = list(self._executions.values())
        if capability_id: results = [e for e in results if e.capability_id == capability_id]
        return sorted(results, key=lambda e: e.created_at, reverse=True)[:limit]

    def get_telemetry(self) -> dict: return dict(self._telemetry)
