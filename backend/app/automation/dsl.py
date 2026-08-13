"""Workflow DSL (Volume 33): parse declarative definitions and validate.

The DSL is YAML (or dict) shaped like:

    workflow:
      name: production-release
      trigger: {type: pull_request_merged}
      steps:
        - {id: run_tests, type: task, action: test, ...}

Parsing is strongly typed: unknown keys are preserved into step.inputs, and
the validator (`WorkflowValidator`) checks schema, DAG shape, policy fields,
risk classification, timeouts, retries and rollback wiring. AI-generated
workflows must pass this validator before they may run.
"""
import copy, logging, re
from typing import Any, Optional

from .dag import validate_dag
from .workflow import WorkflowSpec, WorkflowStep, RetryPolicy

logger = logging.getLogger(__name__)

STEP_KEYS = {"id", "type", "name", "action", "inputs", "output_key",
             "depends_on", "retry", "timeout_s", "risk", "needs_approval",
             "approval_type", "compensation", "condition", "wait_s",
             "parallel_steps", "subworkflow_id", "permissions", "description"}
TRIGGER_TYPES = ("manual", "schedule", "cron", "webhook", "event", "github",
                 "gitlab", "pull_request", "commit", "issue", "deployment",
                 "security_finding", "incident", "metric_threshold",
                 "ai_decision", "api", "cli", "plugin")
RISK_LEVELS = ("low", "medium", "high")


def parse_workflow(data: Any, organization_id: str = "",
                   workflow_id: str = "") -> WorkflowSpec:
    """Parse a DSL dict (or JSON string) into a WorkflowSpec."""
    if isinstance(data, str):
        import json
        try:
            data = json.loads(data)
        except Exception as exc:
            raise ValueError(f"workflow must be a dict or JSON string: {exc}")
    raw = _coerce(data)
    wf = raw.get("workflow") if isinstance(raw, dict) and "workflow" in raw else raw
    if not isinstance(wf, dict):
        raise ValueError("workflow definition must be a dict or YAML document")
    steps = [_parse_step(s) for s in wf.get("steps", [])]
    spec = WorkflowSpec(
        workflow_id=workflow_id or wf.get("workflow_id") or wf.get("id")
        or _slug(wf.get("name", "workflow")),
        name=wf.get("name", "unnamed workflow"),
        description=wf.get("description", ""),
        organization_id=organization_id,
        trigger=_coerce(wf.get("trigger", {"type": "manual"})),
        steps=steps,
        policies=_coerce(wf.get("policies", {})),
        created_by=wf.get("created_by", ""))
    return spec


def _parse_step(raw: Any) -> WorkflowStep:
    if isinstance(raw, str):
        raw = {"id": raw, "name": raw}
    if not isinstance(raw, dict):
        raise ValueError(f"step must be a dict, got {type(raw).__name__}")
    data = dict(raw)
    step_id = str(data.pop("id", _slug(data.get("name", "step"))))
    for key in data:
        if key not in STEP_KEYS:
            data["inputs"].setdefault(key, data[key]) if isinstance(
                data.get("inputs"), dict) else None
    inputs = _coerce(data.pop("inputs", {}))
    retry = data.pop("retry", None)
    if retry is None:
        retry = RetryPolicy()
    elif isinstance(retry, dict):
        retry = RetryPolicy(**{k: v for k, v in retry.items()
                               if k in RetryPolicy.__dataclass_fields__})
    parallel = data.pop("parallel_steps", [])
    step = WorkflowStep(
        id=step_id,
        type=str(data.pop("type", "task")).lower(),
        name=str(data.pop("name", step_id)),
        action=str(data.pop("action", "")),
        inputs=inputs,
        output_key=str(data.pop("output_key", "")),
        depends_on=[str(d) for d in data.pop("depends_on", [])],
        retry=retry,
        timeout_s=int(data.pop("timeout_s", 300)),
        risk=str(data.pop("risk", "medium")).lower(),
        needs_approval=bool(data.pop("needs_approval", False)),
        approval_type=str(data.pop("approval_type", "single")),
        compensation=str(data.pop("compensation", "")),
        condition=str(data.pop("condition", "")),
        wait_s=float(data.pop("wait_s", 0.0)),
        parallel_steps=[_parse_step(p) for p in parallel],
        subworkflow_id=str(data.pop("subworkflow_id", "")),
        permissions=_coerce(data.pop("permissions", {})),
        description=str(data.pop("description", "")))
    if data:  # extra keys land in inputs (loose tolerance, kept typed)
        for k, v in data.items():
            inputs.setdefault(k, v)
        step.inputs = inputs
    return step


class WorkflowValidator:
    """Schema + DAG + policy-surface validation. Returns issues, never mutates."""

    def __init__(self, policy=None):
        self.policy = policy  # optional AutomationPolicy for policy checks

    def validate(self, spec: WorkflowSpec) -> dict:
        errors: list[str] = []
        warnings: list[str] = []
        if not spec.name:
            errors.append("workflow name required")
        if not spec.organization_id:
            warnings.append("organization_id empty (tenant isolation required in production)")
        if not spec.steps:
            errors.append("workflow has no steps")
        trigger = spec.trigger or {}
        if trigger.get("type") not in TRIGGER_TYPES:
            errors.append(f"unknown trigger type '{trigger.get('type')}'")
        if trigger.get("type") in ("schedule", "cron") and not trigger.get("cron"):
            errors.append("schedule trigger requires a cron expression")
        errors.extend(validate_dag(spec))
        for step in spec.flat_steps():
            if step.risk not in RISK_LEVELS:
                errors.append(f"step '{step.id}': risk must be low|medium|high")
            if step.timeout_s <= 0:
                errors.append(f"step '{step.id}': timeout_s must be positive")
            if step.retry.max_retries < 0 or step.retry.max_retries > 20:
                errors.append(f"step '{step.id}': retries out of range")
            if step.needs_approval and step.risk == "low":
                warnings.append(f"step '{step.id}': low-risk step marked for approval")
            if step.risk == "high" and not step.needs_approval:
                warnings.append(
                    f"step '{step.id}': high-risk action without explicit approval "
                    "(policy may require it anyway)")
            if step.compensation and step.compensation not in {
                    s.id for s in spec.flat_steps()} and step.compensation != "rollback":
                errors.append(f"step '{step.id}': unknown compensation '{step.compensation}'")
        policy_issues = self._policy_check(spec)
        errors.extend(policy_issues)
        return {"valid": not errors, "errors": errors, "warnings": warnings,
                "workflow_id": spec.workflow_id, "version": spec.version}

    def _policy_check(self, spec: WorkflowSpec) -> list[str]:
        if self.policy is None:
            return []
        issues = []
        allowed_tools = (spec.policies or {}).get("allowed_tools")
        for step in spec.flat_steps():
            if step.type == "tool" and allowed_tools and \
                    step.action not in allowed_tools:
                issues.append(f"step '{step.id}': tool '{step.action}' not allowed by policy")
        domains = (spec.policies or {}).get("allowed_domains")
        if domains:
            for step in spec.flat_steps():
                url = (step.inputs or {}).get("url", "")
                if url and not any(url.startswith(d) for d in domains):
                    issues.append(f"step '{step.id}': domain {url} not allowed")
        return issues


# ------------------------------------------------------------------ utils
def _coerce(value: Any) -> Any:
    return value if value is not None else {}


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", text.lower()).strip("_")
    return slug or "workflow"