"""Volume 57 — Data Governance models (14 tables, additive-only)."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from app.core.database import Base, TimestampMixin


class GovernanceDataAsset(Base, TimestampMixin):
    __tablename__ = "governance_data_assets"

    asset_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    workspace: Mapped[str | None] = mapped_column(String(64), nullable=True)
    project: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource: Mapped[str] = mapped_column(String(256), nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    classification: Mapped[str] = mapped_column(String(32), default="INTERNAL", nullable=False)
    source: Mapped[str | None] = mapped_column(String(256), nullable=True)
    location: Mapped[str | None] = mapped_column(String(512), nullable=True)
    retention_policy: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sensitivity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (Index("ix_gov_assets_tenant_asset", "tenant", "asset_id", unique=True),)


class GovernanceClassification(Base, TimestampMixin):
    __tablename__ = "governance_classifications"

    asset_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.95, nullable=False)
    advisory: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    classified_by: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (Index("ix_gov_class_tenant_asset", "tenant", "asset_id"),)


class GovernanceLineage(Base, TimestampMixin):
    __tablename__ = "governance_lineage"

    source_asset: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    target_asset: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    transformation: Mapped[str] = mapped_column(String(128), nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (Index("ix_gov_lineage_src_tgt", "source_asset", "target_asset"),)


class GovernanceRetentionPolicy(Base, TimestampMixin):
    __tablename__ = "governance_retention_policies"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource: Mapped[str | None] = mapped_column(String(128), nullable=True)
    classification: Mapped[str | None] = mapped_column(String(32), nullable=True)
    data_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    environment: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False, default="delete")
    state: Mapped[str] = mapped_column(String(32), default="ACTIVE", nullable=False)

    __table_args__ = (Index("ix_gov_retention_tenant", "tenant"),)


class GovernanceDataRequest(Base, TimestampMixin):
    __tablename__ = "governance_data_requests"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    request_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject: Mapped[str] = mapped_column(String(256), nullable=False)
    scope: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    verification_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    approval_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    systems: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    completion: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    exceptions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    requested_by: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (Index("ix_gov_requests_tenant_type", "tenant", "request_type"),)


class GovernanceExport(Base, TimestampMixin):
    __tablename__ = "governance_exports"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("governance_data_requests.id", ondelete="SET NULL"), nullable=True)
    requester: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    data_sources: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    format: Mapped[str] = mapped_column(String(32), default="json", nullable=False)
    token_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)

    __table_args__ = (Index("ix_gov_exports_tenant", "tenant"),)


class GovernanceProcessor(Base, TimestampMixin):
    __tablename__ = "governance_processors"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    purpose: Mapped[str] = mapped_column(String(256), nullable=False)
    data_categories: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    region: Mapped[str | None] = mapped_column(String(32), nullable=True)
    contract_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    access_grants: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    __table_args__ = (Index("ix_gov_processors_tenant_provider", "tenant", "provider"),)


class GovernanceConsent(Base, TimestampMixin):
    __tablename__ = "governance_consents"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(256), nullable=False)
    purpose: Mapped[str] = mapped_column(String(128), nullable=False)
    scope: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    version: Mapped[str] = mapped_column(String(32), default="1.0", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="granted", nullable=False)

    __table_args__ = (Index("ix_gov_consents_tenant_subject", "tenant", "subject"),)


class GovernancePolicyDecision(Base, TimestampMixin):
    __tablename__ = "governance_policy_decisions"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    resource: Mapped[str] = mapped_column(String(256), nullable=False)
    policy_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    policy_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (Index("ix_gov_decisions_tenant", "tenant"),)


class GovernanceControl(Base, TimestampMixin):
    __tablename__ = "governance_controls"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    framework: Mapped[str] = mapped_column(String(64), nullable=False)
    control_id: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    implementation: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="NOT_ASSESSED", nullable=False)

    __table_args__ = (Index("ix_gov_controls_tenant_framework", "tenant", "framework"), UniqueConstraint("tenant", "control_id", name="uq_gov_controls_tenant_control"))


class GovernanceControlEvidence(Base, TimestampMixin):
    __tablename__ = "governance_control_evidence"

    control_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("governance_controls.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    evidence_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(256), nullable=False)
    hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (Index("ix_gov_evidence_control", "control_id"),)


class GovernanceLegalHold(Base, TimestampMixin):
    __tablename__ = "governance_legal_holds"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(256), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    released_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    audit: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    __table_args__ = (Index("ix_gov_holds_tenant", "tenant"),)


class GovernanceException(Base, TimestampMixin):
    __tablename__ = "governance_exceptions"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    policy_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource: Mapped[str | None] = mapped_column(String(256), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    owner: Mapped[str] = mapped_column(String(64), nullable=False)
    approval: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_gov_exceptions_tenant", "tenant"),)


class GovernanceDLPEvent(Base, TimestampMixin):
    __tablename__ = "governance_dlp_events"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource: Mapped[str | None] = mapped_column(String(256), nullable=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)

    __table_args__ = (Index("ix_gov_dlp_tenant", "tenant"),)
