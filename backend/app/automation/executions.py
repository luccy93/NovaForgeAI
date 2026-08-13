"""Execution records (Volume 33).

Every workflow run has an execution_id and a persisted, tenant-scoped
record with status transitions, per-step results, timing and audit trail.
"""
import logging, time
from dataclasses import dataclass, field
from typing import Any, Optional

from ..common.storage import JsonFileStorage
from .workflow import EXECUTION_STATUS

logger = logging.getLogger(__name__)


@dataclass
class StepResult:
    step_id: str
    status: str
    started_at: str = ""
    finished_at: str = ""
    error: str = ""
    output: Any = None
    attempts: int = 1

    def to_dict(self) -> dict:
        return {"step_id": self.step_id, "status": self.status,
                "started_at": self.started_at, "finished_at": self.finished_at,
                "error": self.error, "output": self.output,
                "attempts": self.attempts}


@dataclass
class ExecutionRecord:
    execution_id: str
    workflow_id: str
    organization_id: str = ""
    status: str = "queued"
    created_at: str = field(default_factory=lambda: time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    started_at: str = ""
    finished_at: str = ""
    version: int = 1
    trigger: dict = field(default_factory=dict)
    inputs: dict = field(default_factory=dict)
    steps: dict[str, StepResult] = field(default_factory=dict)
    error: str = ""
    output: dict = field(default_factory=dict)
    total_ms: int = 0
    attempts: int = 1

    def to_dict(self) -> dict:
        return {"execution_id": self.execution_id,
                "workflow_id": self.workflow_id,
                "organization_id": self.organization_id,
                "status": self.status,
                "created_at": self.created_at,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "version": self.version,
                "trigger": self.trigger,
                "inputs": self.inputs,
                "steps": {k: v.to_dict() for k, v in self.steps.items()},
                "error": self.error,
                "output": self.output,
                "total_ms": self.total_ms,
                "attempts": self.attempts}


class ExecutionStore:
    """JSON-persisted execution records. Keys are tenant-scoped."""

    def __init__(self, storage: Optional[JsonFileStorage] = None):
        self._storage = storage or JsonFileStorage(
            "data/automation/executions.json")

    def save(self, rec: ExecutionRecord) -> None:
        self._storage.set(record_key(rec.execution_id, rec.organization_id),
                          rec.to_dict())

    def get(self, execution_id: str, organization_id: str = "") -> Optional[ExecutionRecord]:
        raw = self._storage.get(record_key(execution_id, organization_id))
        if not raw:
            return None
        raw = dict(raw)
        raw["steps"] = {k: StepResult(**v) for k, v in raw.get("steps", {}).items()}
        return ExecutionRecord(**raw)

    def list(self, organization_id: str = "",
             limit: int = 50, status: str = "") -> list[dict]:
        prefix = f"{organization_id or 'default'}:"
        rows = [v for k, v in self._storage.get_all().items()
                if k.startswith(prefix)]
        if status:
            rows = [r for r in rows if r.get("status") == status]
        rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return rows[:limit]

    def count(self) -> int:
        return len(self._storage.get_all())


class ExecutionTracker:
    """Mutates a persisted ExecutionRecord through its lifecycle."""

    def __init__(self, store: ExecutionStore, record: ExecutionRecord):
        self.store = store
        self.record = record

    @classmethod
    def begin(cls, store: ExecutionStore, workflow_id: str,
              organization_id: str = "", version: int = 1,
              trigger: dict | None = None, inputs: dict | None = None,
              execution_id: str = "") -> "ExecutionTracker":
        rec = ExecutionRecord(
            execution_id=execution_id or new_execution_id(workflow_id),
            workflow_id=workflow_id, organization_id=organization_id,
            status="queued", version=version, trigger=trigger or {},
            inputs=inputs or {})
        store.save(rec)
        return cls(store, rec)

    def start(self) -> None:
        self.record.status = "running"
        self.record.started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                               time.gmtime())
        self.store.save(self.record)

    def finish(self, status: str, output: dict | None = None,
               error: str = "") -> None:
        self.record.status = status
        self.record.output = output or {}
        self.record.error = error
        self.record.finished_at = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                time.gmtime())
        self.store.save(self.record)

    def record_step(self, result: StepResult) -> None:
        self.record.steps[result.step_id] = result
        self.store.save(self.record)

    def update_status(self, status: str) -> None:
        self.record.status = status
        self.store.save(self.record)

    def to_dict(self) -> dict:
        return self.record.to_dict()


def record_key(execution_id: str, organization_id: str) -> str:
    return f"{organization_id or 'default'}:{execution_id}"


def new_execution_id(workflow_id: str) -> str:
    import uuid
    return f"exec_{workflow_id}_{uuid.uuid4().hex[:8]}"