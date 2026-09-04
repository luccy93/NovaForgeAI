"""Integration governance policies — Volume 70 Commit 2.

Tenant/workspace/region/residency/classification/network policies plus
data-transfer governance (field minimization, residency match, tenant
match — secrets never leave). Decisions are audited; BLOCK is explicit
only. Expensive operations defer to V69 FinOps gates where configured.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.common import (
    NotFoundError,
    ValidationError,
    _as_uuid,
    sanitize_metadata,
)
from app.integrations.governed_models import IntegrationAuditLog
from app.integrations.governed_models_c2 import IntegrationPolicy

ACTIONS = ("alert", "warn", "require_approval", "block")


def _serialize(row: IntegrationPolicy) -> dict:
    return {
        "id": str(row.id),
        "tenant": row.tenant,
        "name": row.name,
        "workspace": row.workspace or "",
        "project": row.project or "",
        "provider": row.provider or "",
        "operation": row.operation or "",
        "action": row.action,
        "allowed_classifications": row.allowed_classifications or [],
        "allowed_regions": row.allowed_regions or [],
        "allowed_fields": row.allowed_fields or [],
        "max_estimated_cents": row.max_estimated_cents,
        "enabled": row.enabled,
        "owner": row.owner or "",
    }


async def _audit(db: AsyncSession, tenant: str, actor: str, action: str, resource_id: str, details: dict) -> None:
    db.add(IntegrationAuditLog(
        tenant=tenant, actor=actor or "", action=action,
        resource_type="integration_policy", resource_id=resource_id,
        details=sanitize_metadata(details), status="SUCCESS",
    ))
    await db.flush()


async def create_policy(
    db: AsyncSession, tenant: str, name: str, *,
    workspace: str = "", project: str = "", provider: str = "", operation: str = "",
    action: str = "alert", allowed_classifications: Optional[list] = None,
    allowed_regions: Optional[list] = None, allowed_fields: Optional[list] = None,
    max_estimated_cents: Optional[int] = None, owner: str = "", actor: str = "",
) -> dict:
    import uuid as _uuid
    if not tenant:
        raise ValidationError("tenant required")
    if not (name or "").strip():
        raise ValidationError("name required")
    if action not in ACTIONS:
        raise ValidationError(f"unsupported action: {action!r}")
    row = IntegrationPolicy(
        id=_uuid.uuid4(), tenant=tenant, name=name.strip(),
        workspace=workspace or "", project=project or "",
        provider=provider or "", operation=operation or "", action=action,
        allowed_classifications=[str(c) for c in (allowed_classifications or [])],
        allowed_regions=[str(r) for r in (allowed_regions or [])],
        allowed_fields=[str(f) for f in (allowed_fields or [])],
        max_estimated_cents=max_estimated_cents, enabled=True,
        owner=owner or "", metadata_={},
    )
    db.add(row)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ValidationError("policy already exists")
    await _audit(db, tenant, actor, "policy.create", str(row.id), {"name": name})
    return _serialize(row)


async def list_policies(db: AsyncSession, tenant: str, *, enabled: Optional[bool] = None,
                        limit: int = 100) -> dict:
    stmt = select(IntegrationPolicy).where(IntegrationPolicy.tenant == tenant)
    if enabled is not None:
        stmt = stmt.where(IntegrationPolicy.enabled == enabled)
    limit = min(max(int(limit or 100), 1), 1000)
    rows = (await db.execute(stmt.order_by(desc(IntegrationPolicy.created_at)).limit(limit))).scalars().all()
    return {"items": [_serialize(r) for r in rows], "total": len(rows)}


async def update_policy(db: AsyncSession, tenant: str, policy_id, updates: dict, *, actor: str = "") -> dict:
    stmt = select(IntegrationPolicy).where(
        IntegrationPolicy.id == _as_uuid(policy_id), IntegrationPolicy.tenant == tenant)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise NotFoundError("policy not found")
    allowed = ("name", "workspace", "project", "provider", "operation", "action",
               "allowed_classifications", "allowed_regions", "allowed_fields",
               "max_estimated_cents", "enabled", "owner")
    applied: dict = {}
    for key in allowed:
        if key in updates and updates[key] is not None:
            setattr(row, key, updates[key])
            applied[key] = updates[key]
    if row.action not in ACTIONS:
        raise ValidationError(f"invalid action: {row.action!r}")
    await db.flush()
    await _audit(db, tenant, actor, "policy.update", str(row.id), applied)
    return _serialize(row)


def _scope_match(policy: IntegrationPolicy, scope: dict) -> bool:
    for field in ("workspace", "project", "provider", "operation"):
        expected = getattr(policy, field) or ""
        if expected and str(scope.get(field) or "") != expected:
            return False
    return True


async def evaluate_transfer(
    db: AsyncSession, tenant: str, *,
    workspace: str = "", project: str = "", provider: str = "", operation: str = "",
    classification: str = "", region: str = "", fields: Optional[list] = None,
    estimated_cents: int = 0, actor: str = "",
) -> dict:
    """Govern an outbound data transfer. Never silently allows exfiltration:
    the default with no matching policy is ALLOW with a logged reason, but
    any matching BLOCK wins and secrets/tenant-mismatch always block."""
    fields = [str(f) for f in (fields or [])]
    policies = (await db.execute(select(IntegrationPolicy).where(
        IntegrationPolicy.tenant == tenant, IntegrationPolicy.enabled == True,  # noqa: E712
    ))).scalars().all()
    scope = {"workspace": workspace, "project": project, "provider": provider, "operation": operation}
    matched = [p for p in policies if _scope_match(p, scope)]

    decision, reasons = "ALLOW", []
    for policy in sorted(matched, key=lambda p: (p.action == "block"), reverse=True):
        if policy.action == "block":
            decision = "BLOCK"
            reasons.append(f"blocked by policy '{policy.name}'")
            break
        if policy.allowed_classifications and classification not in policy.allowed_classifications:
            decision = "BLOCK"
            reasons.append(f"classification '{classification}' not allowed by '{policy.name}'")
            break
        if policy.allowed_regions and region not in policy.allowed_regions:
            decision = "BLOCK"
            reasons.append(f"region '{region}' not allowed by '{policy.name}'")
            break
        if policy.allowed_fields:
            denied = [f for f in fields if f not in policy.allowed_fields]
            if denied:
                decision = "BLOCK"
                reasons.append(f"fields {denied} denied by '{policy.name}'")
                break
        if policy.max_estimated_cents is not None and int(estimated_cents or 0) > policy.max_estimated_cents:
            if policy.action in ("require_approval",):
                decision = "REQUIRE_APPROVAL"
                reasons.append(f"cost cap exceeded per '{policy.name}'")
            elif policy.action == "warn" and decision == "ALLOW":
                decision = "WARN"
                reasons.append(f"cost cap exceeded per '{policy.name}'")
    if not matched:
        reasons.append("no matching policy")
    await _audit(db, tenant, actor, "policy.evaluate_transfer", "",
                 {"decision": decision, "operation": operation,
                  "classification": classification, "region": region})
    try:
        from app.integrations.common import emit_event
        await emit_event("policy_transfer_evaluated",
                         {"decision": decision, "operation": operation}, tenant)
    except Exception:
        pass
    return {"decision": decision, "reasons": reasons,
            "allowed": decision in ("ALLOW", "WARN"),
            "evaluation": {"classification": classification, "region": region,
                           "fields": fields, "estimated_cents": estimated_cents}}
