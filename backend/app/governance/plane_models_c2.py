"""Central governance enterprise records — Volume 71 Commit 2.

Evidence registry (references + hashes, never copied datasets), drift
findings and report runs. Controls/evidence lifecycle reuses the V57
datagov tables and ControlService; chargeback-style financials reuse
V69 FinOps records.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Index, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GovernancePlaneEvidence(Base, TimestampMixin):
    __tablename__ = "governance_plane_evidence"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    control_key: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    source_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    integrity_hash: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    result: Mapped[str] = mapped_column(String(16), nullable=False, default="PASS")
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant", "control_key", "source_system", "source_ref",
                         name="uq_governance_plane_evidence"),
        Index("ix_governance_plane_evidence_control", "tenant", "control_key"),
    )


class GovernancePlaneDriftFinding(Base, TimestampMixin):
    __tablename__ = "governance_plane_drift"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    finding_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="MEDIUM")
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    resource_id: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    description: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="OPEN")
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        Index("ix_governance_plane_drift_status", "tenant", "status"),
    )


class GovernancePlaneReport(Base, TimestampMixin):
    __tablename__ = "governance_plane_reports"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    report_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False, default="tenant")
    scope_value: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    summary: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    sections: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        Index("ix_governance_plane_reports_type", "tenant", "report_type"),
    )


def new_evidence_id() -> uuid.UUID:
    return uuid.uuid4()
