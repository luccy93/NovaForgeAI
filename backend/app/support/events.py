"""Support events — emission helpers for support events (Volume 54)."""

from __future__ import annotations

import logging
from typing import Optional

from app.core.events import Event, EventType, event_bus

logger = logging.getLogger(__name__)


async def emit_support_event(event_type: EventType, data: dict,
                             organization_id: Optional[str] = None,
                             user_id: Optional[str] = None) -> Event:
    event = Event(event_type=event_type, data=data, source="support",
                  organization_id=organization_id, user_id=user_id)
    try:
        await event_bus.publish_nowait(event)
    except Exception as exc:
        logger.warning("Failed to emit support event %s: %s", event_type.value, exc)
    return event


async def emit_ticket_created(ticket: dict) -> Event:
    return await emit_support_event(
        EventType.support_ticket_created,
        {"ticket_id": ticket["id"], "customer_id": ticket.get("customer_id"),
         "subject": ticket.get("subject"), "priority": ticket.get("priority")},
        organization_id=ticket.get("organization_id"),
    )


async def emit_ticket_updated(ticket: dict, changes: dict) -> Event:
    return await emit_support_event(
        EventType.support_ticket_updated,
        {"ticket_id": ticket["id"], "changes": changes},
        organization_id=ticket.get("organization_id"),
    )


async def emit_ticket_assigned(ticket: dict, agent: str) -> Event:
    return await emit_support_event(
        EventType.support_ticket_assigned,
        {"ticket_id": ticket["id"], "agent": agent, "team": ticket.get("assigned_team")},
        organization_id=ticket.get("organization_id"),
    )


async def emit_ticket_escalated(ticket: dict, escalation: dict) -> Event:
    return await emit_support_event(
        EventType.support_ticket_escalated,
        {"ticket_id": ticket["id"], "escalation_id": escalation.get("id"),
         "type": escalation.get("escalation_type"), "to_level": escalation.get("to_level")},
        organization_id=ticket.get("organization_id"),
    )


async def emit_ticket_resolved(ticket: dict) -> Event:
    return await emit_support_event(
        EventType.support_ticket_resolved,
        {"ticket_id": ticket["id"], "resolved_at": ticket.get("resolved_at")},
        organization_id=ticket.get("organization_id"),
    )


async def emit_ticket_reopened(ticket: dict) -> Event:
    return await emit_support_event(
        EventType.support_ticket_reopened,
        {"ticket_id": ticket["id"]},
        organization_id=ticket.get("organization_id"),
    )


async def emit_ticket_linked_to_incident(ticket_id: str, incident_id: str) -> Event:
    return await emit_support_event(
        EventType.support_ticket_linked_to_incident,
        {"ticket_id": ticket_id, "incident_id": incident_id},
    )


async def emit_ticket_linked_to_issue(ticket_id: str, issue_id: str) -> Event:
    return await emit_support_event(
        EventType.support_ticket_linked_to_issue,
        {"ticket_id": ticket_id, "issue_id": issue_id},
    )


async def emit_ai_response_generated(ticket_id: str, confidence: float,
                                     escalation_recommended: bool) -> Event:
    return await emit_support_event(
        EventType.support_ai_response_generated,
        {"ticket_id": ticket_id, "confidence": confidence,
         "escalation_recommended": escalation_recommended},
    )


async def emit_human_handoff_requested(ticket_id: str, reason: str) -> Event:
    return await emit_support_event(
        EventType.support_human_handoff_requested,
        {"ticket_id": ticket_id, "reason": reason},
    )


async def emit_sla_at_risk(ticket_id: str, sla_state: str) -> Event:
    return await emit_support_event(
        EventType.support_sla_at_risk,
        {"ticket_id": ticket_id, "sla_state": sla_state},
    )


async def emit_sla_breached(ticket_id: str, breach_time: str) -> Event:
    return await emit_support_event(
        EventType.support_sla_breached,
        {"ticket_id": ticket_id, "breached_at": breach_time},
    )


async def emit_knowledge_gap_detected(category: str, ticket_count: int) -> Event:
    return await emit_support_event(
        EventType.support_knowledge_gap_detected,
        {"category": category, "ticket_count": ticket_count},
    )


async def emit_customer_feedback_received(ticket_id: str, rating: int,
                                          feedback_type: str) -> Event:
    return await emit_support_event(
        EventType.support_customer_feedback_received,
        {"ticket_id": ticket_id, "rating": rating, "feedback_type": feedback_type},
    )
