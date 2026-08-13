"""Automation workflow domain (Volume 33): specs, versions, store.

Workflows are declarative, strongly typed and versioned. Every workflow
carries a lifecycle: draft -> published -> paused / deprecated -> archived.
All writes are tenant-scoped and persisted to JSON (JsonFileStorage).
"""
from __future__ import annotations

import logging, time, uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from ..common.storage import JsonFileStorage

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------- status
WORKFLOW_STATUS = ("draft", "published", "paused", "deprecated", "archived")
STEP_TYPES = ("task", "tool", "agent", "approval", "condition", "wait",
              "parallel", "join", "subworkflow", "end", "report", "artifact",
              "decision", "security", "infra", "terminal", "browser", "cicd")
STEP_STATUS = ("pending", "running", "succeeded", "failed", "skipped",
               "waiting_approval", "rolled_back", "cancelled")
EXECUTION_STATUS = ("queued", "scheduled", "running", "waiting_for_approval",
                    "paused", "retrying", "completed", "failed", "cancelled",
                    "timed_out", "rolled_back", "partially_completed")


# ------------------------------------------------------------------ models
@dataclass
class RetryPolicy:
    max_retries: int = 0
    backoff_s: float = 1.0
    multiplier: float = 2.0
    max_backoff_s: float = 60.0
    retry_on: list[str] = field(default_factory=list)  # e.g. ["network", "timeout"]

    def to_dict(self) -> dict:
        return {"max_retries": self.max_retries, "backoff_s": self.backoff_s,
                "multiplier": self.multiplier, "max_backoff_s": self.max_backoff_s,
                "retry_on": self.retry_on}

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "RetryPolicy":
        if not d:
            return cls()
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class WorkflowStep:
    id: str
    type: str = "task"
    name: str = ""
    action: str = ""          # tool_id or agent name
    inputs: dict = field(default_factory=dict)
    output_key: str = ""
    depends_on: list[str] = field(default_factory=list)
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    timeout_s: int = 300
    risk: str = "low"         # low | medium | high
    needs_approval: bool = False
    approval_type: str = "single"
    compensation: str = ""    # step id or action to undo this step
    condition: str = ""       # evaluated against previous step outputs
    wait_s: float = 0.0
    parallel_steps: list["WorkflowStep"] = field(default_factory=list)
    subworkflow_id: str = ""
    permissions: dict = field(default_factory=dict)
    description: str = ""

    def to_dict(self) -> dict:
        return {"id": self.id, "type": self.type, "name": self.name,
                "action": self.action, "inputs": self.inputs,
                "output_key": self.output_key, "depends_on": self.depends_on,
                "retry": self.retry.to_dict(), "timeout_s": self.timeout_s,
                "risk": self.risk, "needs_approval": self.needs_approval,
                "approval_type": self.approval_type,
                "compensation": self.compensation, "condition": self.condition,
                "wait_s": self.wait_s,
                "parallel_steps": [p.to_dict() for p in self.parallel_steps],
                "subworkflow_id": self.subworkflow_id,
                "permissions": self.permissions, "description": self.description}

    @classmethod
    def from_dict(cls, d: dict) -> "WorkflowStep":
        data = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        data["retry"] = RetryPolicy.from_dict(d.get("retry"))
        data["parallel_steps"] = [cls.from_dict(p)
                                  for p in d.get("parallel_steps", [])]
        return cls(**data)

    @property
    def leaf_steps(self) -> list["WorkflowStep"]:
        if self.parallel_steps:
            out = []
            for p in self.parallel_steps:
                out.extend(p.leaf_steps)
            return out
        return [self]


@dataclass
class WorkflowSpec:
    workflow_id: str
    name: str
    organization_id: str
    trigger: dict = field(default_factory=dict)   # {type, cron, event, ...}
    steps: list[WorkflowStep] = field(default_factory=list)
    policies: dict = field(default_factory=dict)  # allowed tools/commands/domains...
    status: str = "draft"
    version: int = 1
    description: str = ""
    created_by: str = ""
    created_at: str = ""
    updated_at: str = ""
    change_history: list[dict] = field(default_factory=list)
    approval_history: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"workflow_id": self.workflow_id, "name": self.name,
                "organization_id": self.organization_id, "trigger": self.trigger,
                "steps": [s.to_dict() for s in self.steps],
                "policies": self.policies, "status": self.status,
                "version": self.version, "description": self.description,
                "created_by": self.created_by, "created_at": self.created_at,
                "updated_at": self.updated_at,
                "change_history": self.change_history[-100:],
                "approval_history": self.approval_history[-100:]}

    @classmethod
    def from_dict(cls, d: dict) -> "WorkflowSpec":
        data = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        data["steps"] = [WorkflowStep.from_dict(s) for s in d.get("steps", [])]
        return cls(**data)

    def flat_steps(self) -> list[WorkflowStep]:
        out = []
        for s in self.steps:
            out.extend(s.leaf_steps)
        return out


@dataclass
class WorkflowVersion:
    version_id: str
    workflow_id: str
    version: int
    status: str
    notes: str
    created_by: str
    created_at: str
    spec: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"version_id": self.version_id, "workflow_id": self.workflow_id,
                "version": self.version, "status": self.status,
                "notes": self.notes, "created_by": self.created_by,
                "created_at": self.created_at, "spec": self.spec}


