"""Ingestion pipeline — chunk documents, compute embeddings, store in DB + Qdrant.

Orchestrates the full ingest flow:
    Source -> Adapter -> Documents -> Chunks -> Embeddings -> Storage
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.common import (
    compute_content_hash,
    DuplicateIngestionError,
    emit_event,
    estimate_tokens,
    MAX_CHUNK_SIZE,
    MAX_CHUNK_OVERLAP,
    DEFAULT_VECTOR_DIM,
    ingest_metric_best_effort,
)
from app.knowledge.models import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeIngestionJob,
    KnowledgeSource,
)
from app.knowledge.sources import get_adapter

logger = logging.getLogger(__name__)


# ─── Chunking ──────────────────────────────────────────────────────────────


def _split_paragraphs(text: str) -> list[str]:
    raw = text.split("\n\n")
    return [p.strip() for p in raw if p.strip()]


def _split_sentences(paragraph: str) -> list[str]:
    import re
    parts = re.split(r'(?<=[.!?])\s+', paragraph)
    return [s.strip() for s in parts if s.strip()]


def chunk_document(
    content: str,
    metadata: dict,
    max_chunk_size: int = MAX_CHUNK_SIZE,
    overlap: int = MAX_CHUNK_OVERLAP,
) -> list[dict]:
    """Split *content* into overlapping chunks.

    Each chunk dict contains:
        {"index", "content", "token_count", "metadata"}
    """
    if not content:
        return []

    chunks: list[dict] = []
    paragraphs = _split_paragraphs(content)

    buffer = ""
    chunk_idx = 0

    for para in paragraphs:
        sentences = _split_sentences(para)
        for sentence in sentences:
            candidate = (buffer + " " + sentence).strip() if buffer else sentence
            if estimate_tokens(candidate) > max_chunk_size and buffer:
                chunks.append(
                    {
                        "index": chunk_idx,
                        "content": buffer,
                        "token_count": max(1, estimate_tokens(buffer)),
                        "metadata": {**metadata, "chunk_index": chunk_idx},
                    }
                )
                chunk_idx += 1
                words = buffer.split()
                overlap_tokens = overlap // 4
                if overlap_tokens > 0 and len(words) > overlap_tokens:
                    buffer = " ".join(words[-overlap_tokens:]) + " " + sentence
                else:
                    buffer = sentence
            else:
                buffer = candidate

    if buffer:
        chunks.append(
            {
                "index": chunk_idx,
                "content": buffer,
                "token_count": max(1, estimate_tokens(buffer)),
                "metadata": {**metadata, "chunk_index": chunk_idx},
            }
        )

    return chunks


# ─── Single document ingestion ─────────────────────────────────────────────


async def ingest_document(
    db: AsyncSession,
    tenant: str,
    source_id: uuid.UUID,
    doc_data: dict,
    *,
    embed_fn: Optional[Callable[[str], Awaitable[list[float]]]] = None,
) -> str:
    """Create or update a KnowledgeDocument + chunks + upsert to Qdrant.

    Returns the document_id (UUID string).
    Deduplicates by content_hash — raises ``DuplicateIngestionError`` if
    a document with the same hash is already INGESTED.
    """
    content_hash = doc_data.get("content_hash") or compute_content_hash(
        doc_data.get("content", "")
    )

    existing_q = select(KnowledgeDocument).where(
        KnowledgeDocument.tenant == tenant,
        KnowledgeDocument.source_id == source_id,
        KnowledgeDocument.external_id == doc_data.get("external_id", ""),
    )
    existing_res = await db.execute(existing_q)
    existing_doc = existing_res.scalar_one_or_none()

    if existing_doc is not None:
        if (
            existing_doc.content_hash == content_hash
            and existing_doc.status == "INGESTED"
        ):
            raise DuplicateIngestionError(
                f"Document with content_hash={content_hash} already ingested"
            )
        existing_doc.content = doc_data.get("content", "")
        existing_doc.summary = doc_data.get("summary", "")
        existing_doc.title = doc_data.get("title", "")
        existing_doc.content_hash = content_hash
        existing_doc.language = doc_data.get("language", "")
        existing_doc.classification = doc_data.get("classification", "INTERNAL")
        existing_doc.tags = doc_data.get("tags", [])
        existing_doc.attribution = doc_data.get("attribution", {})
        existing_doc.metadata_ = doc_data.get("metadata", {})
        existing_doc.version = str(
            float(existing_doc.version or "1.0") + 0.1
        )
        document_id = existing_doc.id
    else:
        new_doc = KnowledgeDocument(
            tenant=tenant,
            source_id=source_id,
            external_id=doc_data.get("external_id", ""),
            title=doc_data.get("title", ""),
            doc_type=doc_data.get("doc_type", "unknown"),
            content=doc_data.get("content", ""),
            summary=doc_data.get("summary", ""),
            language=doc_data.get("language", ""),
            classification=doc_data.get("classification", "INTERNAL"),
            tags=doc_data.get("tags", []),
            attribution=doc_data.get("attribution", {}),
            content_hash=content_hash,
            status="PENDING",
            metadata_=doc_data.get("metadata", {}),
        )
        db.add(new_doc)
        await db.flush()
        document_id = new_doc.id

    old_chunks_q = select(KnowledgeChunk).where(
        KnowledgeChunk.document_id == document_id,
    )
    old_chunks_res = await db.execute(old_chunks_q)
    for old_chunk in old_chunks_res.scalars().all():
        await db.delete(old_chunk)
    await db.flush()

    chunks = chunk_document(
        doc_data.get("content", ""),
        {"tenant": tenant, "source_id": str(source_id), "document_id": str(document_id)},
    )

    vector_points: list[dict] = []
    chunk_count = 0

    for ch in chunks:
        embedding_id = None
        if embed_fn is not None:
            try:
                vec = await embed_fn(ch["content"])
                embedding_id = f"doc_{document_id}_chunk_{ch['index']}"
                vector_points.append(
                    {
                        "id": embedding_id,
                        "vector": vec,
                        "payload": {
                            "tenant": tenant,
                            "source_id": str(source_id),
                            "document_id": str(document_id),
                            "chunk_index": ch["index"],
                            "content": ch["content"],
                            "token_count": ch["token_count"],
                        },
                    }
                )
            except Exception as exc:
                logger.warning("Embedding failed for chunk %d: %s", ch["index"], exc)

        chunk_obj = KnowledgeChunk(
            tenant=tenant,
            document_id=document_id,
            source_id=source_id,
            chunk_index=ch["index"],
            content=ch["content"],
            content_hash=compute_content_hash(ch["content"]),
            token_count=ch["token_count"],
            embedding_id=embedding_id,
            classification=doc_data.get("classification", "INTERNAL"),
            metadata_=ch.get("metadata", {}),
        )
        db.add(chunk_obj)
        chunk_count += 1

    if vector_points:
        try:
            from app.services.vector_store import VectorStoreService, PointStruct

            vs = VectorStoreService()
            collection = f"knowledge_{tenant}"
            points = [
                PointStruct(
                    id=vp["id"],
                    vector=vp["vector"],
                    payload=vp["payload"],
                )
                for vp in vector_points
            ]
            vs.upsert_points(collection, points, size=len(vector_points[0]["vector"]) if vector_points else DEFAULT_VECTOR_DIM)
        except Exception as exc:
            logger.warning("Qdrant upsert failed: %s", exc)

    if existing_doc is not None:
        existing_doc.chunk_count = chunk_count
        existing_doc.status = "INGESTED"
    else:
        res = await db.execute(
            select(KnowledgeDocument).where(KnowledgeDocument.id == document_id)
        )
        fresh_doc = res.scalar_one()
        fresh_doc.chunk_count = chunk_count
        fresh_doc.status = "INGESTED"

    await db.flush()
    return str(document_id)


# ─── Ingestion job ─────────────────────────────────────────────────────────


async def run_ingestion_job(
    db: AsyncSession,
    tenant: str,
    source_id: uuid.UUID,
    *,
    job_type: str = "incremental",
    embed_fn: Optional[Callable[[str], Awaitable[list[float]]]] = None,
) -> dict:
    """Run an ingestion job: create job record, fetch via adapter, ingest each.

    Returns ``{job_id, status, documents_processed, chunks_created, errors}``.
    """
    job = KnowledgeIngestionJob(
        tenant=tenant,
        source_id=source_id,
        job_type=job_type,
        status="RUNNING",
        started_at=datetime.now(timezone.utc),
    )
    db.add(job)
    await db.flush()

    source_q = select(KnowledgeSource).where(KnowledgeSource.id == source_id)
    source_res = await db.execute(source_q)
    source_obj = source_res.scalar_one_or_none()
    if source_obj is None:
        job.status = "FAILED"
        job.error = f"Source {source_id} not found"
        job.completed_at = datetime.now(timezone.utc)
        await db.flush()
        return {
            "job_id": str(job.id),
            "status": "FAILED",
            "documents_processed": 0,
            "chunks_created": 0,
            "errors": [job.error],
        }

    try:
        adapter = get_adapter(source_obj.source_type)
    except ValueError as exc:
        job.status = "FAILED"
        job.error = str(exc)
        job.completed_at = datetime.now(timezone.utc)
        await db.flush()
        return {
            "job_id": str(job.id),
            "status": "FAILED",
            "documents_processed": 0,
            "chunks_created": 0,
            "errors": [str(exc)],
        }

    try:
        if job_type == "incremental" and source_obj.last_ingested_at:
            documents = await adapter.fetch_incremental(
                db, tenant, source_obj, source_obj.last_ingested_at
            )
        else:
            documents = await adapter.fetch_documents(db, tenant, source_obj)
    except Exception as exc:
        job.status = "FAILED"
        job.error = f"Fetch failed: {exc}"
        job.completed_at = datetime.now(timezone.utc)
        await db.flush()
        return {
            "job_id": str(job.id),
            "status": "FAILED",
            "documents_processed": 0,
            "chunks_created": 0,
            "errors": [str(exc)],
        }

    job.documents_total = len(documents)
    await db.flush()

    processed = 0
    total_chunks = 0
    errors: list[str] = []

    for doc_data in documents:
        try:
            doc_id = await ingest_document(
                db, tenant, source_id, doc_data, embed_fn=embed_fn
            )
            processed += 1
            res = await db.execute(
                select(KnowledgeChunk).where(KnowledgeChunk.document_id == doc_id)
            )
            total_chunks += len(res.scalars().all())
            job.documents_processed = processed
            job.chunks_created = total_chunks
            await db.flush()
        except DuplicateIngestionError:
            processed += 1
            job.documents_processed = processed
            await db.flush()
        except Exception as exc:
            err_msg = f"Doc {doc_data.get('external_id', '?')}: {exc}"
            errors.append(err_msg)
            logger.warning("Ingest document failed: %s", err_msg)

    job.documents_failed = len(errors)
    job.chunks_created = total_chunks
    job.status = "COMPLETED" if not errors else "PARTIAL"
    job.error = "; ".join(errors) if errors else None
    job.completed_at = datetime.now(timezone.utc)
    source_obj.last_ingested_at = datetime.now(timezone.utc)
    await db.flush()

    try:
        await emit_event(
            "knowledge_ingestion_completed",
            {
                "source_id": str(source_id),
                "job_id": str(job.id),
                "documents_processed": processed,
                "chunks_created": total_chunks,
                "errors": len(errors),
            },
            tenant,
        )
    except Exception:
        pass

    try:
        ingest_metric_best_effort(
            "knowledge.ingestion.documents",
            float(processed),
            tags={"tenant": tenant, "source_id": str(source_id), "job_type": job_type},
        )
        ingest_metric_best_effort(
            "knowledge.ingestion.chunks",
            float(total_chunks),
            tags={"tenant": tenant, "source_id": str(source_id)},
        )
    except Exception:
        pass

    return {
        "job_id": str(job.id),
        "status": job.status,
        "documents_processed": processed,
        "chunks_created": total_chunks,
        "errors": errors,
    }


# ─── Reindex ───────────────────────────────────────────────────────────────


async def reindex_source(
    db: AsyncSession,
    tenant: str,
    source_id: uuid.UUID,
    *,
    embed_fn: Optional[Callable[[str], Awaitable[list[float]]]] = None,
) -> dict:
    """Run a full reindex job for a source."""
    return await run_ingestion_job(
        db,
        tenant,
        source_id,
        job_type="full",
        embed_fn=embed_fn,
    )
