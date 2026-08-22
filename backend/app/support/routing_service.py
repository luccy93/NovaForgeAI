"""Routing service — rule-based + AI-assisted routing, queue management (Volume 54)."""

from __future__ import annotations

import logging
from typing import Optional

from app.support.constants import (
    TicketPriority, TicketCategory, TicketSeverity,
)

logger = logging.getLogger(__name__)

# ─── Routing rules: (category, severity) → team ──────────────────────
_DEFAULT_ROUTING_TABLE: dict[tuple[str, Optional[str]], str] = {
    (TicketCategory.BILLING.value, None): "billing_support",
    (TicketCategory.SECURITY.value, None): "security_team",
    (TicketCategory.ACCOUNT.value, None): "account_support",
    (TicketCategory.ACCESS.value, None): "iam_support",
    (TicketCategory.BUG.value, "s1"): "engineering_oncall",
    (TicketCategory.BUG.value, "s2"): "engineering_oncall",
    (TicketCategory.BUG.value, None): "engineering_support",
    (TicketCategory.INCIDENT.value, None): "sre_oncall",
    (TicketCategory.PERFORMANCE.value, None): "performance_team",
    (TicketCategory.DEPLOYMENT.value, None): "devops_team",
    (TicketCategory.INTEGRATION.value, None): "integrations_team",
    (TicketCategory.FEATURE_REQUEST.value, None): "product_support",
    (TicketCategory.DOCUMENTATION.value, None): "docs_team",
    (TicketCategory.QUESTION.value, None): "general_support",
}

# ─── Priority-based routing overrides ─────────────────────────────────
_PRIORITY_OVERRIDES: dict[str, str] = {
    TicketPriority.CRITICAL.value: "incident_response",
    TicketPriority.URGENT.value: "escalation_queue",
}

# ─── Service → team mapping ──────────────────────────────────────────
_SERVICE_TEAM_MAP: dict[str, str] = {
    "api": "engineering_support",
    "database": "data_team",
    "infrastructure": "sre_oncall",
    "notifications": "platform_team",
    "billing": "billing_support",
    "auth": "iam_support",
    "ai": "ai_team",
    "search": "search_team",
}


class RoutingService:
    def __init__(self):
        self._routing_table: dict[tuple[str, Optional[str]], str] = dict(_DEFAULT_ROUTING_TABLE)
        self._agent_workloads: dict[str, int] = {}
        self._team_queues: dict[str, list[str]] = {}
        self._routing_log: list[dict] = []
        self._telemetry = {"routed": 0, "escalated": 0, "rerouted": 0}

    def route_ticket(
        self,
        ticket_id: str,
        category: str,
        priority: str = "normal",
        severity: Optional[str] = None,
        service_affected: Optional[str] = None,
        customer_tier: Optional[str] = None,
    ) -> dict:
        team = None
        reason = None

        if priority in _PRIORITY_OVERRIDES:
            team = _PRIORITY_OVERRIDES[priority]
            reason = f"Priority override: {priority} → {team}"
        elif service_affected and service_affected in _SERVICE_TEAM_MAP:
            team = _SERVICE_TEAM_MAP[service_affected]
            reason = f"Service-based routing: {service_affected} → {team}"
        else:
            key = (category, severity)
            team = self._routing_table.get(key) or self._routing_table.get((category, None))
            reason = f"Category-based routing: {category} → {team}"

        if not team:
            team = "general_support"
            reason = "Default fallback routing"

        self._team_queues.setdefault(team, []).append(ticket_id)
        result = {
            "team": team,
            "reason": reason,
            "category": category,
            "priority": priority,
            "severity": severity,
            "service_affected": service_affected,
        }
        self._routing_log.append({
            "ticket_id": ticket_id,
            "routing": result,
        })
        self._telemetry["routed"] += 1
        return result

    def assign_agent(self, ticket_id: str, team: str, preferred_agent: Optional[str] = None) -> dict:
        if preferred_agent:
            agent = preferred_agent
            method = "preferred"
        else:
            agent = self._least_loaded_agent(team)
            method = "least_loaded"
        self._agent_workloads[agent] = self._agent_workloads.get(agent, 0) + 1
        queue = self._team_queues.get(team, [])
        if ticket_id in queue:
            queue.remove(ticket_id)
        return {"agent": agent, "method": method, "team": team, "workload": self._agent_workloads[agent]}

    def _least_loaded_agent(self, team: str) -> str:
        team_agents = [a for a in self._agent_workloads if a.startswith(team)]
        if not team_agents:
            agent = f"{team}_agent_1"
            self._agent_workloads[agent] = 0
            return agent
        return min(team_agents, key=lambda a: self._agent_workloads.get(a, 0))

    def reroute_ticket(self, ticket_id: str, from_team: str, to_team: str, reason: str) -> dict:
        if from_team in self._team_queues and ticket_id in self._team_queues[from_team]:
            self._team_queues[from_team].remove(ticket_id)
        self._team_queues.setdefault(to_team, []).append(ticket_id)
        self._routing_log.append({
            "ticket_id": ticket_id,
            "routing": {"rerouted_from": from_team, "to": to_team, "reason": reason},
        })
        self._telemetry["rerouted"] += 1
        return {"rerouted_from": from_team, "to": to_team, "reason": reason}

    def get_queue_size(self, team: str) -> int:
        return len(self._team_queues.get(team, []))

    def get_team_queues(self) -> dict[str, int]:
        return {team: len(q) for team, q in self._team_queues.items()}

    def get_agent_workload(self, agent: str) -> int:
        return self._agent_workloads.get(agent, 0)

    def get_routing_log(self, limit: int = 50) -> list[dict]:
        return self._routing_log[-limit:]

    def should_escalate(self, sla_state: str, priority: str, escalation_count: int) -> bool:
        if sla_state == "breached":
            return True
        if priority in (TicketPriority.URGENT.value, TicketPriority.CRITICAL.value) and escalation_count == 0:
            return True
        if sla_state == "at_risk" and priority in (TicketPriority.HIGH.value, TicketPriority.URGENT.value,
                                                    TicketPriority.CRITICAL.value):
            return True
        return False

    def get_telemetry(self) -> dict:
        return dict(self._telemetry)


routing_service = RoutingService()
