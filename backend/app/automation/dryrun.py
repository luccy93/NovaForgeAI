"""Dry-run validation (Volume 33).

A dry run reports exactly what WOULD execute: step plan, DAG order,
policy decisions, approval requirements, estimated cost and side-effect
surface — without executing anything. AI-generated workflows MUST pass a
dry run before they are scheduled.
"""
import logging, time
from typing import Any, Optional

from .automation_policy import AutomationPolicy
from .dag import validate_dag, execution_order
from .workflow import WorkflowSpec

logger = logging.getLogger(__name__)


class DryRunReport:
    def __init__(self, spec: WorkflowSpec, policy: Optional[AutomationPolicy],
                 organization_id: str = ""):
        self.spec = spec
        self.policy = policy
        self.organization_id = organization_id
        self.run_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def build(self) -> dict:
        errors = validate_dag(self.spec)
        steps = []
        denied = []
        approvals = []
        for step in self.spec.flat_steps():
            entry = {"step_id": step.id, "type": step.type,
                     "action": step.action, "risk": step.risk,
                     "timeout_s": step.timeout_s,
                     "needs_approval": step.needs_approval}
            if self.policy is not None:
                allowed, reason = self.policy.authorize(step,
                                                        self.organization_id)
                entry["policy"] = {"allowed": allowed, "reason": reason}
                if not allowed:
                    denied.append({"step_id": step.id, "reason": reason})
                if self.policy.requires_approval(step, self.organization_id):
                    approvals.append(step.id)
            steps.append(entry)

        order = []
        if not errors:
            order = [s.id for s in execution_order(self.spec)]

        est = self._estimate()
        return {
            "dry_run": True,
            "executed": False,
            "run_at": self.run_at,
            "workflow_id": self.spec.workflow_id,
            "version": self.spec.version,
            "valid": not errors,
            "dag_errors": errors,
            "steps": steps,
            "execution_order": order,
            "approvals_required": approvals,
            "denied_steps": denied,
            "estimated": est,
            "verdict": "approved_for_dry_run" if not errors and not denied
            else "rejected",
        }

    def _estimate(self) -> dict:
        seconds = 0
        for step in self.spec.flat_steps():
            seconds += min(step.timeout_s or 300, 120)
        return {"estimated_seconds": seconds,
                "estimated_cost_usd": round(0.001 * seconds, 4),
                "side_effects": [s.id for s in self.spec.flat_steps()
                                 if s.type in ("tool", "terminal", "browser",
                                               "infra", "deploy")],
                "disclaimer": "estimates only; nothing was executed"}


def validate_before_run(spec: WorkflowSpec,
                        policy: Optional[AutomationPolicy] = None,
                        organization_id: str = "") -> dict:
    """Dry-run gate used by the gateway and AI-generated workflow path."""
    return DryRunReport(spec, policy, organization_id).build()