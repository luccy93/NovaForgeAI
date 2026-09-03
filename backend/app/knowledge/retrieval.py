"""Hybrid retrieval engine — PostgreSQL lexical + Qdrant vector + Neo4j graph.

Volume 68 — Universal Knowledge & Search Platform.
"""

import logging
import uuid
from typing import Any, Callable, Optional

from sqlalchemy import and_, or_, select, func

from app.knowledge.common import MAX_GRAPH_RESULTS, emit_event
from app.knowledge.models import KnowledgeChunk, KnowledgeDocument, KnowledgeEntity, KnowledgeLink

logger = logging.getLogger(__name__)


# ─── Lexical search ──────────────────────────────────────────────────────────


async def lexical_search(
    db,
    tenant: str,
    query: str,
    *,
    filters: Optional[dict] = None,
    limit: int = 20,
) -> list[dict]:
    """PostgreSQL ILIKE search on document title/content/summary and chunk content."""
    filters = filters or {}
    terms = [t.strip() for t in query.split() if t.strip()]
    if not terms:
        return []

    doc_conditions = []
    chunk_conditions = []
    for term in terms:
        pattern = f"%{term}%"
        doc_conditions.append(
            or_(
                KnowledgeDocument.title.ilike(pattern),
                KnowledgeDocument.content.ilike(pattern),
                KnowledgeDocument.summary.ilike(pattern),
            )
        )
        chunk_conditions.append(KnowledgeChunk.content.ilike(pattern))

    base_doc_filters = [KnowledgeDocument.tenant == tenant]
    base_chunk_filters = [KnowledgeChunk.tenant == tenant]

    if filters.get("classification"):
        base_doc_filters.append(KnowledgeDocument.classification == filters["classification"])
        base_chunk_filters.append(KnowledgeChunk.classification == filters["classification"])
    if filters.get("doc_type"):
        base_doc_filters.append(KnowledgeDocument.doc_type == filters["doc_type"])
    if filters.get("source_id"):
        sid = filters["source_id"]
        base_doc_filters.append(KnowledgeDocument.source_id == sid)
        base_chunk_filters.append(KnowledgeChunk.source_id == sid)
    if filters.get("created_after"):
        base_doc_filters.append(KnowledgeDocument.created_at >= filters["created_after"])
    if filters.get("created_before"):
        base_doc_filters.append(KnowledgeDocument.created_at <= filters["created_before"])

    results: list[dict] = []
    seen_docs: set[uuid.UUID] = set()

    # --- document-level match ---
    try:
        doc_stmt = (
            select(
                KnowledgeDocument.id,
                KnowledgeDocument.title,
                KnowledgeDocument.content,
                KnowledgeDocument.summary,
                KnowledgeDocument.source_id,
                KnowledgeDocument.freshness_score,
                KnowledgeDocument.classification,
                KnowledgeDocument.doc_type,
                KnowledgeDocument.version,
                KnowledgeDocument.attribution,
            )
            .where(and_(*base_doc_filters, *doc_conditions))
            .order_by(KnowledgeDocument.freshness_score.desc())
            .limit(limit)
        )
        doc_rows = (await db.execute(doc_stmt)).fetchall()
        for row in doc_rows:
            doc_id = row[0]
            if doc_id in seen_docs:
                continue
            seen_docs.add(doc_id)
            score = _score_lexical_match(
                query, title=row[1], content=row[2], summary=row[3]
            )
            results.append({
                "document_id": doc_id,
                "chunk_id": None,
                "title": row[1],
                "snippet": _extract_snippet(row[2], terms),
                "score": score,
                "method": "lexical",
                "source_id": row[4],
                "freshness_score": row[5],
                "classification": row[6],
                "doc_type": row[7],
                "version": row[8],
                "attribution": row[9] or {},
            })
    except Exception as exc:
        logger.warning("Lexical document search failed: %s", exc)

    # --- chunk-level match ---
    try:
        chunk_stmt = (
            select(
                KnowledgeChunk.id,
                KnowledgeChunk.document_id,
                KnowledgeChunk.content,
                KnowledgeChunk.source_id,
                KnowledgeChunk.classification,
            )
            .where(and_(*base_chunk_filters, *chunk_conditions))
            .limit(limit)
        )
        chunk_rows = (await db.execute(chunk_stmt)).fetchall()
        for row in chunk_rows:
            chunk_id, doc_id = row[0], row[1]
            if doc_id and doc_id in seen_docs:
                continue
            if doc_id:
                seen_docs.add(doc_id)
            score = _score_lexical_match(query, content=row[2])
            results.append({
                "document_id": doc_id,
                "chunk_id": chunk_id,
                "title": None,
                "snippet": _extract_snippet(row[2], terms),
                "score": score,
                "method": "lexical",
                "source_id": row[3],
                "classification": row[4],
            })
    except Exception as exc:
        logger.warning("Lexical chunk search failed: %s", exc)

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:limit]


# ─── Vector search ───────────────────────────────────────────────────────────


async def vector_search(
    db,
    tenant: str,
    query: str,
    *,
    filters: Optional[dict] = None,
    limit: int = 20,
    embed_fn: Optional[Callable] = None,
) -> list[dict]:
    """Qdrant cosine similarity search on the knowledge_chunks collection."""
    if embed_fn is None:
        return []

    try:
        from app.services.vector_store import VectorStoreService

        vss = VectorStoreService()
        query_vector = await embed_fn(query)

        payload_filter = {"must": [{"key": "tenant", "match": {"value": tenant}}]}
        if filters:
            if filters.get("classification"):
                payload_filter["must"].append(
                    {"key": "classification", "match": {"value": filters["classification"]}}
                )
            if filters.get("source_id"):
                payload_filter["must"].append(
                    {"key": "source_id", "match": {"value": str(filters["source_id"])}}
                )

        collection_name = f"knowledge_{tenant}"
        hits = vss.search(
            collection_name,
            query_vector=query_vector,
            limit=limit,
            filter_=payload_filter,
        )

        results: list[dict] = []
        for hit in hits:
            payload = hit.get("payload") or {}
            results.append({
                "chunk_id": payload.get("chunk_id"),
                "document_id": payload.get("document_id"),
                "score": float(hit.get("score", 0)),
                "method": "vector",
                "source_id": payload.get("source_id"),
                "classification": payload.get("classification"),
            })
        return results
    except Exception as exc:
        logger.warning("Vector search unavailable: %s", exc)
        return []


