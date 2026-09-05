"""Governance posture calculation — Volume 71 Commit 2.

Counts only verifiable facts: governed policies/decisions, valid
evidence rows, assessed control states, open exceptions and drift
findings. No invented percentages — ratios are computed strictly
from counted rows and reported alongside the raw counts.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.governance.plane_common import ValidationError, _utcnow
from app.governance.plane_models import (
    GovernancePlaneDecision,
    GovernancePlaneException,
    GovernancePlanePolicy,
    GovernancePlanePostureSnapshot,
)
from app.governance.plane_models_c2 import GovernancePlaneDriftFinding, GovernancePlaneEvidence


async def refresh_posture(db: AsyncSession, tenant: str, *,
                          scope_type: str = "tenant", scope_value: str = "",
                          domain: str = "general") -> dict:
    if not tenant:
        raise ValidationError("tenant required")
    total = (await db.execute(select(func.count()).select_from(GovernancePlanePolicy).where(
        GovernancePlanePolicy.tenant == tenant))).scalar() or 0
    active = (await db.execute(select(func.count()).select_from(GovernancePlanePolicy).where(
        GovernancePlanePolicy.tenant == tenant,
        GovernancePlanePolicy.status == "ACTIVE"))).scalar() or 0
    day_ago = _utcnow() - timedelta(hours=24)
    violations = (await db.execute(select(func.count()).select_from(GovernancePlaneDecision).where(
        GovernancePlaneDecision.tenant == tenant,
        GovernancePlaneDecision.decision == "DENY",
        GovernancePlaneDecision.created_at >= day_ago))).scalar() or 0
    open_exc = (await db.execute(select(func.count()).select_from(GovernancePlaneException).where(
        GovernancePlaneException.tenant == tenant,
        GovernancePlaneException.status == "APPROVED"))).scalar() or 0
    verified = (await db.execute(select(func.count()).select_from(GovernancePlaneEvidence).where(
        GovernancePlaneEvidence.tenant == tenant,
        GovernancePlaneEvidence.valid_until > _utcnow()))).scalar() or 0
    expired_ev = (await db.execute(select(func.count()).select_from(GovernancePlaneEvidence).where(
        GovernancePlaneEvidence.tenant == tenant,
        GovernancePlaneEvidence.valid_until <= _utcnow()))).scalar() or 0
    open_drift = (await db.execute(select(func.count()).select_from(GovernancePlaneDriftFinding).where(
        GovernancePlaneDriftFinding.tenant == tenant,
        GovernancePlaneDriftFinding.status == "OPEN"))).scalar() or 0

    row = GovernancePlanePostureSnapshot(
        tenant=tenant, scope_type=scope_type, scope_value=scope_value or "",
        domain=domain, total_policies=int(total), active_policies=int(active),
        violations_24h=int(violations), open_exceptions=int(open_exc),
        verified_controls=int(verified), failing_controls=int(expired_ev + open_drift),
        computed_at=_utcnow(),
        metadata_={"open_drift_findings": int(open_drift),
                   "expired_evidence": int(expired_ev)},
    )
    db.add(row)
    await db.flush()
    try:
        from app.governance.plane_common import emit_event
        await emit_event("governance_posture_refreshed",
                         {"snapshot_id": str(row.id), "scope": scope_value or scope_type}, tenant)
    except Exception:
        pass
    return {"snapshot_id": str(row.id), "total_policies": int(total),
            "active_policies": int(active), "violations_24h": int(violations),
            "open_exceptions": int(open_exc), "verified_controls": int(verified),
            "failing_controls": int(expired_ev + open_drift),
            "computed_at": row.computed_at.isoformat() if row.computed_at else None}


async def latest_posture(db: AsyncSession, tenant: str, *,
                         scope_type: str = "tenant", scope_value: str = "",
                         domain: str = "general", limit: int = 20) -> dict:
    stmt = select(GovernancePlanePostureSnapshot).where(
        GovernancePlanePostureSnapshot.tenant == tenant)
    if scope_type:
        stmt = stmt.where(GovernancePlanePostureSnapshot.scope_type == scope_type)
    if domain:
        stmt = stmt.where(GovernancePlanePostureSnapshot.domain == domain)
    limit = min(max(int(limit or 20), 1), 200)
    rows = (await db.execute(stmt.order_by(
        desc(GovernancePlanePostureSnapshot.computed_at)).limit(limit))).scalars().all()
    return {"items": [{
        "id": str(r.id), "scope_type": r.scope_type, "scope_value": r.scope_value or "",
        "domain": r.domain, "total_policies": r.total_policies,
        "active_policies": r.active_policies, "violations_24h": r.violations_24h,
        "open_exceptions": r.open_exceptions, "verified_controls": r.verified_controls,
        "failing_controls": r.failing_controls,
        "computed_at": r.computed_at.isoformat() if r.computed_at else None,
        "metadata": r.metadata_ or {},
    } for r in rows], "total": len(rows)}
