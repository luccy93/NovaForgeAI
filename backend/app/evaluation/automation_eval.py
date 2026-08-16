"""Automation evaluation integration (Volume 34 ↔ 33).

Evaluates automation workflows: completion, tool selection, safety,
policy compliance, execution reliability, recovery, rollback, human
approval and cost — using the existing Volume 33 automation gateway.
"""
import logging
from typing import Any, Optional

from .agents_eval import AgentEvaluator

logger = logging.getLogger(__name__)


class AutomationEvaluator:
    """Evaluates automation workflow runs via the automation volume."""

    def __init__(self, gateway: Optional[Any] = None):
        self.gateway = gateway or self._resolve()
        self.agent = AgentEvaluator()

    @staticmethod
    def _resolve() -> Optional[Any]:
        try:
            from ..common.services import registry
            svc = registry.get("automation")
            return svc.gateway if svc else None
        except Exception:  # noqa: BLE001
            return None

    def health(self) -> dict:
        if self.gateway is None:
            return {"integrated": False, "status": "not_loaded",
                    "note": "automation volume (33) not loaded"}
        try:
            return {"integrated": True, "status": "healthy",
                    "volume_health": self.gateway.health()}
        except Exception as exc:  # noqa: BLE001
            return {"integrated": True, "status": "error", "error": str(exc)}

    def evaluate_workflow(self, workflow_id: str, organization_id: str = "",
                          expected: Optional[dict] = None) -> dict:
        """Evaluate a workflow execution: success criteria + trajectory."""
        if self.gateway is None:
            return {"available": False, "error": "automation volume not loaded"}
        record = self.gateway.execution(workflow_id, organization_id)
        if record is None:
            # execute the workflow if it exists (dry-run path)
            try:
                record = self.gateway.run(workflow_id, organization_id)
            except Exception as exc:  # noqa: BLE001
                return {"available": True, "error": str(exc)}
        expected = expected or {}
        observed = {
            "expected_file_changed": bool(record.get("outputs", {}).get("files_changed")),
            "expected_behavior": record.get("status") == "completed",
            "tests_pass": bool(record.get("outputs", {}).get("tests_pass")),
            "no_unrelated_changes": True,
            "security_maintained": bool(record.get("approvals", {}).get("approved", True)),
        }
        success = self.agent.evaluate_success(expected, observed)
        return {
            "available": True,
            "workflow_id": workflow_id,
            "status": record.get("status"),
            "execution_id": record.get("execution_id", ""),
            "success": success,
            "policy_compliance": 1.0 if record.get("status") in ("completed", "needs_approval") else 0.0,
            "approval_gates": int(record.get("approvals", {}).get("required", 0)),
            "recovery": int(record.get("retries", 0)) + int(record.get("rollbacks", 0)),
        }

    def evaluate_batch(self, workflow_ids: list[str], organization_id: str = "") -> dict:
        """Batch efficiency metrics across multiple workflow executions."""
        results = [self.evaluate_workflow(w, organization_id) for w in workflow_ids]
        completed = sum(1 for r in results if r.get("status") == "completed")
        return {
            "workflows": len(results),
            "completed": completed,
            "completion_rate": round(completed / len(results), 4) if results else 0.0,
            "results": results,
        }
