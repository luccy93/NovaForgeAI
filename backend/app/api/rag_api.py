"""Volume 43 — Knowledge & Retrieval (RAG) API.

Exposes knowledge-source management, indexing, hybrid retrieval, graph
retrieval, citation validation, knowledge health and evaluation over the
already-built ``app.rag`` package.

Authorization model: every endpoint resolves ``tenant_id`` and
``organization_id`` from the authenticated user (treated as the same scoping
dimension). Repository-scoped endpoints additionally accept an optional
``repository_id`` that is resolved server-side — client-supplied tenant or
permission filters are never trusted.
"""

from __future__ import annotations

import math
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import _get_current_user
from app.core.database import get_db
from app.models.user import User

from app.rag import exceptions
from app.rag.events import RAGEventType, RAGEventEmitter
from app.rag.models import (
    KnowledgeSource,
    KnowledgeSourceVersion,
    RagChunk,
    RagEvaluationRun,
    RagRetrievalLog,
)
from app.rag.retrieval.query import route_query
from app.rag.retrieval.retrievers import GraphRetriever
from app.rag.schemas import Answerability

router = APIRouter(prefix="/rag", tags=["Knowledge & RAG"])


# ─── Testability hooks ─────────────────────────────────────────────────────
# Tests call ``configure_rag(fake_embedding, fake_vector_store)`` then rely on
# the cached factory functions below. They may also monkeypatch these functions.

_rag_service: Optional["object"] = None
_embedding_client: Optional["object"] = None
_vector_store: Optional["object"] = None


def configure_rag(embedding_client=None, vector_store=None) -> None:
    global _embedding_client, _vector_store
    _embedding_client = embedding_client
    _vector_store = vector_store


def get_rag_service():
    global _rag_service
    if _rag_service is None:
        from app.rag import RAGService

        _rag_service = RAGService(embedding_client=_embedding_client, vector_store=_vector_store)
    return _rag_service


def get_indexer():
    from app.rag import Indexer

    return Indexer(embedding_client=_embedding_client, vector_store=_vector_store)


def get_registry():
    from app.rag import KnowledgeSourceRegistry

    return KnowledgeSourceRegistry()


# ─── Authorization / scoping helpers ───────────────────────────────────────


def _resolve_scope(user: User) -> tuple[uuid.UUID, uuid.UUID]:
    """Resolve (tenant_id, organization_id) from the authenticated user.

    Tenant and organization are treated as the same scoping dimension. Falls
    back to the first membership if ``organization_id`` is not a direct
    attribute (defensive for multi-org users).
    """
    org_id = getattr(user, "organization_id", None)
    if org_id is None:
        orgs = getattr(user, "organizations", None) or []
        org_id = orgs[0].id if orgs else None
    if org_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not associated with an organization",
        )
    org_id = uuid.UUID(str(org_id))
    return org_id, org_id


def _as_uuid(value: Optional[str], name: str = "id") -> Optional[uuid.UUID]:
    if value is None or value == "":
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {name}: {value!r}",
        )


# ─── Pydantic request / response models ───────────────────────────────────


class SourceCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    source_type: str = Field(..., min_length=1, max_length=50)
    source_uri: Optional[str] = None
    repository_id: Optional[str] = None
    content: Optional[str] = None
    permissions: Optional[dict] = None
    classification: str = "internal"
    metadata: Optional[dict] = None


class SourcePermissionsUpdate(BaseModel):
    permissions: Optional[dict] = None
    classification: Optional[str] = None


class SourceOut(BaseModel):
    id: str
    tenant_id: Optional[str] = None
    organization_id: Optional[str] = None
    workspace_id: Optional[str] = None
    project_id: Optional[str] = None
    repository_id: Optional[str] = None
    name: str
    source_type: str
    source_uri: Optional[str] = None
    version: int = 1
    active_version_id: Optional[str] = None
    content_hash: Optional[str] = None
    owner_id: Optional[str] = None
    permissions: dict = {}
    classification: str = "internal"
    status: str = "queued"
    ingestion_status: str = "queued"
    last_indexed_at: Optional[str] = None
    is_stale: bool = False
    error: Optional[str] = None
    metadata: dict = {}
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class IndexRequest(BaseModel):
    content: Optional[str] = None


