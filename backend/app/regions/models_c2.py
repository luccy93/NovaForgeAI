"""Volume 62 Commit 2 — Multi-Region hardening models (additive-only).

Supports failover orchestration (lease/fencing/generation), tenant migration,
traffic shifts, replication conflict resolution, configuration drift. These
complement the Commit 1 region tables. All tables tenant-scoped where
applicable; region-level tables use region_id as key. No fake status.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.database import Base, TimestampMixin


# Tenant migration states (Commit 2)
MIG_PLANNED = "PLANNED"
MIG_VALIDATING = "VALIDATING"
MIG_COPYING = "COPYING"
MIG_SYNCING = "SYNCING"
MIG_CUTOVER = "CUTOVER"
MIG_VERIFYING = "VERIFYING"
MIG_COMPLETED = "COMPLETED"
MIG_FAILED = "FAILED"
MIG_ROLLED_BACK = "ROLLED_BACK"
MIGRATION_STATES = {MIG_PLANNED, MIG_VALIDATING, MIG_COPYING, MIG_SYNCING, MIG_CUTOVER, MIG_VERIFYING, MIG_COMPLETED, MIG_FAILED, MIG_ROLLED_BACK}

# Conflict resolution policies
CONFLICT_LWW = "LAST_WRITE_WINS"
CONFLICT_SOT = "SOURCE_OF_TRUTH"
CONFLICT_MANUAL = "MANUAL_REVIEW"
CONFLICT_POLICIES = {CONFLICT_LWW, CONFLICT_SOT, CONFLICT_MANUAL}

# Traffic shift percentages (progressive delivery)
TRAFFIC_STEPS = [0, 10, 25, 50, 100]


class RegionLease(Base, TimestampMixin):
    """Leader/fencing lease per region (split-brain protection).

    A region may have a single authoritative primary. The lease carries a
    monotonic epoch/generation; stale/isolated primaries without a current
    lease must not accept writes for strong-consistency services.
    """

    __tablename__ = "region_leases"

    region_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    holder: Mapped[str] = mapped_column(String(128), nullable=False)  # service/control-plane identity
    epoch: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # monotonic generation
    generation: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # fencing generation
    leased_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acquired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fenced: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # True => old primary fenced


class TenantMigration(Base, TimestampMixin):
    """Controlled tenant migration between regions with safety states."""

    __tablename__ = "tenant_migrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_region: Mapped[str] = mapped_column(String(64), nullable=False)
    target_region: Mapped[str] = mapped_column(String(64), nullable=False)
    service: Mapped[str | None] = mapped_column(String(128), nullable=True)
    state: Mapped[str] = mapped_column(String(32), default=MIG_PLANNED, nullable=False, index=True)
    authorized_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verification: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    rollback_strategy: Mapped[str | None] = mapped_column(String(64), nullable=True)  # explicit strategy required for DB
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (
        Index("ix_tenant_migrations_tenant_state", "tenant", "state"),
    )


class RegionTrafficShift(Base, TimestampMixin):
    """Progressive traffic shift / regional canary (0/10/25/50/100)."""

    __tablename__ = "region_traffic_shifts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    region_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    percentage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0/10/25/50/100
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", nullable=False)
    actor: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_region_traffic_region_status", "region_id", "status"),
    )


class ReplicationConflict(Base, TimestampMixin):
    """Detected replication conflict for manual/automated resolution."""

    __tablename__ = "replication_conflicts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant: Mapped[str] = mapped_column(String(64), default="", nullable=False, index=True)
    source_region: Mapped[str] = mapped_column(String(64), nullable=False)
    dest_region: Mapped[str] = mapped_column(String(64), nullable=False)
    resource: Mapped[str] = mapped_column(String(256), nullable=False)
    conflict_type: Mapped[str] = mapped_column(String(32), nullable=False)  # version/timestamp/entity
    detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(32), nullable=True)  # pending/LWW/SOT/MANUAL
    resolved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class ConfigDrift(Base, TimestampMixin):
    """Detected regional configuration drift vs control-plane source of truth."""

    __tablename__ = "config_drift"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    service: Mapped[str] = mapped_column(String(128), nullable=False)
    expected_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    observed_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    drift_type: Mapped[str] = mapped_column(String(32), default="version", nullable=False)
    detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="OPEN", nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
