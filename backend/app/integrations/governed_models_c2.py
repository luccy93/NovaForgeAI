"""Governed integration intelligence records — Volume 70 Commit 2.

OAuth connections, connector syncs, inbound webhook receipts,
governance policies. Tokens live only as Fernet ciphertext (or as
references); serializers never emit them. Chargeback reuses V69
FinOps reports; audit reuses integration_audit_log.
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


class IntegrationOAuthConnection(Base, TimestampMixin):
    __tablename__ = "integration_oauth_connections"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    integration_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    connection_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    client_id: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    scopes: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    redirect_uri: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    state: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    encrypted_verifier: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    encrypted_access: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    encrypted_refresh: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    token_ref: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant", "state", name="uq_oauth_state"),
        Index("ix_oauth_tenant_status", "tenant", "status"),
    )


class IntegrationConnectorSync(Base, TimestampMixin):
    __tablename__ = "integration_connector_syncs"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    connection_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    sync_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="STARTED")
    pages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant", "sync_key", name="uq_connector_sync"),
        Index("ix_connector_sync_connection", "tenant", "connection_id"),
    )


class IntegrationInboundWebhook(Base, TimestampMixin):
    __tablename__ = "integration_inbound_webhooks"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    webhook_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    delivery_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="RECEIVED")
    approval_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant", "delivery_id", name="uq_inbound_webhook"),
        Index("ix_inbound_webhook", "tenant", "webhook_id"),
    )


class IntegrationPolicy(Base, TimestampMixin):
    __tablename__ = "integration_policies"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    workspace: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    project: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    operation: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    action: Mapped[str] = mapped_column(String(32), nullable=False, default="alert")
    allowed_classifications: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    allowed_regions: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    allowed_fields: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    max_estimated_cents: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    owner: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant", "name", name="uq_integration_policy"),
        Index("ix_integration_policy_tenant_enabled", "tenant", "enabled"),
    )
