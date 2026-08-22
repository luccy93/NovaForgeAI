"""Support & ITSM database models — Volume 54."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    DateTime, Float, Index, Integer, String, Text, Boolean,
    ForeignKey,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin


class SupportTicket(Base, TimestampMixin):
    __tablename__ = "support_tickets"

    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    organization_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    workspace_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    subscription_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="normal", index=True)
    severity: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="new", index=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="web")
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    assigned_team: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    assigned_agent: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    product_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    service_affected: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    environment: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    sentiment_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ai_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ai_classification: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    first_response_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sla_deadline_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    linked_incident_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    linked_issue_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    linked_deployment_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    links: Mapped[Optional[dict]] = mapped_column(JSONB, default=list)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    messages = relationship("SupportMessage", back_populates="ticket", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_support_tickets_tenant_status", "tenant_id", "status"),
        Index("ix_support_tickets_tenant_priority", "tenant_id", "priority"),
        Index("ix_support_tickets_customer", "customer_id", "status"),
    )


class SupportMessage(Base, TimestampMixin):
    __tablename__ = "support_messages"

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sender_id: Mapped[str] = mapped_column(String(100), nullable=False)
    sender_type: Mapped[str] = mapped_column(String(20), nullable=False, default="customer")
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[str] = mapped_column(String(20), nullable=False, default="customer")
    attachments: Mapped[Optional[dict]] = mapped_column(JSONB, default=list)
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    edit_history: Mapped[Optional[dict]] = mapped_column(JSONB, default=list)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ai_citations: Mapped[Optional[dict]] = mapped_column(JSONB, default=list)

    ticket = relationship("SupportTicket", back_populates="messages")

    __table_args__ = (
        Index("ix_support_messages_ticket_sender", "ticket_id", "sender_type"),
    )


class SupportAssignment(Base, TimestampMixin):
    __tablename__ = "support_assignments"

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assigned_to: Mapped[str] = mapped_column(String(100), nullable=False)
    assigned_by: Mapped[str] = mapped_column(String(100), nullable=False)
    team: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    unassigned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class SupportCategory(Base, TimestampMixin):
    __tablename__ = "support_categories"

    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    default_team: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    default_priority: Mapped[str] = mapped_column(String(20), default="normal")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        Index("ix_support_categories_tenant_slug", "tenant_id", "slug", unique=True),
    )


class SupportSLAPolicy(Base, TimestampMixin):
    __tablename__ = "support_sla_policies"

    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    plan_tier: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    first_response_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    resolution_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    update_frequency_minutes: Mapped[int] = mapped_column(Integer, default=1440)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        Index("ix_support_sla_policies_tenant_priority", "tenant_id", "priority"),
    )


class SupportSLATracking(Base, TimestampMixin):
    __tablename__ = "support_sla_tracking"

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("support_sla_policies.id", ondelete="SET NULL"), nullable=True
    )
    sla_state: Mapped[str] = mapped_column(String(20), nullable=False, default="on_track")
    first_response_deadline: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_deadline: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    first_response_met: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    resolution_met: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    paused_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    pause_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    total_pause_seconds: Mapped[int] = mapped_column(Integer, default=0)
    breached_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_support_sla_tracking_ticket", "ticket_id", "sla_state"),
    )


class SupportEscalation(Base, TimestampMixin):
    __tablename__ = "support_escalations"

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    escalation_type: Mapped[str] = mapped_column(String(30), nullable=False)
    triggered_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    from_level: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    to_level: Mapped[str] = mapped_column(String(100), nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)


class SupportAttachment(Base, TimestampMixin):
    __tablename__ = "support_attachments"

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("support_messages.id", ondelete="SET NULL"), nullable=True
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    uploaded_by: Mapped[str] = mapped_column(String(100), nullable=False)
    scan_status: Mapped[str] = mapped_column(String(20), default="pending")
    scan_result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class SupportKnowledgeArticle(Base, TimestampMixin):
    __tablename__ = "support_knowledge_articles"

    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    product: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    owner_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
    source_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    tags: Mapped[Optional[dict]] = mapped_column(JSONB, default=list)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    helpful_count: Mapped[int] = mapped_column(Integer, default=0)
    not_helpful_count: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        Index("ix_support_knowledge_tenant_status", "tenant_id", "status"),
        Index("ix_support_knowledge_tenant_category", "tenant_id", "category"),
    )


class SupportFeedback(Base, TimestampMixin):
    __tablename__ = "support_feedback"

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id: Mapped[str] = mapped_column(String(100), nullable=False)
    feedback_type: Mapped[str] = mapped_column(String(30), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_response_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)


class SupportAutomationRun(Base, TimestampMixin):
    __tablename__ = "support_automation_runs"

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    triggered_by: Mapped[str] = mapped_column(String(100), nullable=False, default="system")
    input_data: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    output_data: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False)
    approval_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