class IndexOut(BaseModel):
    source_id: str
    version_id: Optional[str] = None
    status: str


class SourceStatusOut(BaseModel):
    source_id: str
    status: str
    ingestion_status: str
    version: int
    active_version_id: Optional[str] = None
    is_stale: bool = False
    error: Optional[str] = None


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    repository_id: Optional[str] = None
    filters: Optional[dict] = None
    limit: Optional[int] = Field(None, ge=1, le=100)
    rerank_strategy: Optional[str] = None


class SearchOut(BaseModel):
    query: str
    intent: str
    answerability: str
    context: str
    chunks: list[dict] = []
    citations: list[dict] = []


class HybridOut(BaseModel):
    query: str
    intent: str
    answerability: str
    context_text: str
    token_count: int = 0
    chunks: list[dict] = []
    citations: list[dict] = []
    notes: list[str] = []
    budget: dict = {}


class ContextOut(BaseModel):
    query: str
    context_text: str
    token_count: int = 0
    answerability: str
    citations: list[dict] = []


class ValidateCitationsRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    repository_id: Optional[str] = None


class ValidateCitationsOut(BaseModel):
    valid: list[dict] = []
    invalid: list[dict] = []
    answerability: str


class GraphRetrieveRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    repository_id: Optional[str] = None
    limit: Optional[int] = Field(None, ge=1, le=100)


class GraphRetrieveOut(BaseModel):
    query: str
    repository_id: Optional[str] = None
    results: list[dict] = []


class IndexVersionOut(BaseModel):
    id: str
    source_id: str
    version: int = 1
    status: str
    chunk_count: int = 0
    is_active: bool = False
    activated_at: Optional[str] = None
    content_hash: Optional[str] = None


class HealthOut(BaseModel):
    total_sources: int = 0
    by_status: dict = {}
    stale_count: int = 0
    chunk_count: int = 0
    avg_retrieval_latency_ms: float = 0.0
    recent_retrieval_count: int = 0


class EvaluateRequest(BaseModel):
    dataset_name: str = Field(..., min_length=1, max_length=100)
    queries: list[str] = Field(..., min_length=1)
    expected_chunk_ids: list[list[str]] = Field(..., min_length=1)
    query_type: Optional[str] = None
    rerank_strategy: Optional[str] = None
    limit: Optional[int] = Field(10, ge=1, le=100)


class EvaluateOut(BaseModel):
    run_id: str
    dataset_name: str
    query_type: Optional[str] = None
    rerank_strategy: Optional[str] = None
    embedding_model: Optional[str] = None
    k: int
    recall_at_k: float = 0.0
    precision_at_k: float = 0.0
    mrr: float = 0.0
    ndcg: float = 0.0
    citation_accuracy: float = 0.0
    citation_coverage: float = 0.0
    groundedness: float = 0.0
    latency_ms: float = 0.0
    details: dict = {}


class EvaluationRunOut(BaseModel):
    id: str
    dataset_name: str
    query_type: Optional[str] = None
    rerank_strategy: Optional[str] = None
    embedding_model: Optional[str] = None
    recall_at_k: float = 0.0
    precision_at_k: float = 0.0
    mrr: float = 0.0
    ndcg: float = 0.0
    citation_accuracy: float = 0.0
    citation_coverage: float = 0.0
    groundedness: float = 0.0
    latency_ms: float = 0.0
    created_at: Optional[str] = None


# ─── Mapping helpers ──────────────────────────────────────────────────────


