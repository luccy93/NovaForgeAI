"""Lakehouse & data products models — Volume 65 Commit 2 (additive)."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Text, Integer, Float, Boolean, DateTime, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class DataProduct(Base, TimestampMixin):
    __tablename__ = "data_products"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    owner: Mapped[str] = mapped_column(String(64), nullable=False)
    contract: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)  # schema+quality+SLO
    classification: Mapped[str] = mapped_column(String(32), nullable=False, default="INTERNAL")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")  # DRAFT|PUBLISHED|DEPRECATED|RETIRED
    domain: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    slo: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant", "name", name="uq_data_products_tenant_name"),
        Index("ix_data_products_tenant_status", "tenant", "status"),
    )


class DataDomain(Base, TimestampMixin):
    __tablename__ = "data_domains"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    owner: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant", "name", name="uq_data_domains_tenant_name"),
    )


class DataFreshness(Base, TimestampMixin):
    __tablename__ = "data_freshness"

    dataset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    last_update: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expected_interval_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="UNKNOWN")  # FRESH|STALE|MISSING|UNKNOWN
    slo: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    __table_args__ = (
        Index("ix_freshness_tenant_dataset", "tenant", "dataset_id"),
    )


class DataDriftEvent(Base, TimestampMixin):
    __tablename__ = "data_drift_events"

    dataset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    drift_type: Mapped[str] = mapped_column(String(32), nullable=False)  # schema|data|quality
    details: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("ix_drift_tenant_dataset", "tenant", "dataset_id"),
    )


class DataReplayJob(Base, TimestampMixin):
    __tablename__ = "data_replay_jobs"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(128), nullable=False)
    scope: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")  # PENDING|RUNNING|COMPLETED|FAILED
    approved_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_replay_tenant_topic", "tenant", "topic"),
    )
