"""Data Platform models — Volume 65 Commit 1 (12 tables, additive-only)."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, Text, Integer, Float, Boolean, DateTime, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Enum as SAEnum

from app.core.database import Base, TimestampMixin

# Enums as Strings for flexibility, validated in services
DATASET_STATUSES = {"DRAFT", "ACTIVE", "DEPRECATED", "ARCHIVED", "BLOCKED"}
PIPELINE_STATUSES = {"DRAFT", "ACTIVE", "PAUSED", "FAILED", "DEPRECATED"}
RUN_STATUSES = {"PENDING", "RUNNING", "SUCCESS", "FAILED", "PAUSED"}
INGESTION_MODES = {"batch", "incremental", "streaming", "cdc"}
STORAGE_TIERS = {"HOT", "WARM", "COLD"}
CLASSIFICATIONS = {"PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"}


class DataDataset(Base, TimestampMixin):
    __tablename__ = "data_datasets"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    workspace: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    project: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    owner: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    team: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    classification: Mapped[str] = mapped_column(String(32), nullable=False, default="INTERNAL")
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0")
    storage_location: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    storage_tier: Mapped[str] = mapped_column(String(16), nullable=False, default="HOT")
    region: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")
    retention_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant", "name", name="uq_data_datasets_tenant_name"),
        Index("ix_data_datasets_tenant_status", "tenant", "status"),
        Index("ix_data_datasets_tenant_classification", "tenant", "classification"),
        Index("ix_data_datasets_owner", "owner"),
        Index("ix_data_datasets_name", "name"),
    )


class DataDatasetVersion(Base, TimestampMixin):
    __tablename__ = "data_dataset_versions"

    dataset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    pipeline_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    storage_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    row_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    checksum: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint("dataset_id", "version", name="uq_dataset_version"),
        Index("ix_dataset_versions_tenant_dataset", "tenant", "dataset_id"),
    )


class DataSource(Base, TimestampMixin):
    __tablename__ = "data_sources"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    connector: Mapped[str] = mapped_column(String(32), nullable=False)  # postgresql|object_storage|api|git|csv|json|parquet|event_stream
    credentials_ref: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)  # hash ref, never raw
    region: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    classification: Mapped[str] = mapped_column(String(32), nullable=False, default="INTERNAL")
    owner: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    __table_args__ = (
        Index("ix_data_sources_tenant_connector", "tenant", "connector"),
        Index("ix_data_sources_tenant_status", "tenant", "status"),
    )


class DataSchema(Base, TimestampMixin):
    __tablename__ = "data_schemas"

    dataset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    fields: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)  # [{name, type, nullable, classification}]
    types: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    classification: Mapped[str] = mapped_column(String(32), nullable=False, default="INTERNAL")
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        UniqueConstraint("dataset_id", "version", name="uq_data_schema_version"),
        Index("ix_data_schemas_tenant_dataset", "tenant", "dataset_id"),
    )


class DataSchemaVersion(Base, TimestampMixin):
    __tablename__ = "data_schema_versions"

    schema_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    diff: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    compatibility: Mapped[str] = mapped_column(String(16), nullable=False, default="backward")  # backward|forward|full

    __table_args__ = (
        Index("ix_schema_versions_tenant_schema", "tenant", "schema_id"),
    )


class DataPipeline(Base, TimestampMixin):
    __tablename__ = "data_pipelines"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0")
    steps: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)  # DAG steps
    dependencies: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)  # list of pipeline ids
    schedule: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # cron
    owner: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")
    region: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="NORMAL")
    resource_limits: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)  # cpu|memory|concurrency|runtime|storage
    dag_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant", "name", name="uq_data_pipelines_tenant_name"),
        Index("ix_data_pipelines_tenant_status", "tenant", "status"),
    )


class DataPipelineRun(Base, TimestampMixin):
    __tablename__ = "data_pipeline_runs"

    pipeline_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    steps: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    records: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bytes_processed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    checkpoint: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_pipeline_runs_tenant_pipeline", "tenant", "pipeline_id"),
        Index("ix_pipeline_runs_status", "status"),
    )


class DataQualityRule(Base, TimestampMixin):
    __tablename__ = "data_quality_rules"

    dataset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(32), nullable=False)  # required|range|regex|uniqueness|referential
    params: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    version: Mapped[str] = mapped_column(String(16), nullable=False, default="1.0")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        Index("ix_quality_rules_tenant_dataset", "tenant", "dataset_id"),
    )


class DataQualityResult(Base, TimestampMixin):
    __tablename__ = "data_quality_results"

    dataset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    rule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(16), nullable=False)
    passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sample_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)  # masked samples
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    job_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_quality_results_tenant_dataset", "tenant", "dataset_id"),
        Index("ix_quality_results_rule", "rule_id"),
    )


class DataLineageEdge(Base, TimestampMixin):
    __tablename__ = "data_lineage_edges"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(256), nullable=False)  # source: type:id
    target: Mapped[str] = mapped_column(String(256), nullable=False)
    transformation: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    pipeline_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    pipeline_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    version: Mapped[str] = mapped_column(String(16), nullable=False, default="1.0")
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    provenance: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)  # hash etc
    column_lineage: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)  # input->output field

    __table_args__ = (
        Index("ix_lineage_tenant_source", "tenant", "source"),
        Index("ix_lineage_tenant_target", "tenant", "target"),
        Index("ix_lineage_pipeline", "pipeline_id"),
    )


class DataStream(Base, TimestampMixin):
    __tablename__ = "data_streams"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(128), nullable=False)
    partition: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consumer_group: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    offset: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    schema_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    retention_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")

    __table_args__ = (
        UniqueConstraint("tenant", "topic", "partition", "consumer_group", name="uq_stream_consumer"),
        Index("ix_streams_tenant_topic", "tenant", "topic"),
    )


class DataCheckpoint(Base, TimestampMixin):
    __tablename__ = "data_checkpoints"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    consumer: Mapped[str] = mapped_column(String(128), nullable=False)
    topic: Mapped[str] = mapped_column(String(128), nullable=False)
    partition: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    offset: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    watermark: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant", "consumer", "topic", "partition", name="uq_checkpoint"),
        Index("ix_checkpoints_tenant_consumer", "tenant", "consumer"),
    )
