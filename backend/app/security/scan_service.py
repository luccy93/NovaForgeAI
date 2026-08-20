"""Security scan orchestration service (Volume 47)."""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.security.models import SecurityScan

logger = logging.getLogger(__name__)

VALID_SCAN_TYPES = {"sast", "secrets", "dependency", "sbom", "container", "iac", "full", "compliance", "supply_chain"}
VALID_TARGET_TYPES = {"repository", "container", "pipeline", "plugin", "iac", "agent"}
VALID_SCAN_STATUSES = {"pending", "running", "completed", "failed", "cancelled"}


class ScanService:
    """Orchestrate security scans, track status, aggregate results."""

    async def create_scan(
        self,
        db: AsyncSession,
        *,
        tenant: str,
        scan_type: str,
        target_type: str,
        target_id: str,
        repository: str = "",
        branch: str = "main",
        commit_sha: str = "",
        triggered_by: str = "system",
    ) -> SecurityScan:
        scan = SecurityScan(
            tenant=tenant,
            scan_type=scan_type,
            target_type=target_type,
            target_id=target_id,
            repository=repository,
            branch=branch,
            commit_sha=commit_sha,
            status="pending",
            triggered_by=triggered_by,
        )
        db.add(scan)
        await db.flush()
        return scan

    async def start_scan(self, db: AsyncSession, scan_id) -> SecurityScan | None:
        stmt = select(SecurityScan).where(SecurityScan.id == scan_id)
        result = await db.execute(stmt)
        scan = result.scalar_one_or_none()
        if not scan:
            return None
        scan.status = "running"
        scan.started_at = datetime.now(timezone.utc)
        await db.flush()
        return scan

    async def complete_scan(self, db: AsyncSession, scan_id, *, findings_count: int = 0, summary: dict | None = None, scanner_versions: dict | None = None) -> SecurityScan | None:
        stmt = select(SecurityScan).where(SecurityScan.id == scan_id)
        result = await db.execute(stmt)
        scan = result.scalar_one_or_none()
        if not scan:
            return None
        now = datetime.now(timezone.utc)
        scan.status = "completed"
        scan.finished_at = now
        scan.findings_count = findings_count
        scan.summary = summary or {}
        scan.scanner_versions = scanner_versions or {}
        if scan.started_at:
            scan.duration_ms = int((now - scan.started_at).total_seconds() * 1000)
        await db.flush()
        return scan

    async def fail_scan(self, db: AsyncSession, scan_id, error: str) -> SecurityScan | None:
        stmt = select(SecurityScan).where(SecurityScan.id == scan_id)
        result = await db.execute(stmt)
        scan = result.scalar_one_or_none()
        if not scan:
            return None
        now = datetime.now(timezone.utc)
        scan.status = "failed"
        scan.finished_at = now
        scan.error = error
        if scan.started_at:
            scan.duration_ms = int((now - scan.started_at).total_seconds() * 1000)
        await db.flush()
        return scan

    async def get_scan(self, db: AsyncSession, scan_id) -> SecurityScan | None:
        stmt = select(SecurityScan).where(SecurityScan.id == scan_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_scans(
        self,
        db: AsyncSession,
        *,
        tenant: str,
        scan_type: str | None = None,
        target_type: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SecurityScan]:
        stmt = select(SecurityScan).where(SecurityScan.tenant == tenant)
        if scan_type:
            stmt = stmt.where(SecurityScan.scan_type == scan_type)
        if target_type:
            stmt = stmt.where(SecurityScan.target_type == target_type)
        if status:
            stmt = stmt.where(SecurityScan.status == status)
        stmt = stmt.order_by(desc(SecurityScan.created_at)).offset(offset).limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def cancel_scan(self, db: AsyncSession, scan_id) -> SecurityScan | None:
        stmt = select(SecurityScan).where(SecurityScan.id == scan_id)
        result = await db.execute(stmt)
        scan = result.scalar_one_or_none()
        if not scan:
            return None
        scan.status = "cancelled"
        scan.finished_at = datetime.now(timezone.utc)
        await db.flush()
        return scan


scan_service = ScanService()
