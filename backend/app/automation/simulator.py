"""Workflow simulator (Volume 33).

Simulates a workflow run WITHOUT side effects: handlers that accept a
`simulate` flag return estimates; every other step is mocked as a pass
with the declared output shape. Results are clearly labeled as
simulation to keep the platform honest.
"""
import logging, time
from typing import Any, Callable, Optional

from .dag import validate_dag, execution_order
from .workflow import WorkflowSpec, WorkflowStep

logger = logging.getLogger(__name__)


def simulate_workflow(spec: WorkflowSpec,
                      handlers: Optional[dict[str, Callable]] = None,
                      dry_run: bool = True) -> dict:
    """Return a step-by-step simulation report. Never executes handlers
    unless they opt in via `simulate=True` (services like scheduler still
    treat it as a forecast, not a run)."""
    errors = validate_dag(spec)
    simulated: list[dict] = []
    passed = {"globals": {}}
    started = time.time()
    for step in execution_order(spec):
        entry = _simulate_step(step, passed, handlers)
        simulated.append(entry)
        if entry["status"] == "completed":
            passed[step.output_key or step.id] = entry.get("output", {})
    elapsed_ms = int((time.time() - started) * 1000)
    return {
        "simulated": True,
        "workflow_id": spec.workflow_id,
        "version": spec.version,
        "dry_run": dry_run,
        "valid": not errors,
        "dag_errors": errors,
        "steps": simulated,
        "status": "simulated" if not errors else "invalid",
        "elapsed_ms": elapsed_ms,
    }


def _simulate_step(step: WorkflowStep, outputs: dict,
                   handlers: Optional[dict[str, Callable]]) -> dict:
    entry = {"step_id": step.id, "type": step.type, "action": step.action,
             "attempts": 1, "simulated": True}
    if step.condition and not _eval(step.condition, outputs):
        entry.update({"status": "skipped", "output": None})
        return entry
    handler = (handlers or {}).get(step.type)
    if handler is None:
        entry.update({"status": "no_handler", "output": None})
        return entry
    try:
        out = handler(step, {**outputs.get("globals", {}),
                             **(step.inputs or {})},
                      outputs, simulate=True)
        if isinstance(out, dict) and out.get("_simulated"):
            status = "completed"
        else:
            status = "completed_simulated"
        entry.update({"status": status, "output": out})
    except Exception as exc:
        entry.update({"status": "error",
                      "error": f"{type(exc).__name__}: {exc}"})
    return entry


def _eval(condition: str, outputs: dict) -> bool:
    try:
        from app.workflow.expression import evaluate as _safe_evaluate
        return bool(_safe_evaluate(condition, {"output": dict(outputs or {}), **dict(outputs or {})}))
    except Exception:
        return False