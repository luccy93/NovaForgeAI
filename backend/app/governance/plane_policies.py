"""Central policy lifecycle and immutable versioning — Volume 71 Commit 1.

DRAFT → VALIDATING → ACTIVE → SUPERSEDED/RETIRED. ACTIVE versions are
never mutated: changes create a new version (superseding the old one).
Each version carries a checksum for tamper detection.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.governance.plane_common import (
    MAX_POLICY_BYTES,
    MAX_RULES,
    NotFoundError,
    ValidationError,
    _as_uuid,
    _ensure_aware,
    _utcnow,
    canonical_checksum,
    parse_time,
    sanitize_metadata,
)
from app.governance.plane_models import (
    GovernancePlanePolicy,
    GovernancePlanePolicyVersion,
)


def _serialize_policy(row: GovernancePlanePolicy) -> dict:
    return {
        "id": str(row.id),
        "tenant": row.tenant,
        "name": row.name,
        "domain": row.domain,
        "description": row.description or "",
        "owner": row.owner or "",
        "status": row.status,
        "active_version_id": str(row.active_version_id) if row.active_version_id else None,
    }


def _serialize_version(row: GovernancePlanePolicyVersion) -> dict:
    return {
        "id": str(row.id),
        "tenant": row.tenant,
        "policy_id": str(row.policy_id),
        "version": row.version,
        "status": row.status,
        "effective_from": row.effective_from.isoformat() if row.effective_from else None,
        "effective_until": row.effective_until.isoformat() if row.effective_until else None,
        "rules": row.rules or [],
        "default_effect": row.default_effect,
        "checksum": row.checksum,
        "reason": row.reason or "",
        "created_by": row.created_by or "",
    }


def validate_rules(rules: list) -> list:
    from app.governance.plane_engine import validate_rule

    if not isinstance(rules, list) or not rules:
        raise ValidationError("at least one rule required")
    if len(rules) > MAX_RULES:
        raise ValidationError(f"too many rules (max {MAX_RULES})")
    if len(json.dumps(rules, default=str).encode()) > MAX_POLICY_BYTES:
        raise ValidationError("policy payload too large")
    return [validate_rule(rule, index) for index, rule in enumerate(rules)]


async def create_policy(
    db: AsyncSession, tenant: str, name: str, *,
    domain: str = "general", description: str = "", owner: str = "",
    actor: str = "",
) -> dict:
    if not tenant:
        raise ValidationError("tenant required")
    name = (name or "").strip()
    if not name:
        raise ValidationError("name required")
    row = GovernancePlanePolicy(
        id=uuid.uuid4(), tenant=tenant, name=name, domain=domain or "general",
        description=description or "", owner=owner or "", status="DRAFT",
        active_version_id=None, metadata_={},
    )
    db.add(row)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ValidationError("policy already exists")
    try:
        from app.governance.plane_common import emit_event
        await emit_event("governance_policy_created",
                         {"policy_id": str(row.id), "name": name}, tenant)
    except Exception:
        pass
    return _serialize_policy(row)


async def get_policy(db: AsyncSession, tenant: str, policy_id) -> dict:
    stmt = select(GovernancePlanePolicy).where(
        GovernancePlanePolicy.id == _as_uuid(policy_id),
        GovernancePlanePolicy.tenant == tenant,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise NotFoundError("policy not found")
    return _serialize_policy(row)


async def list_policies(db: AsyncSession, tenant: str, *, status: str = "",
                        domain: str = "", limit: int = 100) -> dict:
    stmt = select(GovernancePlanePolicy).where(GovernancePlanePolicy.tenant == tenant)
    if status:
        stmt = stmt.where(GovernancePlanePolicy.status == status)
    if domain:
        stmt = stmt.where(GovernancePlanePolicy.domain == domain)
    limit = min(max(int(limit or 100), 1), 1000)
    rows = (await db.execute(stmt.order_by(desc(GovernancePlanePolicy.created_at)).limit(limit))).scalars().all()
    return {"items": [_serialize_policy(r) for r in rows], "total": len(rows)}


async def create_version(
    db: AsyncSession, tenant: str, policy_id, rules: list, *,
    default_effect: str = "deny", effective_from=None, effective_until=None,
    reason: str = "", actor: str = "",
) -> dict:
    stmt = select(GovernancePlanePolicy).where(
        GovernancePlanePolicy.id == _as_uuid(policy_id),
        GovernancePlanePolicy.tenant == tenant,
    )
    policy = (await db.execute(stmt)).scalar_one_or_none()
    if policy is None:
        raise NotFoundError("policy not found")
    if default_effect not in ("allow", "deny"):
        raise ValidationError("default_effect must be allow or deny")
    clean_rules = validate_rules(rules)
    eff_from = _ensure_aware(parse_time(effective_from) or _utcnow())
    eff_until = _ensure_aware(parse_time(effective_until)) if effective_until else None
    if eff_until and eff_until <= eff_from:
        raise ValidationError("effective_until must be after effective_from")
    from sqlalchemy import func
    max_v = (await db.execute(select(func.max(GovernancePlanePolicyVersion.version)).where(
        GovernancePlanePolicyVersion.tenant == tenant,
        GovernancePlanePolicyVersion.policy_id == policy.id,
    ))).scalar() or 0
    checksum = canonical_checksum({"rules": clean_rules, "default_effect": default_effect})
    row = GovernancePlanePolicyVersion(
        id=uuid.uuid4(), tenant=tenant, policy_id=policy.id, version=int(max_v) + 1,
        status="DRAFT", effective_from=eff_from, effective_until=eff_until,
        rules=clean_rules, default_effect=default_effect, checksum=checksum,
        reason=reason or "", created_by=actor or "", metadata_={},
    )
    db.add(row)
    await db.flush()
    return _serialize_version(row)


async def set_version_status(
    db: AsyncSession, tenant: str, version_id, status: str, *, actor: str = "", reason: str = "",
) -> dict:
    from app.governance.plane_common import VERSION_STATUSES

    if status not in VERSION_STATUSES:
        raise ValidationError(f"invalid status: {status!r}")
    stmt = select(GovernancePlanePolicyVersion).where(
        GovernancePlanePolicyVersion.id == _as_uuid(version_id),
        GovernancePlanePolicyVersion.tenant == tenant,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise NotFoundError("policy version not found")
    if row.status == "ACTIVE" and status != row.status:
        # Leaving ACTIVE is a lifecycle transition, allowed only to
        # terminal states; content fields stay untouched.
        if status not in ("SUPERSEDED", "RETIRED"):
            raise ValidationError("ACTIVE versions can only move to SUPERSEDED or RETIRED")
    if row.status == "SUPERSEDED" and status != row.status and status != "RETIRED":
        raise ValidationError("superseded versions can only move to RETIRED")
    if row.status == "RETIRED" and status != row.status:
        raise ValidationError("terminal versions are immutable")
    # Verify content integrity before activation.
    if status == "ACTIVE":
        expected = canonical_checksum({"rules": row.rules or [], "default_effect": row.default_effect})
        if expected != row.checksum:
            raise ValidationError("checksum mismatch: version content was tampered")
    row.status = status
    if reason:
        row.reason = reason
    await db.flush()
    if status == "ACTIVE":
        # New activation supersedes other ACTIVE versions of the same policy.
        others = (await db.execute(select(GovernancePlanePolicyVersion).where(
            GovernancePlanePolicyVersion.tenant == tenant,
            GovernancePlanePolicyVersion.policy_id == row.policy_id,
            GovernancePlanePolicyVersion.status == "ACTIVE",
            GovernancePlanePolicyVersion.id != row.id,
        ))).scalars().all()
        for other in others:
            other.status = "SUPERSEDED"
        policy_stmt = select(GovernancePlanePolicy).where(
            GovernancePlanePolicy.id == row.policy_id,
            GovernancePlanePolicy.tenant == tenant,
        )
        policy = (await db.execute(policy_stmt)).scalar_one_or_none()
        if policy is not None:
            policy.status = "ACTIVE"
            policy.active_version_id = row.id
        await db.flush()
    try:
        from app.governance.plane_common import emit_event
        await emit_event("governance_policy_activated" if status == "ACTIVE" else "governance_policy_updated",
                         {"policy_id": str(row.policy_id), "version": row.version, "status": status}, tenant)
    except Exception:
        pass
    return _serialize_version(row)


async def list_versions(db: AsyncSession, tenant: str, policy_id, *, limit: int = 100) -> dict:
    stmt = select(GovernancePlanePolicyVersion).where(
        GovernancePlanePolicyVersion.tenant == tenant,
        GovernancePlanePolicyVersion.policy_id == _as_uuid(policy_id),
    )
    limit = min(max(int(limit or 100), 1), 1000)
    rows = (await db.execute(stmt.order_by(desc(GovernancePlanePolicyVersion.version)).limit(limit))).scalars().all()
    return {"items": [_serialize_version(r) for r in rows], "total": len(rows)}


async def get_active_version(db: AsyncSession, tenant: str, policy_id, *, at=None) -> Optional[dict]:
    moment = _ensure_aware(parse_time(at) or _utcnow())
    stmt = (
        select(GovernancePlanePolicyVersion)
        .where(
            GovernancePlanePolicyVersion.tenant == tenant,
            GovernancePlanePolicyVersion.policy_id == _as_uuid(policy_id),
            GovernancePlanePolicyVersion.status == "ACTIVE",
            GovernancePlanePolicyVersion.effective_from <= moment,
            ((GovernancePlanePolicyVersion.effective_until.is_(None))
             | (GovernancePlanePolicyVersion.effective_until > moment)),
        )
        .order_by(desc(GovernancePlanePolicyVersion.version))
        .limit(1)
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    return _serialize_version(row) if row else None
