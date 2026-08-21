"""Unified Analytics Platform -- Database Models (Volume 50)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.database import Base, TimestampMixin


class AnalyticsEvent(Base, TimestampMixin):
    __tablename__ = "analytics_events"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    workspace: Mapped[str] = mapped_column(String(128), default="")
    project: Mapped[str] = mapped_column(String(128), default="")
    actor: Mapped[str] = mapped_column(String(128), default="")
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), default="")
    resource_id: Mapped[str] = mapped_column(String(128), default="")
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    metadata_extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    event_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc), index=True)
    processed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    __table_args__ = (
        Index("ix_analytics_events_tenant_type", "tenant", "event_type"),
        Index("ix_analytics_events_tenant_ts", "tenant", "event_timestamp"),
    )


class MetricDefinition(Base, TimestampMixin):
    __tablename__ = "analytics_metric_definitions"

    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    formula: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    dimensions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), default="")
    aggregation: Mapped[str] = mapped_column(String(32), default="sum")
    version: Mapped[int] = mapped_column(Integer, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class AggregateRecord(Base, TimestampMixin):
    __tablename__ = "analytics_aggregates"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    metric_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    granularity: Mapped[str] = mapped_column(String(16), nullable=False)
    dimensions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    value: Mapped[float] = mapped_column(Float, default=0.0)
    count: Mapped[int] = mapped_column(Integer, default=0)
    min_value: Mapped[float] = mapped_column(Float, default=0.0)
    max_value: Mapped[float] = mapped_column(Float, default=0.0)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metric_version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        Index("ix_agg_tenant_metric_period", "tenant", "metric_name", "period_start"),
        Index("ix_agg_tenant_granularity", "tenant", "granularity", "period_start"),
    )


class CostRecord(Base, TimestampMixin):
    __tablename__ = "analytics_cost_records"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    cost_type: Mapped[str] = mapped_column(String(32), nullable=False)
    amount_usd: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    organization: Mapped[str] = mapped_column(String(128), default="")
    workspace: Mapped[str] = mapped_column(String(128), default="")
    project: Mapped[str] = mapped_column(String(128), default="")
    repository: Mapped[str] = mapped_column(String(256), default="")
    environment: Mapped[str] = mapped_column(String(32), default="")
    model: Mapped[str] = mapped_column(String(128), default="")
    provider: Mapped[str] = mapped_column(String(64), default="")
    agent: Mapped[str] = mapped_column(String(128), default="")
    workflow: Mapped[str] = mapped_column(String(128), default="")
    user_id: Mapped[str] = mapped_column(String(128), default="")
    is_estimated: Mapped[bool] = mapped_column(Boolean, default=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    __table_args__ = (
        Index("ix_cost_tenant_type_period", "tenant", "cost_type", "period_start"),
        Index("ix_cost_tenant_org", "tenant", "organization"),
    )


class Budget(Base, TimestampMixin):
    __tablename__ = "analytics_budgets"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_value: Mapped[str] = mapped_column(String(128), default="")
    cost_type: Mapped[str] = mapped_column(String(32), default="total")
    limit_usd: Mapped[float] = mapped_column(Float, nullable=False)
    period: Mapped[str] = mapped_column(String(16), default="monthly")
    warning_threshold: Mapped[float] = mapped_column(Float, default=0.8)
    soft_limit_threshold: Mapped[float] = mapped_column(Float, default=0.95)
    hard_limit_threshold: Mapped[float] = mapped_column(Float, default=1.0)
    current_spend: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(16), default="ok")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class AnalyticsAlert(Base, TimestampMixin):
    __tablename__ = "analytics_alerts"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(128), default="")
    condition: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    severity: Mapped[str] = mapped_column(String(16), default="medium")
    status: Mapped[str] = mapped_column(String(16), default="active")
    last_triggered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=3600)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class AnalyticsReport(Base, TimestampMixin):
    __tablename__ = "analytics_reports"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    report_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    format: Mapped[str] = mapped_column(String(16), default="json")
    generated_by: Mapped[str] = mapped_column(String(128), default="system")
    status: Mapped[str] = mapped_column(String(16), default="completed")


class Forecast(Base, TimestampMixin):
    __tablename__ = "analytics_forecasts"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    metric_name: Mapped[str] = mapped_column(String(128), nullable=False)
    scope: Mapped[str] = mapped_column(String(32), default="")
    scope_value: Mapped[str] = mapped_column(String(128), default="")
    forecast_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    predicted_value: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_lower: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_upper: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_level: Mapped[float] = mapped_column(Float, default=0.95)
    methodology: Mapped[str] = mapped_column(String(32), default="linear")
    metadata_extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class Recommendation(Base, TimestampMixin):
    __tablename__ = "analytics_recommendations"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    estimated_impact_usd: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    risk: Mapped[str] = mapped_column(String(16), default="low")
    priority: Mapped[str] = mapped_column(String(16), default="medium")
    suggested_action: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    metadata_extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class DataQualityRecord(Base, TimestampMixin):
    __tablename__ = "analytics_data_quality"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    issue_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(64), default="")
    resource_type: Mapped[str] = mapped_column(String(64), default="")
    resource_id: Mapped[str] = mapped_column(String(128), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(16), default="low")
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
