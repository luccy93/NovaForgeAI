"""Security findings lifecycle management (Volume 47)."""

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.security.models import SecurityFinding, SecurityFingerprint

logger = logging.getLogger(__name__)

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "informational": 4}
VALID_SEVERITIES = set(SEVERITY_ORDER.keys())
VALID_STATUSES = {"open", "acknowledged", "in_progress", "fixed", "verified", "false_positive", "risk_accepted", "reopened"}


def compute_fingerprint(rule: str, file_path: str = "", dependency: str = "", cve: str = "", artifact: str = "") -> str:
    raw = f"{rule}:{file_path}:{dependency}:{cve}:{artifact}"
    return hashlib.sha256(raw.encode()).hexdigest()[:64]


def compute_risk_score(severity: str, confidence: str, reachability: str = "unknown", exploitability: str = "unknown") -> float:
    sev = {"critical": 10.0, "high": 7.5, "medium": 5.0, "low": 2.5, "informational": 1.0}.get(severity, 1.0)
    conf = {"high": 1.0, "medium": 0.7, "low": 0.4}.get(confidence, 0.5)
    reach = {"reachable": 1.0, "potentially_reachable": 0.6, "unreachable": 0.2}.get(reachability, 0.5)
    expl = {"known": 1.0, "poc": 0.7, "theoretical": 0.4}.get(exploitability, 0.5)
    return round(sev * conf * max(reach, expl), 2)


class FindingsService:
    """CRUD, deduplication, lifecycle, and risk scoring for security findings."""

    async def create_finding(
        self,
        db: AsyncSession,
        *,
        tenant: str,
        source: str,
        finding_type: str,
        severity: str,
        rule: str,
        message: str,
        file_path: str = "",
        line_start: int | None = None,
        line_end: int | None = None,
        symbol: str = "",
        function: str = "",
        confidence: str = "medium",
        evidence: str = "",
        repository: str = "",
        branch: str = "main",
        commit_sha: str = "",
        project: str = "",
        dependency_name: str = "",
        dependency_version: str = "",
        cve_id: str = "",
        cwe_id: str = "",
        reachability: str = "unknown",
        auto_remediable: bool = False,
        scan_id=None,
        metadata_extra: Optional[dict] = None,
    ) -> SecurityFinding:
        severity = severity.lower() if severity.lower() in VALID_SEVERITIES else "medium"
        fp = compute_fingerprint(rule, file_path, dependency_name, cve_id)
        risk_score = compute_risk_score(severity, confidence, reachability)

        existing = await self._find_by_fingerprint(db, fp)
        now = datetime.now(timezone.utc)
        if existing:
            existing.last_seen = now
            existing.occurrence_count += 1
            if existing.risk_score < risk_score:
                existing.risk_score = risk_score
            await db.flush()
            return existing

        finding = SecurityFinding(
            tenant=tenant,
            scan_id=scan_id,
            project=project,
            repository=repository,
            branch=branch,
            commit_sha=commit_sha,
            source=source,
            finding_type=finding_type,
            severity=severity,
            confidence=confidence,
            file_path=file_path,
            line_start=line_start,
            line_end=line_end,
            symbol=symbol,
            function=function,
            rule=rule,
            message=message,
            evidence=evidence,
            status="open",
            first_seen=now,
            last_seen=now,
            risk_score=risk_score,
            fingerprint=fp,
            dependency_name=dependency_name,
            dependency_version=dependency_version,
            cve_id=cve_id,
            cwe_id=cwe_id,
            reachability=reachability,
            auto_remediable=auto_remediable,
            metadata_extra=metadata_extra or {},
        )
        db.add(finding)
        await db.flush()

        fingerprint_rec = SecurityFingerprint(
            fingerprint_hash=fp,
            finding_id=finding.id,
            rule=rule,
            location=file_path,
            dependency=dependency_name,
            cve=cve_id,
            first_seen=now,
            last_seen=now,
            occurrence_count=1,
            active=True,
        )
        db.add(fingerprint_rec)
        await db.flush()
        return finding

    async def _find_by_fingerprint(self, db: AsyncSession, fp: str) -> SecurityFinding | None:
        stmt = select(SecurityFinding).where(SecurityFinding.fingerprint == fp).limit(1)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_status(self, db: AsyncSession, finding_id, status: str) -> SecurityFinding | None:
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}. Valid: {VALID_STATUSES}")
        stmt = select(SecurityFinding).where(SecurityFinding.id == finding_id)
        result = await db.execute(stmt)
        finding = result.scalar_one_or_none()
        if not finding:
            return None
        finding.status = status
        if status in ("fixed", "verified"):
            finding.fixed_at = datetime.now(timezone.utc)
        if status == "verified":
            finding.verified = True
        await db.flush()
        return finding

    async def get_finding(self, db: AsyncSession, finding_id) -> SecurityFinding | None:
        stmt = select(SecurityFinding).where(SecurityFinding.id == finding_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_findings(
        self,
        db: AsyncSession,
        *,
        tenant: str,
        severity: str | None = None,
        status: str | None = None,
        source: str | None = None,
        repository: str | None = None,
        finding_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SecurityFinding]:
        stmt = select(SecurityFinding).where(SecurityFinding.tenant == tenant)
        if severity:
            stmt = stmt.where(SecurityFinding.severity == severity.lower())
        if status:
            stmt = stmt.where(SecurityFinding.status == status)
        if source:
            stmt = stmt.where(SecurityFinding.source == source)
        if repository:
            stmt = stmt.where(SecurityFinding.repository == repository)
        if finding_type:
            stmt = stmt.where(SecurityFinding.finding_type == finding_type)
        stmt = stmt.order_by(desc(SecurityFinding.risk_score)).offset(offset).limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_summary(self, db: AsyncSession, tenant: str) -> dict:
        stmt = select(
            SecurityFinding.severity,
            SecurityFinding.status,
            func.count(SecurityFinding.id),
        ).where(SecurityFinding.tenant == tenant).group_by(SecurityFinding.severity, SecurityFinding.status)
        result = await db.execute(stmt)
        by_severity = {}
        by_status = {}
        total = 0
        for severity, status, count in result:
            by_severity[severity] = by_severity.get(severity, 0) + count
            by_status[status] = by_status.get(status, 0) + count
            total += count
        return {
            "total": total,
            "by_severity": by_severity,
            "by_status": by_status,
        }

    async def risk_accept(self, db: AsyncSession, finding_id, authorized_by: str, reason: str, expires_at=None) -> dict:
        finding = await self.get_finding(db, finding_id)
        if not finding:
            raise ValueError("Finding not found")
        finding.status = "risk_accepted"
        await db.flush()
        return {"finding_id": str(finding.id), "status": "risk_accepted", "authorized_by": authorized_by}

    async def delete_finding(self, db: AsyncSession, finding_id) -> bool:
        stmt = select(SecurityFinding).where(SecurityFinding.id == finding_id)
        result = await db.execute(stmt)
        finding = result.scalar_one_or_none()
        if not finding:
            return False
        await db.delete(finding)
        await db.flush()
        return True


findings_service = FindingsService()
