"""Knowledge ingestion worker loop — Volume 68.

Provides a deterministic, auditable worker loop that claims one or more
pending ingestion jobs, acquires an in-memory lease (mirrors the V67
agent worker lease), executes via the indexing service, records
checkpoints, completes or fails the job, and releases the lease.
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.common import emit_event
from app.knowledge.models import KnowledgeIngestionJob

logger = logging.getLogger(__name__)

_ingestion_leases: dict[str, dict] = {}


async def acquire_ingestion_lease(tenant: str, job_id: str, worker_id: str, ttl_seconds: int = 60) -> bool:
    key = f"{tenant}:{job_id}"
    now = datetime.now(timezone.utc)
    existing = _ingestion_leases.get(key)
    if existing and existing["expires_at"] > now and existing["worker_id"] != worker_id:
        return False
    _ingestion_leases[key] = {
        "worker_id": worker_id,
        "expires_at": now + timedelta(seconds=ttl_seconds),
        "acquired_at": now,
    }
    return True


async def release_ingestion_lease(tenant: str, job_id: str, worker_id: str) -> None:
    key = f"{tenant}:{job_id}"
    existing = _ingestion_leases.get(key)
    if existing and existing["worker_id"] == worker_id:
        _ingestion_leases.pop(key, None)


def _worker_id() -> str:
    return f"knowledge-worker-{uuid.uuid4().hex[:8]}"


async def claim_next_job(db: AsyncSession, tenant: str, worker_id: str) -> Optional[KnowledgeIngestionJob]:
    stmt = (
        select(KnowledgeIngestionJob)
        .where(KnowledgeIngestionJob.tenant == tenant, KnowledgeIngestionJob.status == "PENDING")
        .order_by(KnowledgeIngestionJob.created_at.asc())
        .limit(5)
    )
    rows = (await db.execute(stmt)).scalars().all()
    for job in rows:
        wid = job.worker_id or worker_id
        if await acquire_ingestion_lease(tenant, str(job.id), wid):
            job.worker_id = wid
            return job
    return None


async def execute_ingestion(
    db: AsyncSession,
    tenant: str,
    job_id,
    *,
    user_id: Optional[str] = None,
    worker_id: Optional[str] = None,
) -> KnowledgeIngestionJob:
    from app.knowledge import indexing as indexing_svc

    job = await _get_job(db, tenant, job_id)
    if job.status != "PENDING":
        return job

    wid = worker_id or job.worker_id or _worker_id()
    if not await acquire_ingestion_lease(tenant, str(job.id), wid):
        raise ValueError("ingestion job already claimed by another worker")

    job.status = "RUNNING"
    job.worker_id = wid
    job.started_at = datetime.now(timezone.utc)

    try:
        result = await indexing_svc.run_ingestion_job(
            db, tenant, job.source_id, job_type=job.job_type
        )

        job.documents_processed = result.get("documents_processed", 0)
        job.chunks_created = result.get("chunks_created", 0)
        job.documents_failed = len(result.get("errors", []))
        job.status = "COMPLETED" if result.get("status") != "FAILED" else "FAILED"
        job.error = "; ".join(result.get("errors", [])) if result.get("errors") else None
        job.completed_at = datetime.now(timezone.utc)
        await db.flush()

        await emit_event(
            "knowledge_ingestion_completed",
            {
                "job_id": str(job.id),
                "source_id": str(job.source_id),
                "documents_processed": job.documents_processed,
                "chunks_created": job.chunks_created,
            },
            tenant,
        )
        return job
    except Exception as exc:
        job.status = "FAILED"
        job.error = f"{type(exc).__name__}: {exc}"
        job.completed_at = datetime.now(timezone.utc)
        await db.flush()

        await emit_event(
            "knowledge_ingestion_failed",
            {"job_id": str(job.id), "error": str(exc)},
            tenant,
        )
        return job
    finally:
        await release_ingestion_lease(tenant, str(job.id), wid)


async def run_ingestion_until_done(
    db: AsyncSession,
    tenant: str,
    job_id,
    *,
    user_id: Optional[str] = None,
    worker_id: Optional[str] = None,
) -> KnowledgeIngestionJob:
    return await execute_ingestion(
        db, tenant, job_id, user_id=user_id, worker_id=worker_id or _worker_id()
    )


async def process_pending_jobs(
    db: AsyncSession,
    tenant: str,
    worker_id: str,
    *,
    limit: int = 3,
) -> list[dict]:
    results: list[dict] = []
    for _ in range(max(1, limit)):
        job = await claim_next_job(db, tenant, worker_id)
        if job is None:
            break
        try:
            job = await execute_ingestion(
                db, tenant, str(job.id), user_id=None, worker_id=worker_id
            )
        except Exception as exc:
            logger.exception("process_pending_jobs execute failed: %s", exc)
        results.append({"job_id": str(job.id), "status": job.status})
    return results


async def _get_job(db: AsyncSession, tenant: str, job_id) -> KnowledgeIngestionJob:
    stmt = select(KnowledgeIngestionJob).where(
        KnowledgeIngestionJob.id == job_id,
        KnowledgeIngestionJob.tenant == tenant,
    )
    job = (await db.execute(stmt)).scalar_one_or_none()
    if job is None:
        raise ValueError(f"Ingestion job {job_id} not found")
    return job
