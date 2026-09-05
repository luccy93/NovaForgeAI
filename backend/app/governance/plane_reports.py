"""Governance reporting — Volume 71 Commit 2.

Organization/tenant/workspace posture, violations, exceptions,
evidence coverage, drift, trends and top risk areas with bounded
filtering and pagination. Persisted as report runs for audit.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Optional

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.governance.plane_common import (
    ValidationError,
    _ensure_aware,
    _utcnow,
    parse_time,
    sanitize_metadata,
)
from app.governance.plane_models import GovernancePlaneDecision, GovernancePlaneException
from app.governance.plane_models_c2 import GovernancePlaneDriftFinding, GovernancePlaneReport

REPORT_TYPES = ("posture", "violations", "compliance")


def _serialize(row: GovernancePlaneReport) -> dict:
    return {
        "id": str(row.id),
        "tenant": row.tenant,
        "report_type": row.report_type,
        "scope_type": row.scope_type or "",
        "scope_value": row.scope_value or "",
        "period_start": row.period_start.isoformat() if row.period_start else None,
        "period_end": row.period_end.isoformat() if row.period_end else None,
        "summary": row.summary or {},
        "sections": row.sections or [],
    }


async def generate_report(
    db: AsyncSession, tenant: str, report_type: str, *,
    scope_type: str = "tenant", scope_value: str = "",
    days: int = 30, actor: str = "",
) -> dict:
    if not tenant:
        raise ValidationError("tenant required")
    if report_type not in REPORT_TYPES:
        raise ValidationError(f"unsupported report type: {report_type!r}")
    days = min(max(int(days or 30), 1), 365)
    end = _utcnow()
    start = end - timedelta(days=days)
    from app.governance.plane_posture import latest_posture
    posture = await latest_posture(db, tenant, scope_type=scope_type,
                                   scope_value=scope_value, limit=30)
    latest = (posture["items"] or [{}])[0]

    violations = (await db.execute(select(GovernancePlaneDecision).where(
        GovernancePlaneDecision.tenant == tenant,
        GovernancePlaneDecision.decision == "DENY",
        GovernancePlaneDecision.created_at >= start,
    ).order_by(desc(GovernancePlaneDecision.created_at)).limit(200))).scalars().all()

    exceptions = (await db.execute(select(GovernancePlaneException).where(
        GovernancePlaneException.tenant == tenant,
        GovernancePlaneException.status.in_(("APPROVED", "PENDING")),
    ).limit(200))).scalars().all()

    drift = (await db.execute(select(GovernancePlaneDriftFinding).where(
        GovernancePlaneDriftFinding.tenant == tenant,
        GovernancePlaneDriftFinding.status == "OPEN",
    ).limit(200))).scalars().all()

    from app.governance.plane_evidence import evidence_coverage
    coverage = await evidence_coverage(db, tenant)

    by_operation: dict[str, int] = {}
    for decision in violations:
        by_operation["denied"] = by_operation.get("denied", 0) + 1
    severity_counts: dict[str, int] = {}
    for finding in drift:
        severity_counts[finding.severity] = severity_counts.get(finding.severity, 0) + 1
    top_risks = sorted(
        [{"area": f"drift:{finding.finding_type}", "severity": finding.severity,
          "resource": finding.resource_id or ""}
         for finding in drift if finding.severity in ("HIGH", "CRITICAL")] +
        [{"area": "exceptions:open", "severity": "MEDIUM",
          "resource": f"{len(exceptions)} open"}] if exceptions else [],
        key=lambda r: ({"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(r["severity"], 4)),
    )[:10]

    summary = {
        "posture": latest,
        "violations": len(violations),
        "open_exceptions": len(exceptions),
        "open_drift": len(drift),
        "evidence": coverage,
        "top_risks": top_risks,
    }
    sections = [
        {"name": "posture", "items": posture["items"][:5]},
        {"name": "violations", "items": [
            {"id": str(v.id), "operation": "", "reason": v.reason or "",
             "scope": f"{v.scope_type}:{v.scope_value or ''}"} for v in violations[:50]]},
        {"name": "exceptions", "items": [
            {"id": str(e.id), "policy_id": str(e.policy_id), "status": e.status,
             "scope": f"{e.scope_type}:{e.scope_value or ''}"} for e in exceptions[:50]]},
        {"name": "drift", "items": [
            {"id": str(d.id), "finding_type": d.finding_type, "severity": d.severity,
             "resource_id": d.resource_id or ""} for d in drift[:50]]},
    ]
    row = GovernancePlaneReport(
        id=uuid.uuid4(), tenant=tenant, report_type=report_type,
        scope_type=scope_type, scope_value=scope_value or "",
        period_start=start, period_end=end,
        summary=summary, sections=sections,
        metadata_={"generated_by": actor or ""},
    )
    db.add(row)
    await db.flush()
    return _serialize(row)


async def list_reports(db: AsyncSession, tenant: str, *, report_type: str = "",
                       limit: int = 50) -> dict:
    stmt = select(GovernancePlaneReport).where(GovernancePlaneReport.tenant == tenant)
    if report_type:
        stmt = stmt.where(GovernancePlaneReport.report_type == report_type)
    limit = min(max(int(limit or 50), 1), 200)
    rows = (await db.execute(stmt.order_by(desc(GovernancePlaneReport.created_at)).limit(limit))).scalars().all()
    return {"items": [_serialize(r) for r in rows], "total": len(rows)}


async def trends(db: AsyncSession, tenant: str, *, days: int = 30, limit: int = 90) -> dict:
    from app.governance.plane_models import GovernancePlanePostureSnapshot

    end = _utcnow()
    start = end - timedelta(days=min(max(int(days or 30), 1), 365))
    rows = (await db.execute(select(GovernancePlanePostureSnapshot).where(
        GovernancePlanePostureSnapshot.tenant == tenant,
        GovernancePlanePostureSnapshot.computed_at >= start,
    ).order_by(desc(GovernancePlanePostureSnapshot.computed_at)).limit(
        min(max(int(limit or 90), 1), 500)))).scalars().all()
    points = [{
        "computed_at": r.computed_at.isoformat() if r.computed_at else None,
        "domain": r.domain, "active_policies": r.active_policies,
        "violations_24h": r.violations_24h, "open_exceptions": r.open_exceptions,
        "verified_controls": r.verified_controls, "failing_controls": r.failing_controls,
    } for r in reversed(list(rows))]
    return {"items": points, "total": len(points)}
