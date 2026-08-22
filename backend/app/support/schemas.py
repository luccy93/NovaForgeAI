"""Support & ITSM Pydantic schemas — Volume 54."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.support.constants import (
    TicketPriority, TicketCategory, TicketSource, TicketSeverity,
    ArticleStatus, EscalationType, FeedbackType, KnowledgeSource,
)


# ─── Ticket schemas ───────────────────────────────────────────────────

class TicketCreate(BaseModel):
    subject: str = Field(..., max_length=500)
    description: str = ""
    category: Optional[TicketCategory] = None
    priority: TicketPriority = TicketPriority.NORMAL
    severity: Optional[TicketSeverity] = None
    source: TicketSource = TicketSource.WEB
    customer_id: str = Field(..., max_length=100)
    organization_id: Optional[str] = None
    workspace_id: Optional[str] = None
    project_id: Optional[str] = None
    product_version: Optional[str] = None
    service_affected: Optional[str] = None
    environment: Optional[str] = None
    region: Optional[str] = None


class TicketUpdate(BaseModel):
    subject: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = None
    category: Optional[TicketCategory] = None
    priority: Optional[TicketPriority] = None
    severity: Optional[TicketSeverity] = None
    status: Optional[str] = None
    assigned_team: Optional[str] = None
    assigned_agent: Optional[str] = None
    product_version: Optional[str] = None
    service_affected: Optional[str] = None
    environment: Optional[str] = None
    region: Optional[str] = None


class TicketSearch(BaseModel):
    query: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    category: Optional[str] = None
    customer_id: Optional[str] = None
    organization_id: Optional[str] = None
    assigned_agent: Optional[str] = None
    assigned_team: Optional[str] = None
    service_affected: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    limit: int = Field(50, ge=1, le=200)
    offset: int = Field(0, ge=0)


# ─── Message schemas ──────────────────────────────────────────────────

class MessageCreate(BaseModel):
    message_text: str = Field(..., min_length=1)
    sender_id: str = Field(..., max_length=100)
    sender_type: str = Field("customer", max_length=20)
    visibility: str = Field("customer", max_length=20)
    attachments: Optional[list[dict]] = None


# ─── Assignment schemas ───────────────────────────────────────────────

class AssignmentCreate(BaseModel):
    assigned_to: str = Field(..., max_length=100)
    assigned_by: str = Field(..., max_length=100)
    team: Optional[str] = None
    reason: Optional[str] = None


# ─── Escalation schemas ──────────────────────────────────────────────

class EscalationCreate(BaseModel):
    escalation_type: EscalationType
    triggered_by: Optional[str] = None
    reason: str = ""
    to_level: str = Field(..., max_length=100)


# ─── Knowledge article schemas ───────────────────────────────────────

class ArticleCreate(BaseModel):
    title: str = Field(..., max_length=500)
    content: str = ""
    category: str = Field(..., max_length=50)
    product: Optional[str] = Field(None, max_length=100)
    version: Optional[str] = Field(None, max_length=50)
    owner_id: Optional[str] = None
    source_type: Optional[KnowledgeSource] = None
    source_url: Optional[str] = None
    tags: Optional[list[str]] = None
    ai_generated: bool = False
    ai_confidence: Optional[float] = None


class ArticleUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=500)
    content: Optional[str] = None
    category: Optional[str] = Field(None, max_length=50)
    product: Optional[str] = Field(None, max_length=100)
    version: Optional[str] = Field(None, max_length=50)
    status: Optional[ArticleStatus] = None
    source_type: Optional[KnowledgeSource] = None
    source_url: Optional[str] = None
    tags: Optional[list[str]] = None


class ArticleSearch(BaseModel):
    query: str = Field(..., min_length=1)
    category: Optional[str] = None
    product: Optional[str] = None
    status: Optional[ArticleStatus] = ArticleStatus.PUBLISHED
    limit: int = Field(20, ge=1, le=100)


# ─── SLA schemas ─────────────────────────────────────────────────────

class SLAPolicyCreate(BaseModel):
    name: str = Field(..., max_length=200)
    priority: TicketPriority
    category: Optional[TicketCategory] = None
    plan_tier: Optional[str] = None
    first_response_minutes: int = Field(..., gt=0)
    resolution_minutes: int = Field(..., gt=0)
    update_frequency_minutes: int = Field(1440, gt=0)


# ─── Feedback schemas ────────────────────────────────────────────────

class FeedbackCreate(BaseModel):
    ticket_id: str
    customer_id: str
    feedback_type: FeedbackType
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None
    ai_response_id: Optional[str] = None


# ─── AI schemas ──────────────────────────────────────────────────────

class AIClassifyRequest(BaseModel):
    ticket_id: str


class AIResponseRequest(BaseModel):
    ticket_id: str
    approved: bool = False


class AIResponse(BaseModel):
    answer: str
    evidence: list[str]
    next_steps: list[str]
    confidence: float
    escalation_recommended: bool
    escalation_reason: Optional[str] = None
    citations: list[dict] = None


# ─── Link schemas ────────────────────────────────────────────────────

class TicketLinkCreate(BaseModel):
    link_type: str = Field(..., max_length=50)
    target_id: str = Field(..., max_length=100)
    target_url: Optional[str] = None
    description: Optional[str] = None


# ─── Automation schemas ──────────────────────────────────────────────

class AutomationRunCreate(BaseModel):
    ticket_id: str
    action: str
    input_data: Optional[dict] = None


class AutomationApproval(BaseModel):
    run_id: str
    approved: bool
    approved_by: str
    reason: Optional[str] = None