def _iso(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _source_to_dict(src: KnowledgeSource) -> dict:
    return {
        "id": str(src.id),
        "tenant_id": str(src.tenant_id) if src.tenant_id else None,
        "organization_id": str(src.organization_id) if src.organization_id else None,
        "workspace_id": str(src.workspace_id) if src.workspace_id else None,
        "project_id": str(src.project_id) if src.project_id else None,
        "repository_id": str(src.repository_id) if src.repository_id else None,
        "name": src.name,
        "source_type": src.source_type,
        "source_uri": src.source_uri,
        "version": src.version,
        "active_version_id": str(src.active_version_id) if src.active_version_id else None,
        "content_hash": src.content_hash,
        "owner_id": str(src.owner_id) if src.owner_id else None,
        "permissions": src.permissions or {},
        "classification": src.classification,
        "status": src.status,
        "ingestion_status": src.ingestion_status,
        "last_indexed_at": _iso(src.last_indexed_at),
        "is_stale": bool(src.is_stale),
        "error": src.error,
        "metadata": src.metadata_ or {},
        "created_at": _iso(src.created_at),
        "updated_at": _iso(src.updated_at),
    }


def _version_to_dict(v: KnowledgeSourceVersion) -> dict:
    return {
        "id": str(v.id),
        "source_id": str(v.source_id),
        "version": v.version,
        "status": v.status,
        "chunk_count": v.chunk_count or 0,
        "is_active": bool(v.is_active),
        "activated_at": _iso(v.activated_at),
        "content_hash": v.content_hash,
    }


# ─── 1. Knowledge source management ────────────────────────────────────────


@router.post("/sources", response_model=SourceOut, status_code=status.HTTP_201_CREATED)
async def create_source(
    body: SourceCreateRequest,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register a new knowledge source (server-side tenant scoping)."""
    tenant_id, organization_id = _resolve_scope(user)
    repository_id = _as_uuid(body.repository_id, "repository_id")
    registry = get_registry()
    try:
        src = await registry.create_source(
            db,
            tenant_id=tenant_id,
            organization_id=organization_id,
            name=body.name,
            source_type=body.source_type,
            source_uri=body.source_uri,
            repository_id=repository_id,
            owner_id=getattr(user, "id", None),
            permissions=body.permissions,
            classification=body.classification,
            content=body.content,
            metadata_=body.metadata,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create source: {exc}",
        )
    await db.commit()
    await db.refresh(src)
    return SourceOut(**_source_to_dict(src))


@router.get("/sources", response_model=list[SourceOut])
async def list_sources(
    repository_id: Optional[str] = Query(None),
    source_type: Optional[str] = Query(None),
    source_status: Optional[str] = Query(None, alias="status"),
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List knowledge sources visible to the authenticated tenant."""
    tenant_id, _ = _resolve_scope(user)
    registry = get_registry()
    sources = await registry.list_sources(
        db,
        tenant_id,
        repository_id=_as_uuid(repository_id, "repository_id"),
        source_type=source_type,
        status=source_status,
    )
    return [SourceOut(**_source_to_dict(s)) for s in sources]


@router.get("/sources/{source_id}", response_model=SourceOut)
async def get_source(
    source_id: uuid.UUID,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single knowledge source."""
    tenant_id, _ = _resolve_scope(user)
    registry = get_registry()
    src = await registry.get_source(db, source_id)
    if src is None or src.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    return SourceOut(**_source_to_dict(src))


@router.post("/sources/{source_id}/index", response_model=IndexOut)
async def index_source(
    source_id: uuid.UUID,
    body: IndexRequest = IndexRequest(),
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger indexing of a knowledge source; returns the new version id."""
    tenant_id, _ = _resolve_scope(user)
    registry = get_registry()
    src = await registry.get_source(db, source_id)
    if src is None or src.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    indexer = get_indexer()
    try:
        version_id = await indexer.index_source(
            db, source_id, content=body.content, registry=registry
        )
    except exceptions.SourceNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Indexing failed: {exc}",
        )
    await db.commit()
    refreshed = await registry.get_source(db, source_id)
    return IndexOut(
        source_id=str(source_id),
        version_id=str(version_id),
        status=refreshed.ingestion_status if refreshed else "validated",
    )


@router.delete("/sources/{source_id}", response_model=IndexOut)
async def delete_source(
    source_id: uuid.UUID,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a source and propagate deletion to chunks + vectors."""
    tenant_id, _ = _resolve_scope(user)
    registry = get_registry()
    src = await registry.get_source(db, source_id)
    if src is None or src.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    indexer = get_indexer()
    try:
        await indexer.delete_propagation(db, source_id, registry=registry)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Delete propagation failed: {exc}",
        )
    await db.commit()
    return IndexOut(source_id=str(source_id), version_id=None, status="deleted")


@router.get("/sources/{source_id}/status", response_model=SourceStatusOut)
async def source_status(
    source_id: uuid.UUID,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the current status/version/staleness of a source."""
    tenant_id, _ = _resolve_scope(user)
    registry = get_registry()
    src = await registry.get_source(db, source_id)
    if src is None or src.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    return SourceStatusOut(
        source_id=str(src.id),
        status=src.status,
        ingestion_status=src.ingestion_status,
        version=src.version,
        active_version_id=str(src.active_version_id) if src.active_version_id else None,
        is_stale=bool(src.is_stale),
        error=src.error,
    )


@router.put("/sources/{source_id}/permissions", response_model=SourceOut)
async def update_permissions(
    source_id: uuid.UUID,
    body: SourcePermissionsUpdate,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update permissions/classification and emit a permission-changed event."""
    tenant_id, _ = _resolve_scope(user)
    registry = get_registry()
    src = await registry.get_source(db, source_id)
    if src is None or src.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")

    if body.permissions is not None:
        src.permissions = body.permissions
    if body.classification is not None:
        src.classification = body.classification
    await db.flush()

    RAGEventEmitter(repository_id=str(src.repository_id) if src.repository_id else None).emit(
        RAGEventType.PERMISSION_CHANGED, source_id=str(source_id)
    )
    await db.commit()
    await db.refresh(src)
    return SourceOut(**_source_to_dict(src))


# ─── 2. Retrieval ────────────────────────────────────────────────────────


def _retrieve_payload(
    db: AsyncSession,
    query: str,
    user: User,
    tenant_id: uuid.UUID,
    organization_id: uuid.UUID,
    repository_id: Optional[str],
    filters: Optional[dict],
    limit: Optional[int],
    rerank_strategy: Optional[str],
) -> dict:
    return dict(
        db=db,
        query=query,
        user=user,
        tenant_id=tenant_id,
        organization_id=organization_id,
        repository_id=_as_uuid(repository_id, "repository_id"),
        filters=filters,
        limit=limit,
        rerank_strategy=rerank_strategy,
        use_cache=True,
    )


@router.post("/search", response_model=SearchOut)
async def search(
    body: SearchRequest,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Hybrid retrieval that returns assembled context + citations."""
    tenant_id, organization_id = _resolve_scope(user)
    service = get_rag_service()
    plan = route_query(body.query, service.config, body.filters or {})
    try:
        ctx = await service.retrieve(
            **_retrieve_payload(
                db, body.query, user, tenant_id, organization_id,
                body.repository_id, body.filters, body.limit, body.rerank_strategy,
            )
        )
    except exceptions.InsufficientEvidenceError:
        return SearchOut(
            query=body.query, intent=plan.intent,
            answerability=Answerability.INSUFFICIENT.value,
            context="", chunks=[], citations=[],
        )
    except exceptions.RagError:
        return SearchOut(
            query=body.query, intent=plan.intent,
            answerability=Answerability.INSUFFICIENT.value,
            context="", chunks=[], citations=[],
        )
    data = ctx.to_dict()
    return SearchOut(
        query=body.query,
        intent=plan.intent,
        answerability=data["answerability"],
        context=data["context_text"],
        chunks=data["chunks"],
        citations=data["citations"],
    )


@router.post("/hybrid", response_model=HybridOut)
async def hybrid(
    body: SearchRequest,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Hybrid retrieval returning the full ContextSet plus the query intent."""
    tenant_id, organization_id = _resolve_scope(user)
    service = get_rag_service()
    plan = route_query(body.query, service.config, body.filters or {})
    try:
        ctx = await service.retrieve(
            **_retrieve_payload(
                db, body.query, user, tenant_id, organization_id,
                body.repository_id, body.filters, body.limit, body.rerank_strategy,
            )
        )
    except exceptions.InsufficientEvidenceError:
        return HybridOut(
            query=body.query, intent=plan.intent,
            answerability=Answerability.INSUFFICIENT.value,
            context_text="", chunks=[], citations=[], notes=[],
        )
    except exceptions.RagError:
        return HybridOut(
            query=body.query, intent=plan.intent,
            answerability=Answerability.INSUFFICIENT.value,
            context_text="", chunks=[], citations=[], notes=[],
        )
    data = ctx.to_dict()
    return HybridOut(
        query=body.query,
        intent=plan.intent,
        answerability=data["answerability"],
        context_text=data["context_text"],
        token_count=data["token_count"],
        chunks=data["chunks"],
        citations=data["citations"],
        notes=data["notes"],
        budget=data["budget"],
    )


@router.post("/context", response_model=ContextOut)
async def context(
    body: SearchRequest,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return only the assembled context set (text, tokens, citations)."""
    tenant_id, organization_id = _resolve_scope(user)
    service = get_rag_service()
    try:
        ctx = await service.retrieve(
            **_retrieve_payload(
                db, body.query, user, tenant_id, organization_id,
                body.repository_id, body.filters, body.limit, body.rerank_strategy,
            )
        )
    except exceptions.InsufficientEvidenceError:
        return ContextOut(
            query=body.query, context_text="",
            answerability=Answerability.INSUFFICIENT.value, citations=[],
        )
    except exceptions.RagError:
        return ContextOut(
            query=body.query, context_text="",
            answerability=Answerability.INSUFFICIENT.value, citations=[],
        )
    data = ctx.to_dict()
    return ContextOut(
        query=body.query,
        context_text=data["context_text"],
        token_count=data["token_count"],
        answerability=data["answerability"],
        citations=data["citations"],
    )


@router.post("/citations/validate", response_model=ValidateCitationsOut)
async def validate_citations(
    body: ValidateCitationsRequest,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run retrieval and split resulting citations into valid / invalid."""
    tenant_id, organization_id = _resolve_scope(user)
    service = get_rag_service()
    repository_id = _as_uuid(body.repository_id, "repository_id")
    filters = {"repository_id": repository_id} if repository_id is not None else {}
    plan = route_query(body.query, service.config, filters)

    results: dict[str, list] = {}
    results["lexical"] = await service.lexical.search(
        db, body.query, tenant_id=tenant_id, filters=filters, limit=service.config.default_limit
    )
    results["vector"] = await service.vector.search(
        db, body.query, tenant_id=tenant_id, filters=filters, limit=service.config.default_limit
    )
    from app.rag.retrieval.fusion import reciprocal_rank_fusion

    fused = reciprocal_rank_fusion(results, plan.weights, k=service.config.rrf_k)
    reranked = service.reranker.rerank(fused, body.query, service.config.rerank_strategy)

    valid: list[dict] = []
    invalid: list[dict] = []
    for chunk in reranked:
        ok, _detail, cit = await service.citations.validate(
            chunk, db, user=user, config=service.config
        )
        if ok and cit is not None:
            valid.append(cit.to_dict())
        else:
            invalid.append(service.citations.build(chunk).to_dict())

    answerability = Answerability.HIGH_CONFIDENCE.value if valid else Answerability.INSUFFICIENT.value
    return ValidateCitationsOut(valid=valid, invalid=invalid, answerability=answerability)


@router.post("/graph/retrieve", response_model=GraphRetrieveOut)
async def graph_retrieve(
    body: GraphRetrieveRequest,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Graph traversal retrieval over the code-intelligence graph."""
    tenant_id, _ = _resolve_scope(user)
    repository_id = _as_uuid(body.repository_id, "repository_id")
    filters = {"repository_id": repository_id} if repository_id is not None else {}
    try:
        chunks = await GraphRetriever().search(
            db, body.query, tenant_id=tenant_id, filters=filters, limit=body.limit or 20
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Graph retrieval failed: {exc}",
        )
    return GraphRetrieveOut(
        query=body.query,
        repository_id=body.repository_id,
        results=[c.to_dict() for c in chunks],
    )


@router.get("/index/versions", response_model=list[IndexVersionOut])
async def index_versions(
    source_id: Optional[str] = Query(None),
    repository_id: Optional[str] = Query(None),
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List knowledge source versions scoped to the tenant."""
    tenant_id, _ = _resolve_scope(user)
    sid = _as_uuid(source_id, "source_id")
    rid = _as_uuid(repository_id, "repository_id")

    stmt = (
        select(KnowledgeSourceVersion)
        .join(KnowledgeSource, KnowledgeSourceVersion.source_id == KnowledgeSource.id)
        .where(KnowledgeSource.tenant_id == tenant_id)
    )
    if sid is not None:
        stmt = stmt.where(KnowledgeSourceVersion.source_id == sid)
    if rid is not None:
        stmt = stmt.where(KnowledgeSource.repository_id == rid)
    stmt = stmt.order_by(KnowledgeSourceVersion.created_at.desc())
    res = await db.execute(stmt)
    versions = res.scalars().all()
    return [_version_to_dict(v) for v in versions]


@router.get("/health", response_model=HealthOut)
async def knowledge_health(
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Knowledge health: source counts by status, staleness, chunks, latency."""
    tenant_id, _ = _resolve_scope(user)

    total_res = await db.execute(
        select(func.count()).select_from(KnowledgeSource).where(KnowledgeSource.tenant_id == tenant_id)
    )
    total = total_res.scalar() or 0

    status_res = await db.execute(
        select(KnowledgeSource.status, func.count())
        .where(KnowledgeSource.tenant_id == tenant_id)
        .group_by(KnowledgeSource.status)
    )
    by_status = {row[0]: row[1] for row in status_res.all()}

    stale_res = await db.execute(
        select(func.count())
        .select_from(KnowledgeSource)
        .where(KnowledgeSource.tenant_id == tenant_id, KnowledgeSource.is_stale.is_(True))
    )
    stale = stale_res.scalar() or 0

    chunk_res = await db.execute(
        select(func.count())
        .select_from(RagChunk)
        .where(RagChunk.tenant_id == tenant_id, RagChunk.is_deleted.is_(False))
    )
    chunk_count = chunk_res.scalar() or 0

    since = datetime.utcnow() - timedelta(hours=24)
    lat_res = await db.execute(
        select(func.avg(RagRetrievalLog.total_latency_ms))
        .where(RagRetrievalLog.tenant_id == tenant_id, RagRetrievalLog.created_at >= since)
    )
    avg_latency = lat_res.scalar()
    avg_latency = float(avg_latency) if avg_latency is not None else 0.0

    cnt_res = await db.execute(
        select(func.count())
        .select_from(RagRetrievalLog)
        .where(RagRetrievalLog.tenant_id == tenant_id, RagRetrievalLog.created_at >= since)
    )
    recent_count = cnt_res.scalar() or 0

    return HealthOut(
        total_sources=total,
        by_status=by_status,
        stale_count=stale,
        chunk_count=chunk_count,
        avg_retrieval_latency_ms=round(avg_latency, 3),
        recent_retrieval_count=recent_count,
    )


# ─── 3. Evaluation ───────────────────────────────────────────────────────


@router.post("/evaluate", response_model=EvaluateOut)
async def evaluate(
    body: EvaluateRequest,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Compute IR metrics over provided queries vs expected chunk ids."""
    tenant_id, organization_id = _resolve_scope(user)
    service = get_rag_service()

    if len(body.queries) != len(body.expected_chunk_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="`queries` and `expected_chunk_ids` must have equal length",
        )

    k = min(body.limit or 10, 10)
    t0 = time.perf_counter()

    recalls: list[float] = []
    precisions: list[float] = []
    rrs: list[float] = []
    ndcgs: list[float] = []
    grounded: list[float] = []
    citation_acc: list[float] = []

    for query, expected in zip(body.queries, body.expected_chunk_ids):
        expected_set = {str(e) for e in (expected or [])}
        try:
            ctx = await service.retrieve(
                **_retrieve_payload(
                    db, query, user, tenant_id, organization_id, None, None, k, body.rerank_strategy
                )
            )
            retrieved = [str(c.chunk_id) for c in ctx.chunks]
            valid_citations = len(ctx.citations)
        except exceptions.InsufficientEvidenceError:
            retrieved = []
            valid_citations = 0
        except exceptions.RagError:
            retrieved = []
            valid_citations = 0

        top_k = retrieved[:k]
        rel_flags = [1 if cid in expected_set else 0 for cid in top_k]

        # Recall@K
        if expected_set:
            recall = len(expected_set & set(top_k)) / len(expected_set)
        else:
            recall = 1.0
        # Precision@K
        precision = (sum(rel_flags) / k) if k else 0.0

        # MRR
        mrr = 0.0
        for i, cid in enumerate(retrieved, start=1):
            if cid in expected_set:
                mrr = 1.0 / i
                break

        # NDCG@K
        dcg = sum(r / math.log2(i + 2) for i, r in enumerate(rel_flags))
        ideal_rel = sorted(rel_flags, reverse=True)
        idcg = sum(r / math.log2(i + 2) for i, r in enumerate(ideal_rel))
        ndcg = dcg / idcg if idcg > 0 else 0.0

        recalls.append(recall)
        precisions.append(precision)
        rrs.append(mrr)
        ndcgs.append(ndcg)
        grounded.append(1.0 if retrieved else 0.0)
        citation_acc.append(min(1.0, valid_citations / k) if k else 0.0)

    def _mean(xs: list[float]) -> float:
        return round(sum(xs) / len(xs), 4) if xs else 0.0

    latency_ms = (time.perf_counter() - t0) * 1000.0

    run = RagEvaluationRun(
        tenant_id=tenant_id,
        organization_id=organization_id,
        dataset_name=body.dataset_name,
        query_type=body.query_type,
        rerank_strategy=body.rerank_strategy or service.config.rerank_strategy,
        embedding_model=service.embeddings.model,
        recall_at_k=_mean(recalls),
        precision_at_k=_mean(precisions),
        mrr=_mean(rrs),
        ndcg=_mean(ndcgs),
        citation_accuracy=_mean(citation_acc),
        citation_coverage=_mean(recalls),
        groundedness=_mean(grounded),
        latency_ms=round(latency_ms, 3),
        details={"k": k, "n_queries": len(body.queries)},
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    return EvaluateOut(
        run_id=str(run.id),
        dataset_name=run.dataset_name,
        query_type=run.query_type,
        rerank_strategy=run.rerank_strategy,
        embedding_model=run.embedding_model,
        k=k,
        recall_at_k=run.recall_at_k,
        precision_at_k=run.precision_at_k,
        mrr=run.mrr,
        ndcg=run.ndcg,
        citation_accuracy=run.citation_accuracy,
        citation_coverage=run.citation_coverage,
        groundedness=run.groundedness,
        latency_ms=run.latency_ms,
        details=run.details or {},
    )


@router.get("/evaluation/runs", response_model=list[EvaluationRunOut])
async def list_evaluation_runs(
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List recent RAG evaluation runs for the tenant."""
    tenant_id, _ = _resolve_scope(user)
    res = await db.execute(
        select(RagEvaluationRun)
        .where(RagEvaluationRun.tenant_id == tenant_id)
        .order_by(RagEvaluationRun.created_at.desc())
        .limit(limit)
    )
    runs = res.scalars().all()
    return [
        EvaluationRunOut(
            id=str(r.id),
            dataset_name=r.dataset_name,
            query_type=r.query_type,
            rerank_strategy=r.rerank_strategy,
            embedding_model=r.embedding_model,
            recall_at_k=r.recall_at_k,
            precision_at_k=r.precision_at_k,
            mrr=r.mrr,
            ndcg=r.ndcg,
            citation_accuracy=r.citation_accuracy,
            citation_coverage=r.citation_coverage,
            groundedness=r.groundedness,
            latency_ms=r.latency_ms,
            created_at=_iso(r.created_at),
        )
        for r in runs
    ]
