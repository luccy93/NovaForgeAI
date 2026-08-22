"""Support agent tools — scoped tool definitions for support AI (Volume 54)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class SupportToolSpec:
    name: str
    description: str
    parameters: dict[str, str]
    required_permissions: list[str] = field(default_factory=lambda: ["read"])
    func: Optional[Callable] = None


class SupportToolRegistry:
    def __init__(self):
        self._tools: dict[str, SupportToolSpec] = {}

    def register(self, tool: SupportToolSpec) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[SupportToolSpec]:
        return self._tools.get(name)

    def describe(self, permissions: Optional[list[str]] = None) -> str:
        lines = []
        for tool in self._tools.values():
            if permissions and not any(p in tool.required_permissions for p in permissions):
                continue
            params = ", ".join(f"{k}: {v}" for k, v in tool.parameters.items())
            lines.append(f"- {tool.name}({params}): {tool.description}")
        return "\n".join(lines)

    def list_tools(self, permissions: Optional[list[str]] = None) -> list[dict]:
        results = []
        for tool in self._tools.values():
            if permissions and not any(p in tool.required_permissions for p in permissions):
                continue
            results.append({
                "name": tool.name, "description": tool.description,
                "parameters": tool.parameters,
                "required_permissions": tool.required_permissions,
            })
        return results

    def validate_call(self, tool_name: str, agent_permissions: list[str]) -> bool:
        tool = self._tools.get(tool_name)
        if not tool:
            return False
        return any(p in agent_permissions for p in tool.required_permissions)


def create_support_tool_registry() -> SupportToolRegistry:
    registry = SupportToolRegistry()

    registry.register(SupportToolSpec(
        name="search_knowledge",
        description="Search knowledge base articles for relevant information",
        parameters={"query": "str", "category": "str?", "product": "str?"},
        required_permissions=["knowledge.read"],
    ))
    registry.register(SupportToolSpec(
        name="get_ticket_context",
        description="Get full ticket context including messages and history",
        parameters={"ticket_id": "str"},
        required_permissions=["ticket.read"],
    ))
    registry.register(SupportToolSpec(
        name="check_entitlement",
        description="Check customer subscription plan and entitlements",
        parameters={"customer_id": "str"},
        required_permissions=["billing.read"],
    ))
    registry.register(SupportToolSpec(
        name="check_billing_status",
        description="Check customer billing status, invoices, and payments",
        parameters={"customer_id": "str"},
        required_permissions=["billing.read"],
    ))
    registry.register(SupportToolSpec(
        name="check_incident_status",
        description="Check public status of active incidents affecting customer's service",
        parameters={"service": "str?"},
        required_permissions=["incident.public.read"],
    ))
    registry.register(SupportToolSpec(
        name="create_ticket",
        description="Create a new support ticket",
        parameters={"subject": "str", "description": "str", "category": "str", "priority": "str"},
        required_permissions=["ticket.write"],
    ))
    registry.register(SupportToolSpec(
        name="update_ticket",
        description="Update ticket fields (status, priority, assignment, etc.)",
        parameters={"ticket_id": "str", "field": "str", "value": "str"},
        required_permissions=["ticket.write"],
    ))
    registry.register(SupportToolSpec(
        name="escalate_ticket",
        description="Escalate a ticket to a higher support tier",
        parameters={"ticket_id": "str", "reason": "str", "to_level": "str"},
        required_permissions=["ticket.write", "escalation.write"],
    ))
    registry.register(SupportToolSpec(
        name="send_response",
        description="Send an approved response to the customer",
        parameters={"ticket_id": "str", "message": "str"},
        required_permissions=["ticket.write"],
    ))
    registry.register(SupportToolSpec(
        name="get_customer_history",
        description="Get customer's past tickets and interaction history",
        parameters={"customer_id": "str"},
        required_permissions=["ticket.read"],
    ))
    registry.register(SupportToolSpec(
        name="link_ticket_to_incident",
        description="Link a ticket to an existing incident",
        parameters={"ticket_id": "str", "incident_id": "str"},
        required_permissions=["ticket.write"],
    ))
    registry.register(SupportToolSpec(
        name="get_service_status",
        description="Get current service health and status",
        parameters={},
        required_permissions=["incident.public.read"],
    ))
    return registry
