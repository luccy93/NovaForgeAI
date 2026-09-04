"""RAG context builder for LLM-ready retrieval — Volume 68.

Assembles retrieved knowledge chunks into structured context for
large language models, with citation tracking and diversity selection.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.common import emit_event, MAX_QUERY_LENGTH, estimate_tokens
from app.knowledge.citations import build_citation, format_citation_text, validate_citations
from app.knowledge.models import KnowledgeChunk, KnowledgeDocument, KnowledgeSource

logger = logging.getLogger(__name__)


DEFAULT_MAX_TOKENS = 4096
DEFAULT_MAX_CHUNKS = 10
DEFAULT_DIVERSITY_FACTOR = 0.3
_CONTEXT_TEMPLATE_DEFAULT = (
    "You are a helpful assistant. Use the following context to answer the question.\n\n"
    "Context:\n{context}\n\n"
    "Question: {query}\n\n"
    "Answer based on the context above. If the context doesn't contain "
    "enough information, say so clearly."
)


async def build_rag_context(
    db: AsyncSession,
    tenant: str,
    query: str,
    search_results: list[dict],
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_chunks: int = DEFAULT_MAX_CHUNKS,
    include_citations: bool = True,
    diversity_factor: float = DEFAULT_DIVERSITY_FACTOR,
) -> dict:
    """Build RAG context from search results for LLM consumption.
    
    Returns: {
        "context_text": str,        # Formatted context string
        "chunks_used": list[dict],  # Selected and ordered chunks
        "citations": list[dict],    # Citation metadata
        "total_tokens": int,        # Estimated token count
        "excluded_count": int,      # Chunks excluded by budget
    }
    """
    if not search_results:
        return {
            "context_text": "",
            "chunks_used": [],
            "citations": [],
            "total_tokens": 0,
            "excluded_count": 0,
        }
    
    # Step 1: Select diverse chunks
    selected = select_diverse_chunks(
        search_results,
        max_chunks=max_chunks,
        diversity_factor=diversity_factor,
    )
    
    # Step 2: Enrich with chunk content from DB
    enriched = await _enrich_chunks_with_content(db, tenant, selected)
    
    # Step 3: Budget-aware selection (trim to max_tokens)
    within_budget: list[dict] = []
    total_tokens = 0
    excluded_count = 0
    
    for chunk in enriched:
        chunk_tokens = estimate_tokens(chunk.get("content", ""))
        if total_tokens + chunk_tokens > max_tokens and within_budget:
            excluded_count += 1
            continue
        within_budget.append(chunk)
        total_tokens += chunk_tokens
    
    # Step 4: Build citations
    citations: list[dict] = []
    if include_citations:
        doc_ids_seen: set[str] = set()
        for chunk in within_budget:
            doc_id = chunk.get("document_id")
            if doc_id and doc_id not in doc_ids_seen:
                doc_ids_seen.add(doc_id)
                try:
                    doc_stmt = select(KnowledgeDocument).where(
                        KnowledgeDocument.id == uuid.UUID(doc_id),
                        KnowledgeDocument.tenant == tenant,
                    )
                    doc_result = await db.execute(doc_stmt)
                    doc = doc_result.scalar_one_or_none()
                    if doc:
                        src_stmt = select(KnowledgeSource).where(
                            KnowledgeSource.id == doc.source_id,
                        )
                        src_result = await db.execute(src_stmt)
                        src = src_result.scalar_one_or_none()
                        citations.append(build_citation(doc, src))
                except Exception:
                    pass
    
    # Step 5: Format context text
    context_text = format_context_for_llm(within_budget, template=_CONTEXT_TEMPLATE_DEFAULT, query=query)
    
    try:
        await emit_event("knowledge.rag.context_built", {
            "query_length": len(query),
            "chunks_used": len(within_budget),
            "citations_count": len(citations),
            "total_tokens": total_tokens,
        }, tenant=tenant)
    except Exception:
        pass
    
    return {
        "context_text": context_text,
        "chunks_used": within_budget,
        "citations": citations,
        "total_tokens": total_tokens,
        "excluded_count": excluded_count,
    }


def select_diverse_chunks(
    results: list[dict],
    *,
    max_chunks: int = DEFAULT_MAX_CHUNKS,
    diversity_factor: float = DEFAULT_DIVERSITY_FACTOR,
) -> list[dict]:
    """MMR-like diversity selection to avoid redundant chunks.
    
    Balances relevance (score) with diversity (different source/document).
    diversity_factor: 0.0 = pure relevance, 1.0 = pure diversity.
    """
    if not results or max_chunks <= 0:
        return []
    
    sorted_results = sorted(results, key=lambda r: r.get("score", 0), reverse=True)
    selected: list[dict] = []
    selected_docs: set[str] = set()
    selected_sources: set[str] = set()
    
    for result in sorted_results:
        if len(selected) >= max_chunks:
            break
        
        doc_id = result.get("document_id", "")
        source_id = result.get("source_id", "")
        score = result.get("score", 0.0)
        
        # Diversity penalty
        doc_penalty = 0.0
        if doc_id in selected_docs:
            doc_penalty += diversity_factor * 0.5
        if source_id in selected_sources:
            doc_penalty += diversity_factor * 0.3
        
        adjusted_score = score * (1.0 - doc_penalty)
        
        # Greedy MMR: pick highest adjusted score
        if not selected:
            selected.append({**result, "_adjusted_score": adjusted_score})
            selected_docs.add(doc_id)
            selected_sources.add(source_id)
        else:
            # Insert in sorted position
            inserted = False
            for i, s in enumerate(selected):
                if adjusted_score > s.get("_adjusted_score", 0):
                    selected.insert(i, {**result, "_adjusted_score": adjusted_score})
                    selected_docs.add(doc_id)
                    selected_sources.add(source_id)
                    inserted = True
                    break
            if not inserted and len(selected) < max_chunks:
                selected.append({**result, "_adjusted_score": adjusted_score})
                selected_docs.add(doc_id)
                selected_sources.add(source_id)
    
    # Remove internal scoring field
    for s in selected:
        s.pop("_adjusted_score", None)
    
    return selected[:max_chunks]


def format_context_for_llm(
    chunks: list[dict],
    *,
    template: str = _CONTEXT_TEMPLATE_DEFAULT,
    query: str = "",
) -> str:
    """Format selected chunks into a prompt-ready context string."""
    if not chunks:
        return template.format(context="[No relevant context found]", query=query)
    
    parts: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        content = chunk.get("content", "")
        title = chunk.get("title", f"Source {i}")
        citation_str = ""
        if chunk.get("source_name"):
            citation_str = f" [{chunk['source_name']}]"
        parts.append(f"[{i}] {title}{citation_str}:\n{content}")
    
    context = "\n\n".join(parts)
    return template.format(context=context, query=query)


def score_relevance_to_query(chunk: dict, query: str) -> float:
    """Score a chunk's relevance to a query based on keyword overlap."""
    if not query or not chunk.get("content", ""):
        return 0.0
    
    query_terms = set(query.lower().split())
    content_lower = chunk["content"].lower()
    hits = sum(1 for term in query_terms if term in content_lower)
    return min(hits / max(len(query_terms), 1), 1.0)


async def _enrich_chunks_with_content(
    db: AsyncSession, tenant: str, chunks: list[dict],
) -> list[dict]:
    """Enrich chunk results with full content from the database."""
    enriched: list[dict] = []
    for chunk in chunks:
        chunk_id = chunk.get("chunk_id")
        if not chunk_id:
            enriched.append(chunk)
            continue
        try:
            stmt = select(KnowledgeChunk).where(
                KnowledgeChunk.id == uuid.UUID(chunk_id),
                KnowledgeChunk.tenant == tenant,
            )
            result = await db.execute(stmt)
            db_chunk = result.scalar_one_or_none()
            if db_chunk:
                enriched.append({
                    **chunk,
                    "content": db_chunk.content or "",
                    "token_count": db_chunk.token_count or 0,
                })
            else:
                enriched.append(chunk)
        except Exception:
            enriched.append(chunk)
    return enriched
