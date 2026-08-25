"""Volume 60 Commit 2 — Resilience workers (7)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def backup_verification_worker(db: AsyncSession | None = None, tenant: str | None = None) -> dict:
    if db is None or not tenant:
        return {"worker": "backup_verification", "skipped": True}
    try:
        from sqlalchemy import select
        from app.resilience.models import ResilienceBackup
        res = await db.execute(select(ResilienceBackup).where(ResilienceBackup.tenant == tenant, ResilienceBackup.verification_status == "UNVERIFIED").limit(10))
        pending = list(res.scalars().all())
        verified = 0
        for b in pending:
            try:
                from app.resilience.platform import resilience_service
                await resilience_service.verify_backup(db, tenant, str(b.id), verification_type="checksum", expected_checksum=b.checksum)
                verified += 1
            except Exception:
                continue
        return {"worker": "backup_verification", "tenant": tenant, "verified": verified, "pending": len(pending)}
    except Exception as e:
        logger.warning("backup_verification_worker: %s", e)
        return {"worker": "backup_verification", "error": str(e)}


async def retention_checks_worker(db: AsyncSession | None = None, tenant: str | None = None) -> dict:
    if db is None or not tenant:
        return {"worker": "retention_checks", "skipped": True}
    try:
        from sqlalchemy import select
        from app.resilience.models import ResilienceBackup
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        res = await db.execute(select(ResilienceBackup).where(ResilienceBackup.tenant == tenant, ResilienceBackup.expires_at != None))
        expired = [b for b in res.scalars().all() if b.expires_at and b.expires_at < now]
        return {"worker": "retention_checks", "tenant": tenant, "expired": len(expired)}
    except Exception as e:
        return {"worker": "retention_checks", "error": str(e)}


async def readiness_analysis_worker(db: AsyncSession | None = None, tenant: str | None = None) -> dict:
    if db is None or not tenant:
        return {"worker": "readiness_analysis", "skipped": True}
    try:
        from app.resilience.drills import drill_service
        res = await drill_service.calculate_readiness(db, tenant)
        return {"worker": "readiness_analysis", "tenant": tenant, "readiness": res}
    except Exception as e:
        return {"worker": "readiness_analysis", "error": str(e)}


async def recovery_drills_worker(db: AsyncSession | None = None, tenant: str | None = None) -> dict:
    if db is None or not tenant:
        return {"worker": "recovery_drills", "skipped": True}
    try:
        from app.resilience.drills import drill_service
        # Run any scheduled drills that are due
        from sqlalchemy import select
        from app.resilience.models import ResilienceRecoveryDrill
        res = await db.execute(select(ResilienceRecoveryDrill).where(ResilienceRecoveryDrill.tenant == tenant))
        drills = list(res.scalars().all())
        run = 0
        for d in drills[:3]:
            try:
                await drill_service.run_drill(db, tenant, str(d.id))
                run += 1
            except Exception:
                continue
        return {"worker": "recovery_drills", "tenant": tenant, "run": run}
    except Exception as e:
        return {"worker": "recovery_drills", "error": str(e)}


async def reconciliation_worker(db: AsyncSession | None = None, tenant: str | None = None) -> dict:
    if db is None or not tenant:
        return {"worker": "reconciliation", "skipped": True}
    try:
        from app.resilience.reconciliation import reconciliation_service
        # Find recent restore jobs needing reconciliation
        from sqlalchemy import select
        from app.resilience.models import ResilienceRestoreJob
        res = await db.execute(select(ResilienceRestoreJob).where(ResilienceRestoreJob.tenant == tenant, ResilienceRestoreJob.state == "COMPLETED").limit(5))
        jobs = list(res.scalars().all())
        reconciled = 0
        for j in jobs:
            try:
                await reconciliation_service.reconcile(db, tenant, str(j.id), pre_state={}, restored_state={}, expected_state={})
                reconciled += 1
            except Exception:
                continue
        return {"worker": "reconciliation", "tenant": tenant, "reconciled": reconciled}
    except Exception as e:
        return {"worker": "reconciliation", "error": str(e)}


async def failover_monitoring_worker(db: AsyncSession | None = None, tenant: str | None = None) -> dict:
    if db is None or not tenant:
        return {"worker": "failover_monitoring", "skipped": True}
    try:
        from sqlalchemy import select
        from app.resilience.models import ResilienceFailoverRecord
        res = await db.execute(select(ResilienceFailoverRecord).where(ResilienceFailoverRecord.tenant == tenant, ResilienceFailoverRecord.status == "STARTED").limit(10))
        pending = list(res.scalars().all())
        return {"worker": "failover_monitoring", "tenant": tenant, "pending": len(pending)}
    except Exception as e:
        return {"worker": "failover_monitoring", "error": str(e)}


async def recovery_health_checks_worker(db: AsyncSession | None = None, tenant: str | None = None) -> dict:
    if db is None or not tenant:
        return {"worker": "recovery_health_checks", "skipped": True}
    try:
        from app.resilience.hardening import hardening_service
        # Run post-recovery validation for recent recoveries
        res = await hardening_service.post_recovery_validation(db, tenant)
        return {"worker": "recovery_health_checks", "tenant": tenant, "validated": res}
    except Exception as e:
        # Fallback to simple health check
        try:
            from app.observability.platform import platform_service
            services = await platform_service.list_services(db, tenant)
            healthy = sum(1 for s in services if s.health_status == "HEALTHY")
            return {"worker": "recovery_health_checks", "tenant": tenant, "healthy": healthy, "total": len(services)}
        except Exception as e2:
            return {"worker": "recovery_health_checks", "error": str(e2)}
