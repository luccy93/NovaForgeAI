"""Volume 61 Commit 1 — Performance models (6 tables, additive-only)."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from app.core.database import Base, TimestampMixin


class PerformanceBudget(Base, TimestampMixin):
    __tablename__ = "performance_budgets"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    service: Mapped[str] = mapped_column(String(128), nullable=False)
    metric_type: Mapped[str] = mapped_column(String(32), nullable=False)  # api/ai/rag/db/queue/deployment
    metric_name: Mapped[str] = mapped_column(String(128), nullable=False)
    target: Mapped[float] = mapped_column(Float, nullable=False)
    window: Mapped[str] = mapped_column(String(32), nullable=False, default="1h")
    owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="ok", nullable=False)

    __table_args__ = (
        Index("ix_perf_budgets_tenant_service", "tenant", "service"),
        Index("ix_perf_budgets_tenant_metric", "tenant", "metric_name"),
    )


class PerformanceServiceMetric(Base, TimestampMixin):
    __tablename__ = "performance_service_metrics"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    service: Mapped[str] = mapped_column(String(128), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    granularity: Mapped[str] = mapped_column(String(16), nullable=False, default="minute")
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    min_val: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_val: Mapped[float | None] = mapped_column(Float, nullable=True)
    p50: Mapped[float | None] = mapped_column(Float, nullable=True)
    p95: Mapped[float | None] = mapped_column(Float, nullable=True)
    p99: Mapped[float | None] = mapped_column(Float, nullable=True)
    dimensions: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (
        Index("ix_perf_metrics_tenant_service_period", "tenant", "service", "period_start"),
        Index("ix_perf_metrics_tenant_metric", "tenant", "metric_name"),
    )


class PerformanceSnapshot(Base, TimestampMixin):
    __tablename__ = "performance_snapshots"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False, default="service")
    cpu: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory: Mapped[float | None] = mapped_column(Float, nullable=True)
    queue_depth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    concurrency: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage: Mapped[float | None] = mapped_column(Float, nullable=True)
    db_load: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (Index("ix_perf_snapshots_tenant_resource", "tenant", "resource"),)


class CapacityPolicy(Base, TimestampMixin):
    __tablename__ = "capacity_policies"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource: Mapped[str] = mapped_column(String(128), nullable=False)
    metric: Mapped[str] = mapped_column(String(64), nullable=False)  # cpu/memory/request_rate/queue_depth/latency/custom
    target: Mapped[float] = mapped_column(Float, nullable=False)
    min_instances: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_instances: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (Index("ix_capacity_policies_tenant_resource", "tenant", "resource"),)


class ResourcePool(Base, TimestampMixin):
    __tablename__ = "resource_pools"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    pool_type: Mapped[str] = mapped_column(String(32), nullable=False)  # cpu/memory/workers/gpu
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    isolated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tenant_isolation: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (Index("ix_resource_pools_tenant_type", "tenant", "pool_type"),)


class PerformanceRecommendation(Base, TimestampMixin):
    __tablename__ = "performance_recommendations"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)  # index/cache/partition/scale/optimize
    resource: Mapped[str] = mapped_column(String(256), nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)

    __table_args__ = (Index("ix_perf_recs_tenant_type", "tenant", "type"),)


class ScalingEvent(Base, TimestampMixin):
    __tablename__ = "scaling_events"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource: Mapped[str] = mapped_column(String(128), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)  # out/in
    reason: Mapped[str] = mapped_column(String(256), nullable=False)
    from_count: Mapped[int] = mapped_column(Integer, nullable=False)
    to_count: Mapped[int] = mapped_column(Integer, nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (Index("ix_scaling_events_tenant_resource", "tenant", "resource"),)
