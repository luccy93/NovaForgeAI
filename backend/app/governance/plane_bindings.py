"""Scoped policy bindings with inheritance — Volume 71 Commit 1.

Scope chain: organization → tenant → workspace → resource. A binding
attaches a policy version to one scope node. Evaluation collects the
chain for the request scope (most-specific wins ties) and always
applies organization mandatory denies first — children can never
override them.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.governance.plane_common import (
    NotFoundError,
    SCOPE_TYPES,
    ValidationError,
    _as_uuid,
    sanitize_metadata,
)
from app.governance.plane_models import GovernancePlaneBinding, GovernancePlanePolicy

SCOPE_DEPTH = {"organization": 0, "tenant": 1, "workspace": 2, "resource": 3}


def _serialize(row: GovernancePlaneBinding) -> dict:
    return {
        "id": str(row.id),
        "tenant": row.tenant,
        "policy_id": str(row.policy_id),
        "version_id": str(row.version_id),
        "scope_type": row.scope_type,
        "scope_value": row.scope_value or "",
        "mandatory": row.mandatory,
        "enabled": row.enabled,
    }


async def create_binding(
    db: AsyncSession, tenant: str, policy_id, version_id, *,
    scope_type: str, scope_value: str = "", mandatory: bool = False,
    actor: str = "",
) -> dict:
    if not tenant:
        raise ValidationError("tenant required")
    if scope_type not in SCOPE_TYPES:
        raise ValidationError(f"invalid scope_type: {scope_type!r}")
    stmt = select(GovernancePlanePolicy).where(
        GovernancePlanePolicy.id == _as_uuid(policy_id),
        GovernancePlanePolicy.tenant == tenant,
    )
    policy = (await db.execute(stmt)).scalar_one_or_none()
    if policy is None:
        raise NotFoundError("policy not found")
    if mandatory and scope_type != "organization":
        raise ValidationError("mandatory bindings require organization scope")
    row = GovernancePlaneBinding(
        id=uuid.uuid4(), tenant=tenant, policy_id=policy.id,
        version_id=_as_uuid(version_id), scope_type=scope_type,
        scope_value=scope_value or "", mandatory=bool(mandatory),
        enabled=True, metadata_={},
    )
    db.add(row)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        raise ValidationError("binding already exists")
    return _serialize(row)


async def list_bindings(db: AsyncSession, tenant: str, *, policy_id=None,
                        scope_type: str = "", limit: int = 100) -> dict:
    stmt = select(GovernancePlaneBinding).where(GovernancePlaneBinding.tenant == tenant)
    if policy_id:
        stmt = stmt.where(GovernancePlaneBinding.policy_id == _as_uuid(policy_id))
    if scope_type:
        stmt = stmt.where(GovernancePlaneBinding.scope_type == scope_type)
    limit = min(max(int(limit or 100), 1), 1000)
    rows = (await db.execute(stmt.order_by(desc(GovernancePlaneBinding.created_at)).limit(limit))).scalars().all()
    return {"items": [_serialize(r) for r in rows], "total": len(rows)}


async def set_binding_enabled(db: AsyncSession, tenant: str, binding_id, enabled: bool, *, actor: str = "") -> dict:
    stmt = select(GovernancePlaneBinding).where(
        GovernancePlaneBinding.id == _as_uuid(binding_id),
        GovernancePlaneBinding.tenant == tenant,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise NotFoundError("binding not found")
    if row.mandatory and not enabled:
        raise ValidationError("mandatory bindings cannot be disabled")
    row.enabled = bool(enabled)
    await db.flush()
    return _serialize(row)


async def delete_binding(db: AsyncSession, tenant: str, binding_id, *, actor: str = "") -> dict:
    stmt = select(GovernancePlaneBinding).where(
        GovernancePlaneBinding.id == _as_uuid(binding_id),
        GovernancePlaneBinding.tenant == tenant,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise NotFoundError("binding not found")
    if row.mandatory:
        raise ValidationError("mandatory bindings cannot be deleted")
    await db.delete(row)
    await db.flush()
    return {"id": str(row.id), "deleted": True}


async def resolve_chain(db: AsyncSession, tenant: str, scope_type: str, scope_value: str) -> list[dict]:
    """Return enabled bindings along the inheritance chain, most-specific first.

    Chain membership: organization bindings always apply; tenant bindings
    apply when the request is at/below tenant scope; workspace bindings
    when the scope value matches; resource bindings on exact match.
    """
    if scope_type not in SCOPE_TYPES:
        raise ValidationError(f"invalid scope_type: {scope_type!r}")
    rows = (await db.execute(select(GovernancePlaneBinding).where(
        GovernancePlaneBinding.tenant == tenant,
        GovernancePlaneBinding.enabled == True,  # noqa: E712
    ))).scalars().all()
    depth = SCOPE_DEPTH[scope_type]
    matched: list[dict] = []
    for row in rows:
        binding_depth = SCOPE_DEPTH.get(row.scope_type, 99)
        if binding_depth > depth:
            continue
        if row.scope_type == "organization":
            applies = True
        elif row.scope_type == "tenant":
            applies = True
        elif row.scope_type == "workspace":
            applies = scope_type in ("workspace", "resource") and (not row.scope_value or row.scope_value in (scope_value, ""))
            if scope_type == "resource" and row.scope_value:
                # Resource values carry workspace prefix "ws:name" when known.
                applies = scope_value == row.scope_value or scope_value.startswith(row.scope_value + ":")
        else:  # resource
            applies = scope_type == "resource" and scope_value == row.scope_value
        if applies:
            matched.append({**_serialize(row), "depth": binding_depth})
    matched.sort(key=lambda b: b["depth"], reverse=True)
    return matched
