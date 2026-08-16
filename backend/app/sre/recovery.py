"""Disaster recovery (Volume 35).

Backup job records, scheduled restore tests, failover tests, and
RTO/RPO reporting. Backups are not considered reliable until a restore
test passes.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sre.constants import TIER_DEFAULTS
from app.sre.models import (
    SREBackupJob,
    SREFailoverTest,
    SRERestoreTest,
    SREService,
)
from app.sre.store import get_one, list_all, new_id, new_key

logger = logging.getLogger(__name__)

BACKUP_TARGETS = ["postgresql", "redis", "qdrant", "neo4j", "object_storage"]

FAILOVER_TARGETS = [
    "region",
    "database",
    "redis",
    "qdrant",
    "neo4j",
    "object_storage",
    "ai_provider",
    "queue",
    "worker",
    "network",
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BackupManager:
    """Backup job lifecycle and verification."""

    async def schedule(
        self,
        db: AsyncSession,
        *,
        target: str,
        kind: str = "full",
        region: str = "",
    ) -> SREBackupJob:
        if target not in BACKUP_TARGETS:
            raise ValueError(f"unsupported backup target: {target}")
        job = SREBackupJob(
            id=new_id(),
            backup_id=new_key("backup"),
            target=target,
            region=region,
            kind=kind,
            status="pending",
        )
        db.add(job)
        await db.flush()
        return job

    async def start(self, db: AsyncSession, backup_id: str) -> Optional[SREBackupJob]:
        job = await get_one(db, SREBackupJob, backup_id=backup_id)
        if job is None:
            return None
        job.status = "running"
        job.started_at = _utcnow()
        await db.flush()
        return job

    async def complete(
        self,
        db: AsyncSession,
        backup_id: str,
        *,
        size_bytes: int = 0,
        verified: bool = False,
        error: str = "",
    ) -> Optional[SREBackupJob]:
        job = await get_one(db, SREBackupJob, backup_id=backup_id)
        if job is None:
            return None
        job.status = "failed" if error else "completed"
        job.completed_at = _utcnow()
        job.size_bytes = size_bytes
        job.verified = verified
        job.error = error
        await db.flush()
        return job

    async def fail(self, db: AsyncSession, backup_id: str, error: str) -> Optional[SREBackupJob]:
        return await self.complete(db, backup_id, error=error)

    async def list(
        self,
        db: AsyncSession,
        *,
        target: str = "",
        status: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        items, total = await list_all(
            db, SREBackupJob, limit=limit, offset=offset, order_by="created_at", target=target, status=status
        )
        return [j.to_dict() for j in items], total

    async def latest_success(self, db: AsyncSession, target: str) -> Optional[dict]:
        result = await db.execute(
            select(SREBackupJob)
            .where(SREBackupJob.target == target, SREBackupJob.status == "completed")
            .order_by(SREBackupJob.completed_at.desc())
            .limit(1)
        )
        job = result.scalar_one_or_none()
        return job.to_dict() if job else None

    async def verify(self, db: AsyncSession, backup_id: str, ok: bool, error: str = "") -> Optional[SREBackupJob]:
        job = await get_one(db, SREBackupJob, backup_id=backup_id)
        if job is None:
            return None
        job.verified = ok
        if error:
            job.error = error
        await db.flush()
        return job

    async def coverage(self, db: AsyncSession) -> dict:
        """Backup freshness per target + verification coverage."""
        report: dict[str, dict] = {}
        for target in BACKUP_TARGETS:
            latest = await self.latest_success(db, target)
            report[target] = {
                "latest_backup": latest["backup_id"] if latest else None,
                "completed_at": latest["completed_at"] if latest else None,
                "verified": latest["verified"] if latest else False,
                "fresh_minutes": (
                    round((_utcnow() - datetime.fromisoformat(latest["completed_at"])).total_seconds() / 60)
                    if latest and latest["completed_at"]
                    else None
                ),
            }
        total_backups = (await db.execute(select(func.count()).select_from(SREBackupJob))).scalar() or 0
        verified_backups = (
            await db.execute(
                select(func.count()).select_from(SREBackupJob).where(SREBackupJob.verified.is_(True))
            )
        ).scalar() or 0
        report["summary"] = {
            "total_backups": total_backups,
            "verified_backups": verified_backups,
            "verification_rate": round(verified_backups / total_backups, 4) if total_backups else 0.0,
        }
        return report


class RestoreTestManager:
    """Scheduled restore verification tests."""

    async def schedule(
        self,
        db: AsyncSession,
        *,
        target: str,
        backup_id: str = "",
        scheduled_for: Optional[datetime] = None,
    ) -> SRERestoreTest:
        test = SRERestoreTest(
            id=new_id(),
            test_id=new_key("restore"),
            backup_id=backup_id,
            target=target,
            status="pending",
            scheduled_for=scheduled_for or _utcnow() + timedelta(days=1),
        )
        db.add(test)
        await db.flush()
        return test

    async def complete(
        self,
        db: AsyncSession,
        test_id: str,
        *,
        integrity: bool,
        completeness: bool,
        consistency: bool,
        app_compatible: bool,
        notes: str = "",
        duration_seconds: int = 0,
    ) -> Optional[SRERestoreTest]:
        test = await get_one(db, SRERestoreTest, test_id=test_id)
        if test is None:
            return None
        test.integrity = integrity
        test.completeness = completeness
        test.consistency = consistency
        test.app_compatible = app_compatible
        test.notes = notes
        test.duration_seconds = duration_seconds
        test.status = "passed" if all([integrity, completeness, consistency, app_compatible]) else "failed"
        test.completed_at = _utcnow()
        await db.flush()
        return test

    async def list(
        self,
        db: AsyncSession,
        *,
        target: str = "",
        status: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        items, total = await list_all(
            db, SRERestoreTest, limit=limit, offset=offset, order_by="scheduled_for", target=target, status=status
        )
        return [t.to_dict() for t in items], total

    async def recent_results(self, db: AsyncSession, limit: int = 20) -> "list[dict]":
        result = await db.execute(
            select(SRERestoreTest)
            .where(SRERestoreTest.status.in_(["passed", "failed"]))
            .order_by(SRERestoreTest.completed_at.desc())
            .limit(limit)
        )
        return [t.to_dict() for t in result.scalars().all()]


class FailoverTestManager:
    """Failover verification tests."""

    async def schedule(
        self,
        db: AsyncSession,
        *,
        target: str,
        scope: str = "",
        scheduled_for: Optional[datetime] = None,
    ) -> SREFailoverTest:
        if target not in FAILOVER_TARGETS:
            raise ValueError(f"unsupported failover target: {target}")
        test = SREFailoverTest(
            id=new_id(),
            test_id=new_key("failover"),
            target=target,
            scope=scope,
            status="pending",
            scheduled_for=scheduled_for or _utcnow() + timedelta(days=1),
        )
        db.add(test)
        await db.flush()
        return test

    async def complete(
        self,
        db: AsyncSession,
        test_id: str,
        *,
        rto_achieved_minutes: int,
        data_loss_minutes: int = 0,
        notes: str = "",
    ) -> Optional[SREFailoverTest]:
        test = await get_one(db, SREFailoverTest, test_id=test_id)
        if test is None:
            return None
        test.rto_achieved_minutes = rto_achieved_minutes
        test.data_loss_minutes = data_loss_minutes
        test.notes = notes
        test.status = "passed" if not notes else "failed"
        test.completed_at = _utcnow()
        await db.flush()
        return test

    async def list(
        self,
        db: AsyncSession,
        *,
        target: str = "",
        status: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        items, total = await list_all(
            db, SREFailoverTest, limit=limit, offset=offset, order_by="scheduled_for", target=target, status=status
        )
        return [t.to_dict() for t in items], total


class DRManager:
    """Disaster recovery plan view: RTO/RPO per tier + test posture."""

    async def plan(self, db: AsyncSession) -> dict:
        services = (await db.execute(select(SREService))).scalars().all()
        by_tier: dict[str, dict] = {}
        for tier, defaults in TIER_DEFAULTS.items():
            matched = [s for s in services if s.tier == tier]
            by_tier[tier] = {
                "services": [s.service_id for s in matched],
                "default_rto_minutes": defaults["rto_minutes"],
                "default_rpo_minutes": defaults.get("rpo_minutes", 60),
                "backup_frequency_minutes": defaults["backup_frequency_minutes"],
            }
        failover_tests, failover_total = await FailoverTestManager().list(db, limit=100)
        restore_tests, restore_total = await RestoreTestManager().list(db, limit=100)
        passed_failover = sum(1 for t in failover_tests if t.get("status") == "passed")
        passed_restore = sum(1 for t in restore_tests if t.get("status") == "passed")
        return {
            "tiers": by_tier,
            "failover_tests": {"total": failover_total, "passed": passed_failover},
            "restore_tests": {"total": restore_total, "passed": passed_restore},
            "recovery_proven": passed_restore > 0 and passed_failover > 0,
        }


backup_manager = BackupManager()
restore_test_manager = RestoreTestManager()
failover_test_manager = FailoverTestManager()
dr_manager = DRManager()
