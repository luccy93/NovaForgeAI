"""Central governance plane records — Volume 71 Commit 1.

PostgreSQL-authoritative policy-as-code plane. Table names use the
`governance_plane_*` prefix deliberately: `governance_controls`,
`governance_control_evidence`, `governance_exceptions` and
`governance_policy_decisions` already belong to the V57 datagov
package and are reused (never duplicated) for data-domain controls.
Every record is tenant-scoped. No secrets or raw payloads stored.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GovernancePlanePolicy(Base, TimestampMixin):
    __tablename__ = "governance_plane_policies"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    domain: Mapped[str] = mapped_column(String(32), nullable=False, default="general")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    owner: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")
    active_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant", "name", name="uq_governance_plane_policy"),
        Index("ix_governance_plane_policy_status", "tenant", "status"),
    )


class GovernancePlanePolicyVersion(Base, TimestampMixin):
    """Immutable policy version. Rows are never mutated once ACTIVE."""

    __tablename__ = "governance_plane_policy_versions"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    policy_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    effective_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rules: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    default_effect: Mapped[str] = mapped_column(String(16), nullable=False, default="deny")
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    reason: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant", "policy_id", "version", name="uq_governance_plane_version"),
        Index("ix_governance_plane_version_status", "tenant", "status"),
    )


class GovernancePlaneBinding(Base, TimestampMixin):
    __tablename__ = "governance_plane_bindings"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    policy_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    version_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_value: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant", "policy_id", "scope_type", "scope_value",
                         name="uq_governance_plane_binding"),
        Index("ix_governance_plane_binding_scope", "tenant", "scope_type"),
    )


class GovernancePlaneEvaluation(Base, TimestampMixin):
    __tablename__ = "governance_plane_evaluations"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    scope_value: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    operation: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    policy_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    version_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        Index("ix_governance_plane_eval_tenant_op", "tenant", "operation"),
    )


class GovernancePlaneDecision(Base, TimestampMixin):
    __tablename__ = "governance_plane_decisions"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    evaluation_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    policy_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    version_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    binding_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    rule_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    scope_value: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reason: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    obligations: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    approval_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    actor: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        Index("ix_governance_plane_decision_policy", "tenant", "policy_id"),
    )


class GovernancePlaneException(Base, TimestampMixin):
    __tablename__ = "governance_plane_exceptions"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    policy_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    scope_value: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    justification: Mapped[str] = mapped_column(Text, nullable=False, default="")
    requester: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    approver: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    max_duration_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    high_risk: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        Index("ix_governance_plane_exception_status", "tenant", "status"),
    )


class GovernancePlaneExceptionApproval(Base, TimestampMixin):
    __tablename__ = "governance_plane_exception_approvals"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    exception_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    approval_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    approval_type: Mapped[str] = mapped_column(String(16), nullable=False, default="jit")
    approver: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    decision: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        Index("ix_governance_plane_exc_approval", "tenant", "exception_id"),
    )


class GovernancePlanePostureSnapshot(Base, TimestampMixin):
    __tablename__ = "governance_plane_posture_snapshots"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False, default="tenant")
    scope_value: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    domain: Mapped[str] = mapped_column(String(32), nullable=False, default="general")
    total_policies: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_policies: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    violations_24h: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    open_exceptions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    verified_controls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failing_controls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        Index("ix_governance_plane_posture_scope", "tenant", "scope_type", "domain"),
    )
