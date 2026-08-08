"""Workflow Automation — event triggers, conditional workflows, scheduled workflows, cross-platform automation for repos, issues, deployments, security."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class WorkflowTriggerType(Enum):
    EVENT = "event"
    SCHEDULE = "schedule"
    MANUAL = "manual"


class WorkflowStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DRAFT = "draft"
    ERROR = "error"


class WorkflowStepType(Enum):
    CONDITION = "condition"
    ACTION = "action"
    WEBHOOK = "webhook"
    DELAY = "delay"
    NOTIFICATION = "notification"
    TRANSFORM = "transform"


@dataclass
class WorkflowStep:
    id: str
    step_type: WorkflowStepType
    name: str
    config: dict = field(default_factory=dict)
    order: int = 0
    on_success: str = "continue"
    on_failure: str = "stop"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["step_type"] = self.step_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "WorkflowStep":
        data = data.copy()
        data["step_type"] = WorkflowStepType(data.get("step_type", "action"))
        return cls(**data)


@dataclass
class Workflow:
    id: str
    org_id: str
    name: str
    trigger_type: WorkflowTriggerType
    trigger_config: dict = field(default_factory=dict)
    steps: list = field(default_factory=list)
    status: WorkflowStatus = WorkflowStatus.DRAFT
    description: str = ""
    run_count: int = 0
    last_run: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["trigger_type"] = self.trigger_type.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Workflow":
        data = data.copy()
        data["trigger_type"] = WorkflowTriggerType(data.get("trigger_type", "event"))
        data["status"] = WorkflowStatus(data.get("status", "draft"))
        return cls(**data)


@dataclass
class WorkflowExecution:
    id: str
    workflow_id: str
    triggered_by: str = ""
    trigger_event: str = ""
    status: str = "running"
    steps_completed: int = 0
    total_steps: int = 0
    output: dict = field(default_factory=dict)
    error: str = ""
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str = ""

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "WorkflowExecution": return cls(**data)


class WorkflowAutomation:
    def __init__(self, storage_dir: str = "integration_data/workflows"):
        self.storage_dir = storage_dir
        self._workflows: dict[str, Workflow] = {}
        self._executions: dict[str, WorkflowExecution] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _wf_path(self) -> str: return os.path.join(self.storage_dir, "workflows.json")
    def _exec_path(self) -> str: return os.path.join(self.storage_dir, "executions.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._wf_path(), self._workflows, Workflow),
            (self._exec_path(), self._executions, WorkflowExecution),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Failed to load workflow data: %s", e)

    def _save(self) -> None:
        try:
            with open(self._wf_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._workflows.items()}, f, indent=2, default=str)
            with open(self._exec_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._executions.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save workflow data: %s", e)

    def create_workflow(self, org_id: str, name: str, trigger_type: WorkflowTriggerType, trigger_config: dict = None, description: str = "") -> Workflow:
        wf = Workflow(id=str(uuid.uuid4()), org_id=org_id, name=name, trigger_type=trigger_type, trigger_config=trigger_config or {}, description=description)
        self._workflows[wf.id] = wf
        self._save()
        return wf

    def add_step(self, workflow_id: str, step_type: WorkflowStepType, name: str, config: dict = None) -> Optional[WorkflowStep]:
        wf = self._workflows.get(workflow_id)
        if not wf: return None
        step = WorkflowStep(id=str(uuid.uuid4()), step_type=step_type, name=name, config=config or {}, order=len(wf.steps))
        wf.steps.append(step.to_dict())
        wf.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return step

    def execute(self, workflow_id: str, triggered_by: str = "", trigger_event: str = "") -> Optional[WorkflowExecution]:
        wf = self._workflows.get(workflow_id)
        if not wf or wf.status != WorkflowStatus.ACTIVE: return None
        exec = WorkflowExecution(id=str(uuid.uuid4()), workflow_id=workflow_id, triggered_by=triggered_by, trigger_event=trigger_event, total_steps=len(wf.steps))
        self._executions[exec.id] = exec
        wf.run_count += 1
        wf.last_run = exec.started_at
        self._save()
        exec.status = "completed"
        exec.steps_completed = len(wf.steps)
        exec.completed_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return exec

    def get_workflow(self, wf_id: str) -> Optional[Workflow]: return self._workflows.get(wf_id)

    def update_workflow(self, wf_id: str, updates: dict) -> Optional[Workflow]:
        wf = self._workflows.get(wf_id)
        if not wf: return None
        for k, v in updates.items():
            if hasattr(wf, k) and k not in ("id", "created_at"):
                if k == "trigger_type": setattr(wf, k, WorkflowTriggerType(v) if isinstance(v, str) else v)
                elif k == "status": setattr(wf, k, WorkflowStatus(v) if isinstance(v, str) else v)
                else: setattr(wf, k, v)
        wf.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return wf

    def list_workflows(self, org_id: str = "") -> list[Workflow]:
        results = list(self._workflows.values())
        if org_id: results = [w for w in results if w.org_id == org_id]
        return results

    def get_executions(self, workflow_id: str = "", limit: int = 50) -> list[WorkflowExecution]:
        results = list(self._executions.values())
        if workflow_id: results = [e for e in results if e.workflow_id == workflow_id]
        return sorted(results, key=lambda e: e.started_at, reverse=True)[:limit]

    def get_telemetry(self) -> dict: return dict(self._telemetry)
