"""Governed policy exceptions / waivers — Volume 71 Commit 1.

Exact policy/resource scope, justification, requester/approver, bounded
windows with maximum durations, and a full audit trail. Expired
exceptions automatically stop affecting decisions (enforced at
evaluation time) and are swept to EXPIRED by workers. No permanent
bypass exists. High-risk exceptions require an approved JIT or
workflow approval before they take effect.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.governance.plane_common import (
    EXCEPTION_STATUSES,
    SCOPE_TYPES,
    NotFoundError,
    ValidationError,
    _as_uuid,
    _ensure_aware,
    _utcnow,
    parse_time,
    sanitize_metadata,
)
from app.governance.plane_models import (
    GovernancePlaneException,
    GovernancePlaneExceptionApproval,
    GovernancePlanePolicy,
)

MAX_DURATION_HOURS = 24 * 30


def _serialize(row: GovernancePlaneException) -> dict:
    return {
        "id": str(row.id),
        "tenant": row.tenant,
        "policy_id": str(row.policy_id),
        "scope_type": row.scope_type or "",
        "scope_value": row.scope_value or "",
        "justification": row.justification or "",
        "requester": row.requester or "",
        "approver": row.approver or "",
        "start_at": row.start_at.isoformat() if row.start_at else None,
        "end_at": row.end_at.isoformat() if row.end_at else None,
        "max_duration_hours": row.max_duration_hours,
        "high_risk": row.high_risk,
        "status": row.status,
    }


async def request_exception(
    db: AsyncSession, tenant: str, policy_id, *,
    scope_type: str = "", scope_value: str = "", justification: str = "",
    requester: str = "", duration_hours: int = 24, high_risk: bool = False,
) -> dict:
    if not tenant:
        raise ValidationError("tenant required")
    stmt = select(GovernancePlanePolicy).where(
        GovernancePlanePolicy.id == _as_uuid(policy_id),
        GovernancePlanePolicy.tenant == tenant,
    )
    if (await db.execute(stmt)).scalar_one_or_none() is None:
        raise NotFoundError("policy not found")
    if scope_type and scope_type not in SCOPE_TYPES:
        raise ValidationError(f"invalid scope_type: {scope_type!r}")
    if not (justification or "").strip():
        raise ValidationError("justification required")
    duration_hours = int(duration_hours or 0)
    if duration_hours < 1 or duration_hours > MAX_DURATION_HOURS:
        raise ValidationError(f"duration must be 1-{MAX_DURATION_HOURS} hours")
    now = _utcnow()
    row = GovernancePlaneException(
        id=uuid.uuid4(), tenant=tenant, policy_id=_as_uuid(policy_id),
        scope_type=scope_type or "", scope_value=scope_value or "",
        justification=justification.strip(), requester=requester or "",
        approver="", start_at=now, end_at=now + timedelta(hours=duration_hours),
        max_duration_hours=duration_hours, high_risk=bool(high_risk),
        status="PENDING", metadata_={},
    )
    db.add(row)
    await db.flush()
    try:
        from app.governance.plane_common import emit_event
        await emit_event("governance_exception_requested",
                         {"exception_id": str(row.id), "policy_id": str(row.policy_id)}, tenant)
    except Exception:
        pass
    return _serialize(row)


async def get_exception(db: AsyncSession, tenant: str, exception_id) -> dict:
    stmt = select(GovernancePlaneException).where(
        GovernancePlaneException.id == _as_uuid(exception_id),
        GovernancePlaneException.tenant == tenant,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise NotFoundError("exception not found")
    return _serialize(row)


async def list_exceptions(db: AsyncSession, tenant: str, *, status: str = "",
                          policy_id=None, limit: int = 100) -> dict:
    stmt = select(GovernancePlaneException).where(GovernancePlaneException.tenant == tenant)
    if status:
        stmt = stmt.where(GovernancePlaneException.status == status)
    if policy_id:
        stmt = stmt.where(GovernancePlaneException.policy_id == _as_uuid(policy_id))
    limit = min(max(int(limit or 100), 1), 1000)
    rows = (await db.execute(stmt.order_by(desc(GovernancePlaneException.created_at)).limit(limit))).scalars().all()
    return {"items": [_serialize(r) for r in rows], "total": len(rows)}


async def approve_exception(
    db: AsyncSession, tenant: str, exception_id, *,
    approver: str, approval_id: str = "", approval_type: str = "jit",
) -> dict:
    """Approve an exception. High-risk exceptions require a verified,
    approved/active approval record from existing JIT or workflow
    controls — the approval ID alone is never trusted."""
    stmt = select(GovernancePlaneException).where(
        GovernancePlaneException.id == _as_uuid(exception_id),
        GovernancePlaneException.tenant == tenant,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise NotFoundError("exception not found")
    if row.status != "PENDING":
        raise ValidationError(f"exception is {row.status}")
    if not approver:
        raise ValidationError("approver required")
    if row.high_risk:
        if not approval_id:
            raise ValidationError("high-risk exceptions require an approved JIT/workflow approval")
        await _verify_approval(db, tenant, approval_id, approval_type)
        db.add(GovernancePlaneExceptionApproval(
            tenant=tenant, exception_id=row.id, approval_id=approval_id,
            approval_type=approval_type, approver=approver, decision="APPROVED",
            metadata_={},
        ))
    row.status = "APPROVED"
    row.approver = approver
    await db.flush()
    try:
        from app.governance.plane_common import emit_event
        await emit_event("governance_exception_granted",
                         {"exception_id": str(row.id), "approver": approver}, tenant)
    except Exception:
        pass
    return _serialize(row)


async def _verify_approval(db: AsyncSession, tenant: str, approval_id: str, approval_type: str) -> None:
    if approval_type == "jit":
        from app.zero_trust.jit import get_access
        rec = await get_access(db, tenant, approval_id)
        if rec is None or rec.status not in ("APPROVED", "ACTIVE"):
            raise ValidationError("JIT approval is not approved/active")
        return
    if approval_type == "workflow":
        from app.workflow.approval import get_approval
        rec = await get_approval(db, tenant, approval_id)
        if rec is None or rec.status != "APPROVED":
            raise ValidationError("workflow approval is not approved")
        return
    raise ValidationError(f"unknown approval type: {approval_type!r}")


async def deny_exception(db: AsyncSession, tenant: str, exception_id, *, approver: str) -> dict:
    stmt = select(GovernancePlaneException).where(
        GovernancePlaneException.id == _as_uuid(exception_id),
        GovernancePlaneException.tenant == tenant,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise NotFoundError("exception not found")
    if row.status != "PENDING":
        raise ValidationError(f"exception is {row.status}")
    row.status = "DENIED"
    row.approver = approver or ""
    await db.flush()
    return _serialize(row)


async def revoke_exception(db: AsyncSession, tenant: str, exception_id, *, actor: str = "") -> dict:
    stmt = select(GovernancePlaneException).where(
        GovernancePlaneException.id == _as_uuid(exception_id),
        GovernancePlaneException.tenant == tenant,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise NotFoundError("exception not found")
    if row.status not in ("PENDING", "APPROVED"):
        raise ValidationError(f"exception is {row.status}")
    row.status = "REVOKED"
    await db.flush()
    return _serialize(row)


async def expire_due_exceptions(db: AsyncSession, tenant: str, *, limit: int = 500) -> dict:
    """Sweep expired APPROVED exceptions to EXPIRED. Idempotent."""
    now = _utcnow()
    rows = (await db.execute(select(GovernancePlaneException).where(
        GovernancePlaneException.tenant == tenant,
        GovernancePlaneException.status == "APPROVED",
        GovernancePlaneException.end_at <= now,
    ).limit(min(max(int(limit or 500), 1), 2000)))).scalars().all()
    for row in rows:
        row.status = "EXPIRED"
    if rows:
        await db.flush()
        try:
            from app.governance.plane_common import emit_event
            for row in rows:
                await emit_event("governance_exception_expired",
                                 {"exception_id": str(row.id)}, tenant)
        except Exception:
            pass
    return {"expired": len(rows)}
