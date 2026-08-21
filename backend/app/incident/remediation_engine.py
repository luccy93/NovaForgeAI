"""Incident Response Platform -- Remediation Engine (Volume 49).

Remediation pipeline: diagnose → propose → dry-run → approve → execute → verify → rollback.
Requires approval for non-safe actions. Supports dry-run.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.incident.constants import (
    ACTION_TRANSITIONS, ACTION_PROPOSED, ACTION_APPROVED, ACTION_EXECUTING,
    ACTION_SUCCEEDED, ACTION_FAILED, ACTION_ROLLED_BACK, ACTION_REJECTED,
    AUTO_EXECUTABLE_RISKS,
)


def validate_action_transition(current: str, target: str) -> bool:
    return target in ACTION_TRANSITIONS.get(current, ())


class RemediationEngine:
    """Remediation pipeline with approval workflow and dry-run."""

    def __init__(self, require_approval_above: str = "moderate",
                 dry_run_default: bool = True):
        self._actions: dict[str, dict[str, Any]] = {}
        self._require_approval_above = require_approval_above
        self._dry_run_default = dry_run_default

    def propose(self, incident_id: str, action_type: str, description: str = "",
                risk_level: str = "moderate", approval_required: bool = True,
                runbook_id: str = "", metadata: dict | None = None) -> dict[str, Any]:
        action_id = str(uuid4())
        if risk_level in AUTO_EXECUTABLE_RISKS and not approval_required:
            effective_approval = False
        else:
            effective_approval = approval_required

        action = {
            "id": action_id,
            "incident_id": incident_id,
            "action_type": action_type,
            "description": description,
            "risk_level": risk_level,
            "status": ACTION_PROPOSED,
            "approval_required": effective_approval,
            "approver": "",
            "dry_run_result": {},
            "execution_result": {},
            "rollback_result": {},
            "runbook_id": runbook_id,
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._actions[action_id] = action
        return action

    def approve(self, action_id: str, approver: str = "user") -> dict[str, Any]:
        action = self._actions.get(action_id)
        if not action:
            raise ValueError(f"Action {action_id} not found")
        if not validate_action_transition(action["status"], ACTION_APPROVED):
            raise ValueError(f"Cannot approve action in status: {action['status']}")
        action["status"] = ACTION_APPROVED
        action["approver"] = approver
        action["approved_at"] = datetime.now(timezone.utc).isoformat()
        return action

    def reject(self, action_id: str, approver: str = "user",
               reason: str = "") -> dict[str, Any]:
        action = self._actions.get(action_id)
        if not action:
            raise ValueError(f"Action {action_id} not found")
        if not validate_action_transition(action["status"], ACTION_REJECTED):
            raise ValueError(f"Cannot reject action in status: {action['status']}")
        action["status"] = ACTION_REJECTED
        action["approver"] = approver
        action["metadata"]["rejection_reason"] = reason
        return action

    def execute(self, action_id: str, dry_run: bool = False) -> dict[str, Any]:
        action = self._actions.get(action_id)
        if not action:
            raise ValueError(f"Action {action_id} not found")
        if action["approval_required"] and action["status"] != ACTION_APPROVED:
            raise ValueError(f"Action requires approval before execution, current status: {action['status']}")
        if not validate_action_transition(action["status"], ACTION_EXECUTING):
            raise ValueError(f"Cannot execute action in status: {action['status']}")

        action["status"] = ACTION_EXECUTING
        action["executed_at"] = datetime.now(timezone.utc).isoformat()

        if dry_run:
            action["dry_run_result"] = {
                "dry_run": True,
                "would_succeed": True,
                "changes_preview": f"Would execute {action['action_type']}: {action['description']}",
                "executed_at": datetime.now(timezone.utc).isoformat(),
            }
            action["status"] = ACTION_APPROVED
            return action

        action["execution_result"] = {
            "dry_run": False,
            "success": True,
            "message": f"Executed {action['action_type']}",
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }
        action["status"] = ACTION_SUCCEEDED
        action["completed_at"] = datetime.now(timezone.utc).isoformat()
        return action

    def rollback(self, action_id: str, reason: str = "") -> dict[str, Any]:
        action = self._actions.get(action_id)
        if not action:
            raise ValueError(f"Action {action_id} not found")
        if action["status"] not in (ACTION_FAILED, ACTION_SUCCEEDED):
            raise ValueError(f"Can only rollback from failed/succeeded, current: {action['status']}")

        action["status"] = ACTION_ROLLED_BACK
        action["rollback_result"] = {
            "success": True,
            "reason": reason,
            "rolled_back_at": datetime.now(timezone.utc).isoformat(),
        }
        return action

    def mark_failed(self, action_id: str, error: str = "") -> dict[str, Any]:
        action = self._actions.get(action_id)
        if not action:
            raise ValueError(f"Action {action_id} not found")
        if action["status"] != ACTION_EXECUTING:
            raise ValueError(f"Can only fail from executing, current: {action['status']}")
        action["status"] = ACTION_FAILED
        action["execution_result"]["success"] = False
        action["execution_result"]["error"] = error
        return action

    def get(self, action_id: str) -> dict[str, Any] | None:
        return self._actions.get(action_id)

    def list_actions(self, incident_id: str = "", status: str = "",
                     limit: int = 50) -> list[dict[str, Any]]:
        results = []
        for action in self._actions.values():
            if incident_id and action.get("incident_id") != incident_id:
                continue
            if status and action.get("status") != status:
                continue
            results.append(action)
        return results[:limit]

    def get_pending_approvals(self) -> list[dict[str, Any]]:
        return [a for a in self._actions.values()
                if a["status"] == ACTION_PROPOSED and a["approval_required"]]
