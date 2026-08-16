"""Audit log, notification, analytics, and other supporting models."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, Index, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.core.database import Base, TimestampMixin


# ─── Audit Log ────────────────────────────────────────────────────────

class AuditAction(enum.Enum):
    LOGIN = "login"
    LOGOUT = "logout"
    REGISTER = "register"
    REPOSITORY_CREATE = "repository_create"
    REPOSITORY_DELETE = "repository_delete"
    REPOSITORY_IMPORT = "repository_import"
    PERMISSION_CHANGE = "permission_change"
    API_KEY_CREATE = "api_key_create"
    API_KEY_DELETE = "api_key_delete"
    SUBSCRIPTION_CHANGE = "subscription_change"
    DEPLOYMENT = "deployment"
    AI_CALL = "ai_call"
    SECURITY_SCAN = "security_scan"
    SETTINGS_CHANGE = "settings_change"
    MEMBER_ADD = "member_add"
    MEMBER_REMOVE = "member_remove"
    ORGANIZATION_CREATE = "organization_create"
    ORGANIZATION_DELETE = "organization_delete"


class AuditLog(Base, TimestampMixin):
    __tablename__ = "audit_logs"

    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[AuditAction] = mapped_column(
        Enum(AuditAction, name="audit_action", create_constraint=True), nullable=False, index=True
    )
    resource_type: Mapped[Optional[str]] = mapped_column(String(100))
    resource_id: Mapped[Optional[str]] = mapped_column(String(255))
    details: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(String(500))
    immutable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        Index("ix_audit_logs_org_id", "organization_id"),
        Index("ix_audit_logs_user_id", "user_id"),
        Index("ix_audit_logs_created_at", "created_at"),
    )


# ─── Notification Channel ─────────────────────────────────────────────

class NotificationChannel(Base, TimestampMixin):
    __tablename__ = "notification_channels"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    channel_type: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="notification_channels")

    __table_args__ = (
        Index("ix_notification_channels_user_id", "user_id"),
    )


# ─── Notification ─────────────────────────────────────────────────────

class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    notification_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    action_url: Mapped[Optional[str]] = mapped_column(String(500))
    extra: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    user: Mapped["User"] = relationship(back_populates="notifications")  # noqa: F821

    __table_args__ = (
        Index("ix_notifications_user_id", "user_id"),
        Index("ix_notifications_read", "user_id", "is_read"),
    )


# ─── Feature Flag ─────────────────────────────────────────────────────

class FeatureFlag(Base, TimestampMixin):
    __tablename__ = "feature_flags"

    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    config: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    __table_args__ = (
        Index("ix_feature_flags_org_name", "organization_id", "name", unique=True),
    )


# ─── App Settings ─────────────────────────────────────────────────────

class AppSetting(Base, TimestampMixin):
    __tablename__ = "app_settings"

    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True
    )
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    scope: Mapped[str] = mapped_column(String(50), default="organization", nullable=False)

    __table_args__ = (
        Index("ix_app_settings_org_key", "organization_id", "key", unique=True),
    )


# ─── Agent Runs ───────────────────────────────────────────────────────

class AgentRun(Base, TimestampMixin):
    __tablename__ = "agent_runs"

    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    pipeline_id: Mapped[Optional[str]] = mapped_column(String(255))
    input: Mapped[Optional[dict]] = mapped_column(JSONB)
    output: Mapped[Optional[dict]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer)
    model_used: Mapped[Optional[str]] = mapped_column(String(100))
    error: Mapped[Optional[str]] = mapped_column(Text)
    extra: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    __table_args__ = (
        Index("ix_agent_runs_org_id", "organization_id"),
        Index("ix_agent_runs_user_id", "user_id"),
        Index("ix_agent_runs_agent_name", "agent_name"),
        Index("ix_agent_runs_status", "status"),
        Index("ix_agent_runs_created_at", "created_at"),
    )


# ─── Analytics Events ─────────────────────────────────────────────────

class AnalyticsEvent(Base, TimestampMixin):
    __tablename__ = "analytics_events"

    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    event_name: Mapped[str] = mapped_column(String(255), nullable=False)
    properties: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    session_id: Mapped[Optional[str]] = mapped_column(String(100))

    __table_args__ = (
        Index("ix_analytics_events_org_id", "organization_id"),
        Index("ix_analytics_events_type", "event_type"),
        Index("ix_analytics_events_created_at", "created_at"),
    )


# ─── Usage Tracking ───────────────────────────────────────────────────

class UsageRecord(Base, TimestampMixin):
    __tablename__ = "usage_records"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    metric: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_usage_records_org_id", "organization_id"),
        Index("ix_usage_records_metric", "metric"),
        Index("ix_usage_records_recorded_at", "recorded_at"),
        Index("ix_usage_records_org_metric", "organization_id", "metric"),
    )


# ─── Security Reports ─────────────────────────────────────────────────

class SecurityReport(Base, TimestampMixin):
    __tablename__ = "security_reports"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    scan_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    findings: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    summary: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)

    __table_args__ = (
        Index("ix_security_reports_repo_id", "repository_id"),
        Index("ix_security_reports_status", "status"),
    )


# ─── Deployment History ───────────────────────────────────────────────

class Deployment(Base, TimestampMixin):
    __tablename__ = "deployments"

    repository_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("repositories.id", ondelete="SET NULL"), nullable=True
    )
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    environment: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    commit_sha: Mapped[Optional[str]] = mapped_column(String(40))
    version: Mapped[Optional[str]] = mapped_column(String(50))
    triggered_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    extra: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    __table_args__ = (
        Index("ix_deployments_repo_id", "repository_id"),
        Index("ix_deployments_status", "status"),
    )
