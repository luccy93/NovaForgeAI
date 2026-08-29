"""Zero Trust models — Volume 64 (additive-only).

PostgreSQL authoritative for session and credential metadata.
All hashes, never plaintext secrets.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class IAMCredentialsMetadata(Base, TimestampMixin):
    __tablename__ = "iam_credentials_metadata"

    credential_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    credential_type: Mapped[str] = mapped_column(String(32), nullable=False)  # api_key|service_token|workload|agent
    credential_fingerprint: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    credential_status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")  # ACTIVE|PENDING_ROTATION|EXPIRED|REVOKED
    credential_expiry: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rotation_state: Mapped[str] = mapped_column(String(16), nullable=False, default="idle")  # idle|requested|verified|completed
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_type: Mapped[str] = mapped_column(String(32), nullable=False, default="human")
    scope: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    warning_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_iam_credentials_tenant", "tenant_id"),
        Index("ix_iam_credentials_owner", "owner_id"),
        Index("ix_iam_credentials_status", "credential_status"),
    )


class IAMPrivilegedAccess(Base, TimestampMixin):
    __tablename__ = "iam_privileged_access"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    identity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    privilege_level: Mapped[str] = mapped_column(String(16), nullable=False)  # HIGH|CRITICAL
    jit_request_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="REQUESTED")  # REQUESTED|APPROVED|ACTIVE|EXPIRED|REVOKED|DENIED
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)
    approved_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    binding_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    __table_args__ = (
        Index("ix_iam_privileged_tenant", "tenant_id"),
        Index("ix_iam_privileged_identity", "identity_id"),
        Index("ix_iam_privileged_status", "status"),
    )


class IAMIdentityRiskSnapshot(Base, TimestampMixin):
    __tablename__ = "iam_identity_risk_snapshots"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    identity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    identity_type: Mapped[str] = mapped_column(String(32), nullable=False)  # human|service|agent|plugin
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)  # LOW|MEDIUM|HIGH|CRITICAL
    risk_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    factors: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    signals: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    method_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1.0")

    __table_args__ = (
        Index("ix_iam_risk_tenant", "tenant_id"),
        Index("ix_iam_risk_identity", "identity_id"),
    )
