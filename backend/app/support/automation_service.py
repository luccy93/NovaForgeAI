"""Automation service — safe workflow execution, approval gates, audit (Volume 54)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.support.constants import AutomationAction

logger = logging.getLogger(__name__)

HIGH_RISK_ACTIONS = {
    AutomationAction.CLOSE_AFTER_CONFIRMATION.value,
    AutomationAction.SEND_APPROVED_ANSWER.value,
    AutomationAction.CREATE_ISSUE.value,
}


class AutomationService:
    def __init__(self):
        self._runs: dict[str, dict] = {}
        self._telemetry = {"runs": 0, "approved": 0, "denied": 0}

    def create_run(self, ticket_id: str, action: str,
                   input_data: Optional[dict] = None,
                   triggered_by: str = "system") -> dict:
        run_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        approval_required = action in HIGH_RISK_ACTIONS
        run = {
            "id": run_id, "ticket_id": ticket_id, "action": action,
            "status": "pending" if not approval_required else "awaiting_approval",
            "triggered_by": triggered_by, "input_data": input_data or {},
            "output_data": {}, "error_message": None,
            "approval_required": approval_required,
            "approval_status": "pending" if approval_required else None,
            "executed_at": None,
            "created_at": now.isoformat(), "updated_at": now.isoformat(),
        }
        self._runs[run_id] = run
        self._telemetry["runs"] += 1
        return run

    def get_run(self, run_id: str) -> Optional[dict]:
        return self._runs.get(run_id)

    def list_runs(self, ticket_id: Optional[str] = None, action: Optional[str] = None,
                  status: Optional[str] = None, limit: int = 50) -> list[dict]:
        results = list(self._runs.values())
        if ticket_id:
            results = [r for r in results if r["ticket_id"] == ticket_id]
        if action:
            results = [r for r in results if r["action"] == action]
        if status:
            results = [r for r in results if r["status"] == status]
        results.sort(key=lambda r: r["created_at"], reverse=True)
        return results[:limit]

    def approve_run(self, run_id: str, approved: bool, approved_by: str,
                    reason: Optional[str] = None) -> Optional[dict]:
        run = self._runs.get(run_id)
        if not run or not run["approval_required"]:
            return None
        now = datetime.now(timezone.utc)
        run["approval_status"] = "approved" if approved else "denied"
        run["updated_at"] = now.isoformat()
        if approved:
            run["status"] = "ready"
            self._telemetry["approved"] += 1
        else:
            run["status"] = "denied"
            run["error_message"] = reason or "Denied by approver"
            self._telemetry["denied"] += 1
        return run

    def execute_run(self, run_id: str, output_data: Optional[dict] = None) -> Optional[dict]:
        run = self._runs.get(run_id)
        if not run:
            return None
        if run["status"] not in ("pending", "ready"):
            return run
        now = datetime.now(timezone.utc)
        run["status"] = "completed"
        run["output_data"] = output_data or {}
        run["executed_at"] = now.isoformat()
        run["updated_at"] = now.isoformat()
        return run

    def fail_run(self, run_id: str, error_message: str) -> Optional[dict]:
        run = self._runs.get(run_id)
        if not run:
            return None
        run["status"] = "failed"
        run["error_message"] = error_message
        run["updated_at"] = datetime.now(timezone.utc).isoformat()
        return run

    def get_pending_approvals(self) -> list[dict]:
        return [r for r in self._runs.values() if r["status"] == "awaiting_approval"]

    def get_telemetry(self) -> dict:
        return dict(self._telemetry)


automation_service = AutomationService()
