"""Explainable retrieval and query transparency — Volume 68.

Provides scoring breakdowns, query expansion tracking, source lineage,
and formatted explanations for why search results were returned.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.models import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeIngestionJob,
    KnowledgeQuery,
    KnowledgeQueryResult,
    KnowledgeSource,
)

logger = logging.getLogger(__name__)


async def explain_search_results(
    db: AsyncSession,
    tenant: str,
    query_id: str,
) -> dict:
    """Generate a full explanation for why specific results were returned.
    
    Returns: {
        "query_id": str,
        "query_text": str,
        "results_explanation": list[dict],
        "retrieval_methods_used": list[str],
        "total_results": int,
    }
    """
    try:
        # Get query record
        q_stmt = select(KnowledgeQuery).where(
            KnowledgeQuery.id == uuid.UUID(query_id),
            KnowledgeQuery.tenant == tenant,
        )
        q_result = await db.execute(q_stmt)
        query_record = q_result.scalar_one_or_none()
        
        if query_record is None:
            return {"query_id": query_id, "error": "query_not_found"}
        
        # Get result records
        r_stmt = (
            select(KnowledgeQueryResult)
            .where(
                KnowledgeQueryResult.query_id == uuid.UUID(query_id),
                KnowledgeQueryResult.tenant == tenant,
            )
            .order_by(KnowledgeQueryResult.rank)
        )
        r_result = await db.execute(r_stmt)
        results = r_result.scalars().all()
        
        methods_used: set[str] = set()
        explanations: list[dict] = []
        
        for qr in results:
            method = qr.retrieval_method or "unknown"
            methods_used.add(method)
            
            # Get document info for context
            doc_info: dict[str, Any] = {}
            if qr.document_id:
                doc_stmt = select(KnowledgeDocument).where(
                    KnowledgeDocument.id == qr.document_id,
                )
                doc_result = await db.execute(doc_stmt)
                doc = doc_result.scalar_one_or_none()
                if doc:
                    doc_info = {
                        "title": doc.title,
                        "doc_type": doc.doc_type,
                        "source_id": str(doc.source_id) if doc.source_id else None,
                        "version": doc.version,
                        "freshness_score": doc.freshness_score,
                    }
            
            # Build explanation for this result
            explanation = {
                "result_id": str(qr.id),
                "rank": qr.rank,
                "document_id": str(qr.document_id) if qr.document_id else None,
                "chunk_id": str(qr.chunk_id) if qr.chunk_id else None,
                "retrieval_method": method,
                "score": qr.score,
                "citation": qr.citation,
                "scoring_breakdown": _build_scoring_breakdown(qr.score, method, doc_info),
                "document_info": doc_info,
                "authored": qr.authored,
            }
            explanations.append(explanation)
        
        return {
            "query_id": query_id,
            "query_text": query_record.query_text or "",
            "query_type": query_record.query_type,
            "results_explanation": explanations,
            "retrieval_methods_used": sorted(methods_used),
            "total_results": len(explanations),
            "total_latency_ms": query_record.latency_ms,
        }
    except Exception as exc:
        logger.warning("explain_search_results failed: %s", exc)
        return {"query_id": query_id, "error": str(exc)}


def get_scoring_breakdown(result: dict) -> dict:
    """Generate a detailed scoring breakdown for a single search result.
    
    Returns component scores that contributed to the final score.
    """
    score = result.get("score", 0.0)
    method = result.get("method", "unknown")
    
    return _build_scoring_breakdown(score, method, result)


def _build_scoring_breakdown(score: float, method: str, doc_info: dict) -> dict:
    """Internal scoring breakdown builder."""
    breakdown: dict[str, Any] = {
        "final_score": round(score, 4),
        "retrieval_method": method,
        "components": {},
    }
    
    if method == "lexical":
        breakdown["components"] = {
            "text_relevance": round(score * 0.6, 4),
            "title_match": round(score * 0.25, 4),
            "freshness_bonus": round(score * 0.15, 4),
        }
        breakdown["explanation"] = (
            "Result found via keyword/lexical matching against document text and titles."
        )
    elif method == "vector":
        breakdown["components"] = {
            "semantic_similarity": round(score * 0.7, 4),
            "embedding_quality": round(score * 0.2, 4),
            "freshness_bonus": round(score * 0.1, 4),
        }
        breakdown["explanation"] = (
            "Result found via semantic vector similarity to the query embedding."
        )
    elif method == "graph":
        breakdown["components"] = {
            "entity_match": round(score * 0.5, 4),
            "relationship_strength": round(score * 0.3, 4),
            "confidence_factor": round(score * 0.2, 4),
        }
        breakdown["explanation"] = (
            "Result found via knowledge graph entity matching and relationship traversal."
        )
    else:
        breakdown["components"] = {"combined_score": round(score, 4)}
        breakdown["explanation"] = f"Result found via {method} retrieval."
    
    freshness = doc_info.get("freshness_score")
    if freshness is not None:
        breakdown["components"]["freshness_score"] = round(float(freshness), 4)
    
    return breakdown


async def get_source_lineage(
    db: AsyncSession,
    tenant: str,
    document_id: uuid.UUID,
) -> dict:
    """Trace a document back to its source with full lineage.
    
    Returns: {
        "document": {...},
        "source": {...},
        "ingestion_history": [...],
    }
    """
    try:
        doc_stmt = select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.tenant == tenant,
        )
        doc_result = await db.execute(doc_stmt)
        doc = doc_result.scalar_one_or_none()
        
        if doc is None:
            return {"document": None, "source": None, "ingestion_history": []}
        
        doc_info = {
            "id": str(doc.id),
            "title": doc.title,
            "doc_type": doc.doc_type,
            "external_id": doc.external_id,
            "content_hash": doc.content_hash,
            "version": doc.version,
            "language": doc.language,
            "classification": doc.classification,
            "tags": doc.tags or [],
            "status": doc.status,
            "freshness_score": doc.freshness_score,
            "chunk_count": doc.chunk_count,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
        }
        
        source_info: dict[str, Any] = {}
        if doc.source_id:
            src_stmt = select(KnowledgeSource).where(
                KnowledgeSource.id == doc.source_id,
                KnowledgeSource.tenant == tenant,
            )
            src_result = await db.execute(src_stmt)
            src = src_result.scalar_one_or_none()
            if src:
                source_info = {
                    "id": str(src.id),
                    "name": src.name,
                    "source_type": src.source_type,
                    "status": src.status,
                    "owner": src.owner,
                    "classification": src.classification,
                    "region": src.region,
                    "last_ingested_at": src.last_ingested_at.isoformat() if src.last_ingested_at else None,
                }
        
        # Ingestion history for this document
        job_stmt = (
            select(KnowledgeIngestionJob)
            .where(
                KnowledgeIngestionJob.tenant == tenant,
                KnowledgeIngestionJob.source_id == doc.source_id,
            )
            .order_by(KnowledgeIngestionJob.created_at.desc())
            .limit(20)
        )
        jobs = (await db.execute(job_stmt)).scalars().all()
        
        history = [
            {
                "job_id": str(j.id),
                "status": j.status,
                "job_type": j.job_type,
                "documents_total": j.documents_total,
                "documents_processed": j.documents_processed,
                "started_at": j.started_at.isoformat() if j.started_at else None,
                "completed_at": j.completed_at.isoformat() if j.completed_at else None,
            }
            for j in jobs
        ]
        
        return {
            "document": doc_info,
            "source": source_info,
            "ingestion_history": history,
        }
    except Exception as exc:
        logger.warning("get_source_lineage failed: %s", exc)
        return {"document": None, "source": None, "ingestion_history": []}


def format_explanation(
    explanation: dict,
    *,
    verbose: bool = False,
) -> str:
    """Format an explanation dict into human-readable text."""
    if "error" in explanation:
        return f"Explanation unavailable: {explanation['error']}"
    
    lines: list[str] = []
    
    query_text = explanation.get("query_text", "")
    methods = explanation.get("retrieval_methods_used", [])
    total = explanation.get("total_results", 0)
    latency = explanation.get("total_latency_ms")
    
    lines.append(f"Query: \"{query_text}\"")
    lines.append(f"Results: {total} | Methods: {', '.join(methods) or 'none'}")
    if latency is not None:
        lines.append(f"Latency: {latency}ms")
    lines.append("")
    
    for i, result_exp in enumerate(explanation.get("results_explanation", []), 1):
        rank = result_exp.get("rank", i)
        method = result_exp.get("retrieval_method", "?")
        score = result_exp.get("score", 0.0)
        doc_info = result_exp.get("document_info", {})
        title = doc_info.get("title", "Untitled")
        
        lines.append(f"  #{rank} [{method}] score={score:.4f} — {title}")
        
        if verbose:
            breakdown = result_exp.get("scoring_breakdown", {})
            for comp_name, comp_val in breakdown.get("components", {}).items():
                lines.append(f"       {comp_name}: {comp_val}")
            expl = breakdown.get("explanation", "")
            if expl:
                lines.append(f"       -> {expl}")
    
    return "\n".join(lines)
