"""Knowledge foundation models — Volume 68.

Tables: knowledge_sources, knowledge_documents, knowledge_chunks,
knowledge_entities, knowledge_links, knowledge_ingestion_jobs,
knowledge_queries, knowledge_query_results.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ─── 1. KnowledgeSource ─────────────────────────────────────────────────────


class KnowledgeSource(Base, TimestampMixin):
    __tablename__ = "knowledge_sources"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # code_intelligence|data_catalog|documents|workflows|incidents|security|conversations|external
    connector_config: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    owner: Mapped[Optional[str]] = mapped_column(String(64))
    classification: Mapped[str] = mapped_column(
        String(32), nullable=False, default="INTERNAL"
    )
    region: Mapped[Optional[str]] = mapped_column(String(64))
    last_ingested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ingestion_config: Mapped[Optional[dict]] = mapped_column(
        JSONB, default=dict
    )  # frequency, batch_size, etc.
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant", "name", name="uq_knowledge_sources_tenant_name"),
        Index("ix_knowledge_sources_tenant_status", "tenant", "status"),
        Index("ix_knowledge_sources_source_type", "source_type"),
    )


# ─── 2. KnowledgeDocument ───────────────────────────────────────────────────


class KnowledgeDocument(Base, TimestampMixin):
    __tablename__ = "knowledge_documents"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True))
    external_id: Mapped[Optional[str]] = mapped_column(String(256))
    title: Mapped[Optional[str]] = mapped_column(String(512))
    doc_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64))
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0")
    content: Mapped[Optional[str]] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    language: Mapped[Optional[str]] = mapped_column(String(16))
    classification: Mapped[str] = mapped_column(
        String(32), nullable=False, default="INTERNAL"
    )
    tags: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    attribution: Mapped[Optional[dict]] = mapped_column(
        JSONB, default=dict
    )  # {"author":...,"created_by":...,"url":...}
    freshness_score: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="INGESTED")
    ingestion_error: Mapped[Optional[str]] = mapped_column(Text)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint(
            "tenant", "source_id", "external_id",
            name="uq_knowledge_documents_tenant_source_external",
        ),
        Index("ix_knowledge_documents_tenant_doc_type", "tenant", "doc_type"),
        Index("ix_knowledge_documents_tenant_status", "tenant", "status"),
        Index("ix_knowledge_documents_content_hash", "content_hash"),
        Index("ix_knowledge_documents_freshness_score", "freshness_score"),
    )


# ─── 3. KnowledgeChunk ──────────────────────────────────────────────────────


class KnowledgeChunk(Base, TimestampMixin):
    __tablename__ = "knowledge_chunks"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), index=True
    )
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64))
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    embedding_id: Mapped[Optional[str]] = mapped_column(
        String(128)
    )  # Qdrant point ID
    classification: Mapped[str] = mapped_column(
        String(32), nullable=False, default="INTERNAL"
    )
    metadata_: Mapped[Optional[dict]] = mapped_column(
        "metadata", JSONB, default=dict
    )  # file_path, line_start, line_end, etc.

    __table_args__ = (
        Index("ix_knowledge_chunks_tenant_classification", "tenant", "classification"),
    )


# ─── 4. KnowledgeEntity ─────────────────────────────────────────────────────


class KnowledgeEntity(Base, TimestampMixin):
    __tablename__ = "knowledge_entities"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # person|service|repository|dataset|api|team|file|concept
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    canonical_id: Mapped[Optional[str]] = mapped_column(String(256))
    description: Mapped[Optional[str]] = mapped_column(Text)
    source_ids: Mapped[Optional[list]] = mapped_column(
        JSONB, default=list
    )  # contributing knowledge_sources
    properties: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    classification: Mapped[str] = mapped_column(
        String(32), nullable=False, default="INTERNAL"
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")

    __table_args__ = (
        UniqueConstraint(
            "tenant", "entity_type", "canonical_id",
            name="uq_knowledge_entities_tenant_type_canonical",
        ),
        Index("ix_knowledge_entities_tenant_entity_type", "tenant", "entity_type"),
        Index("ix_knowledge_entities_name", "name"),
    )


# ─── 5. KnowledgeLink ───────────────────────────────────────────────────────


class KnowledgeLink(Base, TimestampMixin):
    __tablename__ = "knowledge_links"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), index=True
    )
    target_entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), index=True
    )
    link_type: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # DEPENDS_ON|OWNS|MAINTAINS|REFERENCES|DERIVED_FROM|etc.
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    properties: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    classification: Mapped[str] = mapped_column(
        String(32), nullable=False, default="INTERNAL"
    )

    __table_args__ = (
        Index("ix_knowledge_links_link_type", "link_type"),
        Index("ix_knowledge_links_tenant_link_type", "tenant", "link_type"),
    )


# ─── 6. KnowledgeIngestionJob ───────────────────────────────────────────────


class KnowledgeIngestionJob(Base, TimestampMixin):
    __tablename__ = "knowledge_ingestion_jobs"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), index=True
    )
    job_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # full|incremental|reindex
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    documents_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    documents_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    documents_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunks_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    worker_id: Mapped[Optional[str]] = mapped_column(String(64))

    __table_args__ = (
        Index("ix_knowledge_ingestion_jobs_tenant_status", "tenant", "status"),
    )


# ─── 7. KnowledgeQuery ──────────────────────────────────────────────────────


class KnowledgeQuery(Base, TimestampMixin):
    __tablename__ = "knowledge_queries"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    query_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="search"
    )  # search|rag|entity_lookup|graph_traverse
    filters: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    results_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    user_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(128))
    classification: Mapped[str] = mapped_column(
        String(32), nullable=False, default="INTERNAL"
    )
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        Index("ix_knowledge_queries_tenant_query_type", "tenant", "query_type"),
        Index("ix_knowledge_queries_created_at", "created_at"),
    )


# ─── 8. KnowledgeQueryResult ────────────────────────────────────────────────


class KnowledgeQueryResult(Base, TimestampMixin):
    __tablename__ = "knowledge_query_results"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    query_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), index=True
    )
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), index=True
    )
    chunk_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True))
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retrieval_method: Mapped[Optional[str]] = mapped_column(
        String(32)
    )  # lexical|vector|graph|hybrid
    citation: Mapped[Optional[str]] = mapped_column(Text)
    authored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        Index("ix_knowledge_query_results_score", "score"),
    )


# ─── 9. KnowledgeCacheEntry ────────────────────────────────────────────────


class KnowledgeCacheEntry(Base, TimestampMixin):
    """Cached search results with content-addressed keys and TTL expiry."""

    __tablename__ = "knowledge_cache_entries"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    cache_key: Mapped[str] = mapped_column(String(128), nullable=False)
    query_text: Mapped[str] = mapped_column(String(2048), nullable=False)
    results: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    filters: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    source_count: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    hit_count: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    last_hit_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant", "cache_key", name="uq_knowledge_cache_tenant_key"),
        Index("ix_knowledge_cache_tenant_expires", "tenant", "expires_at"),
    )


# ─── 10. KnowledgeExplanation ───────────────────────────────────────────────


class KnowledgeExplanation(Base, TimestampMixin):
    """Stored retrieval explanations for audit and debugging."""

    __tablename__ = "knowledge_explanations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    query_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    explanation_data: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    methods_used: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    result_count: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_knowledge_explanations_query_id", "query_id"),
    )


# ─── 11. KnowledgeAdminAudit ────────────────────────────────────────────────


class KnowledgeAdminAudit(Base, TimestampMixin):
    """Audit log for admin operations on the knowledge system."""

    __tablename__ = "knowledge_admin_audit"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="SUCCESS")

    __table_args__ = (
        Index("ix_knowledge_admin_audit_tenant_action", "tenant", "action"),
    )


# ─── 12. KnowledgeGraphCommunity ────────────────────────────────────────────


class KnowledgeGraphCommunity(Base, TimestampMixin):
    """Detected communities/clusters in the knowledge graph."""

    __tablename__ = "knowledge_graph_communities"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    entity_ids: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    entity_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_internal_weight: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")

    __table_args__ = (
        Index("ix_knowledge_graph_communities_tenant_status", "tenant", "status"),
    )