# ─── Graph search ────────────────────────────────────────────────────────────


async def graph_search(
    db,
    tenant: str,
    query: str,
    *,
    entity_types: Optional[list[str]] = None,
    limit: int = 10,
) -> list[dict]:
    """Neo4j / relational entity search with link traversal."""
    try:
        terms = [t.strip() for t in query.split() if t.strip()]
        if not terms:
            return []

        conditions = [KnowledgeEntity.tenant == tenant, KnowledgeEntity.status == "ACTIVE"]
        if entity_types:
            conditions.append(KnowledgeEntity.entity_type.in_(entity_types))

        name_conditions = [
            KnowledgeEntity.name.ilike(f"%{term}%") for term in terms
        ]
        conditions.append(or_(*name_conditions))

        stmt = (
            select(KnowledgeEntity)
            .where(and_(*conditions))
            .order_by(KnowledgeEntity.confidence.desc())
            .limit(limit)
        )
        entity_rows = (await db.execute(stmt)).scalars().all()

        results: list[dict] = []
        for entity in entity_rows:
            link_stmt = select(KnowledgeLink).where(
                or_(
                    KnowledgeLink.source_entity_id == entity.id,
                    KnowledgeLink.target_entity_id == entity.id,
                ),
                KnowledgeLink.tenant == tenant,
            )
            link_rows = (await db.execute(link_stmt)).scalars().all()

            links = []
            for link in link_rows:
                links.append({
                    "source_entity_id": str(link.source_entity_id),
                    "target_entity_id": str(link.target_entity_id),
                    "link_type": link.link_type,
                    "weight": link.weight,
                })

            results.append({
                "entity_id": str(entity.id),
                "entity_type": entity.entity_type,
                "name": entity.name,
                "description": entity.description,
                "confidence": entity.confidence,
                "classification": entity.classification,
                "properties": entity.properties or {},
                "links": links,
                "method": "graph",
                "score": entity.confidence,
            })

        return results
    except Exception as exc:
        logger.warning("Graph search failed: %s", exc)
        return []


# ─── Hybrid orchestration ───────────────────────────────────────────────────


async def hybrid_search(
    db,
    tenant: str,
    query: str,
    *,
    filters: Optional[dict] = None,
    limit: int = 20,
    embed_fn: Optional[Callable] = None,
) -> list[dict]:
    """Primary search entry point — merges lexical, vector, and graph results."""
    lexical_results = await lexical_search(db, tenant, query, filters=filters, limit=limit)
    vector_results = await vector_search(
        db, tenant, query, filters=filters, limit=limit, embed_fn=embed_fn
    )
    graph_results = await graph_search(db, tenant, query, limit=min(limit, 10))

    all_results = lexical_results + vector_results + graph_results

    merged = _deduplicate_and_merge(all_results)
    merged.sort(key=lambda r: r["score"], reverse=True)

    try:
        await emit_event(
            "knowledge_search_completed",
            {"query_length": len(query), "results_count": len(merged)},
            tenant,
        )
    except Exception:
        pass

    return merged[:limit]


# ─── Private helpers ─────────────────────────────────────────────────────────


def _score_lexical_match(
    query: str,
    *,
    title: Optional[str] = None,
    content: Optional[str] = None,
    summary: Optional[str] = None,
) -> float:
    """Score relevance: exact match > partial, title > content."""
    terms = [t.lower() for t in query.split() if t.strip()]
    if not terms:
        return 0.0

    score = 0.0
    combined_text = " ".join(
        filter(None, [title, summary, content])
    ).lower()

    for term in terms:
        if term in combined_text:
            score += 1.0
        elif term[:4] in combined_text:
            score += 0.5

    if title:
        title_lower = title.lower()
        for term in terms:
            if term == title_lower:
                score += 2.0
            elif term in title_lower:
                score += 1.5

    if summary:
        summary_lower = summary.lower()
        for term in terms:
            if term in summary_lower:
                score += 1.0

    if content:
        content_lower = content.lower()
        for term in terms:
            if term in content_lower:
                score += 0.8

    max_possible = len(terms) * 3.0
    return min(score / max_possible, 1.0) if max_possible > 0 else 0.0


def _extract_snippet(text: Optional[str], terms: list[str], length: int = 300) -> str:
    """Extract a snippet around the first matched term."""
    if not text:
        return ""
    text_lower = text.lower()
    best_pos = 0
    for term in terms:
        pos = text_lower.find(term.lower())
        if pos != -1:
            best_pos = pos
            break
    start = max(0, best_pos - length // 4)
    end = min(len(text), start + length)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    return snippet


def _deduplicate_and_merge(results: list[dict]) -> list[dict]:
    """Deduplicate by document_id, keeping the highest-scoring entry."""
    by_doc: dict[str, dict] = {}
    for r in results:
        doc_id = r.get("document_id")
        if doc_id is None:
            doc_id = r.get("chunk_id")
        key = str(doc_id) if doc_id else id(r)
        if key not in by_doc or r["score"] > by_doc[key]["score"]:
            by_doc[key] = r
    return list(by_doc.values())
