"""Incident Response Platform -- Escalation Manager (Volume 49).

Escalation policies, on-call lookup, timeout-based escalation,
secondary escalation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


class EscalationManager:
    """Escalation policy management and execution."""

    def __init__(self):
        self._policies: dict[str, dict[str, Any]] = {}
        self._escalations: list[dict[str, Any]] = []
        self._oncall_schedules: dict[str, list[dict[str, Any]]] = {}

    def create_policy(self, tenant: str, name: str, description: str = "",
                      rules: list | None = None, enabled: bool = True) -> dict[str, Any]:
        policy_id = str(uuid4())
        policy = {
            "id": policy_id, "tenant": tenant, "name": name,
            "description": description, "rules": rules or [], "enabled": enabled,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._policies[policy_id] = policy
        return policy

    def get_policy(self, policy_id: str) -> dict[str, Any] | None:
        return self._policies.get(policy_id)

    def list_policies(self, tenant: str = "") -> list[dict]:
        return [p for p in self._policies.values()
                if not tenant or p.get("tenant") == tenant]

    def set_oncall(self, service: str, schedule: list[dict[str, Any]]) -> dict:
        self._oncall_schedules[service] = schedule
        return {"service": service, "oncall_count": len(schedule)}

    def get_oncall(self, service: str) -> dict[str, Any] | None:
        schedule = self._oncall_schedules.get(service, [])
        if not schedule:
            return None
        return schedule[0] if schedule else None

    def check_escalation(self, incident: dict, policy_id: str = "") -> dict[str, Any]:
        incident_id = incident.get("id", "")
        severity = incident.get("severity", "SEV2")
        status = incident.get("status", "detected")
        service = incident.get("service", "")

        should_escalate = False
        reason = ""

        if status == "detected":
            should_escalate = True
            reason = "Incident not yet acknowledged"
        elif severity in ("SEV0", "SEV1") and status not in ("mitigating", "monitoring", "resolved", "closed"):
            should_escalate = True
            reason = f"{severity} incident not mitigated"

        targets = []
        oncall = self.get_oncall(service)
        if oncall:
            targets.append(oncall.get("name", "on-call"))

        escalation = {
            "incident_id": incident_id,
            "should_escalate": should_escalate,
            "reason": reason,
            "severity": severity,
            "targets": targets,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

        if should_escalate:
            self._escalations.append(escalation)

        return escalation

    def record_escalation(self, incident_id: str, target: str, channel: str = "slack",
                          message: str = "", level: int = 1) -> dict:
        record = {
            "incident_id": incident_id, "target": target, "channel": channel,
            "message": message, "level": level,
            "escalated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._escalations.append(record)
        return record

    def get_escalations(self, incident_id: str = "", limit: int = 50) -> list[dict]:
        results = []
        for esc in self._escalations:
            if incident_id and esc.get("incident_id") != incident_id:
                continue
            results.append(esc)
        return results[:limit]

    def get_stats(self, tenant: str = "") -> dict[str, Any]:
        return {
            "total_escalations": len(self._escalations),
            "policies_count": len([p for p in self._policies.values()
                                   if not tenant or p.get("tenant") == tenant]),
            "oncall_services": len(self._oncall_schedules),
        }
