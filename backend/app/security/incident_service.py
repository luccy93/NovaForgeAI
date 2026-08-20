"""Security incident integration service (Volume 47).

Creates incidents from critical findings, links findings to incidents,
integrates with the SRE incident system and compliance module.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.security.models import SecurityFinding, SecurityRemediation

logger = logging.getLogger(__name__)

SEVERITY_TO_INCIDENT = {
    "critical": "P1",
    "high": "P2",
    "medium": "P3",
    "low": "P4",
}


class IncidentService:
    """Link critical findings to incidents, create remediation tracks."""

    async def create_incident_from_finding(
        self,
        db: AsyncSession,
        *,
        tenant: str,
        finding_id,
        priority: str = "",
    ) -> dict:
        stmt = select(SecurityFinding).where(SecurityFinding.id == finding_id)
        result = await db.execute(stmt)
        finding = result.scalar_one_or_none()
        if not finding:
            return {"error": "Finding not found"}

        if not priority:
            priority = SEVERITY_TO_INCIDENT.get(finding.severity, "P4")

        incident = {
            "finding_id": str(finding.id),
            "title": f"[{finding.severity.upper()}] {finding.rule}: {finding.message[:200]}",
            "priority": priority,
            "status": "open",
            "severity": finding.severity,
            "source": finding.source,
            "repository": finding.repository,
            "file_path": finding.file_path,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "linked_findings": [str(finding.id)],
        }

        return incident

    async def create_remediation(
        self,
        db: AsyncSession,
        *,
        tenant: str,
        finding_id,
        remediation_type: str = "auto",
        approach: str = "",
    ) -> SecurityRemediation:
        stmt = select(SecurityFinding).where(SecurityFinding.id == finding_id)
        result = await db.execute(stmt)
        finding = result.scalar_one_or_none()
        if not finding:
            raise ValueError("Finding not found")

        remediation = SecurityRemediation(
            tenant=tenant,
            finding_id=finding_id,
            remediation_type=remediation_type,
            status="pending",
            approach=approach or finding.remediation or f"Fix for {finding.rule}",
        )
        db.add(remediation)
        await db.flush()
        return remediation

    async def get_remediation(self, db: AsyncSession, remediation_id) -> SecurityRemediation | None:
        stmt = select(SecurityRemediation).where(SecurityRemediation.id == remediation_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_remediations(
        self,
        db: AsyncSession,
        *,
        tenant: str,
        status: str | None = None,
        limit: int = 20,
    ) -> list[SecurityRemediation]:
        stmt = select(SecurityRemediation).where(SecurityRemediation.tenant == tenant)
        if status:
            stmt = stmt.where(SecurityRemediation.status == status)
        stmt = stmt.order_by(desc(SecurityRemediation.created_at)).limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def update_remediation_status(
        self,
        db: AsyncSession,
        remediation_id,
        status: str,
        verified: bool = False,
        error: str | None = None,
    ) -> SecurityRemediation | None:
        stmt = select(SecurityRemediation).where(SecurityRemediation.id == remediation_id)
        result = await db.execute(stmt)
        remediation = result.scalar_one_or_none()
        if not remediation:
            return None
        remediation.status = status
        if verified:
            remediation.verified = True
            remediation.verified_at = datetime.now(timezone.utc)
        if error:
            remediation.error = error
        await db.flush()
        return remediation


incident_service = IncidentService()
