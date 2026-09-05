"""Workflow execution engine (Volume 33).

Lifecycle: validate -> policy gate -> approvals -> execute steps in DAG
order with retries/timeouts -> checkpoint each step -> on failure run
compensation. Every run is persisted via ExecutionStore. Dry-run mode
produces an honest simulation report without executing anything.
"""
import logging, threading, time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ..common.storage import JsonFileStorage
from .checkpoint import CheckpointStore, build_resume_plan
from .compensation import CompensationStore, compensation_plan, run_compensation
from .dag import execution_order, ready_steps, validate_dag
from .executions import (ExecutionRecord, ExecutionStore, ExecutionTracker,
                         StepResult)
from .retry import run_with_retry, is_transient
from .workflow import (EXECUTION_STATUS, WorkflowSpec,
                       WorkflowStep)

logger = logging.getLogger(__name__)

StepHandler = Callable[[WorkflowStep, dict, dict], dict]
"""handler(step, inputs, outputs_so_far) -> step output dict"""


@dataclass
class EngineConfig:
    default_timeout_s: int = 300
    max_retries: int = 0
    backoff_s: float = 1.0
    max_backoff_s: float = 60.0
    checkpoint_enabled: bool = True
    approvals_enabled: bool = True
    dry_run: bool = False
    records_dir: str = "data/automation/executions.json"
    checkpoints_dir: str = "data/automation/checkpoints.json"
    approvals_dir: str = "data/automation/approvals.json"
    compensations_dir: str = "data/automation/compensations.json"
    max_parallel: int = 4


