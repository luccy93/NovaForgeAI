"""Volume 59 — Observability metadata models (6 tables, additive-only)."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid
from sqlalchemy import Index, UniqueConstraint

from app.core.database import Base, TimestampMixin


class ObservabilityService(Base, TimestampMixin):
    __tablename__ = "observability_services"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    workspace: Mapped[str | None] = mapped_column(String(64), nullable=True)
    project: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource: Mapped[str] = mapped_column(String(256), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False, default="service")
    environment: Mapped[str] = mapped_column(String(32), nullable=False, default="production")
    deployment: Mapped[str | None] = mapped_column(String(128), nullable=True)
    repository: Mapped[str | None] = mapped_column(String(256), nullable=True)
    host: Mapped[str | None] = mapped_column(String(128), nullable=True)
    container: Mapped[str | None] = mapped_column(String(128), nullable=True)
    pod: Mapped[str | None] = mapped_column(String(128), nullable=True)
    workflow: Mapped[str | None] = mapped_column(String(128), nullable=True)
    agent: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tool: Mapped[str | None] = mapped_column(String(128), nullable=True)
    database: Mapped[str | None] = mapped_column(String(128), nullable=True)
    queue: Mapped[str | None] = mapped_column(String(128), nullable=True)
    api: Mapped[str | None] = mapped_column(String(256), nullable=True)
    health_status: Mapped[str] = mapped_column(String(16), default="UNKNOWN", nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (
        Index("ix_obs_services_tenant_resource", "tenant", "resource"),
        Index("ix_obs_services_tenant_env", "tenant", "environment"),
        UniqueConstraint("tenant", "resource", name="uq_obs_services_tenant_resource"),
    )


class ObservabilityAlertRule(Base, TimestampMixin):
    __tablename__ = "observability_alert_rules"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    resource: Mapped[str] = mapped_column(String(256), nullable=False)
    condition: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)  # threshold/rate/anomaly/absence/SLO/log_pattern/trace
    severity: Mapped[str] = mapped_column(String(16), default="WARNING", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    fingerprint_fields: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    __table_args__ = (Index("ix_obs_rules_tenant_resource", "tenant", "resource"),)


class ObservabilityAlert(Base, TimestampMixin):
    __tablename__ = "observability_alerts"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource: Mapped[str] = mapped_column(String(256), nullable=False)
    condition: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), default="WARNING", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="FIRING", nullable=False, index=True)  # FIRING/ACKNOWLEDGED/SUPPRESSED/RESOLVED
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="observability")
    fingerprint: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_obs_alerts_tenant_fingerprint", "tenant", "fingerprint"),
        Index("ix_obs_alerts_tenant_status", "tenant", "status"),
    )


class ObservabilitySLO(Base, TimestampMixin):
    __tablename__ = "observability_slos"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    service: Mapped[str] = mapped_column(String(128), nullable=False)
    indicator: Mapped[str] = mapped_column(String(64), nullable=False)  # availability/latency/error_rate/custom
    target: Mapped[float] = mapped_column(Float, nullable=False)
    window: Mapped[str] = mapped_column(String(32), nullable=False, default="30d")
    owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (Index("ix_obs_slos_tenant_service", "tenant", "service"),)


class ObservabilitySyntheticCheck(Base, TimestampMixin):
    __tablename__ = "observability_synthetic_checks"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    check_type: Mapped[str] = mapped_column(String(32), nullable=False, default="HTTP")  # HTTP/API/workflow
    target: Mapped[str] = mapped_column(String(512), nullable=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_status: Mapped[str] = mapped_column(String(16), default="UNKNOWN", nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_obs_synthetic_tenant", "tenant"),)


class ObservabilityHealthSnapshot(Base, TimestampMixin):
    __tablename__ = "observability_health_snapshots"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource: Mapped[str] = mapped_column(String(256), nullable=False)
    health: Mapped[str] = mapped_column(String(16), nullable=False)  # HEALTHY/DEGRADED/UNHEALTHY/UNKNOWN
    checks: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("ix_obs_health_tenant_resource", "tenant", "resource"),
        Index("ix_obs_health_timestamp", "timestamp"),
    )
