"""Workflow models — Volume 66 Commit 1 (8 tables, additive, FK to workflow_versions.id)."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Text, Integer, Float, Boolean, DateTime, Index, UniqueConstraint, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class WorkflowDefinition(Base, TimestampMixin):
    __tablename__ = "workflow_definitions"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    workspace: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0")
    owner: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")  # DRAFT|ACTIVE|PAUSED|DEPRECATED|RETIRED
    current_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant", "name", name="uq_workflow_definitions_tenant_name"),
        Index("ix_workflow_definitions_tenant_status", "tenant", "status"),
    )


class WorkflowVersion(Base, TimestampMixin):
    __tablename__ = "workflow_versions"

    workflow_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workflow_definitions.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    definition: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)  # steps, dependencies, inputs/outputs, conditions, timeouts, retry, approvals
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")
    dag_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint("workflow_id", "version", name="uq_workflow_versions_workflow_version"),
        Index("ix_workflow_versions_tenant_status", "tenant", "status"),
    )


class WorkflowRun(Base, TimestampMixin):
    __tablename__ = "workflow_runs"

    workflow_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workflow_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    workflow_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)  # legacy convenience
    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    execution_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    trigger: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")  # PENDING|RUNNING|WAITING|PAUSED|FAILED|COMPENSATING|COMPLETED|CANCELLED|TIMED_OUT
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="NORMAL")
    region: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    trace_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    checkpoints: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, unique=True, index=True)

    __table_args__ = (
        Index("ix_workflow_runs_tenant_status", "tenant", "status"),
        Index("ix_workflow_runs_workflow_version", "workflow_version_id"),
    )


class WorkflowStepRun(Base, TimestampMixin):
    __tablename__ = "workflow_step_runs"

    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    step_id: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    input_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    output_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    worker_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_step_runs_run_step", "run_id", "step_id"),
    )


class WorkflowSchedule(Base, TimestampMixin):
    __tablename__ = "workflow_schedules"

    workflow_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workflow_definitions.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    cron: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    interval_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    event_filter: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False, default="schedule")  # once|interval|cron|event
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_tick: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_schedules_tenant_enabled", "tenant", "enabled"),
    )


class WorkflowApproval(Base, TimestampMixin):
    __tablename__ = "workflow_approvals"

    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    step_id: Mapped[str] = mapped_column(String(64), nullable=False)
    workflow_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workflow_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    workflow_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    requester: Mapped[str] = mapped_column(String(64), nullable=False)
    approver: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    scope: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expiry: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")  # PENDING|APPROVED|DENIED|EXPIRED|CANCELLED
    decision: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    binding_hash: Mapped[str] = mapped_column(String(128), nullable=False)

    __table_args__ = (
        Index("ix_approvals_tenant_status", "tenant", "status"),
    )


class WorkflowCheckpoint(Base, TimestampMixin):
    __tablename__ = "workflow_checkpoints"

    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    step_id: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    can_resume: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index("ix_checkpoints_run_step", "run_id", "step_id"),
    )


class WorkflowCompensation(Base, TimestampMixin):
    __tablename__ = "workflow_compensations"

    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    step_id: Mapped[str] = mapped_column(String(64), nullable=False)
    original_step_id: Mapped[str] = mapped_column(String(64), nullable=False)
    handler: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index("ix_compensations_run", "run_id"),
    )
