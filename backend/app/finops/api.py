"""Governed FinOps API — Volume 69 Commit 1.

Tenant-scoped usage, costs, allocations, pricing, budgets and
aggregations. Authorization reuses billing:read / billing:admin through
the existing policy authorizer; explicit deny overrides are honored
(fail-closed on deny).
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db as _get_db_session

from app.finops.governed_common import ADMIN_PERMISSION, READ_PERMISSION

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/finops", tags=["FinOps"])


async def _get_db():
    from app.core.database import async_session
    async with async_session() as session:
        yield session


async def _resolve_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(_get_db_session),
):
    try:
        from app.api.auth import _get_current_user
        return await _get_current_user(authorization, db)
    except HTTPException:
        raise
    except Exception:
        class _Anon:
            id = ""
            organization_id = ""
            role = "anonymous"
        return _Anon()


def _tenant(user) -> str:
    oid = getattr(user, "organization_id", None) or getattr(user, "id", None)
    if not oid:
        raise HTTPException(status_code=403, detail="No tenant context")
    return str(oid)


def _iam_check(user, tenant: str, perm: str) -> None:
    # Same convention as app.api.auth.require_permission: superusers bypass.
    if getattr(user, "is_superuser", False):
        return
    try:
        from app.iam.policy_authorizer import policy_authorizer
        result = policy_authorizer.authorize(
            str(getattr(user, "id", "")), tenant, perm,
            context={"role": getattr(user, "role", "user")},
        )
        if isinstance(result, dict) and not result.get("allowed", True):
            raise HTTPException(status_code=403, detail="forbidden")
    except HTTPException:
        raise
    except Exception:
        pass


def _err(exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    msg = f"{type(exc).__name__}: {exc}"
    lowered = str(exc).lower()
    if "not found" in lowered:
        return HTTPException(status_code=404, detail=msg)
    if "already exists" in lowered or "duplicate" in lowered:
        return HTTPException(status_code=409, detail=msg)
    if "required" in lowered or "too large" in lowered or "must be" in lowered or "unsupported" in lowered or "sum to" in lowered:
        return HTTPException(status_code=422, detail=msg)
    return HTTPException(status_code=500, detail=msg)


def _user_id(user) -> str:
    return str(getattr(user, "id", "") or "")


# ─── Schemas ─────────────────────────────────────────────────────────────────


class CostRecordIn(BaseModel):
    usage: dict


class AllocationIn(BaseModel):
    cost_record_id: str
    splits: list
    basis: str = "direct"


class PricingIn(BaseModel):
    provider: str = Field(..., min_length=1, max_length=64)
    model: str = Field(default="", max_length=128)
    resource: str = Field(default="", max_length=128)
    unit: str = "tokens"
    input_price_cents_per_m: float = 0.0
    output_price_cents_per_m: float = 0.0
    request_price_cents: float = 0.0
    storage_price_cents: float = 0.0
    compute_price_cents: float = 0.0
    currency: str = "USD"
    effective_from: Optional[str] = None
    effective_until: Optional[str] = None
    source: str = "manual"
    reason: str = ""


class BudgetIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    amount_cents: int = Field(..., gt=0)
    scope_type: str = "tenant"
    scope_value: str = ""
    provider: str = ""
    model: str = ""
    environment: str = ""
    currency: str = "USD"
    period: str = "monthly"
    warning_threshold: float = 0.8
    hard_limit_threshold: float = 1.0
    enforcement: str = "alert"
    owner: str = ""
    approval_policy: str = "none"


class BudgetUpdateIn(BaseModel):
    name: Optional[str] = None
    amount_cents: Optional[int] = None
    warning_threshold: Optional[float] = None
    hard_limit_threshold: Optional[float] = None
    enforcement: Optional[str] = None
    enabled: Optional[bool] = None
    owner: Optional[str] = None
    approval_policy: Optional[str] = None
    status: Optional[str] = None


class AggregationRunIn(BaseModel):
    granularity: str = "day"
    start: Optional[str] = None
    end: Optional[str] = None
    dimensions: Optional[dict] = None


# ─── Usage & costs ───────────────────────────────────────────────────────────


@router.get("/usage/summary")
async def usage_summary(
    start: Optional[str] = None, end: Optional[str] = None,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.finops.costing import usage_summary as _summary
        return await _summary(db, tenant, start=start, end=end)
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/costs")
async def list_costs(
    provider: Optional[str] = None, model: Optional[str] = None,
    workspace: Optional[str] = None, project: Optional[str] = None,
    service: Optional[str] = None, environment: Optional[str] = None,
    cost_basis: Optional[str] = None, start: Optional[str] = None, end: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.finops.costing import list_costs as _list
        filters = {k: v for k, v in {
            "provider": provider, "model": model, "workspace": workspace,
            "project": project, "service": service, "environment": environment,
            "cost_basis": cost_basis, "start": start, "end": end,
        }.items() if v}
        return await _list(db, tenant, filters=filters, limit=limit, offset=offset)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/costs/record", status_code=201)
async def record_cost(
    payload: CostRecordIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.finops.costing import record_usage_cost
        result = await record_usage_cost(db, tenant, payload.usage or {}, actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


# ─── Allocations ─────────────────────────────────────────────────────────────


@router.get("/allocations")
async def get_allocations(
    cost_record_id: Optional[str] = None, limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.finops.allocation import list_allocations as _list
        return await _list(db, tenant, cost_record_id=cost_record_id, limit=limit)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/allocations", status_code=201)
async def create_allocation(
    payload: AllocationIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.finops.allocation import allocate_cost
        result = await allocate_cost(
            db, tenant, payload.cost_record_id, payload.splits,
            actor=_user_id(current_user), basis=payload.basis,
        )
        await db.commit()
        return {"items": result, "total": len(result)}
    except Exception as exc:
        raise _err(exc) from exc


# ─── Pricing ─────────────────────────────────────────────────────────────────


@router.get("/pricing")
async def get_pricing(
    provider: Optional[str] = None, model: Optional[str] = None, status: Optional[str] = None,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.finops.pricing import list_pricing_versions as _list
        return {"items": await _list(db, tenant, provider=provider or "", model=model or "", status=status or "")}
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/pricing", status_code=201)
async def create_pricing(
    payload: PricingIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.finops.pricing import create_pricing_version as _create
        data = payload.model_dump()
        data.pop("provider", None)
        result = await _create(db, tenant, payload.provider, **data, operator=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/pricing/{version_id}/deprecate")
async def deprecate_pricing(
    version_id: str,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.finops.pricing import deprecate_pricing_version as _deprecate
        result = await _deprecate(db, tenant, version_id, operator=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


# ─── Budgets ─────────────────────────────────────────────────────────────────


@router.get("/budgets")
async def get_budgets(
    status: Optional[str] = None,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.finops.budgets import list_budgets as _list
        return await _list(db, tenant, status=status or "")
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/budgets", status_code=201)
async def create_budget(
    payload: BudgetIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.finops.budgets import create_budget as _create
        result = await _create(db, tenant, payload.name, payload.amount_cents, **{
            k: v for k, v in payload.model_dump().items() if k not in ("name", "amount_cents")
        }, actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/budgets/{budget_id}")
async def get_budget(
    budget_id: str,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.finops.budgets import evaluate_budget as _evaluate
        return await _evaluate(db, tenant, budget_id, actor=_user_id(current_user))
    except Exception as exc:
        raise _err(exc) from exc


@router.patch("/budgets/{budget_id}")
async def update_budget(
    budget_id: str, payload: BudgetUpdateIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.finops.budgets import update_budget as _update
        result = await _update(db, tenant, budget_id,
                               {k: v for k, v in payload.model_dump().items() if v is not None},
                               actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/budgets/{budget_id}/evaluate")
async def evaluate_budget(
    budget_id: str,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.finops.budgets import evaluate_budget as _evaluate
        result = await _evaluate(db, tenant, budget_id, actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


# ─── Aggregations ────────────────────────────────────────────────────────────


@router.post("/aggregations/run")
async def run_aggregation(
    payload: AggregationRunIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.finops.governed_workers import execute_aggregation as _execute
        result = await _execute(
            db, tenant, payload.granularity, payload.start, payload.end,
            dimensions=payload.dimensions, actor=_user_id(current_user),
        )
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/aggregations")
async def get_aggregations(
    granularity: str = "", start: Optional[str] = None, end: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.finops.aggregation import list_aggregations as _list
        return await _list(db, tenant, granularity=granularity or "", start=start, end=end, limit=limit)
    except Exception as exc:
        raise _err(exc) from exc
