"""Volume 43 — RAG persistence models.

Nine entities are added to the existing relational schema (reusing ``Base``
and ``TimestampMixin``). Every entity carries tenant/project/repository
scoping so authorization can be enforced before results reach a model.

Tables:
    rag_sources            knowledge source registry
    rag_source_versions   immutable per-ingestion versions (atomic reindex)
    rag_chunks            embedded, retrievable knowledge chunks
    rag_ingestion_jobs    ingestion job lifecycle
    rag_retrieval_logs    per-query observability
    rag_context_sets      assembled context snapshots
    rag_citation_records  citation validation audit trail
    rag_evaluation_runs   benchmark evaluation runs
    rag_quality_metrics   time-series quality metrics
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin


def _utc() -> datetime:
    return datetime.now(timezone.utc)


class KnowledgeSource(Base, TimestampMixin):
    __tablename__ = "rag_sources"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    repository_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source_uri: Mapped[str | None] = mapped_column(Text, nullable=True)

    version: Mapped[int] = mapped_column(Integer, default=1)
    active_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    permissions: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    classification: Mapped[str] = mapped_column(String(50), default="internal")
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    ingestion_status: Mapped[str] = mapped_column(String(30), default="queued")
    last_indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)

    versions: Mapped[list["KnowledgeSourceVersion"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class KnowledgeSourceVersion(Base, TimestampMixin):
    __tablename__ = "rag_source_versions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("rag_sources.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    commit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    branch: Mapped[str | None] = mapped_column(String(100), nullable=True)
    document_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    parser_version: Mapped[str] = mapped_column(String(50), default="1.0.0")
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    embedding_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="processing", index=True)
    validated: Mapped[bool] = mapped_column(Boolean, default=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    source: Mapped[KnowledgeSource] = relationship(back_populates="versions")


class RagChunk(Base, TimestampMixin):
    __tablename__ = "rag_chunks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    repository_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)

    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("rag_sources.id", ondelete="CASCADE"), index=True
    )
    source_version_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    chunk_type: Mapped[str] = mapped_column(String(50), default="section", index=True)
    sequence: Mapped[int] = mapped_column(Integer, default=0)

    content: Mapped[str] = mapped_column(Text, nullable=False)
    snippet: Mapped[str] = mapped_column(Text, default="")
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    symbol: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    language: Mapped[str | None] = mapped_column(String(50), nullable=True)
    branch: Mapped[str | None] = mapped_column(String(100), nullable=True)
    commit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    start_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_line: Mapped[int | None] = mapped_column(Integer, nullable=True)

    embedding_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    embedding_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    vector_collection: Mapped[str | None] = mapped_column(String(100), nullable=True)

    permissions: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    classification: Mapped[str] = mapped_column(String(50), default="internal")
    source_type: Mapped[str] = mapped_column(String(50), default="documentation")
    quality: Mapped[str] = mapped_column(String(30), default="maintained")
    metadata_: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)


class RagIngestionJob(Base, TimestampMixin):
    __tablename__ = "rag_ingestion_jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    repository_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    source_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    job_type: Mapped[str] = mapped_column(String(30), default="ingest")  # ingest|reindex|delete|validate
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    stage: Mapped[str] = mapped_column(String(30), default="queued")
    total: Mapped[int] = mapped_column(Integer, default=0)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)


class RagRetrievalLog(Base, TimestampMixin):
    __tablename__ = "rag_retrieval_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    repository_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)

    query: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(50), nullable=True)
    strategies: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    filters: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    rerank_strategy: Mapped[str | None] = mapped_column(String(30), nullable=True)

    lexical_count: Mapped[int] = mapped_column(Integer, default=0)
    vector_count: Mapped[int] = mapped_column(Integer, default=0)
    graph_count: Mapped[int] = mapped_column(Integer, default=0)
    fused_count: Mapped[int] = mapped_column(Integer, default=0)
    context_chunks: Mapped[int] = mapped_column(Integer, default=0)
    citations: Mapped[int] = mapped_column(Integer, default=0)
    invalid_citations: Mapped[int] = mapped_column(Integer, default=0)
    answerability: Mapped[str | None] = mapped_column(String(30), nullable=True)

    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    lexical_latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    vector_latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    graph_latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    rerank_latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    total_latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    empty_retrieval: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)


class RagContextSet(Base, TimestampMixin):
    __tablename__ = "rag_context_sets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    repository_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)

    query: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_ids: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    citation_ids: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    answerability: Mapped[str] = mapped_column(String(30), default="PARTIAL")
    context_text: Mapped[str] = mapped_column(Text, default="")
    metadata_: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)


class RagCitationRecord(Base, TimestampMixin):
    __tablename__ = "rag_citation_records"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    repository_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)

    chunk_id: Mapped[str] = mapped_column(String(255), index=True)
    source_id: Mapped[str] = mapped_column(String(255), index=True)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    symbol: Mapped[str | None] = mapped_column(String(255), nullable=True)
    commit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    snippet: Mapped[str] = mapped_column(Text, default="")
    retrieval_method: Mapped[str | None] = mapped_column(String(30), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    valid: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    validation_detail: Mapped[str | None] = mapped_column(Text, nullable=True)


class RagEvaluationRun(Base, TimestampMixin):
    __tablename__ = "rag_evaluation_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    dataset_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    query_type: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    rerank_strategy: Mapped[str | None] = mapped_column(String(30), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)

    recall_at_k: Mapped[float] = mapped_column(Float, default=0.0)
    precision_at_k: Mapped[float] = mapped_column(Float, default=0.0)
    mrr: Mapped[float] = mapped_column(Float, default=0.0)
    ndcg: Mapped[float] = mapped_column(Float, default=0.0)
    citation_accuracy: Mapped[float] = mapped_column(Float, default=0.0)
    citation_coverage: Mapped[float] = mapped_column(Float, default=0.0)
    groundedness: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)


class RagQualityMetric(Base, TimestampMixin):
    __tablename__ = "rag_quality_metrics"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    repository_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    metric_name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    metric_value: Mapped[float] = mapped_column(Float, default=0.0)
    dimensions: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
