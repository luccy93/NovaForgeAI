"""Support & ITSM API — ~55 endpoints for tickets, knowledge, SLA, analytics (Volume 54)."""

from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.support.schemas import (
    TicketCreate, TicketUpdate, TicketSearch, MessageCreate, AssignmentCreate,
    EscalationCreate, ArticleCreate, ArticleUpdate, ArticleSearch,
    SLAPolicyCreate, FeedbackCreate, TicketLinkCreate, AutomationRunCreate,
    AutomationApproval,
)

router = APIRouter()


# ─── Tickets ──────────────────────────────────────────────────────────

@router.post("/support/tickets")
async def create_ticket(body: TicketCreate):
    from app.support.ticket_service import ticket_service
    ticket = await asyncio.to_thread(
        ticket_service.create_ticket,
        tenant_id="default", customer_id=body.customer_id, subject=body.subject,
        description=body.description, category=body.category.value if body.category else None,
        priority=body.priority.value, severity=body.severity.value if body.severity else None,
        source=body.source.value, organization_id=body.organization_id,
        workspace_id=body.workspace_id, project_id=body.project_id,
        product_version=body.product_version, service_affected=body.service_affected,
        environment=body.environment, region=body.region,
    )
    return ticket


@router.get("/support/tickets")
async def list_tickets(
    status: Optional[str] = None, priority: Optional[str] = None,
    category: Optional[str] = None, customer_id: Optional[str] = None,
    organization_id: Optional[str] = None, assigned_agent: Optional[str] = None,
    assigned_team: Optional[str] = None, service_affected: Optional[str] = None,
    date_from: Optional[str] = None, date_to: Optional[str] = None,
    active_only: bool = False, limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    from app.support.ticket_service import ticket_service
    return await asyncio.to_thread(
        ticket_service.list_tickets, tenant_id="default", status=status,
        priority=priority, category=category, customer_id=customer_id,
        organization_id=organization_id, assigned_agent=assigned_agent,
        assigned_team=assigned_team, service_affected=service_affected,
        date_from=date_from, date_to=date_to, active_only=active_only,
        limit=limit, offset=offset,
    )


@router.get("/support/tickets/{ticket_id}")
async def get_ticket(ticket_id: str):
    from app.support.ticket_service import ticket_service
    ticket = await asyncio.to_thread(ticket_service.get_ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.put("/support/tickets/{ticket_id}")
async def update_ticket(ticket_id: str, body: TicketUpdate):
    from app.support.ticket_service import ticket_service
    kwargs = body.model_dump(exclude_none=True)
    ticket = await asyncio.to_thread(ticket_service.update_ticket, ticket_id, **kwargs)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.post("/support/tickets/{ticket_id}/transition")
async def transition_ticket(ticket_id: str, new_status: str = Query(...)):
    from app.support.ticket_service import ticket_service
    try:
        ticket = await asyncio.to_thread(ticket_service.transition_ticket, ticket_id, new_status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.post("/support/tickets/{ticket_id}/assign")
async def assign_ticket(ticket_id: str, body: AssignmentCreate):
    from app.support.ticket_service import ticket_service
    ticket = await asyncio.to_thread(
        ticket_service.assign_ticket, ticket_id,
        assigned_to=body.assigned_to, assigned_by=body.assigned_by,
        team=body.team, reason=body.reason,
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.post("/support/tickets/{ticket_id}/escalate")
async def escalate_ticket(ticket_id: str, body: EscalationCreate):
    from app.support.escalation_service import escalation_service
    esc = await asyncio.to_thread(
        escalation_service.create_escalation, ticket_id,
        escalation_type=body.escalation_type.value, to_level=body.to_level,
        triggered_by=body.triggered_by, reason=body.reason,
    )
    return esc


@router.post("/support/tickets/{ticket_id}/resolve")
async def resolve_ticket(ticket_id: str):
    from app.support.ticket_service import ticket_service
    ticket = await asyncio.to_thread(ticket_service.transition_ticket, ticket_id, "resolved")
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.post("/support/tickets/{ticket_id}/close")
async def close_ticket(ticket_id: str):
    from app.support.ticket_service import ticket_service
    ticket = await asyncio.to_thread(ticket_service.transition_ticket, ticket_id, "closed")
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.post("/support/tickets/{ticket_id}/reopen")
async def reopen_ticket(ticket_id: str):
    from app.support.ticket_service import ticket_service
    try:
        ticket = await asyncio.to_thread(ticket_service.transition_ticket, ticket_id, "reopened")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.post("/support/tickets/{ticket_id}/link")
async def link_ticket(ticket_id: str, body: TicketLinkCreate):
    from app.support.ticket_service import ticket_service
    link = await asyncio.to_thread(
        ticket_service.link_ticket, ticket_id,
        link_type=body.link_type, target_id=body.target_id,
        target_url=body.target_url, description=body.description,
    )
    if not link:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return link


@router.get("/support/tickets/{ticket_id}/links")
async def get_ticket_links(ticket_id: str):
    from app.support.ticket_service import ticket_service
    return await asyncio.to_thread(ticket_service.get_ticket_links, ticket_id)


@router.get("/support/tickets/{ticket_id}/audit")
async def get_ticket_audit(ticket_id: str):
    from app.support.ticket_service import ticket_service
    return await asyncio.to_thread(ticket_service.get_audit_log, ticket_id)


@router.post("/support/tickets/search")
async def search_tickets(body: TicketSearch):
    from app.support.ticket_service import ticket_service
    results = await asyncio.to_thread(
        ticket_service.search_tickets, body.query or "", tenant_id="default", limit=body.limit,
    )
    return {"results": results, "count": len(results)}


@router.post("/support/tickets/duplicates")
async def detect_duplicates(body: TicketSearch):
    from app.support.ticket_service import ticket_service
    from app.support.classification_service import classification_service
    all_tickets = await asyncio.to_thread(
        ticket_service.list_tickets, tenant_id="default", limit=200,
    )
    dupes = await asyncio.to_thread(
        classification_service.detect_duplicates, "default",
        body.query or "", body.query or "", existing_tickets=all_tickets,
    )
    return {"candidates": dupes}


# ─── Messages ─────────────────────────────────────────────────────────

@router.post("/support/tickets/{ticket_id}/messages")
async def create_message(ticket_id: str, body: MessageCreate):
    from app.support.message_service import message_service
    msg = await asyncio.to_thread(
        message_service.create_message, ticket_id,
        sender_id=body.sender_id, message_text=body.message_text,
        sender_type=body.sender_type, visibility=body.visibility,
        attachments=body.attachments,
    )
    return msg


@router.get("/support/tickets/{ticket_id}/messages")
async def list_messages(ticket_id: str, include_internal: bool = False,
                        limit: int = Query(100, ge=1, le=500)):
    from app.support.message_service import message_service
    return await asyncio.to_thread(
        message_service.list_messages, ticket_id, include_internal=include_internal, limit=limit,
    )


# ─── Knowledge ────────────────────────────────────────────────────────

@router.post("/support/knowledge/articles")
async def create_article(body: ArticleCreate):
    from app.support.knowledge_service import knowledge_service
    article = await asyncio.to_thread(
        knowledge_service.create_article, "default", title=body.title,
        content=body.content, category=body.category, product=body.product,
        version=body.version, owner_id=body.owner_id,
        source_type=body.source_type.value if body.source_type else None,
        source_url=body.source_url, tags=body.tags,
        ai_generated=body.ai_generated, ai_confidence=body.ai_confidence,
    )
    return article


@router.get("/support/knowledge/articles")
async def list_articles(category: Optional[str] = None, product: Optional[str] = None,
                        status: Optional[str] = None, limit: int = Query(50, ge=1, le=200)):
    from app.support.knowledge_service import knowledge_service
    return await asyncio.to_thread(
        knowledge_service.list_articles, tenant_id="default",
        category=category, product=product, status=status, limit=limit,
    )


@router.get("/support/knowledge/articles/{article_id}")
async def get_article(article_id: str):
    from app.support.knowledge_service import knowledge_service
    article = await asyncio.to_thread(knowledge_service.get_article, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


@router.put("/support/knowledge/articles/{article_id}")
async def update_article(article_id: str, body: ArticleUpdate):
    from app.support.knowledge_service import knowledge_service
    kwargs = body.model_dump(exclude_none=True)
    if "status" in kwargs:
        kwargs["status"] = kwargs["status"].value if hasattr(kwargs["status"], "value") else kwargs["status"]
    article = await asyncio.to_thread(knowledge_service.update_article, article_id, **kwargs)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


@router.post("/support/knowledge/articles/{article_id}/transition")
async def transition_article(article_id: str, new_status: str = Query(...)):
    from app.support.knowledge_service import knowledge_service
    try:
        article = await asyncio.to_thread(knowledge_service.transition_article, article_id, new_status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


@router.post("/support/knowledge/search")
async def search_knowledge(body: ArticleSearch):
    from app.support.knowledge_service import knowledge_service
    status = body.status.value if body.status else "published"
    return await asyncio.to_thread(
        knowledge_service.search_articles, body.query, tenant_id="default",
        category=body.category, product=body.product, status=status, limit=body.limit,
    )


@router.get("/support/knowledge/gaps")
async def knowledge_gaps():
    from app.support.knowledge_service import knowledge_service
    return await asyncio.to_thread(knowledge_service.detect_knowledge_gaps, "default")


@router.get("/support/knowledge/stats")
async def knowledge_stats():
    from app.support.knowledge_service import knowledge_service
    return await asyncio.to_thread(knowledge_service.get_article_stats, "default")


# ─── SLA ──────────────────────────────────────────────────────────────

@router.post("/support/sla/policies")
async def create_sla_policy(body: SLAPolicyCreate):
    from app.support.sla_service import sla_service
    return await asyncio.to_thread(
        sla_service.create_policy, "default", name=body.name,
        priority=body.priority.value, first_response_minutes=body.first_response_minutes,
        resolution_minutes=body.resolution_minutes, category=body.category.value if body.category else None,
        plan_tier=body.plan_tier, update_frequency_minutes=body.update_frequency_minutes,
    )


@router.get("/support/sla/policies")
async def list_sla_policies():
    from app.support.sla_service import sla_service
    return await asyncio.to_thread(sla_service.list_policies, "default")


@router.post("/support/sla/tracking")
async def start_sla_tracking(ticket_id: str, policy_id: Optional[str] = None,
                             priority: str = "normal", plan_tier: Optional[str] = None):
    from app.support.sla_service import sla_service
    return await asyncio.to_thread(
        sla_service.start_tracking, ticket_id, policy_id=policy_id,
        priority=priority, plan_tier=plan_tier, tenant_id="default",
    )


@router.get("/support/sla/tracking/{ticket_id}")
async def get_sla_tracking(ticket_id: str):
    from app.support.sla_service import sla_service
    tracking = await asyncio.to_thread(sla_service.get_tracking, ticket_id)
    if not tracking:
        raise HTTPException(status_code=404, detail="No SLA tracking for this ticket")
    return tracking


@router.get("/support/sla/summary")
async def sla_summary():
    from app.support.sla_service import sla_service
    return await asyncio.to_thread(sla_service.get_sla_summary, "default")


@router.post("/support/sla/check")
async def check_sla():
    from app.support.sla_service import sla_service
    return await asyncio.to_thread(sla_service.check_all_active)


# ─── Escalations ──────────────────────────────────────────────────────

@router.get("/support/escalations")
async def list_escalations(ticket_id: Optional[str] = None, limit: int = Query(50, ge=1, le=200)):
    from app.support.escalation_service import escalation_service
    return await asyncio.to_thread(
        escalation_service.list_escalations, ticket_id=ticket_id, limit=limit,
    )


@router.post("/support/escalations")
async def create_escalation(body: EscalationCreate):
    from app.support.escalation_service import escalation_service
    return await asyncio.to_thread(
        escalation_service.create_escalation, ticket_id="",
        escalation_type=body.escalation_type.value, to_level=body.to_level,
        triggered_by=body.triggered_by, reason=body.reason,
    )


@router.get("/support/escalations/{escalation_id}")
async def get_escalation(escalation_id: str):
    from app.support.escalation_service import escalation_service
    esc = await asyncio.to_thread(escalation_service.get_escalation, escalation_id)
    if not esc:
        raise HTTPException(status_code=404, detail="Escalation not found")
    return esc


@router.post("/support/escalations/{escalation_id}/resolve")
async def resolve_escalation(escalation_id: str):
    from app.support.escalation_service import escalation_service
    esc = await asyncio.to_thread(escalation_service.resolve_escalation, escalation_id)
    if not esc:
        raise HTTPException(status_code=404, detail="Escalation not found")
    return esc


# ─── Feedback ─────────────────────────────────────────────────────────

@router.post("/support/feedback")
async def submit_feedback(body: FeedbackCreate):
    import uuid as _uuid
    from datetime import datetime, timezone
    from app.support.ticket_service import ticket_service
    ticket = await asyncio.to_thread(ticket_service.get_ticket, body.ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {
        "id": str(_uuid.uuid4()), "ticket_id": body.ticket_id,
        "customer_id": body.customer_id, "feedback_type": body.feedback_type.value,
        "rating": body.rating, "comment": body.comment,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


# ─── Automation ───────────────────────────────────────────────────────

@router.post("/support/automation/run")
async def create_automation_run(body: AutomationRunCreate):
    from app.support.automation_service import automation_service
    return await asyncio.to_thread(
        automation_service.create_run, body.ticket_id, body.action,
        input_data=body.input_data,
    )


@router.post("/support/automation/{run_id}/approve")
async def approve_automation_run(run_id: str, body: AutomationApproval):
    from app.support.automation_service import automation_service
    run = await asyncio.to_thread(
        automation_service.approve_run, run_id, approved=body.approved,
        approved_by=body.approved_by, reason=body.reason,
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found or not awaiting approval")
    return run


@router.get("/support/automation/pending")
async def pending_approvals():
    from app.support.automation_service import automation_service
    return await asyncio.to_thread(automation_service.get_pending_approvals)


# ─── AI Support ───────────────────────────────────────────────────────

@router.post("/support/tickets/{ticket_id}/classify")
async def classify_ticket(ticket_id: str):
    from app.support.ticket_service import ticket_service
    from app.support.classification_service import classification_service
    ticket = await asyncio.to_thread(ticket_service.get_ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    result = await asyncio.to_thread(
        classification_service.classify_ticket, ticket["subject"], ticket["description"],
        service_affected=ticket.get("service_affected"),
    )
    return result


@router.get("/support/tickets/{ticket_id}/ai-suggest")
async def ai_suggest_response(ticket_id: str):
    from app.support.ticket_service import ticket_service
    from app.support.knowledge_service import knowledge_service
    ticket = await asyncio.to_thread(ticket_service.get_ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    articles = await asyncio.to_thread(
        knowledge_service.search_articles, ticket["subject"], tenant_id="default", limit=3,
    )
    evidence = [a["article"]["title"] for a in articles]
    return {
        "answer": f"Based on our knowledge base, here are suggestions for: {ticket['subject']}",
        "evidence": evidence, "confidence": 0.7,
        "escalation_recommended": False, "citations": [],
    }


# ─── Customer Portal ──────────────────────────────────────────────────

@router.get("/support/customer/{customer_id}/tickets")
async def customer_tickets(customer_id: str, limit: int = Query(50, ge=1, le=200)):
    from app.support.ticket_service import ticket_service
    return await asyncio.to_thread(
        ticket_service.list_tickets, customer_id=customer_id, limit=limit,
    )


# ─── Status Page ──────────────────────────────────────────────────────

@router.get("/support/status")
async def service_status():
    return {
        "services": [
            {"name": "API", "status": "operational"},
            {"name": "AI Engine", "status": "operational"},
            {"name": "Knowledge Base", "status": "operational"},
            {"name": "Notifications", "status": "operational"},
        ],
        "overall_status": "operational",
    }


# ─── Analytics ────────────────────────────────────────────────────────

@router.get("/support/analytics")
async def support_analytics():
    from app.support.ticket_service import ticket_service
    from app.support.message_service import message_service
    from app.support.classification_service import classification_service
    from app.support.sla_service import sla_service
    from app.support.knowledge_service import knowledge_service
    from app.support.escalation_service import escalation_service
    return {
        "tickets": await asyncio.to_thread(ticket_service.get_telemetry),
        "messages": await asyncio.to_thread(message_service.get_telemetry),
        "classification": await asyncio.to_thread(classification_service.get_telemetry),
        "sla": await asyncio.to_thread(sla_service.get_telemetry),
        "knowledge": await asyncio.to_thread(knowledge_service.get_telemetry),
        "escalations": await asyncio.to_thread(escalation_service.get_telemetry),
    }


# ─── Routing ──────────────────────────────────────────────────────────

@router.get("/support/routing/queues")
async def routing_queues():
    from app.support.routing_service import routing_service
    return await asyncio.to_thread(routing_service.get_team_queues)
