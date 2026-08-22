"""SLA service — policy CRUD, tracking, breach detection, time calculations (Volume 54)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.support.constants import (
    SLAState, TicketPriority, DEFAULT_SLA_POLICIES, PLAN_SLA_MULTIPLIER,
)

logger = logging.getLogger(__name__)

AT_RISK_THRESHOLD = 0.8


class SLAService:
    def __init__(self):
        self._policies: dict[str, dict] = {}
        self._tracking: dict[str, dict] = {}
        self._telemetry = {"policies_created": 0, "tracking_started": 0, "breaches": 0, "paused": 0}

    def create_policy(self, tenant_id: str, name: str, priority: str,
                      first_response_minutes: int, resolution_minutes: int,
                      category: Optional[str] = None, plan_tier: Optional[str] = None,
                      update_frequency_minutes: int = 1440) -> dict:
        policy_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        policy = {
            "id": policy_id, "tenant_id": tenant_id, "name": name, "priority": priority,
            "category": category, "plan_tier": plan_tier,
            "first_response_minutes": first_response_minutes,
            "resolution_minutes": resolution_minutes,
            "update_frequency_minutes": update_frequency_minutes,
            "is_active": True, "created_at": now.isoformat(), "updated_at": now.isoformat(),
        }
        self._policies[policy_id] = policy
        self._telemetry["policies_created"] += 1
        return policy

    def get_policy(self, policy_id: str) -> Optional[dict]:
        return self._policies.get(policy_id)

    def list_policies(self, tenant_id: Optional[str] = None) -> list[dict]:
        results = list(self._policies.values())
        if tenant_id:
            results = [p for p in results if p["tenant_id"] == tenant_id]
        return [p for p in results if p["is_active"]]

    def find_policy(self, tenant_id: str, priority: str,
                    category: Optional[str] = None,
                    plan_tier: Optional[str] = None) -> Optional[dict]:
        for p in self._policies.values():
            if p["tenant_id"] != tenant_id or not p["is_active"]:
                continue
            if p["priority"] != priority:
                continue
            if category and p.get("category") and p["category"] != category:
                continue
            if plan_tier and p.get("plan_tier") and p["plan_tier"] != plan_tier:
                continue
            return p
        return None

    def start_tracking(self, ticket_id: str, policy_id: Optional[str] = None,
                       priority: str = "normal", plan_tier: Optional[str] = None,
                       tenant_id: Optional[str] = None) -> dict:
        now = datetime.now(timezone.utc)
        if policy_id and policy_id in self._policies:
            policy = self._policies[policy_id]
            resp_min = policy["first_response_minutes"]
            res_min = policy["resolution_minutes"]
        else:
            resp_min, res_min = DEFAULT_SLA_POLICIES.get(
                TicketPriority(priority) if priority in [e.value for e in TicketPriority]
                else TicketPriority.NORMAL, (1440, 4320),
            )
            if plan_tier and plan_tier in PLAN_SLA_MULTIPLIER:
                m = PLAN_SLA_MULTIPLIER[plan_tier]
                resp_min = int(resp_min * m)
                res_min = int(res_min * m)
        tracking = {
            "id": str(uuid.uuid4()), "ticket_id": ticket_id, "policy_id": policy_id,
            "sla_state": SLAState.ON_TRACK.value,
            "first_response_deadline": (now + timedelta(minutes=resp_min)).isoformat(),
            "resolution_deadline": (now + timedelta(minutes=res_min)).isoformat(),
            "first_response_met": None, "resolution_met": None,
            "paused_at": None, "pause_reason": None, "total_pause_seconds": 0,
            "breached_at": None, "created_at": now.isoformat(), "updated_at": now.isoformat(),
        }
        self._tracking[ticket_id] = tracking
        self._telemetry["tracking_started"] += 1
        return tracking

    def get_tracking(self, ticket_id: str) -> Optional[dict]:
        return self._tracking.get(ticket_id)

    def check_sla_status(self, ticket_id: str) -> Optional[dict]:
        tracking = self._tracking.get(ticket_id)
        if not tracking:
            return None
        if tracking["sla_state"] == SLAState.PAUSED.value:
            return tracking
        now = datetime.now(timezone.utc)
        if tracking.get("first_response_met") is None and tracking.get("first_response_deadline"):
            deadline = datetime.fromisoformat(tracking["first_response_deadline"])
            created = datetime.fromisoformat(tracking["created_at"])
            total = (deadline - created).total_seconds()
            elapsed = (now - created).total_seconds() - tracking["total_pause_seconds"]
            if now > deadline:
                tracking["sla_state"] = SLAState.BREACHED.value
                tracking["breached_at"] = now.isoformat()
                self._telemetry["breaches"] += 1
            elif total > 0 and elapsed / total >= AT_RISK_THRESHOLD:
                tracking["sla_state"] = SLAState.AT_RISK.value
            else:
                tracking["sla_state"] = SLAState.ON_TRACK.value
        tracking["updated_at"] = now.isoformat()
        return tracking

    def mark_first_response_met(self, ticket_id: str) -> Optional[dict]:
        tracking = self._tracking.get(ticket_id)
        if not tracking:
            return None
        tracking["first_response_met"] = True
        tracking["updated_at"] = datetime.now(timezone.utc).isoformat()
        if tracking["sla_state"] != SLAState.PAUSED.value:
            tracking["sla_state"] = SLAState.ON_TRACK.value
        return tracking

    def mark_resolution_met(self, ticket_id: str) -> Optional[dict]:
        tracking = self._tracking.get(ticket_id)
        if not tracking:
            return None
        tracking["resolution_met"] = True
        tracking["updated_at"] = datetime.now(timezone.utc).isoformat()
        return tracking

    def pause_tracking(self, ticket_id: str, reason: str = "waiting_customer") -> Optional[dict]:
        tracking = self._tracking.get(ticket_id)
        if not tracking or tracking["sla_state"] == SLAState.PAUSED.value:
            return tracking
        tracking["sla_state"] = SLAState.PAUSED.value
        tracking["paused_at"] = datetime.now(timezone.utc).isoformat()
        tracking["pause_reason"] = reason
        tracking["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._telemetry["paused"] += 1
        return tracking

    def resume_tracking(self, ticket_id: str) -> Optional[dict]:
        tracking = self._tracking.get(ticket_id)
        if not tracking or tracking["sla_state"] != SLAState.PAUSED.value:
            return tracking
        now = datetime.now(timezone.utc)
        if tracking.get("paused_at"):
            pause_start = datetime.fromisoformat(tracking["paused_at"])
            tracking["total_pause_seconds"] += int((now - pause_start).total_seconds())
        tracking["paused_at"] = None
        tracking["pause_reason"] = None
        tracking["sla_state"] = SLAState.ON_TRACK.value
        tracking["updated_at"] = now.isoformat()
        return tracking

    def check_all_active(self) -> dict:
        breached, at_risk = [], []
        for tid, tracking in self._tracking.items():
            if tracking["sla_state"] == SLAState.PAUSED.value:
                continue
            self.check_sla_status(tid)
            if tracking["sla_state"] == SLAState.BREACHED.value:
                breached.append(tracking)
            elif tracking["sla_state"] == SLAState.AT_RISK.value:
                at_risk.append(tracking)
        return {"breached": breached, "at_risk": at_risk}

    def get_sla_summary(self, tenant_id: Optional[str] = None) -> dict:
        items = list(self._tracking.values())
        total = len(items)
        on_track = sum(1 for t in items if t["sla_state"] == SLAState.ON_TRACK.value)
        at_risk = sum(1 for t in items if t["sla_state"] == SLAState.AT_RISK.value)
        breached = sum(1 for t in items if t["sla_state"] == SLAState.BREACHED.value)
        paused = sum(1 for t in items if t["sla_state"] == SLAState.PAUSED.value)
        compliance = (on_track / total * 100) if total > 0 else 100.0
        return {"total": total, "on_track": on_track, "at_risk": at_risk,
                "breached": breached, "paused": paused, "compliance_rate": round(compliance, 1)}

    def get_telemetry(self) -> dict:
        return dict(self._telemetry)


sla_service = SLAService()
