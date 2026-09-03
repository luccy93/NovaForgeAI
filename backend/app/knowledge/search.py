"""Unified search service — Volume 68.

Orchestrates retrieval → ranking → auth filtering → paginated response.
"""

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from sqlalchemy import select, func

from app.knowledge.common import (
    DEFAULT_RESULTS,
    MAX_QUERY_LENGTH,
    MAX_RESULTS,
    SEARCH_PERMISSION,
    PermissionDeniedError,
    NotFoundError,
    emit_event,
    ingest_metric_best_effort,
    record_usage_best_effort,
)
from app.knowledge.models import (
    KnowledgeDocument,
    KnowledgeQuery,
    KnowledgeQueryResult,
    KnowledgeSource,
)
from app.knowledge.retrieval import hybrid_search
from app.knowledge.ranking import (
    apply_freshness_boost,
    normalize_scores,
    rerank_by_relevance,
)

logger = logging.getLogger(__name__)

_CLEARANCE_ORDER = {"PUBLIC": 0, "INTERNAL": 1, "CONFIDENTIAL": 2, "SECRET": 3}


# ─── Main search entry point ────────────────────────────────────────────────


async def search(
    db,
    tenant: str,
    query: str,
    *,
    filters: Optional[dict] = None,
    limit: int = DEFAULT_RESULTS,
    offset: int = 0,
    embed_fn: Optional[Callable] = None,
    user: Any = None,
) -> dict:
    """Search, rank, filter, paginate, audit.

    Returns ``{"items", "total", "query_id", "latency_ms", "filters_applied"}``.
    """
    start = time.monotonic()
    query_id = uuid.uuid4()

    # ── 1. validate ──────────────────────────────────────────────────────
    query = (query or "").strip()
    if not query:
        return _empty_response(query_id, start, filters)
    if len(query) > MAX_QUERY_LENGTH:
        query = query[:MAX_QUERY_LENGTH]
    limit = max(1, min(limit, MAX_RESULTS))
    offset = max(0, offset)

    filters = filters or {}

    # ── 2. retrieval ─────────────────────────────────────────────────────
    raw_results = await hybrid_search(
        db, tenant, query, filters=filters, limit=limit + offset + 20, embed_fn=embed_fn
    )

    # ── 3. freshness boost ──────────────────────────────────────────────
    freshness_map = await _build_freshness_map(db, tenant, raw_results)
    raw_results = apply_freshness_boost(raw_results, freshness_map)

    # ── 4. rerank ────────────────────────────────────────────────────────
    raw_results = rerank_by_relevance(raw_results, query)
    raw_results = normalize_scores(raw_results)

    # ── 5. auth filter ──────────────────────────────────────────────────
    raw_results = _filter_by_classification(raw_results, user)

    total = len(raw_results)

    # ── 6. paginate ─────────────────────────────────────────────────────
    page = raw_results[offset : offset + limit]

    # ── 7. enrich ────────────────────────────────────────────────────────
    items = await _enrich_results(db, tenant, page)

    # ── 8. audit ────────────────────────────────────────────────────────
    latency_ms = int((time.monotonic() - start) * 1000)
    await _audit_query(db, tenant, query, query_id, filters, total, latency_ms, user)

    # ── 9. bill & emit ──────────────────────────────────────────────────
    record_usage_best_effort(tenant, "search", 1)
    try:
        await emit_event(
            "knowledge_search",
            {"query_id": str(query_id), "results": total, "latency_ms": latency_ms},
            tenant,
        )
    except Exception:
        pass

    try:
        ingest_metric_best_effort(
            "knowledge.search.latency_ms", latency_ms, tags={"tenant": tenant}
        )
    except Exception:
        pass

    return {
        "items": items,
        "total": total,
        "query_id": str(query_id),
        "latency_ms": latency_ms,
        "filters_applied": filters,
    }


# ─── Document / source lookups ──────────────────────────────────────────────


async def get_document(db, tenant: str, document_id) -> dict:
    """Fetch a single document with full metadata."""
    stmt = select(KnowledgeDocument).where(
        KnowledgeDocument.id == document_id,
        KnowledgeDocument.tenant == tenant,
    )
    doc = (await db.execute(stmt)).scalar_one_or_none()
    if doc is None:
        raise NotFoundError(f"Document {document_id} not found")
    return {
        "document_id": str(doc.id),
        "title": doc.title,
        "content": doc.content,
        "summary": doc.summary,
        "doc_type": doc.doc_type,
        "version": doc.version,
        "classification": doc.classification,
        "source_id": str(doc.source_id) if doc.source_id else None,
        "freshness_score": doc.freshness_score,
        "chunk_count": doc.chunk_count,
        "status": doc.status,
        "tags": doc.tags or [],
        "attribution": doc.attribution or {},
        "language": doc.language,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
    }


