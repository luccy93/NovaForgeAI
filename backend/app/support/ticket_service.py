"""Ticket service — full lifecycle, state machine, assignment, linking, search (Volume 54)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.support.constants import (
    TicketStatus, TicketPriority, TicketCategory, TicketSource,
    TICKET_TRANSITIONS, TICKET_ACTIVE_STATUSES, REOPEN_WINDOW_DAYS,
    DUPLICATE_SIMILARITY_THRESHOLD, DEFAULT_SLA_POLICIES, PLAN_SLA_MULTIPLIER,
    TicketLinkType,
)

logger = logging.getLogger(__name__)


class TicketService:
    def __init__(self):
        self._tickets: dict[str, dict] = {}
        self._links: dict[str, list[dict]] = {}
        self._audit_log: list[dict] = []
        self._telemetry = {"created": 0, "updated": 0, "resolved": 0, "closed": 0, "reopened": 0}

    def create_ticket(
        self,
        tenant_id: str,
        customer_id: str,
        subject: str,
        description: str = "",
        category: Optional[str] = None,
        priority: str = "normal",
        severity: Optional[str] = None,
        source: str = "web",
        organization_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        project_id: Optional[str] = None,
        product_version: Optional[str] = None,
        service_affected: Optional[str] = None,
        environment: Optional[str] = None,
        region: Optional[str] = None,
        subscription_id: Optional[str] = None,
        plan_tier: Optional[str] = None,
    ) -> dict:
        ticket_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        priority_enum = TicketPriority(priority) if priority in [e.value for e in TicketPriority] else TicketPriority.NORMAL

        resp_minutes, res_minutes = DEFAULT_SLA_POLICIES.get(priority_enum, (1440, 4320))
        if plan_tier and plan_tier in PLAN_SLA_MULTIPLIER:
            multiplier = PLAN_SLA_MULTIPLIER[plan_tier]
            resp_minutes = int(resp_minutes * multiplier)
            res_minutes = int(res_minutes * multiplier)
        sla_deadline = now + timedelta(minutes=res_minutes)

        ticket = {
            "id": ticket_id,
            "tenant_id": tenant_id,
            "customer_id": customer_id,
            "organization_id": organization_id,
            "workspace_id": workspace_id,
            "project_id": project_id,
            "subscription_id": subscription_id,
            "category": category or TicketCategory.QUESTION.value,
            "priority": priority,
            "severity": severity,
            "status": TicketStatus.NEW.value,
            "source": source,
            "subject": subject,
            "description": description,
            "assigned_team": None,
            "assigned_agent": None,
            "product_version": product_version,
            "service_affected": service_affected,
            "environment": environment,
            "region": region,
            "sentiment_score": None,
            "ai_confidence": None,
            "ai_classification": None,
            "message_count": 0,
            "resolved_at": None,
            "closed_at": None,
            "first_response_at": None,
            "sla_deadline_at": sla_deadline.isoformat(),
            "linked_incident_id": None,
            "linked_issue_id": None,
            "linked_deployment_id": None,
            "links": [],
            "metadata": {},
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        self._tickets[ticket_id] = ticket
        self._links[ticket_id] = []
        self._audit(ticket_id, "created", {"customer_id": customer_id, "subject": subject})
        self._telemetry["created"] += 1
        return ticket

    def get_ticket(self, ticket_id: str) -> Optional[dict]:
        return self._tickets.get(ticket_id)

    def list_tickets(
        self,
        tenant_id: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        category: Optional[str] = None,
        customer_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        assigned_agent: Optional[str] = None,
        assigned_team: Optional[str] = None,
        service_affected: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        active_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        results = list(self._tickets.values())
        if tenant_id:
            results = [t for t in results if t["tenant_id"] == tenant_id]
        if status:
            results = [t for t in results if t["status"] == status]
        if priority:
            results = [t for t in results if t["priority"] == priority]
        if category:
            results = [t for t in results if t["category"] == category]
        if customer_id:
            results = [t for t in results if t["customer_id"] == customer_id]
        if organization_id:
            results = [t for t in results if t.get("organization_id") == organization_id]
        if assigned_agent:
            results = [t for t in results if t.get("assigned_agent") == assigned_agent]
        if assigned_team:
            results = [t for t in results if t.get("assigned_team") == assigned_team]
        if service_affected:
            results = [t for t in results if t.get("service_affected") == service_affected]
        if active_only:
            results = [t for t in results if t["status"] in [s.value for s in TICKET_ACTIVE_STATUSES]]
        if date_from:
            results = [t for t in results if t["created_at"] >= date_from]
        if date_to:
            results = [t for t in results if t["created_at"] <= date_to]
        results.sort(key=lambda t: t["created_at"], reverse=True)
        return results[offset:offset + limit]

    def update_ticket(self, ticket_id: str, **fields) -> Optional[dict]:
        ticket = self._tickets.get(ticket_id)
        if not ticket:
            return None
        updates = {}
        for k, v in fields.items():
            if v is not None and k in ticket and k not in ("id", "created_at"):
                old_val = ticket[k]
                ticket[k] = v
                updates[k] = {"old": old_val, "new": v}
        ticket["updated_at"] = datetime.now(timezone.utc).isoformat()
        if updates:
            self._audit(ticket_id, "updated", updates)
            self._telemetry["updated"] += 1
        return ticket

    def transition_ticket(self, ticket_id: str, new_status: str, actor: str = "system") -> Optional[dict]:
        ticket = self._tickets.get(ticket_id)
        if not ticket:
            return None
        current = TicketStatus(ticket["status"])
        target = TicketStatus(new_status)
        allowed = TICKET_TRANSITIONS.get(current, [])
        if target not in allowed:
            raise ValueError(
                f"Invalid transition: {current.value} → {new_status}. "
                f"Allowed: {[s.value for s in allowed]}"
            )
        now = datetime.now(timezone.utc)
        ticket["status"] = target.value
        ticket["updated_at"] = now.isoformat()
        if target == TicketStatus.RESOLVED:
            ticket["resolved_at"] = now.isoformat()
            self._telemetry["resolved"] += 1
        elif target == TicketStatus.CLOSED:
            ticket["closed_at"] = now.isoformat()
            self._telemetry["closed"] += 1
        elif target == TicketStatus.REOPENED:
            if ticket.get("closed_at"):
                closed_dt = datetime.fromisoformat(ticket["closed_at"])
                if (now - closed_dt).days > REOPEN_WINDOW_DAYS:
                    raise ValueError(f"Cannot reopen: closed more than {REOPEN_WINDOW_DAYS} days ago")
            ticket["closed_at"] = None
            ticket["resolved_at"] = None
            self._telemetry["reopened"] += 1
        elif target == TicketStatus.OPEN:
            if current == TicketStatus.NEW:
                pass
        self._audit(ticket_id, "transitioned", {
            "from": current.value, "to": target.value, "actor": actor,
        })
        return ticket

    def assign_ticket(self, ticket_id: str, assigned_to: str, assigned_by: str,
                      team: Optional[str] = None, reason: Optional[str] = None) -> Optional[dict]:
        ticket = self._tickets.get(ticket_id)
        if not ticket:
            return None
        now = datetime.now(timezone.utc)
        old_agent = ticket.get("assigned_agent")
        ticket["assigned_agent"] = assigned_to
        ticket["assigned_team"] = team or ticket.get("assigned_team")
        ticket["updated_at"] = now.isoformat()
        if ticket["status"] == TicketStatus.NEW.value:
            ticket["status"] = TicketStatus.OPEN.value
        self._audit(ticket_id, "assigned", {
            "from": old_agent, "to": assigned_to, "by": assigned_by, "team": team,
        })
        return ticket

    def search_tickets(self, query: str, tenant_id: Optional[str] = None, limit: int = 50) -> list[dict]:
        query_lower = query.lower()
        words = set(query_lower.split())
        results = []
        for ticket in self._tickets.values():
            if tenant_id and ticket["tenant_id"] != tenant_id:
                continue
            text = f"{ticket.get('subject', '')} {ticket.get('description', '')} {ticket.get('category', '')}".lower()
            score = sum(1 for w in words if w in text)
            if score > 0:
                results.append((score, ticket))
        results.sort(key=lambda x: x[0], reverse=True)
        return [t for _, t in results[:limit]]

    def detect_duplicates(self, tenant_id: str, subject: str, description: str,
                          customer_id: Optional[str] = None,
                          service_affected: Optional[str] = None) -> list[dict]:
        query_words = set(f"{subject} {description}".lower().split())
        candidates = []
        for ticket in self._tickets.values():
            if ticket["tenant_id"] != tenant_id:
                continue
            existing_words = set(f"{ticket['subject']} {ticket.get('description', '')}".lower().split())
            if not query_words or not existing_words:
                continue
            intersection = query_words & existing_words
            union = query_words | existing_words
            similarity = len(intersection) / len(union) if union else 0
            if similarity >= DUPLICATE_SIMILARITY_THRESHOLD:
                if customer_id and ticket.get("customer_id") == customer_id:
                    similarity += 0.1
                if service_affected and ticket.get("service_affected") == service_affected:
                    similarity += 0.05
                candidates.append({"ticket_id": ticket["id"], "similarity": min(similarity, 1.0), "ticket": ticket})
        candidates.sort(key=lambda x: x["similarity"], reverse=True)
        return candidates[:10]

    def link_ticket(self, ticket_id: str, link_type: str, target_id: str,
                    target_url: Optional[str] = None, description: Optional[str] = None) -> Optional[dict]:
        ticket = self._tickets.get(ticket_id)
        if not ticket:
            return None
        link = {
            "id": str(uuid.uuid4()),
            "ticket_id": ticket_id,
            "link_type": link_type,
            "target_id": target_id,
            "target_url": target_url,
            "description": description,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._links.setdefault(ticket_id, []).append(link)
        ticket["links"] = self._links[ticket_id]
        ticket["updated_at"] = datetime.now(timezone.utc).isoformat()
        if link_type == "incident":
            ticket["linked_incident_id"] = target_id
        elif link_type == "issue":
            ticket["linked_issue_id"] = target_id
        elif link_type == "deployment":
            ticket["linked_deployment_id"] = target_id
        self._audit(ticket_id, "linked", {"type": link_type, "target": target_id})
        return link

    def get_ticket_links(self, ticket_id: str) -> list[dict]:
        return self._links.get(ticket_id, [])

    def get_audit_log(self, ticket_id: str) -> list[dict]:
        return [a for a in self._audit_log if a.get("ticket_id") == ticket_id]

    def get_tickets_by_incident(self, incident_id: str) -> list[dict]:
        return [t for t in self._tickets.values() if t.get("linked_incident_id") == incident_id]

    def count_active_tickets(self, tenant_id: Optional[str] = None) -> int:
        count = 0
        for t in self._tickets.values():
            if tenant_id and t["tenant_id"] != tenant_id:
                continue
            if t["status"] in [s.value for s in TICKET_ACTIVE_STATUSES]:
                count += 1
        return count

    def get_tickets_by_service(self, service: str, tenant_id: Optional[str] = None) -> list[dict]:
        return [t for t in self._tickets.values()
                if t.get("service_affected") == service
                and (not tenant_id or t["tenant_id"] == tenant_id)]

    def mark_first_response(self, ticket_id: str) -> Optional[dict]:
        ticket = self._tickets.get(ticket_id)
        if not ticket or ticket.get("first_response_at"):
            return ticket
        ticket["first_response_at"] = datetime.now(timezone.utc).isoformat()
        ticket["updated_at"] = datetime.now(timezone.utc).isoformat()
        return ticket

    def get_telemetry(self) -> dict:
        return dict(self._telemetry)

    def _audit(self, ticket_id: str, action: str, details: dict) -> None:
        self._audit_log.append({
            "ticket_id": ticket_id,
            "action": action,
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


ticket_service = TicketService()
