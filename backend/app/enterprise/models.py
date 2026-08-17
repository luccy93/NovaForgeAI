"""Enterprise Integration models — Volume 40: Identity & External Integrations.

PostgreSQL models for integration registry, SSO (OIDC/SAML), SCIM provisioning,
directory sync, source control adapters, and token management.

All models use UUID primary keys, JSONB for flexible config, and enforce
tenant isolation via organization_id.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Text, Boolean, Integer, Float, DateTime, ForeignKey,
    UniqueConstraint, Index, JSON, Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base, TimestampMixin


# ─── Enums ─────────────────────────────────────────────────────────────────

class IntegrationProvider(str):
    GITHUB = "github"
    GITLAB = "gitlab"
    BITBUCKET = "bitbucket"
    JIRA = "jira"
    SLACK = "slack"
    TEAMS = "microsoft_teams"
    GOOGLE_WORKSPACE = "google_workspace"
    MICROSOFT_365 = "microsoft_365"
    OIDC = "oidc"
    SAML = "saml"
    SCIM = "scim"
    EMAIL = "email"
    CALENDAR = "calendar"
    CUSTOM = "custom"


class ConnectionStatus(str):
    CREATED = "created"
    CONNECTED = "connected"
    ACTIVE = "active"
    DEGRADED = "degraded"
    REAUTHORIZATION_REQUIRED = "reauthorization_required"
    DISCONNECTED = "disconnected"
    REVOKED = "revoked"


class SyncStatus(str):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SSOProtocol(str):
    OIDC = "oidc"
    SAML = "saml"
    PASSWORD = "password"


# ─── Enterprise Integration Registry ───────────────────────────────────────

class EnterpriseIntegration(TimestampMixin, Base):
    """Central registry for all enterprise integrations."""
    __tablename__ = "enterprise_integrations"

    organization_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    provider = Column(String(100), nullable=False, index=True)
    category = Column(String(50), nullable=False, index=True)
    status = Column(String(30), nullable=False, default=ConnectionStatus.CREATED)
    description = Column(Text, default="")
    version = Column(String(20), default="1.0.0")

    owner_id = Column(UUID(as_uuid=True), nullable=True)

    scopes_requested = Column(JSONB, default=list)
    scopes_granted = Column(JSONB, default=list)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    health_status = Column(String(30), default="unknown")
    health_checked_at = Column(DateTime(timezone=True), nullable=True)
    health_details = Column(JSONB, default=dict)

    config = Column(JSONB, default=dict)
    metadata_ = Column("metadata", JSONB, default=dict)

    is_active = Column(Boolean, default=True)

    __table_args__ = (
        Index("ix_ei_org_provider", "organization_id", "provider"),
    )


class IntegrationConnection(TimestampMixin, Base):
    """OAuth/API token connections for each integration instance."""
    __tablename__ = "integration_connections"

    integration_id = Column(UUID(as_uuid=True), ForeignKey("enterprise_integrations.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    provider = Column(String(100), nullable=False)
    status = Column(String(30), nullable=False, default=ConnectionStatus.CREATED)

    access_token_ref = Column(Text, nullable=True)
    refresh_token_ref = Column(Text, nullable=True)
    token_type = Column(String(50), default="Bearer")
    expires_at = Column(DateTime(timezone=True), nullable=True)
    scopes = Column(JSONB, default=list)

    provider_user_id = Column(String(255), nullable=True)
    provider_username = Column(String(255), nullable=True)
    provider_email = Column(String(255), nullable=True)

    device_info = Column(JSONB, default=dict)
    last_rotated_at = Column(DateTime(timezone=True), nullable=True)

    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)

    __table_args__ = (
        Index("ix_ic_org_provider", "organization_id", "provider"),
    )


class IntegrationScope(Base):
    """Declarative scope definitions per integration type."""
    __tablename__ = "integration_scopes"

    provider = Column(String(100), nullable=False, index=True)
    scope_name = Column(String(100), nullable=False)
    description = Column(Text, default="")
    permission_level = Column(String(20), default="read")
    is_required = Column(Boolean, default=False)
    is_dangerous = Column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint("provider", "scope_name", name="uq_provider_scope"),
    )


class IntegrationSyncJob(TimestampMixin, Base):
    """Tracks synchronization jobs between NovaForge and external providers."""
    __tablename__ = "integration_sync_jobs"

    integration_id = Column(UUID(as_uuid=True), ForeignKey("enterprise_integrations.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    sync_type = Column(String(50), nullable=False)
    status = Column(String(30), nullable=False, default=SyncStatus.PENDING)
    trigger = Column(String(30), default="manual")

    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Float, default=0.0)

    records_processed = Column(Integer, default=0)
    records_created = Column(Integer, default=0)
    records_updated = Column(Integer, default=0)
    records_deleted = Column(Integer, default=0)

    error_message = Column(Text, nullable=True)
    errors = Column(JSONB, default=list)

    idempotency_key = Column(String(255), nullable=True, index=True)
    resumable = Column(Boolean, default=True)
    checkpoint_data = Column(JSONB, default=dict)


class IntegrationEvent(TimestampMixin, Base):
    """Normalized integration events from external providers."""
    __tablename__ = "integration_events"

    integration_id = Column(UUID(as_uuid=True), ForeignKey("enterprise_integrations.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    event_type = Column(String(100), nullable=False, index=True)
    provider_event_id = Column(String(255), nullable=True)
    source = Column(String(100), nullable=False)
    severity = Column(String(20), default="info")

    payload = Column(JSONB, default=dict)
    normalized_payload = Column(JSONB, default=dict)

    idempotency_key = Column(String(255), nullable=True, index=True)
    processed = Column(Boolean, default=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)

    correlation_id = Column(String(255), nullable=True, index=True)


class IntegrationHealth(Base):
    """Health monitoring for integration providers."""
    __tablename__ = "integration_provider_health"

    provider = Column(String(100), nullable=False, index=True)
    organization_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    authentication_ok = Column(Boolean, default=True)
    api_available = Column(Boolean, default=True)
    rate_limit_remaining = Column(Integer, default=0)
    rate_limit_reset_at = Column(DateTime(timezone=True), nullable=True)

    webhook_delivery_ok = Column(Boolean, default=True)
    sync_healthy = Column(Boolean, default=True)

    token_expiring_soon = Column(Boolean, default=False)
    token_expires_at = Column(DateTime(timezone=True), nullable=True)

    last_error = Column(Text, nullable=True)
    last_error_at = Column(DateTime(timezone=True), nullable=True)
    error_count_24h = Column(Integer, default=0)

    checked_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


# ─── SSO / Identity ────────────────────────────────────────────────────────

class SSOConnection(TimestampMixin, Base):
    """SSO configuration per organization (OIDC or SAML)."""
    __tablename__ = "sso_connections"

    organization_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    protocol = Column(String(20), nullable=False)
    provider_name = Column(String(255), nullable=False)
    is_enforced = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    # OIDC fields
    oidc_issuer = Column(Text, nullable=True)
    oidc_client_id = Column(Text, nullable=True)
    oidc_client_secret_ref = Column(Text, nullable=True)
    oidc_scopes = Column(JSONB, default=lambda: ["openid", "email", "profile"])
    oidc_discovery_url = Column(Text, nullable=True)
    oidc_authorization_endpoint = Column(Text, nullable=True)
    oidc_token_endpoint = Column(Text, nullable=True)
    oidc_userinfo_endpoint = Column(Text, nullable=True)
    oidc_jwks_uri = Column(Text, nullable=True)
    oidc_end_session_endpoint = Column(Text, nullable=True)

    # SAML fields
    saml_entity_id = Column(Text, nullable=True)
    saml_sso_url = Column(Text, nullable=True)
    saml_slo_url = Column(Text, nullable=True)
    saml_certificate = Column(Text, nullable=True)
    saml_metadata_url = Column(Text, nullable=True)
    saml_signed_requests = Column(Boolean, default=False)
    saml_attribute_mapping = Column(JSONB, default=dict)
    saml_group_mapping = Column(JSONB, default=dict)

    # Common
    allowed_redirect_uris = Column(JSONB, default=list)
    default_role = Column(String(50), default="member")
    jit_provisioning = Column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint("organization_id", "protocol", name="uq_sso_org_protocol"),
    )


class ExternalIdentity(TimestampMixin, Base):
    """Maps external identity provider users to NovaForge users."""
    __tablename__ = "external_identities"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    sso_connection_id = Column(UUID(as_uuid=True), ForeignKey("sso_connections.id", ondelete="CASCADE"), nullable=True)

    provider = Column(String(100), nullable=False)
    provider_user_id = Column(String(255), nullable=False)
    provider_email = Column(String(255), nullable=True)
    provider_username = Column(String(255), nullable=True)
    provider_groups = Column(JSONB, default=list)

    last_login_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_external_identity"),
    )


# ─── SCIM Provisioning ─────────────────────────────────────────────────────

class SCIMDirectory(TimestampMixin, Base):
    """SCIM directory connection per organization."""
    __tablename__ = "scim_directories"

    organization_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    sso_connection_id = Column(UUID(as_uuid=True), ForeignKey("sso_connections.id", ondelete="SET NULL"), nullable=True)

    provider = Column(String(100), nullable=False)
    base_url = Column(Text, nullable=False)
    bearer_token_ref = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)

    sync_status = Column(String(30), default=SyncStatus.PENDING)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_sync_error = Column(Text, nullable=True)

    users_synced = Column(Integer, default=0)
    groups_synced = Column(Integer, default=0)

    config = Column(JSONB, default=dict)


class SCIMUser(TimestampMixin, Base):
    """SCIM-provisioned user record."""
    __tablename__ = "scim_users"

    directory_id = Column(UUID(as_uuid=True), ForeignKey("scim_directories.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    external_id = Column(String(255), nullable=False)
    username = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True)
    display_name = Column(String(255), nullable=True)
    active = Column(Boolean, default=True)

    groups = Column(JSONB, default=list)
    roles = Column(JSONB, default=list)
    raw_scim = Column(JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint("directory_id", "external_id", name="uq_scim_user"),
    )


class SCIMGroup(TimestampMixin, Base):
    """SCIM-provisioned group record."""
    __tablename__ = "scim_groups"

    directory_id = Column(UUID(as_uuid=True), ForeignKey("scim_directories.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    external_id = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=False)
    members = Column(JSONB, default=list)

    mapped_role = Column(String(50), nullable=True)
    mapped_workspace_ids = Column(JSONB, default=list)
    mapped_project_ids = Column(JSONB, default=list)
    mapped_policies = Column(JSONB, default=list)

    raw_scim = Column(JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint("directory_id", "external_id", name="uq_scim_group"),
    )


# ─── Service Accounts & API Keys ──────────────────────────────────────────

class ServiceAccount(TimestampMixin, Base):
    """Machine identity for CI/CD and automation."""
    __tablename__ = "service_accounts"

    organization_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    client_id = Column(String(255), nullable=False, unique=True)
    client_secret_ref = Column(Text, nullable=False)

    scopes = Column(JSONB, default=list)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    last_rotated_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)

    last_used_at = Column(DateTime(timezone=True), nullable=True)
    last_used_ip = Column(String(45), nullable=True)


# ─── Group Mapping ─────────────────────────────────────────────────────────

class GroupMapping(TimestampMixin, Base):
    """Maps external groups to NovaForge roles, workspaces, projects, policies."""
    __tablename__ = "group_mappings"

    organization_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    sso_connection_id = Column(UUID(as_uuid=True), ForeignKey("sso_connections.id", ondelete="CASCADE"), nullable=True)
    scim_directory_id = Column(UUID(as_uuid=True), ForeignKey("scim_directories.id", ondelete="CASCADE"), nullable=True)

    external_group_name = Column(String(255), nullable=False)
    mapped_role = Column(String(50), nullable=True)
    mapped_workspace_ids = Column(JSONB, default=list)
    mapped_project_ids = Column(JSONB, default=list)
    mapped_policies = Column(JSONB, default=list)

    is_active = Column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint("organization_id", "external_group_name", name="uq_group_mapping"),
    )
