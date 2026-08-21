"""Incident Response Platform -- Runbook Engine (Volume 49).

Versioned runbooks, matching to incidents, auto-execution of safe runbooks,
approval for high-risk.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.incident.constants import AUTO_EXECUTABLE_RISKS


class RunbookEngine:
    """Versioned runbook management and execution."""

    def __init__(self):
        self._runbooks: dict[str, dict[str, Any]] = {}

    def create(self, tenant: str, name: str, incident_type: str = "",
               description: str = "", steps: list | None = None,
               permissions: list | None = None, risk_level: str = "moderate",
               auto_executable: bool = False, enabled: bool = True) -> dict[str, Any]:
        runbook_id = str(uuid4())
        runbook = {
            "id": runbook_id,
            "tenant": tenant,
            "name": name,
            "version": "1.0",
            "incident_type": incident_type,
            "description": description,
            "steps": steps or [],
            "permissions": permissions or [],
            "risk_level": risk_level,
            "auto_executable": auto_executable,
            "enabled": enabled,
            "execution_count": 0,
            "last_executed": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._runbooks[runbook_id] = runbook
        return runbook

    def get(self, runbook_id: str) -> dict[str, Any] | None:
        return self._runbooks.get(runbook_id)

    def list_runbooks(self, tenant: str = "", incident_type: str = "",
                      enabled_only: bool = True) -> list[dict[str, Any]]:
        results = []
        for rb in self._runbooks.values():
            if tenant and rb.get("tenant") != tenant:
                continue
            if incident_type and rb.get("incident_type") != incident_type:
                continue
            if enabled_only and not rb.get("enabled"):
                continue
            results.append(rb)
        return results

    def match_runbook(self, incident: dict, tenant: str = "") -> dict[str, Any] | None:
        incident_type = incident.get("incident_type", "")
        service = incident.get("service", "")
        candidates = self.list_runbooks(tenant=tenant, incident_type=incident_type)
        if candidates:
            return candidates[0]
        candidates = self.list_runbooks(tenant=tenant)
        for rb in candidates:
            if any(kw.lower() in incident.get("title", "").lower()
                   for kw in [rb.get("name", "")]):
                return rb
        return None

    def execute_runbook(self, runbook_id: str, incident_id: str,
                        dry_run: bool = True) -> dict[str, Any]:
        runbook = self._runbooks.get(runbook_id)
        if not runbook:
            raise ValueError(f"Runbook {runbook_id} not found")
        if not runbook["enabled"]:
            raise ValueError(f"Runbook {runbook_id} is disabled")

        execution_id = str(uuid4())
        result = {
            "execution_id": execution_id,
            "runbook_id": runbook_id,
            "incident_id": incident_id,
            "dry_run": dry_run,
            "risk_level": runbook["risk_level"],
            "steps_executed": len(runbook.get("steps", [])),
            "status": "dry_run_completed" if dry_run else "completed",
            "results": [],
        }

        for i, step in enumerate(runbook.get("steps", [])):
            step_result = {
                "step": i + 1,
                "action": step.get("action", ""),
                "command": step.get("command", ""),
                "status": "would_execute" if dry_run else "executed",
            }
            result["results"].append(step_result)

        if not dry_run:
            runbook["execution_count"] = runbook.get("execution_count", 0) + 1
            runbook["last_executed"] = datetime.now(timezone.utc).isoformat()

        return result

    def can_auto_execute(self, runbook_id: str) -> bool:
        runbook = self._runbooks.get(runbook_id)
        if not runbook:
            return False
        return (runbook["auto_executable"]
                and runbook["enabled"]
                and runbook["risk_level"] in AUTO_EXECUTABLE_RISKS)

    def disable(self, runbook_id: str) -> bool:
        runbook = self._runbooks.get(runbook_id)
        if not runbook:
            return False
        runbook["enabled"] = False
        return True

    def update_version(self, runbook_id: str, new_version: str) -> dict | None:
        runbook = self._runbooks.get(runbook_id)
        if not runbook:
            return None
        runbook["version"] = new_version
        runbook["updated_at"] = datetime.now(timezone.utc).isoformat()
        return runbook