class WorkflowEngine:
    def __init__(self, handlers: Optional[dict[str, StepHandler]] = None,
                 approvals=None, policy=None, config: Optional[EngineConfig] = None):
        self.handlers = handlers or {}
        self.config = config or EngineConfig()
        self.executions = ExecutionStore(JsonFileStorage(self.config.records_dir))
        self.checkpoints = CheckpointStore(
            JsonFileStorage(self.config.checkpoints_dir))
        self.approvals = approvals or ApprovalStore(
            JsonFileStorage(self.config.approvals_dir))
        self.compensations = CompensationStore(
            JsonFileStorage(self.config.compensations_dir))
        self.policy = policy  # AutomationPolicy: authorize(step, ctx)
        self._lock = threading.RLock()

    def register_handler(self, step_type: str, handler: StepHandler) -> None:
        self.handlers[step_type] = handler

    # ------------------------------------------------------------------
    def run(self, spec: WorkflowSpec, inputs: dict | None = None,
            organization_id: str = "", execution_id: str = "",
            resume: bool = False, trigger: dict | None = None) -> dict:
        """Execute a workflow and return its persisted execution record."""
        if spec.organization_id:
            organization_id = organization_id or spec.organization_id
        errors = validate_dag(spec)
        if errors:
            raise ValueError(f"workflow invalid: {'; '.join(errors)}")

        tracker = ExecutionTracker.begin(
            self.executions, spec.workflow_id, organization_id,
            version=spec.version, trigger=trigger or {},
            inputs=inputs or {}, execution_id=execution_id)
        exec_id = tracker.record.execution_id

        if self.config.dry_run:
            tracker.start()
            tracker.finish("dry_run", output=self._dry_run_report(spec))
            return tracker.to_dict()

        if self.config.approvals_enabled and not self._gates_cleared(spec,
                                                                     organization_id):
            self._ensure_requests(spec, organization_id, exec_id)
            tracker.update_status("awaiting_approval")
            return tracker.to_dict()

        tracker.start()
        completed: set[str] = set()
        outputs: dict[str, Any] = {}
        if resume:
            checkpoint = self.checkpoints.resume_point(
                exec_id, [s.id for s in spec.flat_steps()])
            if checkpoint is not None:
                completed.add(checkpoint.step_id)
                outputs.update(checkpoint.outputs or {})
            plan = build_resume_plan(
                exec_id, [s.id for s in spec.flat_steps()], checkpoint)
            if not plan:
                tracker.finish("completed",
                               output=self._collect_outputs(spec, outputs))
                return tracker.to_dict()
            ordered = plan
        else:
            ordered = [s.id for s in execution_order(spec)]

        status = "completed"
        error = ""
        try:
            self._execute_ordered(spec, ordered, outputs, completed,
                                  tracker, organization_id)
        except StepFailure as exc:
            status = "failed"
            error = str(exc)
            self._trigger_compensation(spec, exc.step_id,
                                       list(completed), tracker,
                                       organization_id)
        finally:
            elapsed_ms = int((time.time() - self._started) * 1000) \
                if hasattr(self, "_started") else 0
            tracker.record.total_ms = elapsed_ms
            tracker.finish(status, output=self._collect_outputs(spec, outputs),
                           error=error)
        return tracker.to_dict()

    def _execute_ordered(self, spec, ordered, outputs, completed,
                         tracker, organization_id) -> None:
        self._started = time.time()
        for step_id in ordered:
            step = next(s for s in spec.flat_steps() if s.id == step_id)
            result = self._run_step(step, outputs, organization_id,
                                    tracker, spec)
            if result.status == "succeeded":
                completed.add(step_id)
                outputs[step.output_key or step.id] = result.output
                if self.config.checkpoint_enabled:
                    self.checkpoints.save(
                        tracker.record.execution_id, step_id,
                        {step.output_key or step.id: result.output},
                        sequence=len(completed))
            elif result.status == "failed":
                raise StepFailure(step.id, result.error or "step failed")

    def _run_step(self, step: WorkflowStep, outputs: dict,
                  organization_id: str, tracker: ExecutionTracker,
                  spec: WorkflowSpec) -> StepResult:
        if step.condition and not self._eval_condition(step.condition, outputs):
            return StepResult(step_id=step.id, status="skipped")

        if self.config.approvals_enabled:
            required = step.needs_approval or (
                self.policy is not None and
                self.policy.requires_approval(step, organization_id))
            if required:
                request = self.approvals.get(spec.workflow_id, step.id,
                                             organization_id)
                if request is None or request.decision not in (
                        "approved", "auto_approved"):
                    raise StepFailure(step.id, "awaiting human approval")

        inputs = {**outputs.get("globals", {}), **(step.inputs or {}),
                  "execution_id": tracker.record.execution_id}
        handler = self.handlers.get(step.type)
        if handler is None:
            return StepResult(step_id=step.id, status="failed",
                              error=f"no handler for step type '{step.type}'")

        started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        timeout = step.timeout_s or self.config.default_timeout_s

        def invoke() -> dict:
            if timeout > 0:
                return _call_with_timeout(
                    handler, step, inputs, outputs, timeout_s=timeout)
            return handler(step, inputs, outputs)

        value, outcome = run_with_retry(
            step.id, invoke,
            max_retries=step.retry.max_retries if step.retry else
            self.config.max_retries,
            backoff_s=step.retry.backoff_s if step.retry else self.config.backoff_s,
            max_backoff_s=self.config.max_backoff_s,
            retryable=is_transient if step.retry.retry_on else None,
            seed=hash(step.id) % (2 ** 32))
        finished = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        if outcome.succeeded:
            result = StepResult(step_id=step.id, status="succeeded",
                                started_at=started, finished_at=finished,
                                output=value, attempts=outcome.attempts)
        else:
            result = StepResult(step_id=step.id, status="failed",
                                started_at=started, finished_at=finished,
                                error=outcome.error, attempts=outcome.attempts)
        tracker.record_step(result)
        return result

    # ------------------------------------------------------------------
    def _ensure_requests(self, spec, organization_id, execution_id="") -> None:
        """Create pending approval requests for gating steps that have no
        record yet, so humans can act on them."""
        for step in spec.flat_steps():
            required = step.needs_approval or (
                self.policy is not None and
                self.policy.requires_approval(step, organization_id))
            if not required:
                continue
            if steps_pending(self.approvals, spec.workflow_id, step.id,
                             organization_id):
                continue
            try:
                self.approvals.create(spec.workflow_id, step.id,
                                      organization_id=organization_id,
                                      execution_id=execution_id)
                logger.info("approval request created for %s/%s",
                            spec.workflow_id, step.id)
            except Exception as exc:
                logger.warning("approval request creation failed: %s", exc)

    def _gates_cleared(self, spec: WorkflowSpec, organization_id: str) -> bool:
        for step in spec.flat_steps():
            required = step.needs_approval or (
                self.policy is not None and
                self.policy.requires_approval(step, organization_id))
            if not required:
                continue
            request = self.approvals.get(spec.workflow_id, step.id,
                                         organization_id)
            if request is None or request.decision not in ("approved",
                                                           "auto_approved"):
                logger.info("workflow %s awaits approval for step %s",
                            spec.workflow_id, step.id)
                return False
        return True

    def _trigger_compensation(self, spec, failed_step_id, completed,
                              tracker, organization_id) -> None:
        try:
            plan = compensation_plan(spec, failed_step_id, completed)
        except Exception as exc:
            logger.warning("compensation plan failed: %s", exc)
            return
        handlers: dict[str, Any] = {}
        for step_type, handler in self.handlers.items():
            handlers.setdefault(step_type, handler)
        for step in spec.flat_steps():
            handler = self.handlers.get(step.type)
            if handler is not None and step.action:
                handlers.setdefault(step.action, handler)
        if "rollback_signal" not in handlers:
            handlers["rollback_signal"] = lambda inputs: {
                "note": "rollback signal recorded; no runtime attached"}
        results = run_compensation({}, plan, handlers)
        for result in results:
            self.compensations.record(
                tracker.record.execution_id, result["step_id"],
                result.get("tool_id", "notify"), result.get("inputs") or {},
                status=result["status"], error=result.get("error", ""))

    def _eval_condition(self, condition: str, outputs: dict) -> bool:
        ctx = {k: (v if not isinstance(v, dict) else v.get("value", v))
               for k, v in outputs.items()}
        try:
            from app.workflow.expression import evaluate as _safe_evaluate
            return bool(_safe_evaluate(condition, {"output": ctx, **ctx}))
        except Exception:
            return False

    def _collect_outputs(self, spec, outputs) -> dict:
        collected = {}
        for step in spec.flat_steps():
            key = step.output_key or step.id
            if key in outputs:
                collected[key] = outputs[key]
        return collected

    def _dry_run_report(self, spec) -> dict:
        from .simulator import simulate_workflow
        return simulate_workflow(spec, self.handlers, dry_run=True)

    # ------------------------------------------------------------------
    def health(self) -> dict:
        return {"executions": self.executions.count(),
                "checkpoints": self.checkpoints.count(),
                "approvals": self.approvals.count() if self.approvals else 0,
                "pending_approvals": self.approvals.pending_count()
                if self.approvals else 0,
                "compensations": self.compensations.count(),
                "handlers": sorted(self.handlers.keys()),
                "dry_run": self.config.dry_run,
                "status": "healthy"}


class StepFailure(Exception):
    def __init__(self, step_id: str, message: str):
        super().__init__(message)
        self.step_id = step_id


def _call_with_timeout(fn, *args, timeout_s: int, **kwargs):
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(fn, *args, **kwargs)
        return future.result(timeout=timeout_s)


def steps_pending(approval_store, workflow_id: str, step_id: str,
                  organization_id: str) -> bool:
    """True if an approved/auto-approved record already exists."""
    req = approval_store.get(workflow_id, step_id, organization_id)
    if req is None:
        return False
    if approval_store.is_expired(req):
        return False
    return req.decision in ("approved", "auto_approved")


from .approvals import ApprovalStore  # noqa: E402  (local import to avoid cycle)