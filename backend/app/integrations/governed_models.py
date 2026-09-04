"""Governed integration records — Volume 70 Commit 1.

PostgreSQL-authoritative integration metadata and state. Credential
material is never stored raw: references point at encrypted rows managed
through the existing EncryptionService, and serializers never emit
secret material. Every record is tenant-scoped.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Integration(Base, TimestampMixin):
    __tablename__ = "integrations"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="", index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0.0")
    workspace: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    environment: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    region: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    capabilities: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    health: Mapped[str] = mapped_column(String(16), nullable=False, default="UNKNOWN")
    config: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    owner: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant", "name", name="uq_integrations_tenant_name"),
        Index("ix_integrations_tenant_status", "tenant", "status"),
    )


class IntegrationVersion(Base, TimestampMixin):
    __tablename__ = "integration_versions"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    integration_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    contract: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    compatibility: Mapped[str] = mapped_column(String(16), nullable=False, default="compatible")
    deprecated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    migration_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant", "integration_id", "version", name="uq_integration_version"),
    )


class IntegrationConnection(Base, TimestampMixin):
    __tablename__ = "integration_connections"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    integration_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    workspace: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    environment: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    endpoint_ref: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    credential_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    scopes: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    health: Mapped[str] = mapped_column(String(16), nullable=False, default="UNKNOWN")
    last_success_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        Index("ix_integration_connections_tenant_status", "tenant", "status"),
    )


class IntegrationCredential(Base, TimestampMixin):
    """Credential metadata. Raw material lives only in `encrypted_material`
    (Fernet ciphertext) and is never serialized, logged, or emitted."""

    __tablename__ = "integration_credentials"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    connection_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    secret_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    encrypted_material: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    material_hint: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    scopes: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        Index("ix_integration_credentials_tenant_status", "tenant", "status"),
    )


class IntegrationExecution(Base, TimestampMixin):
    __tablename__ = "integration_executions"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    connection_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    method: Mapped[str] = mapped_column(String(16), nullable=False, default="GET")
    endpoint_ref: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="SUCCESS")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    request_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    response_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant", "idempotency_key", name="uq_integration_execution"),
        Index("ix_integration_executions_connection", "tenant", "connection_id"),
    )


class IntegrationHealthCheck(Base, TimestampMixin):
    __tablename__ = "integration_health_checks"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    integration_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    connection_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="UNKNOWN")
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        Index("ix_integration_health_integration", "tenant", "integration_id"),
    )


class IntegrationWebhook(Base, TimestampMixin):
    __tablename__ = "integration_webhooks"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    integration_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    events: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    credential_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant", "name", name="uq_integration_webhook"),
        Index("ix_integration_webhooks_tenant_status", "tenant", "status"),
    )


class IntegrationWebhookDelivery(Base, TimestampMixin):
    __tablename__ = "integration_webhook_deliveries"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    webhook_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    delivery_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    response_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant", "delivery_id", name="uq_webhook_delivery"),
        Index("ix_webhook_delivery_webhook_status", "tenant", "webhook_id", "status"),
    )


class IntegrationApiSubscription(Base, TimestampMixin):
    __tablename__ = "integration_api_subscriptions"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    connection_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    event_filter: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    target_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    credential_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        Index("ix_api_subscriptions_tenant_status", "tenant", "status"),
    )


class IntegrationAuditLog(Base, TimestampMixin):
    __tablename__ = "integration_audit_log"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    details: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="SUCCESS")

    __table_args__ = (
        Index("ix_integration_audit_tenant_action", "tenant", "action"),
    )