# ------------------------------------------------------------------- store
class WorkflowStore:
    """Tenant-scoped workflow registry with versioning and lifecycle."""

    def __init__(self, storage: Optional[JsonFileStorage] = None):
        self.storage = storage or JsonFileStorage("data/automation/workflows.json")
        self._workflows: dict[str, WorkflowSpec] = {}
        self._versions: dict[str, list[WorkflowVersion]] = {}
        self._load()

    def _load(self) -> None:
        try:
            wf = self.storage.get("workflows") or {}
            self._workflows = {k: WorkflowSpec.from_dict(v)
                               for k, v in wf.items() if isinstance(v, dict)}
            ver = self.storage.get("versions") or {}
            self._versions = {k: [WorkflowVersion(**{f: x.get(f)
                                                     for f in WorkflowVersion.__dataclass_fields__})
                                  for x in v]
                              for k, v in ver.items() if isinstance(v, list)}
        except Exception as exc:
            logger.warning("workflow store load failed: %s", exc)

    def _flush(self) -> None:
        try:
            self.storage.set("workflows", {k: v.to_dict()
                                           for k, v in self._workflows.items()})
            self.storage.set("versions", {k: [v.to_dict() for v in vals]
                                          for k, vals in self._versions.items()})
        except Exception as exc:
            logger.warning("workflow store flush failed: %s", exc)

    # ------------------------------------------------------------- crud
    def put(self, spec: WorkflowSpec) -> WorkflowSpec:
        spec.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if not spec.created_at:
            spec.created_at = spec.updated_at
        self._workflows[spec.workflow_id] = spec
        self._flush()
        return spec

    def get(self, workflow_id: str, organization_id: str = "") -> Optional[WorkflowSpec]:
        spec = self._workflows.get(workflow_id)
        if spec and organization_id and spec.organization_id != organization_id:
            return None  # tenant isolation
        return spec

    def list(self, organization_id: str = "", status: str = "",
             limit: int = 200) -> list[dict]:
        rows = [w for w in self._workflows.values()
                if (not organization_id or w.organization_id == organization_id)
                and (not status or w.status == status)]
        rows.sort(key=lambda w: w.updated_at, reverse=True)
        return [w.to_dict() for w in rows[:limit]]

    def count(self, organization_id: str = "") -> int:
        return len(self.list(organization_id))

    def delete(self, workflow_id: str, organization_id: str = "") -> bool:
        spec = self.get(workflow_id, organization_id)
        if not spec:
            return False
        spec.status = "archived"
        spec.change_history.append({"action": "delete", "at": _now(),
                                    "by": "system"})
        self._flush()
        return True

    # ------------------------------------------------------- versioning
    def publish(self, workflow_id: str, actor: str = "", notes: str = "") -> Optional[WorkflowSpec]:
        spec = self.get(workflow_id)
        if not spec:
            return None
        prev = spec.status
        spec.status = "published"
        spec.change_history.append({"action": "publish", "from": prev,
                                    "to": "published", "at": _now(), "by": actor})
        self._flush()
        return spec

    def transition(self, workflow_id: str, status: str, actor: str = "",
                   notes: str = "") -> Optional[WorkflowSpec]:
        if status not in WORKFLOW_STATUS:
            return None
        spec = self.get(workflow_id)
        if not spec:
            return None
        prev = spec.status
        spec.status = status
        spec.change_history.append({"action": "transition", "from": prev,
                                    "to": status, "at": _now(), "by": actor,
                                    "notes": notes})
        self._flush()
        return spec

    def new_version(self, workflow_id: str, spec: dict, actor: str = "",
                    notes: str = "") -> Optional[WorkflowVersion]:
        current = self.get(workflow_id)
        if not current:
            return None
        existing_versions = [v.version for v in
                             self._versions.get(workflow_id, [])]
        if current.version not in existing_versions:
            snapshot = WorkflowVersion(
                version_id=uuid.uuid4().hex[:16], workflow_id=workflow_id,
                version=current.version, status=current.status,
                notes="snapshot", created_by="system", created_at=_now(),
                spec=current.to_dict())
            self._versions.setdefault(workflow_id, []).append(snapshot)
        loaded = WorkflowSpec.from_dict(spec)
        loaded.workflow_id = workflow_id
        loaded.organization_id = current.organization_id
        loaded.status = current.status
        loaded.version = current.version + 1
        loaded.created_at = current.created_at
        loaded.change_history = current.change_history + [{
            "action": "version", "version": loaded.version, "at": _now(),
            "by": actor, "notes": notes}]
        self._workflows[workflow_id] = loaded
        version = WorkflowVersion(
            version_id=uuid.uuid4().hex[:16], workflow_id=workflow_id,
            version=loaded.version, status=loaded.status, notes=notes,
            created_by=actor, created_at=_now(), spec=loaded.to_dict())
        self._versions.setdefault(workflow_id, []).append(version)
        self._flush()
        return version

    def rollback(self, workflow_id: str, version: int,
                 actor: str = "") -> Optional[WorkflowSpec]:
        """Roll back to a previous version (history preserved)."""
        versions = self._versions.get(workflow_id, [])
        target = next((v for v in versions if v.version == version), None)
        current = self.get(workflow_id)
        if not target or not current:
            return None
        spec = WorkflowSpec.from_dict(target.spec)
        spec.workflow_id = workflow_id
        spec.organization_id = current.organization_id
        spec.status = current.status
        spec.version = current.version + 1
        spec.change_history = current.change_history + [{
            "action": "rollback", "to_version": version, "at": _now(),
            "by": actor}]
        self._workflows[workflow_id] = spec
        self._flush()
        return spec

    def versions(self, workflow_id: str, limit: int = 100) -> list[dict]:
        return [v.to_dict() for v in (self._versions.get(workflow_id, []) or [])][-limit:]

    def history(self, workflow_id: str) -> list[dict]:
        spec = self.get(workflow_id)
        return (spec.change_history if spec else [])[-100:]


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def new_workflow_id() -> str:
    return f"wf_{uuid.uuid4().hex[:12]}"


def new_execution_id() -> str:
    return f"ex_{uuid.uuid4().hex[:12]}"