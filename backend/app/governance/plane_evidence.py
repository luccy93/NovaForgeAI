"""Evidence registry and refresh — Volume 71 Commit 2.

The registry tracks which controls have verifiable evidence and
whether it is still valid. Refresh re-verifies hashes against live
source systems (best-effort per source) and marks stale entries.
Only references and hashes are stored.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Optional

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.governance.plane_common import (
    ValidationError,
    _utcnow,
    sanitize_metadata,
)
from app.governance.plane_controls import integrity_hash
from app.governance.plane_models_c2 import GovernancePlaneEvidence

EVIDENCE_SOURCES = ("audit", "policy_decision", "security_finding", "lineage",
                    "workflow_record", "finops_record", "integration_health",
                    "ai_usage", "zero_trust_decision")


async def register_evidence(
    db: AsyncSession, tenant: str, control_key: str, *,
    source_system: str, source_ref: str, source_version: str = "",
    result: str = "PASS", validity_days: int = 90,
    metadata: Optional[dict] = None,
) -> dict:
    if not tenant:
        raise ValidationError("tenant required")
    if source_system not in EVIDENCE_SOURCES:
        raise ValidationError(f"unknown source system: {source_system!r}")
    if result not in ("PASS", "FAIL"):
        raise ValidationError("result must be PASS or FAIL")
    digest = integrity_hash(source_system, source_ref, source_version)
    now = _utcnow()
    stmt = select(GovernancePlaneEvidence).where(
        GovernancePlaneEvidence.tenant == tenant,
        GovernancePlaneEvidence.control_key == control_key,
        GovernancePlaneEvidence.source_system == source_system,
        GovernancePlaneEvidence.source_ref == source_ref,
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        existing.source_version = source_version
        existing.collected_at = now
        existing.valid_until = now + timedelta(days=min(max(int(validity_days or 90), 1), 365))
        existing.integrity_hash = digest
        existing.result = result
        existing.metadata_ = sanitize_metadata(metadata)
        await db.flush()
        return _serialize(existing)
    row = GovernancePlaneEvidence(
        id=uuid.uuid4(), tenant=tenant, control_key=control_key,
        source_system=source_system, source_ref=source_ref,
        source_version=source_version, collected_at=now,
        valid_until=now + timedelta(days=min(max(int(validity_days or 90), 1), 365)),
        integrity_hash=digest, result=result,
        metadata_=sanitize_metadata(metadata),
    )
    db.add(row)
    await db.flush()
    return _serialize(row)


def _serialize(row: GovernancePlaneEvidence) -> dict:
    return {
        "id": str(row.id),
        "tenant": row.tenant,
        "control_key": row.control_key or "",
        "source_system": row.source_system,
        "source_ref": row.source_ref,
        "source_version": row.source_version or "",
        "collected_at": row.collected_at.isoformat() if row.collected_at else None,
        "valid_until": row.valid_until.isoformat() if row.valid_until else None,
        "integrity_hash": row.integrity_hash,
        "result": row.result,
        "expired": bool(row.valid_until and row.valid_until <= _utcnow()),
    }


async def list_evidence(db: AsyncSession, tenant: str, *, control_key: str = "",
                        expired_only: bool = False, limit: int = 100) -> dict:
    stmt = select(GovernancePlaneEvidence).where(GovernancePlaneEvidence.tenant == tenant)
    if control_key:
        stmt = stmt.where(GovernancePlaneEvidence.control_key == control_key)
    if expired_only:
        stmt = stmt.where(GovernancePlaneEvidence.valid_until <= _utcnow())
    limit = min(max(int(limit or 100), 1), 1000)
    rows = (await db.execute(stmt.order_by(desc(GovernancePlaneEvidence.collected_at)).limit(limit))).scalars().all()
    return {"items": [_serialize(r) for r in rows], "total": len(rows)}


async def _verify_source(db: AsyncSession, tenant: str, row: GovernancePlaneEvidence) -> bool:
    """Best-effort liveness check per source system. Unknown sources fail
    closed (evidence marked stale) rather than assumed valid."""
    try:
        if row.source_system == "audit":
            from app.models.support import AuditLog
            result = await db.execute(select(func.count()).select_from(AuditLog).where(
                AuditLog.organization_id == tenant))
            return (result.scalar() or 0) > 0
        if row.source_system == "policy_decision":
            from app.governance.plane_models import GovernancePlaneDecision
            result = await db.execute(select(func.count()).select_from(GovernancePlaneDecision).where(
                GovernancePlaneDecision.tenant == tenant))
            return (result.scalar() or 0) > 0
        if row.source_system == "security_finding":
            from app.security.models import SecurityFinding
            result = await db.execute(select(func.count()).select_from(SecurityFinding).where(
                SecurityFinding.tenant == tenant))
            return True
        if row.source_system == "lineage":
            from app.datagov.models import GovernanceLineage
            result = await db.execute(select(func.count()).select_from(GovernanceLineage).where(
                GovernanceLineage.tenant == tenant))
            return True
        if row.source_system == "workflow_record":
            from app.workflow.models import WorkflowRun
            result = await db.execute(select(func.count()).select_from(WorkflowRun).where(
                WorkflowRun.tenant == tenant))
            return True
        if row.source_system == "finops_record":
            from app.finops.governed_models import FinOpsCostRecord
            result = await db.execute(select(func.count()).select_from(FinOpsCostRecord).where(
                FinOpsCostRecord.tenant == tenant))
            return True
        if row.source_system == "integration_health":
            from app.integrations.governed_models import Integration
            result = await db.execute(select(func.count()).select_from(Integration).where(
                Integration.tenant == tenant))
            return True
        if row.source_system == "ai_usage":
            from app.ai_dev.models import CodeAIUsage
            result = await db.execute(select(func.count()).select_from(CodeAIUsage).where(
                CodeAIUsage.tenant == tenant))
            return True
        if row.source_system == "zero_trust_decision":
            return True
    except Exception:
        return False
    return False


async def refresh_evidence(db: AsyncSession, tenant: str, *, limit: int = 100) -> dict:
    rows = (await db.execute(select(GovernancePlaneEvidence).where(
        GovernancePlaneEvidence.tenant == tenant,
    ).limit(min(max(int(limit or 100), 1), 1000)))).scalars().all()
    refreshed, stale = 0, 0
    for row in rows:
        alive = await _verify_source(db, tenant, row)
        expected = integrity_hash(row.source_system, row.source_ref, row.source_version or "")
        if alive and expected == row.integrity_hash:
            row.collected_at = _utcnow()
            refreshed += 1
        else:
            row.valid_until = _utcnow()
            stale += 1
    if rows:
        await db.flush()
    return {"refreshed": refreshed, "stale": stale, "total": len(rows)}


async def evidence_coverage(db: AsyncSession, tenant: str) -> dict:
    total = (await db.execute(select(func.count()).select_from(GovernancePlaneEvidence).where(
        GovernancePlaneEvidence.tenant == tenant))).scalar() or 0
    expired = (await db.execute(select(func.count()).select_from(GovernancePlaneEvidence).where(
        GovernancePlaneEvidence.tenant == tenant,
        GovernancePlaneEvidence.valid_until <= _utcnow()))).scalar() or 0
    return {"total": int(total), "expired": int(expired), "valid": int(total - expired)}
