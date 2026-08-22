"""IAM SQLAlchemy models — extends existing models with enterprise multi-tenancy."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, String, Text, Table, Column, Index, Float, Enum as SAEnum
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin


class Workspace(Base, TimestampMixin):
    __tablename__ = "iam_workspaces"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    settings: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    organization = relationship("Organization")
    projects = relationship("Project", back_populates="workspace", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_iam_workspaces_org_id", "organization_id"),
        Index("ix_iam_workspaces_org_slug", "organization_id", "slug", unique=True),
    )


class IAMProject(Base, TimestampMixin):
    __tablename__ = "iam_projects"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iam_workspaces.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    settings: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    workspace = relationship("Workspace", back_populates="projects")

    __table_args__ = (
        Index("ix_iam_projects_org_id", "organization_id"),
        Index("ix_iam_projects_workspace_id", "workspace_id"),
        Index("ix_iam_projects_workspace_slug", "workspace_id", "slug", unique=True),
    )


class Team(Base, TimestampMixin):
    __tablename__ = "iam_teams"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    parent_team_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("iam_teams.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    organization = relationship("Organization")
    parent_team = relationship("Team", remote_side="Team.id", backref="child_teams")

    __table_args__ = (
        Index("ix_iam_teams_org_id", "organization_id"),
        Index("ix_iam_teams_parent_id", "parent_team_id"),
    )


team_members = Table(
    "iam_team_members",
    Base.metadata,
    Column("team_id", UUID(as_uuid=True), ForeignKey("iam_teams.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role", String(50), default="member", nullable=False),
    Column("created_at", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
    Index("ix_iam_team_members_team_id", "team_id"),
    Index("ix_iam_team_members_user_id", "user_id"),
)


class IAMMembership(Base, TimestampMixin):
    __tablename__ = "iam_memberships"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(50), default="viewer", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    invited_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    invited_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    suspended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    suspension_reason: Mapped[Optional[str]] = mapped_column(Text)

    user = relationship("User", foreign_keys=[user_id])
    organization = relationship("Organization")
    inviter = relationship("User", foreign_keys=[invited_by])

    __table_args__ = (
        Index("ix_iam_memberships_user_id", "user_id"),
        Index("ix_iam_memberships_org_id", "organization_id"),
        Index("ix_iam_memberships_user_org", "user_id", "organization_id", unique=True),
    )


class IAMRole(Base, TimestampMixin):
    __tablename__ = "iam_roles"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    permissions: Mapped[dict] = mapped_column(JSONB, default=list)
    inherits_from: Mapped[Optional[dict]] = mapped_column(JSONB, default=list)
    metadata: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    organization = relationship("Organization")

    __table_args__ = (
        Index("ix_iam_roles_org_id", "organization_id"),
        Index("ix_iam_roles_org_name", "organization_id", "name", unique=True),
    )


class ResourcePolicy(Base, TimestampMixin):
    __tablename__ = "iam_resource_policies"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    effect: Mapped[str] = mapped_column(String(20), default="allow", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    resource_scope: Mapped[str] = mapped_column(String(50), default="organization", nullable=False)
    conditions: Mapped[dict] = mapped_column(JSONB, default=list)
    principals: Mapped[dict] = mapped_column(JSONB, default=list)
    actions: Mapped[dict] = mapped_column(JSONB, default=list)
    metadata: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    organization = relationship("Organization")

    __table_args__ = (
        Index("ix_iam_resource_policies_org_id", "organization_id"),
        Index("ix_iam_resource_policies_scope", "resource_scope"),
    )


class IAMServiceAccount(Base, TimestampMixin):
    __tablename__ = "iam_service_accounts"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    client_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    client_secret_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    scopes: Mapped[dict] = mapped_column(JSONB, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_rotated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    max_usage: Mapped[Optional[int]] = mapped_column(Integer)
    current_usage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    organization = relationship("Organization")

    __table_args__ = (
        Index("ix_iam_service_accounts_org_id", "organization_id"),
    )


class IAMAPIKey(Base, TimestampMixin):
    __tablename__ = "iam_api_keys"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    key_prefix: Mapped[str] = mapped_column(String(10), nullable=False)
    scopes: Mapped[dict] = mapped_column(JSONB, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    revocation_reason: Mapped[Optional[str]] = mapped_column(Text)
    last_rotated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    organization = relationship("Organization")
    user = relationship("User")

    __table_args__ = (
        Index("ix_iam_api_keys_org_id", "organization_id"),
        Index("ix_iam_api_keys_user_id", "user_id"),
    )


class IAMSession(Base, TimestampMixin):
    __tablename__ = "iam_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    session_token: Mapped[str] = mapped_column(String(500), unique=True, nullable=False, index=True)
    refresh_token: Mapped[Optional[str]] = mapped_column(String(500), index=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(String(500))
    device_fingerprint: Mapped[Optional[str]] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    revocation_reason: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auth_method: Mapped[str] = mapped_column(String(50), default="password", nullable=False)

    user = relationship("User")

    __table_args__ = (
        Index("ix_iam_sessions_user_id", "user_id"),
        Index("ix_iam_sessions_expires_at", "expires_at"),
    )


class IdentityProvider(Base, TimestampMixin):
    __tablename__ = "iam_identity_providers"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    protocol: Mapped[str] = mapped_column(String(50), nullable=False)
    issuer: Mapped[Optional[str]] = mapped_column(String(500))
    client_id: Mapped[Optional[str]] = mapped_column(String(255))
    client_secret_encrypted: Mapped[Optional[str]] = mapped_column(String(500))
    metadata_url: Mapped[Optional[str]] = mapped_column(String(500))
    certificate: Mapped[Optional[str]] = mapped_column(Text)
    attribute_mapping: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    group_mapping: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    sync_status: Mapped[str] = mapped_column(String(50), default="idle", nullable=False)
    config_validated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    organization = relationship("Organization")

    __table_args__ = (
        Index("ix_iam_idp_org_id", "organization_id"),
    )


class AccessRequest(Base, TimestampMixin):
    __tablename__ = "iam_access_requests"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    permission: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[Optional[str]] = mapped_column(String(255))
    resource_type: Mapped[Optional[str]] = mapped_column(String(100))
    justification: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    review_reason: Mapped[Optional[str]] = mapped_column(Text)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    user = relationship("User", foreign_keys=[user_id])
    reviewer = relationship("User", foreign_keys=[reviewed_by])
    organization = relationship("Organization")

    __table_args__ = (
        Index("ix_iam_access_requests_org_id", "organization_id"),
        Index("ix_iam_access_requests_user_id", "user_id"),
        Index("ix_iam_access_requests_status", "status"),
    )


class BreakGlassSession(Base, TimestampMixin):
    __tablename__ = "iam_break_glass_sessions"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[dict] = mapped_column(JSONB, default=list)
    resource_id: Mapped[Optional[str]] = mapped_column(String(255))
    resource_type: Mapped[Optional[str]] = mapped_column(String(100))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    mfa_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    end_reason: Mapped[Optional[str]] = mapped_column(Text)

    user = relationship("User", foreign_keys=[user_id])
    approver = relationship("User", foreign_keys=[approved_by])
    organization = relationship("Organization")

    __table_args__ = (
        Index("ix_iam_break_glass_org_id", "organization_id"),
        Index("ix_iam_break_glass_user_id", "user_id"),
    )


class QuotaPolicy(Base, TimestampMixin):
    __tablename__ = "iam_quota_policies"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    quota_type: Mapped[str] = mapped_column(String(100), nullable=False)
    limit: Mapped[int] = mapped_column(Integer, nullable=False)
    used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    period: Mapped[str] = mapped_column(String(20), default="monthly", nullable=False)
    period_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    organization = relationship("Organization")

    __table_args__ = (
        Index("ix_iam_quota_policies_org_id", "organization_id"),
        Index("ix_iam_quota_policies_org_type", "organization_id", "quota_type", unique=True),
    )


class DomainVerification(Base, TimestampMixin):
    __tablename__ = "iam_domain_verifications"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    verification_token: Mapped[str] = mapped_column(String(255), nullable=False)
    method: Mapped[str] = mapped_column(String(50), default="dns", nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    organization = relationship("Organization")

    __table_args__ = (
        Index("ix_iam_domain_verifications_org_id", "organization_id"),
        Index("ix_iam_domain_verifications_domain", "domain", unique=True),
    )


class IAMAuditLog(Base, TimestampMixin):
    __tablename__ = "iam_audit_logs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_type: Mapped[str] = mapped_column(String(50), default="user", nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[Optional[str]] = mapped_column(String(100))
    resource_id: Mapped[Optional[str]] = mapped_column(String(255))
    result: Mapped[str] = mapped_column(String(20), default="success", nullable=False)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(String(500))
    request_id: Mapped[Optional[str]] = mapped_column(String(255))
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True))
    risk_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    immutable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    actor = relationship("User", foreign_keys=[actor_id])
    organization = relationship("Organization")

    __table_args__ = (
        Index("ix_iam_audit_logs_org_id", "organization_id"),
        Index("ix_iam_audit_logs_actor_id", "actor_id"),
        Index("ix_iam_audit_logs_action", "action"),
        Index("ix_iam_audit_logs_created_at", "created_at"),
    )


class AccessReview(Base, TimestampMixin):
    __tablename__ = "iam_access_reviews"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    review_type: Mapped[str] = mapped_column(String(50), nullable=False)
    scope: Mapped[str] = mapped_column(String(50), default="all", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    initiated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    results: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    stale_items: Mapped[Optional[dict]] = mapped_column(JSONB, default=list)
    actions_taken: Mapped[Optional[dict]] = mapped_column(JSONB, default=list)

    initiator = relationship("User")
    organization = relationship("Organization")

    __table_args__ = (
        Index("ix_iam_access_reviews_org_id", "organization_id"),
    )


class PrivilegeAnalysis(Base, TimestampMixin):
    __tablename__ = "iam_privilege_analyses"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    analysis_type: Mapped[str] = mapped_column(String(50), nullable=False)
    findings: Mapped[dict] = mapped_column(JSONB, default=list)
    recommendations: Mapped[dict] = mapped_column(JSONB, default=list)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    requires_human_approval: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    approved: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    organization = relationship("Organization")
    approver = relationship("User", foreign_keys=[approved_by])

    __table_args__ = (
        Index("ix_iam_privilege_analyses_org_id", "organization_id"),
    )
