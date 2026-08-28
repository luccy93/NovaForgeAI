"""Volume 62 — Multi-Region models (7 tables, additive-only).

Global control plane + regional data plane foundation. Reuses Volume 57 data
governance policy bridge, Volume 60 resilience failover records, Volume 59
observability. Region-level tables (regions, capabilities, health snapshots)
are not tenant-scoped; placement/routing/replication/failover records are
tenant-scoped with an empty-string tenant for global/control-plane entries.

Status/state constants are fail-closed: UNKNOWN is never treated as healthy.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
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


# Region status (fail-closed: UNKNOWN != healthy)
REGION_ACTIVE = "ACTIVE"
REGION_DEGRADED = "DEGRADED"
REGION_DRAINING = "DRAINING"
REGION_FAILED = "FAILED"
REGION_UNKNOWN = "UNKNOWN"
REGION_STATUSES = {REGION_ACTIVE, REGION_DEGRADED, REGION_DRAINING, REGION_FAILED, REGION_UNKNOWN}

# Region capability service catalog
REGION_CAP_AI = "AI"
REGION_CAP_GPU = "GPU"
REGION_CAP_RAG = "RAG"
REGION_CAP_VECTOR = "vector_search"
REGION_CAP_GRAPH = "graph"
REGION_CAP_STORAGE = "storage"
REGION_CAP_COMPUTE = "compute"
REGION_CAP_DEPLOYMENT = "deployment"
REGION_CAP_BILLING = "billing"
REGION_CAP_MARKETPLACE = "marketplace"

# Replication states
REPL_HEALTHY = "HEALTHY"
REPL_LAGGING = "LAGGING"
REPL_BROKEN = "BROKEN"
REPL_PAUSED = "PAUSED"
REPL_UNKNOWN = "UNKNOWN"
REPL_STATES = {REPL_HEALTHY, REPL_LAGGING, REPL_BROKEN, REPL_PAUSED, REPL_UNKNOWN}

# Consistency classification
CONS_STRONG = "STRONG"
CONS_EVENTUAL = "EVENTUAL"
CONS_CONFIGURABLE = "CONFIGURABLE"
CONSISTENCY_LEVELS = {CONS_STRONG, CONS_EVENTUAL, CONS_CONFIGURABLE}

# Failover/failback record status
FO_STARTED = "STARTED"
FO_PROMOTED = "PROMOTED"
FO_COMPLETED = "COMPLETED"
FO_FAILED = "FAILED"
FO_ROLLED_BACK = "ROLLED_BACK"


class Region(Base, TimestampMixin):
    """Global region registry (control-plane metadata, not tenant-scoped)."""

    __tablename__ = "regions"

    region_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)  # cloud/provider label, not hard-coded
    location: Mapped[str] = mapped_column(String(128), nullable=False)  # geo/location label
    status: Mapped[str] = mapped_column(String(16), default=REGION_ACTIVE, nullable=False, index=True)
    capacity: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)  # cpu/memory/storage/queue/ai/database
    data_residency: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)  # provider/restricted constraints
    environment: Mapped[str] = mapped_column(String(32), default="production", nullable=False)


class RegionCapability(Base, TimestampMixin):
    """Per-region supported service capabilities."""

    __tablename__ = "region_capabilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    region_id: Mapped[str] = mapped_column(String(64), ForeignKey("regions.region_id", ondelete="CASCADE"), nullable=False, index=True)
    service: Mapped[str] = mapped_column(String(64), nullable=False)  # REGION_CAP_* value
    supported: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("region_id", "service", name="uq_region_capability"),
        Index("ix_region_capabilities_region_service", "region_id", "service"),
    )


class TenantRegionPlacement(Base, TimestampMixin):
    """Tenant -> region placement (primary/secondary/allowed) + residency policy."""

    __tablename__ = "tenant_region_placements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    primary_region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    secondary_region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    allowed_regions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    data_classification: Mapped[str | None] = mapped_column(String(32), nullable=True)  # PUBLIC/INTERNAL/RESTRICTED/SECRET
    residency_policy: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(32), default="1.0.0", nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant", name="uq_tenant_region_placement"),
        Index("ix_tenant_placements_tenant", "tenant"),
    )


class RegionRoutingPolicy(Base, TimestampMixin):
    """Versioned routing policy: primary -> preferred secondary -> emergency fallback."""

    __tablename__ = "region_routing_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    service: Mapped[str] = mapped_column(String(128), nullable=False)
    primary_region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    preferred_secondary: Mapped[str | None] = mapped_column(String(64), nullable=True)
    emergency_fallback: Mapped[str | None] = mapped_column(String(64), nullable=True)
    consistency: Mapped[str] = mapped_column(String(16), default=CONS_CONFIGURABLE, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(32), default="1.0.0", nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)  # region-specific overrides, propagation status

    __table_args__ = (
        UniqueConstraint("tenant", "service", name="uq_region_routing_policy"),
        Index("ix_region_routing_tenant_service", "tenant", "service"),
    )


class RegionReplicationRecord(Base, TimestampMixin):
    """Cross-region replication tracking with lag + status (never faked)."""

    __tablename__ = "region_replication_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant: Mapped[str] = mapped_column(String(64), default="", nullable=False, index=True)  # "" = global
    source_region: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    dest_region: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource: Mapped[str] = mapped_column(String(256), nullable=False)  # db/collection/graph/object/vector
    lag_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=REPL_HEALTHY, nullable=False, index=True)
    last_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resource_type: Mapped[str | None] = mapped_column(String(32), nullable=True)  # vector/graph/db/object

    __table_args__ = (
        Index("ix_region_replication_src_dst", "source_region", "dest_region"),
        Index("ix_region_replication_resource", "resource"),
    )


class RegionFailoverRecord(Base, TimestampMixin):
    """Failover / failback metadata (control-plane record; orchestration in Commit 2)."""

    __tablename__ = "region_failover_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    service: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failover_type: Mapped[str] = mapped_column(String(16), default="failover", nullable=False)  # failover/failback
    status: Mapped[str] = mapped_column(String(32), default=FO_STARTED, nullable=False, index=True)
    authorized_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    data_residency_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    health_verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (
        Index("ix_region_failover_tenant_type", "tenant", "failover_type"),
    )


class RegionHealthSnapshot(Base, TimestampMixin):
    """Region health snapshots (region-level, not tenant-scoped)."""

    __tablename__ = "region_health_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    region_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default=REGION_UNKNOWN, nullable=False, index=True)
    checks: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)  # per-check results
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_region_health_region_time", "region_id", "observed_at"),
    )
