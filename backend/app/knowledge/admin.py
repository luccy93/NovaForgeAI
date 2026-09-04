"""Knowledge admin and source lifecycle — Volume 68.

Provides source health monitoring, bulk operations, maintenance tasks,
system statistics, and metadata export.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.common import emit_event, ingest_metric_best_effort
from app.knowledge.models import (
    KnowledgeDocument,
    KnowledgeIngestionJob,
    KnowledgeSource,
)

logger = logging.getLogger(__name__)


async def get_source_health(db: AsyncSession, tenant: str, source_id: uuid.UUID) -> dict:
    """Check health of a knowledge source: freshness, error rate, doc count."""
    try:
        stmt = select(KnowledgeSource).where(
            KnowledgeSource.id == source_id,
            KnowledgeSource.tenant == tenant,
            KnowledgeSource.status != "DELETED",
        )
        result = await db.execute(stmt)
        source = result.scalar_one_or_none()
        if source is None:
            return {"status": "not_found", "source_id": str(source_id)}
        
        # Document count
        doc_count_stmt = (
            select(func.count())
            .select_from(KnowledgeDocument)
            .where(
                KnowledgeDocument.tenant == tenant,
                KnowledgeDocument.source_id == source_id,
                KnowledgeDocument.status != "DELETED",
            )
        )
        doc_count = (await db.execute(doc_count_stmt)).scalar() or 0
        
        # Recent job stats
        jobs_stmt = (
            select(KnowledgeIngestionJob)
            .where(
                KnowledgeIngestionJob.tenant == tenant,
                KnowledgeIngestionJob.source_id == source_id,
            )
            .order_by(KnowledgeIngestionJob.created_at.desc())
            .limit(10)
        )
        recent_jobs = (await db.execute(jobs_stmt)).scalars().all()
        
        failed_jobs = sum(1 for j in recent_jobs if j.status == "FAILED")
        completed_jobs = sum(1 for j in recent_jobs if j.status == "COMPLETED")
        error_rate = failed_jobs / max(len(recent_jobs), 1)
        
        # Freshness
        last_ingested = source.last_ingested_at
        now = datetime.now(timezone.utc)
        if last_ingested:
            if last_ingested.tzinfo is None:
                last_ingested = last_ingested.replace(tzinfo=timezone.utc)
            hours_since = (now - last_ingested).total_seconds() / 3600
        else:
            hours_since = None
        
        # Health score (0-1)
        health = 1.0
        if error_rate > 0:
            health -= error_rate * 0.4
        if hours_since is not None and hours_since > 168:  # 7 days
            health -= min((hours_since - 168) / 168, 0.3)
        if doc_count == 0:
            health -= 0.2
        health = max(health, 0.0)
        
        health_label = "healthy" if health >= 0.7 else "degraded" if health >= 0.4 else "unhealthy"
        
        return {
            "source_id": str(source_id),
            "source_name": source.name,
            "source_type": source.source_type,
            "status": source.status,
            "document_count": doc_count,
            "recent_jobs": len(recent_jobs),
            "failed_jobs": failed_jobs,
            "completed_jobs": completed_jobs,
            "error_rate": round(error_rate, 4),
            "hours_since_last_ingestion": round(hours_since, 1) if hours_since is not None else None,
            "health_score": round(health, 4),
            "health_label": health_label,
        }
    except Exception as exc:
        logger.warning("get_source_health failed: %s", exc)
        return {"status": "error", "error": str(exc)}


async def bulk_update_source_status(
    db: AsyncSession,
    tenant: str,
    source_ids: list[uuid.UUID],
    new_status: str,
) -> dict:
    """Bulk update status of multiple sources.
    
    Returns: {"updated_count": int, "failed_ids": list[str]}
    """
    updated_count = 0
    failed_ids: list[str] = []
    
    for sid in source_ids:
        try:
            stmt = select(KnowledgeSource).where(
                KnowledgeSource.id == sid,
                KnowledgeSource.tenant == tenant,
                KnowledgeSource.status != "DELETED",
            )
            result = await db.execute(stmt)
            source = result.scalar_one_or_none()
            if source is None:
                failed_ids.append(str(sid))
                continue
            
            source.status = new_status
            updated_count += 1
        except Exception:
            failed_ids.append(str(sid))
    
    await db.flush()
    
    try:
        await emit_event("knowledge.admin.bulk_status_update", {
            "new_status": new_status,
            "updated_count": updated_count,
            "failed_count": len(failed_ids),
        }, tenant=tenant, source="knowledge")
    except Exception:
        pass
    
    return {"updated_count": updated_count, "failed_ids": failed_ids}


async def get_system_stats(db: AsyncSession, tenant: str) -> dict:
    """Aggregate statistics across all knowledge sources."""
    try:
        source_stmt = (
            select(
                func.count().label("total"),
                func.count().filter(KnowledgeSource.status == "ACTIVE").label("active"),
                func.count().filter(KnowledgeSource.status == "ERROR").label("error"),
            )
            .select_from(KnowledgeSource)
            .where(KnowledgeSource.tenant == tenant, KnowledgeSource.status != "DELETED")
        )
        source_row = (await db.execute(source_stmt)).one()
        
        doc_stmt = (
            select(func.count())
            .select_from(KnowledgeDocument)
            .where(KnowledgeDocument.tenant == tenant, KnowledgeDocument.status != "DELETED")
        )
        doc_count = (await db.execute(doc_stmt)).scalar() or 0
        
        job_stmt = (
            select(
                func.count().label("total"),
                func.count().filter(KnowledgeIngestionJob.status == "COMPLETED").label("completed"),
                func.count().filter(KnowledgeIngestionJob.status == "FAILED").label("failed"),
                func.count().filter(KnowledgeIngestionJob.status == "RUNNING").label("running"),
            )
            .select_from(KnowledgeIngestionJob)
            .where(KnowledgeIngestionJob.tenant == tenant)
        )
        job_row = (await db.execute(job_stmt)).one()
        
        chunk_stmt = (
            select(func.count())
            .select_from(KnowledgeDocument)
            .where(KnowledgeDocument.tenant == tenant, KnowledgeDocument.status != "DELETED")
        )
        
        return {
            "sources": {
                "total": source_row.total,
                "active": source_row.active,
                "error": source_row.error,
            },
            "documents": {"total": doc_count},
            "ingestion_jobs": {
                "total": job_row.total,
                "completed": job_row.completed,
                "failed": job_row.failed,
                "running": job_row.running,
            },
        }
    except Exception as exc:
        logger.warning("get_system_stats failed: %s", exc)
        return {"sources": {}, "documents": {}, "ingestion_jobs": {}}


async def run_maintenance(
    db: AsyncSession,
    tenant: str,
    *,
    prune_stale: bool = True,
    recompute_freshness: bool = True,
) -> dict:
    """Run maintenance tasks: mark stale docs, recompute freshness."""
    results: dict[str, Any] = {}
    
    if prune_stale:
        try:
            from app.knowledge.freshness import mark_stale as _mark_stale
            results["stale_marked"] = await _mark_stale(db, tenant)
        except Exception as exc:
            logger.warning("Maintenance prune_stale failed: %s", exc)
            results["stale_marked"] = 0
    
    if recompute_freshness:
        try:
            stmt = select(KnowledgeDocument.id).where(
                KnowledgeDocument.tenant == tenant,
                KnowledgeDocument.status != "DELETED",
            )
            doc_ids = (await db.execute(stmt)).scalars().all()
            
            recomputed = 0
            for doc_id in doc_ids:
                try:
                    from app.knowledge.freshness import update_document_freshness
                    await update_document_freshness(db, tenant, doc_id)
                    recomputed += 1
                except Exception:
                    pass
            results["freshness_recomputed"] = recomputed
        except Exception as exc:
            logger.warning("Maintenance recompute_freshness failed: %s", exc)
            results["freshness_recomputed"] = 0
    
    try:
        await emit_event("knowledge.admin.maintenance", results, tenant=tenant, source="knowledge")
    except Exception:
        pass
    
    return results


async def export_source_metadata(db: AsyncSession, tenant: str, source_id: uuid.UUID) -> dict:
    """Export full source metadata: config, stats, recent jobs."""
    try:
        stmt = select(KnowledgeSource).where(
            KnowledgeSource.id == source_id,
            KnowledgeSource.tenant == tenant,
            KnowledgeSource.status != "DELETED",
        )
        result = await db.execute(stmt)
        source = result.scalar_one_or_none()
        if source is None:
            return {"error": "source_not_found"}
        
        doc_stmt = (
            select(func.count())
            .select_from(KnowledgeDocument)
            .where(
                KnowledgeDocument.tenant == tenant,
                KnowledgeDocument.source_id == source_id,
                KnowledgeDocument.status != "DELETED",
            )
        )
        doc_count = (await db.execute(doc_stmt)).scalar() or 0
        
        job_stmt = (
            select(KnowledgeIngestionJob)
            .where(
                KnowledgeIngestionJob.tenant == tenant,
                KnowledgeIngestionJob.source_id == source_id,
            )
            .order_by(KnowledgeIngestionJob.created_at.desc())
            .limit(5)
        )
        recent_jobs = (await db.execute(job_stmt)).scalars().all()
        
        return {
            "source_id": str(source.id),
            "name": source.name,
            "source_type": source.source_type,
            "status": source.status,
            "classification": source.classification,
            "region": source.region,
            "connector_config": source.connector_config or {},
            "ingestion_config": source.ingestion_config or {},
            "owner": source.owner,
            "document_count": doc_count,
            "last_ingested_at": source.last_ingested_at.isoformat() if source.last_ingested_at else None,
            "recent_jobs": [
                {
                    "job_id": str(j.id),
                    "status": j.status,
                    "job_type": j.job_type,
                    "started_at": j.started_at.isoformat() if j.started_at else None,
                    "completed_at": j.completed_at.isoformat() if j.completed_at else None,
                }
                for j in recent_jobs
            ],
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.warning("export_source_metadata failed: %s", exc)
        return {"error": str(exc)}
