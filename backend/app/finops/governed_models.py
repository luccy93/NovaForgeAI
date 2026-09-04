"""Governed FinOps records — Volume 69 Commit 1.

PostgreSQL-authoritative financial intelligence plane. This module does NOT
duplicate usage metering: authoritative usage stays in CodeAIUsage,
billing_usage_metering, AnalyticsEvent/CostRecord, KnowledgeQuery and their
peers. FinOps normalizes those sources into deterministic, auditable cost
records with source provenance, then attributes, aggregates, budgets and
governs them.

Money is stored as integer cents. Pricing versions are immutable history:
a historical cost record keeps the pricing version that was effective for
its usage. Unknown pricing is recorded explicitly as UNPRICED, never
fabricated.
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


# ─── 1. Versioned pricing ────────────────────────────────────────────────────


class FinOpsPricingVersion(Base, TimestampMixin):
    """Immutable pricing version for a provider/model/resource unit."""

    __tablename__ = "finops_pricing_versions"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, default="", index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(128), nullable=False, default="", index=True)
    resource: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    unit: Mapped[str] = mapped_column(String(32), nullable=False, default="tokens")
    input_price_cents_per_m: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    output_price_cents_per_m: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    request_price_cents: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    storage_price_cents: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    compute_price_cents: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    effective_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="manual")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    operator: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    reason: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant", "provider", "model", "unit", "version", name="uq_finops_pricing_version"),
        Index("ix_finops_pricing_effective", "provider", "model", "effective_from"),
        Index("ix_finops_pricing_status", "status"),
    )


# ─── 2. Normalized cost records ──────────────────────────────────────────────


class FinOpsCostRecord(Base, TimestampMixin):
    """Deterministic cost record normalized from an authoritative usage source."""

    __tablename__ = "finops_cost_records"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    workspace: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    project: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    service: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    workflow: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    model: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="", index=True)
    environment: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    region: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    resource: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    operation: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    actor: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    cost_basis: Mapped[str] = mapped_column(String(16), nullable=False, default="actual")
    pricing_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    pricing_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant", "idempotency_key", name="uq_finops_cost_idempotency"),
        Index("ix_finops_cost_tenant_occurred", "tenant", "occurred_at"),
        Index("ix_finops_cost_tenant_provider_model", "tenant", "provider", "model"),
        Index("ix_finops_cost_source", "source_type", "source_id"),
    )


# ─── 3. Cost allocations ─────────────────────────────────────────────────────


class FinOpsCostAllocation(Base, TimestampMixin):
    """Deterministic attribution of a cost record to target dimensions."""

    __tablename__ = "finops_cost_allocations"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    cost_record_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    allocation_key: Mapped[str] = mapped_column(String(64), nullable=False)
    target_workspace: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    target_project: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    target_service: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    target_environment: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    share: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    basis: Mapped[str] = mapped_column(String(32), nullable=False, default="direct")
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant", "cost_record_id", "allocation_key", name="uq_finops_allocation"),
    )


# ─── 4. Governed budgets ─────────────────────────────────────────────────────


class FinOpsBudget(Base, TimestampMixin):
    """Governed budget with thresholds, enforcement policy and lifecycle state."""

    __tablename__ = "finops_budgets"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False, default="tenant")
    scope_value: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    model: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    environment: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    period: Mapped[str] = mapped_column(String(16), nullable=False, default="monthly")
    warning_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
    hard_limit_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    enforcement: Mapped[str] = mapped_column(String(32), nullable=False, default="alert")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    owner: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    approval_policy: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        Index("ix_finops_budgets_tenant_status", "tenant", "status"),
    )


class FinOpsBudgetEvent(Base, TimestampMixin):
    """Threshold-crossing event for a budget within a period."""

    __tablename__ = "finops_budget_events"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    budget_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    spend_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant", "budget_id", "event_type", "period_start", name="uq_finops_budget_event"),
        Index("ix_finops_budget_events_budget", "budget_id"),
    )


# ─── 5. Idempotent aggregations ──────────────────────────────────────────────


class FinOpsCostAggregation(Base, TimestampMixin):
    """Precomputed cost bucket. Unique key makes aggregation retry-safe."""

    __tablename__ = "finops_cost_aggregations"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    granularity: Mapped[str] = mapped_column(String(16), nullable=False)
    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    bucket_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    dimensions_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    dimensions: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("tenant", "granularity", "bucket_start", "dimensions_hash", name="uq_finops_aggregation"),
        Index("ix_finops_agg_tenant_granularity", "tenant", "granularity", "bucket_start"),
    )


# ─── 6. Audit log ────────────────────────────────────────────────────────────


class FinOpsAuditLog(Base, TimestampMixin):
    """Audit trail for pricing, budget, policy, approval, allocation and report actions."""

    __tablename__ = "finops_audit_log"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    details: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="SUCCESS")

    __table_args__ = (
        Index("ix_finops_audit_tenant_action", "tenant", "action"),
    )
