"""Knowledge API (Volume 68).

Production APIs for knowledge search, sources, documents, ingestion,
entities, links, freshness, and audit.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge", tags=["Knowledge"])


async def _get_db():
    from app.core.database import async_session
    async with async_session() as session:
        yield session


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

async def _resolve_user():
    try:
        from app.api.auth import get_current_user
        return await get_current_user()
    except Exception:
        class _Anon:
            id = ""
            organization_id = ""
            role = "anonymous"
            clearance = "PUBLIC"
        return _Anon()


async def _tenant(user) -> str:
    oid = getattr(user, "organization_id", None) or getattr(user, "id", None)
    return str(oid) if oid else ""


async def _iam_check(user, tenant, perm):
    try:
        from app.iam.policy_authorizer import policy_authorizer
        result = await policy_authorizer.authorize(
            str(getattr(user, "id", "")), tenant, perm,
            context={"role": getattr(user, "role", "user")},
        )
        if not result.get("allowed", True):
            raise HTTPException(status_code=403, detail="forbidden")
    except HTTPException:
        raise
    except Exception:
        pass


def _err(exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    msg = f"{type(exc).__name__}: {exc}"
    if "not found" in str(exc).lower():
        return HTTPException(status_code=404, detail=msg)
    if "already exists" in str(exc).lower():
        return HTTPException(status_code=409, detail=msg)
    return HTTPException(status_code=500, detail=msg)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class SearchIn(BaseModel):
    query: str
    source_type: Optional[str] = None
    doc_type: Optional[str] = None
    classification: Optional[str] = None
    limit: int = 20
    offset: int = 0


class SourceCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    source_type: str = Field(..., max_length=32)
    connector_config: Optional[dict] = None
    classification: str = "INTERNAL"
    region: Optional[str] = None


class SourceUpdateIn(BaseModel):
    status: Optional[str] = None
    connector_config: Optional[dict] = None
    classification: Optional[str] = None


class DocumentIn(BaseModel):
    source_id: str
    external_id: str
    title: str
    content: str
    doc_type: str = "document"
    classification: str = "INTERNAL"
    tags: Optional[list] = None


class IngestionJobIn(BaseModel):
    source_id: str
    job_type: str = "incremental"


class ReindexIn(BaseModel):
    source_id: str


class EntityIn(BaseModel):
    entity_type: str = Field(..., max_length=32)
    name: str = Field(..., min_length=1, max_length=256)
    canonical_id: Optional[str] = None
    description: Optional[str] = None
    properties: Optional[dict] = None
    classification: str = "INTERNAL"


class LinkIn(BaseModel):
    source_entity_id: str
    target_entity_id: str
    link_type: str = Field(..., max_length=64)
    weight: float = 1.0
    properties: Optional[dict] = None


class MarkStaleIn(BaseModel):
    older_than_hours: int = 168


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/search")
async def search_knowledge(
    query: str = Query(..., max_length=2000),
    source_type: Optional[str] = Query(None),
    doc_type: Optional[str] = Query(None),
    classification: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(_get_db),
    current_user=Depends(_resolve_user),
):
    try:
        await _iam_check(current_user, await _tenant(current_user), "knowledge:read")
        from app.knowledge.search import search as search_svc
        result = await search_svc.search(
            db, await _tenant(current_user), query,
            filters={"source_type": source_type, "doc_type": doc_type, "classification": classification},
            limit=limit, offset=offset, user=current_user,
        )
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/sources")
async def list_sources(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(_get_db),
    current_user=Depends(_resolve_user),
):
    try:
        await _iam_check(current_user, await _tenant(current_user), "knowledge:read")
        from app.knowledge.search import list_sources as _list_sources
        items = await _list_sources(db, await _tenant(current_user), status=status, limit=limit)
        return {"items": items, "total": len(items)}
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/sources")
async def create_source(
    body: SourceCreateIn,
    db: AsyncSession = Depends(_get_db),
    current_user=Depends(_resolve_user),
):
    try:
        tenant = await _tenant(current_user)
        await _iam_check(current_user, tenant, "knowledge:write")
        from app.knowledge.models import KnowledgeSource
        src = KnowledgeSource(
            tenant=tenant,
            name=body.name,
            source_type=body.source_type,
            connector_config=body.connector_config or {},
            classification=body.classification,
            region=body.region,
            status="ACTIVE",
            owner=str(getattr(current_user, "id", "")),
        )
        db.add(src)
        await db.flush()
        return {
            "source_id": str(src.id),
            "name": src.name,
            "source_type": src.source_type,
            "status": src.status,
        }
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/sources/{source_id}")
async def get_source(
    source_id: str,
    db: AsyncSession = Depends(_get_db),
    current_user=Depends(_resolve_user),
):
    try:
        tenant = await _tenant(current_user)
        await _iam_check(current_user, tenant, "knowledge:read")
        from app.knowledge.search import get_source as _get_source
        return await _get_source(db, tenant, source_id)
    except Exception as exc:
        raise _err(exc) from exc


@router.patch("/sources/{source_id}")
async def update_source(
    source_id: str,
    body: SourceUpdateIn,
    db: AsyncSession = Depends(_get_db),
    current_user=Depends(_resolve_user),
):
    try:
        tenant = await _tenant(current_user)
        await _iam_check(current_user, tenant, "knowledge:write")
        from app.knowledge.models import KnowledgeSource
        from app.knowledge.common import NotFoundError
        stmt = select(KnowledgeSource).where(
            KnowledgeSource.id == source_id, KnowledgeSource.tenant == tenant
        )
        src = (await db.execute(stmt)).scalar_one_or_none()
        if src is None:
            raise NotFoundError(f"Source {source_id} not found")
        if body.status is not None:
            src.status = body.status
        if body.connector_config is not None:
            src.connector_config = body.connector_config
        if body.classification is not None:
            src.classification = body.classification
        await db.flush()
        return {"source_id": str(src.id), "name": src.name, "status": src.status}
    except Exception as exc:
        raise _err(exc) from exc


@router.delete("/sources/{source_id}")
async def delete_source(
    source_id: str,
    db: AsyncSession = Depends(_get_db),
    current_user=Depends(_resolve_user),
):
    try:
        tenant = await _tenant(current_user)
        await _iam_check(current_user, tenant, "knowledge:write")
        from app.knowledge.models import KnowledgeSource
        from app.knowledge.common import NotFoundError
        stmt = select(KnowledgeSource).where(
            KnowledgeSource.id == source_id, KnowledgeSource.tenant == tenant
        )
        src = (await db.execute(stmt)).scalar_one_or_none()
        if src is None:
            raise NotFoundError(f"Source {source_id} not found")
        src.status = "DELETED"
        await db.flush()
        return {"source_id": str(src.id), "status": "DELETED"}
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/documents/{document_id}")
async def get_document(
    document_id: str,
    db: AsyncSession = Depends(_get_db),
    current_user=Depends(_resolve_user),
):
    try:
        tenant = await _tenant(current_user)
        await _iam_check(current_user, tenant, "knowledge:read")
        from app.knowledge.search import get_document as _get_document
        return await _get_document(db, tenant, document_id)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/documents")
async def add_document(
    body: DocumentIn,
    db: AsyncSession = Depends(_get_db),
    current_user=Depends(_resolve_user),
):
    try:
        tenant = await _tenant(current_user)
        await _iam_check(current_user, tenant, "knowledge:write")
        from app.knowledge.indexing import ingest_document
        doc_id = await ingest_document(
            db, tenant, body.source_id, {
                "external_id": body.external_id,
                "title": body.title,
                "content": body.content,
                "doc_type": body.doc_type,
                "classification": body.classification,
                "tags": body.tags or [],
            },
        )
        return {"document_id": doc_id, "status": "INGESTED"}
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/ingestion/jobs")
async def create_ingestion_job(
    body: IngestionJobIn,
    db: AsyncSession = Depends(_get_db),
    current_user=Depends(_resolve_user),
):
    try:
        tenant = await _tenant(current_user)
        await _iam_check(current_user, tenant, "knowledge:write")
        from app.knowledge.models import KnowledgeIngestionJob
        job = KnowledgeIngestionJob(
            tenant=tenant,
            source_id=body.source_id,
            job_type=body.job_type,
            status="PENDING",
        )
        db.add(job)
        await db.flush()
        return {"job_id": str(job.id), "status": job.status, "job_type": job.job_type}
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/ingestion/jobs")
async def list_ingestion_jobs(
    source_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(_get_db),
    current_user=Depends(_resolve_user),
):
    try:
        tenant = await _tenant(current_user)
        await _iam_check(current_user, tenant, "knowledge:read")
        from app.knowledge.models import KnowledgeIngestionJob
        conditions = [KnowledgeIngestionJob.tenant == tenant]
        if source_id:
            conditions.append(KnowledgeIngestionJob.source_id == source_id)
        stmt = (
            select(KnowledgeIngestionJob)
            .where(*conditions)
            .order_by(KnowledgeIngestionJob.created_at.desc())
            .limit(min(limit, 200))
        )
        rows = (await db.execute(stmt)).scalars().all()
        items = [
            {
                "job_id": str(j.id),
                "source_id": str(j.source_id) if j.source_id else None,
                "job_type": j.job_type,
                "status": j.status,
                "documents_processed": j.documents_processed,
                "chunks_created": j.chunks_created,
                "error": j.error,
                "created_at": j.created_at.isoformat() if j.created_at else None,
            }
            for j in rows
        ]
        return {"items": items, "total": len(items)}
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/ingestion/jobs/{job_id}")
async def get_ingestion_job(
    job_id: str,
    db: AsyncSession = Depends(_get_db),
    current_user=Depends(_resolve_user),
):
    try:
        tenant = await _tenant(current_user)
        await _iam_check(current_user, tenant, "knowledge:read")
        from app.knowledge.models import KnowledgeIngestionJob
        from app.knowledge.common import NotFoundError
        stmt = select(KnowledgeIngestionJob).where(
            KnowledgeIngestionJob.id == job_id, KnowledgeIngestionJob.tenant == tenant
        )
        job = (await db.execute(stmt)).scalar_one_or_none()
        if job is None:
            raise NotFoundError(f"Job {job_id} not found")
        return {
            "job_id": str(job.id),
            "source_id": str(job.source_id) if job.source_id else None,
            "job_type": job.job_type,
            "status": job.status,
            "documents_total": job.documents_total,
            "documents_processed": job.documents_processed,
            "documents_failed": job.documents_failed,
            "chunks_created": job.chunks_created,
            "error": job.error,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/ingestion/reindex")
async def trigger_reindex(
    body: ReindexIn,
    db: AsyncSession = Depends(_get_db),
    current_user=Depends(_resolve_user),
):
    try:
        tenant = await _tenant(current_user)
        await _iam_check(current_user, tenant, "knowledge:write")
        from app.knowledge.indexing import reindex_source
        result = await reindex_source(db, tenant, body.source_id)
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/entities")
async def list_entities(
    entity_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(_get_db),
    current_user=Depends(_resolve_user),
):
    try:
        tenant = await _tenant(current_user)
        await _iam_check(current_user, tenant, "knowledge:read")
        from app.knowledge.models import KnowledgeEntity
        conditions = [KnowledgeEntity.tenant == tenant]
        if entity_type:
            conditions.append(KnowledgeEntity.entity_type == entity_type)
        stmt = (
            select(KnowledgeEntity)
            .where(*conditions)
            .order_by(KnowledgeEntity.created_at.desc())
            .limit(min(limit, 200))
        )
        rows = (await db.execute(stmt)).scalars().all()
        items = [
            {
                "entity_id": str(e.id),
                "entity_type": e.entity_type,
                "name": e.name,
                "canonical_id": e.canonical_id,
                "description": e.description,
                "classification": e.classification,
                "confidence": e.confidence,
                "status": e.status,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in rows
        ]
        return {"items": items, "total": len(items)}
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/entities")
async def create_entity(
    body: EntityIn,
    db: AsyncSession = Depends(_get_db),
    current_user=Depends(_resolve_user),
):
    try:
        tenant = await _tenant(current_user)
        await _iam_check(current_user, tenant, "knowledge:write")
        from app.knowledge.models import KnowledgeEntity
        entity = KnowledgeEntity(
            tenant=tenant,
            entity_type=body.entity_type,
            name=body.name,
            canonical_id=body.canonical_id,
            description=body.description,
            properties=body.properties or {},
            classification=body.classification,
        )
        db.add(entity)
        await db.flush()
        return {
            "entity_id": str(entity.id),
            "entity_type": entity.entity_type,
            "name": entity.name,
        }
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/entities/{entity_id}")
async def get_entity(
    entity_id: str,
    db: AsyncSession = Depends(_get_db),
    current_user=Depends(_resolve_user),
):
    try:
        tenant = await _tenant(current_user)
        await _iam_check(current_user, tenant, "knowledge:read")
        from app.knowledge.models import KnowledgeEntity, KnowledgeLink
        from app.knowledge.common import NotFoundError
        stmt = select(KnowledgeEntity).where(
            KnowledgeEntity.id == entity_id, KnowledgeEntity.tenant == tenant
        )
        entity = (await db.execute(stmt)).scalar_one_or_none()
        if entity is None:
            raise NotFoundError(f"Entity {entity_id} not found")
        link_stmt = select(KnowledgeLink).where(
            (KnowledgeLink.source_entity_id == entity_id) | (KnowledgeLink.target_entity_id == entity_id)
        )
        links = (await db.execute(link_stmt)).scalars().all()
        return {
            "entity_id": str(entity.id),
            "entity_type": entity.entity_type,
            "name": entity.name,
            "canonical_id": entity.canonical_id,
            "description": entity.description,
            "properties": entity.properties or {},
            "classification": entity.classification,
            "confidence": entity.confidence,
            "status": entity.status,
            "links": [
                {
                    "link_id": str(l.id),
                    "source_entity_id": str(l.source_entity_id),
                    "target_entity_id": str(l.target_entity_id),
                    "link_type": l.link_type,
                    "weight": l.weight,
                }
                for l in links
            ],
        }
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/links")
async def create_link(
    body: LinkIn,
    db: AsyncSession = Depends(_get_db),
    current_user=Depends(_resolve_user),
):
    try:
        tenant = await _tenant(current_user)
        await _iam_check(current_user, tenant, "knowledge:write")
        from app.knowledge.models import KnowledgeLink
        link = KnowledgeLink(
            tenant=tenant,
            source_entity_id=body.source_entity_id,
            target_entity_id=body.target_entity_id,
            link_type=body.link_type,
            weight=body.weight,
            properties=body.properties or {},
        )
        db.add(link)
        await db.flush()
        return {
            "link_id": str(link.id),
            "source_entity_id": str(link.source_entity_id),
            "target_entity_id": str(link.target_entity_id),
            "link_type": link.link_type,
        }
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/freshness/stats")
async def freshness_stats(
    db: AsyncSession = Depends(_get_db),
    current_user=Depends(_resolve_user),
):
    try:
        tenant = await _tenant(current_user)
        await _iam_check(current_user, tenant, "knowledge:read")
        from app.knowledge.freshness import get_freshness_stats as _freshness_stats
        return await _freshness_stats(db, tenant)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/freshness/mark-stale")
async def mark_stale(
    body: MarkStaleIn,
    db: AsyncSession = Depends(_get_db),
    current_user=Depends(_resolve_user),
):
    try:
        tenant = await _tenant(current_user)
        await _iam_check(current_user, tenant, "knowledge:write")
        from app.knowledge.freshness import mark_stale as _mark_stale
        return await _mark_stale(db, tenant, older_than_hours=body.older_than_hours)
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/audit/usage")
async def usage_stats(
    since_hours: int = Query(24, ge=1, le=720),
    db: AsyncSession = Depends(_get_db),
    current_user=Depends(_resolve_user),
):
    try:
        tenant = await _tenant(current_user)
        await _iam_check(current_user, tenant, "knowledge:read")
        from app.knowledge.audit import usage_stats as _usage_stats
        return await _usage_stats(db, tenant, since_hours=since_hours)
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/audit/history")
async def query_history(
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(_get_db),
    current_user=Depends(_resolve_user),
):
    try:
        tenant = await _tenant(current_user)
        await _iam_check(current_user, tenant, "knowledge:read")
        from app.knowledge.models import KnowledgeQuery
        stmt = (
            select(KnowledgeQuery)
            .where(KnowledgeQuery.tenant == tenant)
            .order_by(KnowledgeQuery.created_at.desc())
            .limit(min(limit, 200))
        )
        rows = (await db.execute(stmt)).scalars().all()
        items = [
            {
                "query_id": str(q.id),
                "query_text": q.query_text,
                "query_type": q.query_type,
                "results_count": q.results_count,
                "latency_ms": q.latency_ms,
                "user_id": q.user_id,
                "created_at": q.created_at.isoformat() if q.created_at else None,
            }
            for q in rows
        ]
        return {"items": items, "total": len(items)}
    except Exception as exc:
        raise _err(exc) from exc
