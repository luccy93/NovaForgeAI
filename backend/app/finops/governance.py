"""Cost governance and expensive-operation gate — Volume 69 Commit 2.

Policies evaluate identity, tenant, workspace, operation, server-side
estimated cost, budgets and risk, then return ALLOW, WARN,
REQUIRE_APPROVAL or BLOCK. REQUIRE_APPROVAL reuses the existing Zero
Trust JIT approval flow (no parallel approval system). Client-supplied
estimates are never trusted alone: the server recomputes from pricing
and takes the maximum.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.finops.governed_common import NotFoundError, ValidationError, _as_uuid, sanitize_metadata
from app.finops.governed_models import FinOpsAuditLog
from app.finops.governed_models_c2 import FinOpsPolicy, FinOpsPolicyDecision

ACTIONS = ("alert", "warn", "require_approval", "block")
DECISIONS = ("ALLOW", "WARN", "REQUIRE_APPROVAL", "BLOCK")


def _serialize(row: FinOpsPolicy) -> dict:
    return {
        "id": str(row.id),
        "tenant": row.tenant,
        "name": row.name,
        "workspace": row.workspace or "",
        "project": row.project or "",
        "model": row.model or "",
        "provider": row.provider or "",
        "operation": row.operation or "",
        "max_estimated_cents": row.max_estimated_cents,
        "action": row.action,
        "enabled": row.enabled,
        "owner": row.owner or "",
    }


async def create_policy(
    db: AsyncSession, tenant: str, name: str, *,
    workspace: str = "", project: str = "", model: str = "", provider: str = "",
    operation: str = "", max_estimated_cents: Optional[int] = None,
    action: str = "alert", owner: str = "", actor: str = "",
) -> dict:
    if not tenant:
        raise ValidationError("tenant required")
    if not (name or "").strip():
        raise ValidationError("name required")
    if action not in ACTIONS:
        raise ValidationError(f"unsupported action: {action!r}")
    if max_estimated_cents is not None and int(max_estimated_cents) < 0:
        raise ValidationError("max_estimated_cents must be >= 0")
    row = FinOpsPolicy(
        id=uuid.uuid4(), tenant=tenant, name=name.strip(),
        workspace=workspace or "", project=project or "", model=model or "",
        provider=provider or "", operation=operation or "",
        max_estimated_cents=max_estimated_cents, action=action,
        enabled=True, owner=owner or "",
        metadata_={},
    )
    db.add(row)
    await db.flush()
    db.add(FinOpsAuditLog(
        tenant=tenant, actor=actor or "", action="policy.create",
        resource_type="policy", resource_id=str(row.id),
        details={"name": name, "action": action}, status="SUCCESS",
    ))
    await db.flush()
    return _serialize(row)


async def list_policies(db: AsyncSession, tenant: str, *, enabled: Optional[bool] = None, limit: int = 100) -> dict:
    stmt = select(FinOpsPolicy).where(FinOpsPolicy.tenant == tenant)
    if enabled is not None:
        stmt = stmt.where(FinOpsPolicy.enabled == enabled)
    limit = min(max(int(limit or 100), 1), 1000)
    rows = (await db.execute(stmt.order_by(desc(FinOpsPolicy.created_at)).limit(limit))).scalars().all()
    return {"items": [_serialize(r) for r in rows], "total": len(rows)}


async def update_policy(db: AsyncSession, tenant: str, policy_id, updates: dict, *, actor: str = "") -> dict:
    stmt = select(FinOpsPolicy).where(FinOpsPolicy.id == _as_uuid(policy_id), FinOpsPolicy.tenant == tenant)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise NotFoundError("policy not found")
    allowed = ("name", "workspace", "project", "model", "provider", "operation",
               "max_estimated_cents", "action", "enabled", "owner")
    applied: dict = {}
    for key in allowed:
        if key in updates and updates[key] is not None:
            setattr(row, key, updates[key])
            applied[key] = updates[key]
    if row.action not in ACTIONS:
        raise ValidationError(f"invalid action: {row.action!r}")
    await db.flush()
    db.add(FinOpsAuditLog(
        tenant=tenant, actor=actor or "", action="policy.update",
        resource_type="policy", resource_id=str(row.id),
        details=sanitize_metadata(applied), status="SUCCESS",
    ))
    await db.flush()
    return _serialize(row)


def _specificity(policy: FinOpsPolicy) -> int:
    return sum(1 for field in (policy.workspace, policy.project, policy.model,
                               policy.provider, policy.operation) if field)


def _server_estimate_cents(pricing: Optional[dict], usage: dict) -> Optional[int]:
    if not pricing:
        return None
    try:
        from app.finops.costing import compute_cost_cents
        amount, _, _ = compute_cost_cents(
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            requests=usage.get("requests", 1),
            pricing=pricing,
        )
        return amount
    except Exception:
        return None


async def evaluate_operation(
    db: AsyncSession, tenant: str, identity: str, operation: str, *,
    estimated_cents: int = 0, usage: Optional[dict] = None,
    workspace: str = "", project: str = "", model: str = "", provider: str = "",
    reason: str = "",
) -> dict:
    """Gate an expensive operation. Returns decision + optional JIT approval id."""
    if not tenant:
        raise ValidationError("tenant required")
    operation = (operation or "").strip()
    if not operation:
        raise ValidationError("operation required")
    usage = usage or {}

    server_estimate: Optional[int] = None
    if provider:
        try:
            from app.finops.pricing import get_effective_pricing
            pricing = await get_effective_pricing(db, tenant, provider, model=model or "")
            server_estimate = _server_estimate_cents(pricing, usage)
        except Exception:
            server_estimate = None
    client_estimate = max(int(estimated_cents or 0), 0)
    effective = max(client_estimate, server_estimate or 0)

    policies = (await db.execute(select(FinOpsPolicy).where(
        FinOpsPolicy.tenant == tenant, FinOpsPolicy.enabled == True,  # noqa: E712
    ))).scalars().all()
    matched = [p for p in policies
               if (not p.operation or p.operation == operation)
               and (not p.model or p.model == (model or ""))
               and (not p.provider or p.provider == (provider or ""))
               and (not p.workspace or p.workspace == (workspace or ""))
               and (not p.project or p.project == (project or ""))]
    matched.sort(key=_specificity, reverse=True)

    decision = "ALLOW"
    approval_id = ""
    matched_policy_id = None
    decision_reason = "no matching policy"
    for policy in matched:
        cap = policy.max_estimated_cents
        if cap is not None and effective > cap:
            matched_policy_id = policy.id
            if policy.action == "block":
                decision, decision_reason = "BLOCK", f"exceeds policy '{policy.name}' cap of {cap}c"
            elif policy.action == "require_approval":
                decision, decision_reason = "REQUIRE_APPROVAL", f"requires approval per policy '{policy.name}'"
            else:
                decision, decision_reason = "WARN", f"exceeds policy '{policy.name}' cap of {cap}c"
            break

    if decision == "REQUIRE_APPROVAL":
        try:
            from app.zero_trust.jit import request_access
            rec = await request_access(
                db, tenant, identity or "unknown", f"finops:operation:{operation}",
                operation, reason or f"FinOps gate for {operation} (~{effective}c)",
                duration_seconds=3600, scope={"estimated_cents": effective},
                privilege_level="MEDIUM", requested_by=identity or "unknown",
            )
            approval_id = str(rec.id)
        except Exception as exc:
            decision, decision_reason = "BLOCK", f"approval unavailable: {type(exc).__name__}"

    row = FinOpsPolicyDecision(
        tenant=tenant, policy_id=matched_policy_id, identity=identity or "",
        operation=operation, estimated_cents=effective, decision=decision,
        approval_id=approval_id, reason=decision_reason,
        context={"workspace": workspace, "project": project, "model": model,
                 "provider": provider, "client_estimate_cents": client_estimate,
                 "server_estimate_cents": server_estimate},
    )
    db.add(row)
    db.add(FinOpsAuditLog(
        tenant=tenant, actor=identity or "", action="policy.decide",
        resource_type="operation", resource_id=operation,
        details={"decision": decision, "estimated_cents": effective, "approval_id": approval_id},
        status="SUCCESS",
    ))
    await db.flush()
    try:
        from app.finops.governed_events import policy_decision
        await policy_decision(tenant, {"operation": operation, "decision": decision,
                                       "estimated_cents": effective, "approval_id": approval_id})
    except Exception:
        pass
    return {"decision": decision, "reason": decision_reason, "estimated_cents": effective,
            "approval_id": approval_id, "policy_id": str(matched_policy_id) if matched_policy_id else None,
            "allowed": decision in ("ALLOW", "WARN", "REQUIRE_APPROVAL")}
