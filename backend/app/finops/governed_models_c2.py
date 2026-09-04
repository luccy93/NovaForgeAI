"""Governed FinOps intelligence records — Volume 69 Commit 2.

Forecasts, anomalies, recommendations, governance policies/decisions and
chargeback reports. All tenant-scoped, all idempotent by unique keys, all
auditable. Savings that cannot be computed reliably are stored as NULL
(UNKNOWN), never fabricated.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FinOpsForecast(Base, TimestampMixin):
    __tablename__ = "finops_forecasts"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    forecast_type: Mapped[str] = mapped_column(String(32), nullable=False)
    dimensions: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    dimensions_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    predicted_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    daily_rate_cents: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    quality: Mapped[str] = mapped_column(String(16), nullable=False, default="LOW")
    method: Mapped[str] = mapped_column(String(64), nullable=False, default="linear_baseline")
    basis_buckets: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    budget_exhaustion_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="READY")

    __table_args__ = (
        UniqueConstraint("tenant", "forecast_type", "dimensions_hash", "horizon_days", "period_start",
                         name="uq_finops_forecast"),
        Index("ix_finops_forecast_tenant_type", "tenant", "forecast_type"),
    )


class FinOpsAnomaly(Base, TimestampMixin):
    __tablename__ = "finops_anomalies"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    dimension_key: Mapped[str] = mapped_column(String(64), nullable=False)
    dimension_value: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    granularity: Mapped[str] = mapped_column(String(16), nullable=False, default="day")
    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    baseline_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    observed_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deviation: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="LOW")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    evidence: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="OPEN")

    __table_args__ = (
        UniqueConstraint("tenant", "dimension_key", "dimension_value", "bucket_start",
                         name="uq_finops_anomaly"),
        Index("ix_finops_anomaly_tenant_severity", "tenant", "severity"),
    )


class FinOpsRecommendation(Base, TimestampMixin):
    __tablename__ = "finops_recommendations"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    rec_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    evidence: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    estimated_savings_cents: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    savings_known: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    affected_resource: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    risk: Mapped[str] = mapped_column(String(16), nullable=False, default="LOW")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="OPEN")

    __table_args__ = (
        Index("ix_finops_rec_tenant_type", "tenant", "rec_type"),
        Index("ix_finops_rec_tenant_status", "tenant", "status"),
    )


class FinOpsPolicy(Base, TimestampMixin):
    __tablename__ = "finops_policies"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    workspace: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    project: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    model: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    operation: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    max_estimated_cents: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False, default="alert")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    owner: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        Index("ix_finops_policy_tenant_enabled", "tenant", "enabled"),
    )


class FinOpsPolicyDecision(Base, TimestampMixin):
    __tablename__ = "finops_policy_decisions"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    policy_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), nullable=True)
    identity: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    operation: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    estimated_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    approval_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    reason: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    context: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    __table_args__ = (
        Index("ix_finops_decision_tenant_operation", "tenant", "operation"),
    )


class FinOpsChargebackReport(Base, TimestampMixin):
    __tablename__ = "finops_chargeback_reports"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    report_type: Mapped[str] = mapped_column(String(16), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scope: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lines: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    provenance: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant", "report_type", "period_start", "period_end",
                         name="uq_finops_report"),
    )
