"""Governed budgets and enforcement evaluation — Volume 69 Commit 1.

Budget states: ACTIVE, WARNING, EXCEEDED, SUSPENDED, CLOSED. Evaluation
sums governed cost records in the current period scoped to the budget;
threshold crossings emit one event per (budget, event, period) so retries
and repeated evaluations cannot create alert storms. Enforcement defaults
to alert; blocking or approval requirements come only from explicit
policy configured on the budget.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.finops.governed_common import (
    BUDGET_STATUSES,
    ENFORCEMENTS,
    NotFoundError,
    ValidationError,
    _ensure_aware,
    _utcnow,
    sanitize_metadata,
)
from app.finops.governed_models import FinOpsAuditLog, FinOpsBudget, FinOpsBudgetEvent, FinOpsCostRecord

PERIODS = ("daily", "weekly", "monthly")


def _serialize(row: FinOpsBudget) -> dict:
    return {
        "id": str(row.id),
        "tenant": row.tenant,
        "name": row.name,
        "scope_type": row.scope_type,
        "scope_value": row.scope_value or "",
        "provider": row.provider or "",
        "model": row.model or "",
        "environment": row.environment or "",
        "amount_cents": row.amount_cents,
        "currency": row.currency,
        "period": row.period,
        "warning_threshold": row.warning_threshold,
        "hard_limit_threshold": row.hard_limit_threshold,
        "enforcement": row.enforcement,
        "enabled": row.enabled,
        "owner": row.owner or "",
        "approval_policy": row.approval_policy,
        "status": row.status,
    }


def period_bounds(period: str, now: Optional[datetime] = None) -> tuple[datetime, datetime]:
    now = _ensure_aware(now or _utcnow())
    if period == "daily":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1)
    if period == "weekly":
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=7)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        return start, start.replace(year=start.year + 1, month=1)
    return start, start.replace(month=start.month + 1)


async def _audit(db: AsyncSession, tenant: str, actor: str, action: str, resource_id: str, details: dict) -> None:
    db.add(FinOpsAuditLog(
        tenant=tenant, actor=actor or "", action=action,
        resource_type="budget", resource_id=resource_id,
        details=sanitize_metadata(details), status="SUCCESS",
    ))
    await db.flush()


async def create_budget(
    db: AsyncSession, tenant: str, name: str, amount_cents: int, *,
    scope_type: str = "tenant", scope_value: str = "", provider: str = "",
    model: str = "", environment: str = "", currency: str = "USD",
    period: str = "monthly", warning_threshold: float = 0.8,
    hard_limit_threshold: float = 1.0, enforcement: str = "alert",
    owner: str = "", approval_policy: str = "none",
    metadata: Optional[dict] = None, actor: str = "",
) -> dict:
    if not tenant:
        raise ValidationError("tenant required")
    if not (name or "").strip():
        raise ValidationError("name required")
    if int(amount_cents) <= 0:
        raise ValidationError("amount_cents must be > 0")
    if period not in PERIODS:
        raise ValidationError(f"unsupported period: {period!r}")
    if enforcement not in ENFORCEMENTS:
        raise ValidationError(f"unsupported enforcement: {enforcement!r}")
    if not (0 < warning_threshold <= hard_limit_threshold):
        raise ValidationError("require 0 < warning_threshold <= hard_limit_threshold")
    row = FinOpsBudget(
        id=uuid.uuid4(), tenant=tenant, name=name.strip(),
        scope_type=scope_type or "tenant", scope_value=scope_value or "",
        provider=provider or "", model=model or "", environment=environment or "",
        amount_cents=int(amount_cents), currency=(currency or "USD").upper(),
        period=period, warning_threshold=float(warning_threshold),
        hard_limit_threshold=float(hard_limit_threshold), enforcement=enforcement,
        enabled=True, owner=owner or "", approval_policy=approval_policy or "none",
        status="ACTIVE", metadata_=sanitize_metadata(metadata),
    )
    db.add(row)
    await db.flush()
    await _audit(db, tenant, actor, "budget.create", str(row.id), {"name": name, "amount_cents": amount_cents})
    return _serialize(row)


async def get_budget(db: AsyncSession, tenant: str, budget_id) -> dict:
    from app.finops.governed_common import _as_uuid
    stmt = select(FinOpsBudget).where(FinOpsBudget.id == _as_uuid(budget_id), FinOpsBudget.tenant == tenant)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise NotFoundError("budget not found")
    return _serialize(row)


async def list_budgets(db: AsyncSession, tenant: str, *, status: str = "", limit: int = 100) -> dict:
    stmt = select(FinOpsBudget).where(FinOpsBudget.tenant == tenant)
    if status:
        stmt = stmt.where(FinOpsBudget.status == status)
    limit = min(max(int(limit or 100), 1), 1000)
    rows = (await db.execute(stmt.order_by(desc(FinOpsBudget.created_at)).limit(limit))).scalars().all()
    return {"items": [_serialize(r) for r in rows], "total": len(rows)}


async def update_budget(db: AsyncSession, tenant: str, budget_id, updates: dict, *, actor: str = "") -> dict:
    from app.finops.governed_common import _as_uuid
    stmt = select(FinOpsBudget).where(FinOpsBudget.id == _as_uuid(budget_id), FinOpsBudget.tenant == tenant)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise NotFoundError("budget not found")
    allowed = ("name", "amount_cents", "warning_threshold", "hard_limit_threshold",
               "enforcement", "enabled", "owner", "approval_policy", "status",
               "provider", "model", "environment", "scope_type", "scope_value")
    applied: dict = {}
    for key in allowed:
        if key in updates and updates[key] is not None:
            setattr(row, key, updates[key])
            applied[key] = updates[key]
    if row.status not in BUDGET_STATUSES:
        raise ValidationError(f"invalid status: {row.status!r}")
    if row.enforcement not in ENFORCEMENTS:
        raise ValidationError(f"invalid enforcement: {row.enforcement!r}")
    await db.flush()
    await _audit(db, tenant, actor, "budget.update", str(row.id), applied)
    return _serialize(row)


def _scope_match(row: FinOpsBudget):
    clauses = []
    if row.scope_type == "provider" and row.scope_value:
        clauses.append(FinOpsCostRecord.provider == row.scope_value)
    elif row.scope_type == "model" and row.scope_value:
        clauses.append(FinOpsCostRecord.model == row.scope_value)
    elif row.scope_type == "workspace" and row.scope_value:
        clauses.append(FinOpsCostRecord.workspace == row.scope_value)
    elif row.scope_type == "project" and row.scope_value:
        clauses.append(FinOpsCostRecord.project == row.scope_value)
    elif row.scope_type == "service" and row.scope_value:
        clauses.append(FinOpsCostRecord.service == row.scope_value)
    elif row.scope_type == "environment" and row.scope_value:
        clauses.append(FinOpsCostRecord.environment == row.scope_value)
    if row.provider:
        clauses.append(FinOpsCostRecord.provider == row.provider)
    if row.model:
        clauses.append(FinOpsCostRecord.model == row.model)
    if row.environment:
        clauses.append(FinOpsCostRecord.environment == row.environment)
    return clauses


async def evaluate_budget(db: AsyncSession, tenant: str, budget_id, *, actor: str = "") -> dict:
    from app.finops.governed_common import _as_uuid
    stmt = select(FinOpsBudget).where(FinOpsBudget.id == _as_uuid(budget_id), FinOpsBudget.tenant == tenant)
    budget = (await db.execute(stmt)).scalar_one_or_none()
    if budget is None:
        raise NotFoundError("budget not found")
    if budget.status in ("SUSPENDED", "CLOSED") or not budget.enabled:
        return {**_serialize(budget), "spend_cents": 0, "utilization": 0.0, "evaluation": "skipped"}

    start, end = period_bounds(budget.period)
    q = select(func.coalesce(func.sum(FinOpsCostRecord.amount_cents), 0)).where(
        FinOpsCostRecord.tenant == tenant,
        FinOpsCostRecord.occurred_at >= start,
        FinOpsCostRecord.occurred_at < end,
        *_scope_match(budget),
    )
    spend = int((await db.execute(q)).scalar() or 0)
    utilization = (spend / budget.amount_cents) if budget.amount_cents else 0.0

    new_status = "ACTIVE"
    crossed: Optional[tuple[str, float]] = None
    if utilization >= budget.hard_limit_threshold:
        new_status = "EXCEEDED"
        crossed = ("exceeded", budget.hard_limit_threshold)
    elif utilization >= budget.warning_threshold:
        new_status = "WARNING"
        crossed = ("warning", budget.warning_threshold)

    if crossed:
        event_type, threshold = crossed
        dup_stmt = select(FinOpsBudgetEvent).where(
            FinOpsBudgetEvent.tenant == tenant,
            FinOpsBudgetEvent.budget_id == budget.id,
            FinOpsBudgetEvent.event_type == event_type,
            FinOpsBudgetEvent.period_start == start,
        )
        if (await db.execute(dup_stmt)).scalar_one_or_none() is None:
            db.add(FinOpsBudgetEvent(
                tenant=tenant, budget_id=budget.id, event_type=event_type,
                threshold=threshold, spend_cents=spend, period_start=start,
                details={"utilization": round(utilization, 4), "enforcement": budget.enforcement},
            ))
            await db.flush()
            try:
                from app.finops.governed_events import budget_exceeded, budget_warning
                if event_type == "exceeded":
                    await budget_exceeded(tenant, str(budget.id), spend, threshold)
                else:
                    await budget_warning(tenant, str(budget.id), spend, threshold)
            except Exception:
                pass

    if budget.status not in ("SUSPENDED", "CLOSED") and new_status != budget.status:
        budget.status = new_status
        await db.flush()
    await _audit(db, tenant, actor, "budget.evaluate", str(budget.id),
                 {"spend_cents": spend, "utilization": round(utilization, 4), "status": budget.status})
    return {**_serialize(budget), "spend_cents": spend, "utilization": round(utilization, 4),
            "period_start": start.isoformat(), "period_end": end.isoformat()}
