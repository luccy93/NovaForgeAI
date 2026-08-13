"""Compensation actions (Volume 33).

When a workflow fails after side effects, compensation steps roll back:
tool_id + inputs driven rollback plan. The engine invokes compensation on
failed executions for steps that declare one.
"""
import logging, time
from typing import Any, Optional

from ..common.storage import JsonFileStorage
from .workflow import WorkflowSpec

logger = logging.getLogger(__name__)

ROLLBACK_TOOL = "rollback_signal"


class CompensationError(Exception):
    pass


class CompensationStore:
    """Persists executed compensation actions (tenant-scoped by key)."""

    def __init__(self, storage: Optional[JsonFileStorage] = None):
        self._storage = storage or JsonFileStorage(
            "data/automation/compensations.json")

    def record(self, execution_id: str, step_id: str, tool_id: str,
               inputs: dict, status: str = "queued",
               error: str = "") -> dict:
        entry = {
            "execution_id": execution_id,
            "step_id": step_id,
            "compensating_tool": tool_id,
            "inputs": inputs,
            "status": status,
            "error": error,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self._storage.set(f"{execution_id}:{step_id}", entry)
        return entry

    def update(self, execution_id: str, step_id: str, status: str,
               error: str = "") -> None:
        key = f"{execution_id}:{step_id}"
        raw = self._storage.get(key) or {}
        raw.update({"status": status, "error": error})
        self._storage.set(key, raw)

    def list(self, execution_id: str) -> list[dict]:
        prefix = f"{execution_id}:"
        return [v for k, v in self._storage.get_all().items()
                if k.startswith(prefix)]

    def count(self) -> int:
        return len(self._storage.get_all())


def compensation_plan(spec: WorkflowSpec, failed_step_id: str,
                      completed_step_ids: list[str]) -> list[dict]:
    """Build a rollback plan for a failed step.

    - Steps that declare compensation run their compensation action.
    - Steps without compensation are reported so the operator can decide.
    - Rollback order: reverse completion order.
    """
    by_id = {s.id: s for s in spec.flat_steps()}
    if failed_step_id not in by_id:
        raise CompensationError(f"unknown step '{failed_step_id}'")
    plan = []
    for step_id in reversed(completed_step_ids):
        if step_id == failed_step_id:
            continue
        step = by_id.get(step_id)
        if step is None:
            continue
        if step.compensation:
            plan.append({"step_id": step_id, "type": "compensate",
                         "action": step.compensation,
                         "tool_id": step.action or "rollback_signal",
                         "inputs": step.inputs or {}})
        else:
            plan.append({"step_id": step_id, "type": "notify",
                         "action": "operator_review",
                         "note": "no compensation declared"})
    return plan


def run_compensation(existing_compensations: dict, plan: list[dict],
                     handlers: dict) -> list[dict]:
    """Execute compensation actions via handler map (tool_id -> callable).

    Returns a per-action result list with status/error; never raises.
    """
    results = []
    for action in plan:
        tool_id = action.get("tool_id", "")
        if action.get("type") == "notify":
            results.append({**action, "status": "notified",
                            "handled": True})
            continue
        handler = handlers.get(tool_id)
        if handler is None:
            results.append({**action, "status": "unhandled",
                            "error": f"no handler for '{tool_id}'"})
            continue
        try:
            outcome = handler(action.get("inputs") or {})
            results.append({**action, "status": "completed",
                            "outcome": outcome})
        except Exception as exc:
            results.append({**action, "status": "failed",
                            "error": f"{type(exc).__name__}: {exc}"})
    return results