async def list_sources(
    db,
    tenant: str,
    *,
    status: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """List knowledge sources for a tenant."""
    conditions = [KnowledgeSource.tenant == tenant]
    if status:
        conditions.append(KnowledgeSource.status == status)

    stmt = (
        select(KnowledgeSource)
        .where(*conditions)
        .order_by(KnowledgeSource.created_at.desc())
        .limit(min(limit, MAX_RESULTS))
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [_source_to_dict(s) for s in rows]


async def get_source(db, tenant: str, source_id) -> dict:
    """Fetch a single knowledge source."""
    stmt = select(KnowledgeSource).where(
        KnowledgeSource.id == source_id,
        KnowledgeSource.tenant == tenant,
    )
    src = (await db.execute(stmt)).scalar_one_or_none()
    if src is None:
        raise NotFoundError(f"Source {source_id} not found")
    return _source_to_dict(src)


# ─── Private helpers ─────────────────────────────────────────────────────────


async def _build_freshness_map(db, tenant: str, results: list[dict]) -> dict:
    """Batch-load freshness scores for documents in the result set."""
    doc_ids = list({r["document_id"] for r in results if r.get("document_id")})
    if not doc_ids:
        return {}
    stmt = select(KnowledgeDocument.id, KnowledgeDocument.freshness_score).where(
        KnowledgeDocument.tenant == tenant,
        KnowledgeDocument.id.in_(doc_ids),
    )
    rows = (await db.execute(stmt)).fetchall()
    return {str(row[0]): row[1] for row in rows}


def _filter_by_classification(results: list[dict], user: Any) -> list[dict]:
    """Drop results whose classification exceeds the user's clearance."""
    if user is None:
        return [r for r in results if r.get("classification", "INTERNAL") in ("PUBLIC", "INTERNAL")]
    user_clearance = getattr(user, "clearance", None) or getattr(user, "classification", "INTERNAL")
    max_level = _CLEARANCE_ORDER.get(str(user_clearance).upper(), 1)
    return [
        r
        for r in results
        if _CLEARANCE_ORDER.get(str(r.get("classification", "INTERNAL")).upper(), 1) <= max_level
    ]


async def _enrich_results(db, tenant: str, results: list[dict]) -> list[dict]:
    """Build citations and normalize output for each result."""
    doc_ids = list({r["document_id"] for r in results if r.get("document_id")})
    doc_map: dict[str, dict] = {}
    if doc_ids:
        stmt = select(KnowledgeDocument).where(
            KnowledgeDocument.tenant == tenant,
            KnowledgeDocument.id.in_(doc_ids),
        )
        docs = (await db.execute(stmt)).scalars().all()
        doc_map = {str(d.id): d for d in docs}

    enriched: list[dict] = []
    for r in results:
        doc = doc_map.get(str(r.get("document_id"))) if r.get("document_id") else None
        source_type = None
        version = None
        attribution = {}
        if doc:
            source_type = doc.doc_type
            version = doc.version
            attribution = doc.attribution or {}

        citation = {
            "source_name": attribution.get("author", "unknown"),
            "doc_type": source_type,
            "version": version,
            "url": attribution.get("url"),
        }

        enriched.append({
            "document_id": r.get("document_id"),
            "chunk_id": r.get("chunk_id"),
            "title": r.get("title") or (doc.title if doc else None),
            "snippet": r.get("snippet", ""),
            "score": round(r.get("score", 0.0), 6),
            "source_type": source_type,
            "classification": r.get("classification", "INTERNAL"),
            "freshness_score": r.get("freshness_score"),
            "citations": [citation],
            "retrieval_method": r.get("method", "hybrid"),
        })

    return enriched


async def _audit_query(
    db,
    tenant: str,
    query: str,
    query_id: uuid.UUID,
    filters: dict,
    results_count: int,
    latency_ms: int,
    user: Any,
):
    """Insert a KnowledgeQuery audit record."""
    try:
        user_id = None
        if user is not None:
            user_id = str(getattr(user, "id", "") or "")

        record = KnowledgeQuery(
            id=query_id,
            tenant=tenant,
            query_text=query,
            query_type="search",
            filters=filters,
            results_count=results_count,
            latency_ms=latency_ms,
            user_id=user_id,
            classification="INTERNAL",
        )
        db.add(record)
        await db.flush()
    except Exception as exc:
        logger.warning("Audit query insert failed: %s", exc)


def _source_to_dict(src: KnowledgeSource) -> dict:
    return {
        "source_id": str(src.id),
        "name": src.name,
        "source_type": src.source_type,
        "status": src.status,
        "classification": src.classification,
        "owner": src.owner,
        "region": src.region,
        "last_ingested_at": src.last_ingested_at.isoformat() if src.last_ingested_at else None,
        "created_at": src.created_at.isoformat() if src.created_at else None,
    }


def _empty_response(query_id: uuid.UUID, start: float, filters: dict) -> dict:
    latency_ms = int((time.monotonic() - start) * 1000)
    return {
        "items": [],
        "total": 0,
        "query_id": str(query_id),
        "latency_ms": latency_ms,
        "filters_applied": filters,
    }
