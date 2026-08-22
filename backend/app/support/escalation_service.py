"""Escalation service — policies, triggers, on-call, audit trail (Volume 54)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.support.constants import EscalationType

logger = logging.getLogger(__name__)


class EscalationService:
    def __init__(self):
        self._escalations: dict[str, dict] = {}
        self._policies: dict[str, dict] = {}
        self._on_call: dict[str, list[dict]] = {}
        self._telemetry = {"escalations": 0, "resolved": 0}

    def create_escalation(self, ticket_id: str, escalation_type: str,
                          to_level: str, triggered_by: Optional[str] = None,
                          reason: str = "", from_level: Optional[str] = None) -> dict:
        esc_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        escalation = {
            "id": esc_id, "ticket_id": ticket_id,
            "escalation_type": escalation_type, "triggered_by": triggered_by,
            "reason": reason, "from_level": from_level, "to_level": to_level,
            "resolved_at": None, "is_resolved": False,
            "created_at": now.isoformat(), "updated_at": now.isoformat(),
        }
        self._escalations[esc_id] = escalation
        self._telemetry["escalations"] += 1
        return escalation

    def get_escalation(self, escalation_id: str) -> Optional[dict]:
        return self._escalations.get(escalation_id)

    def list_escalations(self, ticket_id: Optional[str] = None,
                         is_resolved: Optional[bool] = None,
                         limit: int = 50) -> list[dict]:
        results = list(self._escalations.values())
        if ticket_id:
            results = [e for e in results if e["ticket_id"] == ticket_id]
        if is_resolved is not None:
            results = [e for e in results if e["is_resolved"] == is_resolved]
        results.sort(key=lambda e: e["created_at"], reverse=True)
        return results[:limit]

    def resolve_escalation(self, escalation_id: str, resolved_by: str = "system") -> Optional[dict]:
        esc = self._escalations.get(escalation_id)
        if not esc or esc["is_resolved"]:
            return None
        now = datetime.now(timezone.utc)
        esc["is_resolved"] = True
        esc["resolved_at"] = now.isoformat()
        esc["updated_at"] = now.isoformat()
        self._telemetry["resolved"] += 1
        return esc

    def create_escalation_policy(self, tenant_id: str, name: str,
                                 trigger_type: str, trigger_config: dict,
                                 target_level: str, is_active: bool = True) -> dict:
        policy_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        policy = {
            "id": policy_id, "tenant_id": tenant_id, "name": name,
            "trigger_type": trigger_type, "trigger_config": trigger_config,
            "target_level": target_level, "is_active": is_active,
            "created_at": now.isoformat(), "updated_at": now.isoformat(),
        }
        self._policies[policy_id] = policy
        return policy

    def list_escalation_policies(self, tenant_id: Optional[str] = None) -> list[dict]:
        results = list(self._policies.values())
        if tenant_id:
            results = [p for p in results if p["tenant_id"] == tenant_id]
        return [p for p in results if p["is_active"]]

    def set_on_call(self, team: str, agent: str, schedule_start: str,
                    schedule_end: str, role: str = "primary") -> dict:
        entry = {
            "id": str(uuid.uuid4()), "team": team, "agent": agent,
            "role": role, "schedule_start": schedule_start,
            "schedule_end": schedule_end,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._on_call.setdefault(team, []).append(entry)
        return entry

    def get_on_call(self, team: str) -> Optional[dict]:
        now = datetime.now(timezone.utc).isoformat()
        for entry in self._on_call.get(team, []):
            if entry["schedule_start"] <= now <= entry["schedule_end"]:
                return entry
        return None

    def should_escalate_time(self, sla_state: str, priority: str, escalation_count: int) -> bool:
        if sla_state == "breached":
            return True
        if sla_state == "at_risk" and priority in ("high", "urgent", "critical"):
            return True
        if priority in ("urgent", "critical") and escalation_count == 0:
            return True
        return False

    def get_escalation_history(self, ticket_id: str) -> list[dict]:
        return self.list_escalations(ticket_id=ticket_id, limit=100)

    def get_telemetry(self) -> dict:
        return dict(self._telemetry)


escalation_service = EscalationService()
