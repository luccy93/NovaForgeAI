"""NovaForge Knowledge Graph Platform -- Database Models (Volume 50)."""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.database import Base, TimestampMixin


class KGEntity(Base, TimestampMixin):
    __tablename__ = "kg_entities"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default="default")
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(256), index=True)
    provider: Mapped[Optional[str]] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(512))
    description: Mapped[Optional[str]] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="active")
    aliases: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)


class KGRelationship(Base, TimestampMixin):
    __tablename__ = "kg_relationships"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default="default")
    source_entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("kg_entities.id"), nullable=False, index=True)
    target_entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("kg_entities.id"), nullable=False, index=True)
    relationship_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    confidence: Mapped[str] = mapped_column(String(32), default="confirmed")
    evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    valid_from: Mapped[Optional[str]] = mapped_column(String(64))
    valid_to: Mapped[Optional[str]] = mapped_column(String(64))
    observed_at: Mapped[Optional[str]] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        UniqueConstraint("source_entity_id", "target_entity_id", "relationship_type"),
    )


class KGEntityAlias(Base, TimestampMixin):
    __tablename__ = "kg_entity_aliases"

    entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("kg_entities.id"), nullable=False, index=True)
    alias_type: Mapped[Optional[str]] = mapped_column(String(64))
    alias_value: Mapped[str] = mapped_column(String(512), nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String(128))
    __table_args__ = (
        UniqueConstraint("entity_id", "alias_type", "alias_value"),
    )


class KGSnapshot(Base, TimestampMixin):
    __tablename__ = "kg_snapshots"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True, default="default")
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    snapshot_type: Mapped[Optional[str]] = mapped_column(String(64))
    reference_id: Mapped[Optional[str]] = mapped_column(String(256))
    reference_type: Mapped[Optional[str]] = mapped_column(String(64))
    entity_count: Mapped[int] = mapped_column(Integer, default=0)
    relationship_count: Mapped[int] = mapped_column(Integer, default=0)
    data_json: Mapped[dict] = mapped_column(JSON, default=dict)


class KGSyncJob(Base, TimestampMixin):
    __tablename__ = "kg_sync_jobs"

    tenant: Mapped[str] = mapped_column(String(64), index=True, default="default")
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    entities_created: Mapped[int] = mapped_column(Integer, default=0)
    entities_updated: Mapped[int] = mapped_column(Integer, default=0)
    entities_deleted: Mapped[int] = mapped_column(Integer, default=0)
    relationships_created: Mapped[int] = mapped_column(Integer, default=0)
    relationships_updated: Mapped[int] = mapped_column(Integer, default=0)
    relationships_deleted: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    started_at: Mapped[Optional[str]] = mapped_column(String(64))
    completed_at: Mapped[Optional[str]] = mapped_column(String(64))


class KGQualityMetric(Base, TimestampMixin):
    __tablename__ = "kg_quality_metrics"

    tenant: Mapped[str] = mapped_column(String(64), index=True, default="default")
    metric_name: Mapped[str] = mapped_column(String(128), nullable=False)
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)
    entity_type: Mapped[Optional[str]] = mapped_column(String(64))
    dimensions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    measured_at: Mapped[str] = mapped_column(String(64), nullable=False)


class KGAuditLog(Base, TimestampMixin):
    __tablename__ = "kg_audit_log"

    tenant: Mapped[str] = mapped_column(String(64), index=True, default="default")
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), index=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String(64))
    actor: Mapped[Optional[str]] = mapped_column(String(256))
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class KGAuthorizationPolicy(Base, TimestampMixin):
    __tablename__ = "kg_authorization_policies"

    tenant: Mapped[str] = mapped_column(String(64), index=True, default="default")
    entity_type: Mapped[Optional[str]] = mapped_column(String(64))
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True))
    principal_type: Mapped[Optional[str]] = mapped_column(String(64))
    principal_id: Mapped[Optional[str]] = mapped_column(String(256))
    permission: Mapped[Optional[str]] = mapped_column(String(64))
    conditions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
