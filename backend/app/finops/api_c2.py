"""Governed FinOps intelligence API — Volume 69 Commit 2.

Forecasts, anomalies, recommendations, model comparison, governance
policies, operation gating and chargeback/showback reports. Auth helpers
are reused from the C1 router; all queries are tenant-scoped and bounded.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.finops.api import (
    ADMIN_PERMISSION,
    READ_PERMISSION,
    _err,
    _get_db,
    _iam_check,
    _resolve_user,
    _tenant,
    _user_id,
)

router = APIRouter(prefix="/finops", tags=["FinOps"])


class PolicyIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    workspace: str = ""
    project: str = ""
    model: str = ""
    provider: str = ""
    operation: str = ""
    max_estimated_cents: Optional[int] = None
    action: str = "alert"
    owner: str = ""


class PolicyUpdateIn(BaseModel):
    name: Optional[str] = None
    workspace: Optional[str] = None
    project: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    operation: Optional[str] = None
    max_estimated_cents: Optional[int] = None
    action: Optional[str] = None
    enabled: Optional[bool] = None
    owner: Optional[str] = None


class GateIn(BaseModel):
    identity: str = ""
    operation: str = Field(..., min_length=1, max_length=128)
    estimated_cents: int = 0
    usage: Optional[dict] = None
    workspace: str = ""
    project: str = ""
    model: str = ""
    provider: str = ""
    reason: str = ""


class ReportIn(BaseModel):
    start: Optional[str] = None
    end: Optional[str] = None
    group_by: str = "workspace"


class DetectIn(BaseModel):
    lookback_days: int = 14


class ForecastIn(BaseModel):
    horizon_days: int = 30
    provider: str = ""
    model: str = ""
    workspace: str = ""
    project: str = ""
    budget_id: Optional[str] = None


@router.get("/forecast")
async def get_forecast(
    horizon_days: int = Query(30, ge=1, le=90), provider: str = "", model: str = "",
    workspace: str = "", project: str = "", budget_id: Optional[str] = None,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.finops.governed_forecasting import generate_forecast
        from app.finops.governed_cache import cache_get_tenant, cache_set_tenant
        scope = {"horizon_days": horizon_days, "provider": provider, "model": model,
                 "workspace": workspace, "project": project, "budget_id": budget_id or ""}
        cached = await cache_get_tenant(tenant, "forecast", scope)
        if cached is not None:
            return {**cached, "cached": True}
        result = await generate_forecast(
            db, tenant, horizon_days=horizon_days,
            dimensions={k: v for k, v in {"provider": provider, "model": model,
                                          "workspace": workspace, "project": project}.items() if v},
            budget_id=budget_id, actor=_user_id(current_user))
        await db.commit()
        if result.get("status") == "READY":
            await cache_set_tenant(tenant, "forecast", result, scope, ttl=600)
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/forecasts")
async def get_forecasts(
    limit: int = Query(50, ge=1, le=1000),
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.finops.governed_forecasting import list_forecasts as _list
        return await _list(db, tenant, limit=limit)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/anomalies/detect")
async def detect_anomalies(
    payload: DetectIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.finops.anomalies import detect_anomalies as _detect
        result = await _detect(db, tenant, lookback_days=payload.lookback_days, actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/anomalies")
async def get_anomalies(
    severity: str = "", status: str = "", limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.finops.anomalies import list_anomalies as _list
        return await _list(db, tenant, severity=severity, status=status, limit=limit)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/recommendations/generate")
async def generate_recommendations(
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.finops.recommendations import generate_recommendations as _generate
        result = await _generate(db, tenant, actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/recommendations")
async def get_recommendations(
    rec_type: str = "", status: str = "", limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.finops.recommendations import list_recommendations as _list
        return await _list(db, tenant, rec_type=rec_type, status=status, limit=limit)
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/models/compare")
async def compare_models(
    start: Optional[str] = None, end: Optional[str] = None, provider: str = "",
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.finops.governed_cache import cache_get_tenant, cache_set_tenant
        from app.finops.model_intelligence import compare_models as _compare
        scope = {"start": start or "", "end": end or "", "provider": provider}
        cached = await cache_get_tenant(tenant, "model-compare", scope)
        if cached is not None:
            return {**cached, "cached": True}
        result = await _compare(db, tenant, start=start, end=end, provider=provider)
        await cache_set_tenant(tenant, "model-compare", result, scope, ttl=600)
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/policies")
async def get_policies(
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.finops.governance import list_policies as _list
        return await _list(db, tenant)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/policies", status_code=201)
async def create_policy(
    payload: PolicyIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.finops.governance import create_policy as _create
        from app.finops.governed_cache import cache_invalidate_tenant
        result = await _create(db, tenant, payload.name, **{
            k: v for k, v in payload.model_dump().items() if k != "name"
        }, actor=_user_id(current_user))
        await db.commit()
        await cache_invalidate_tenant(tenant)
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.patch("/policies/{policy_id}")
async def update_policy(
    policy_id: str, payload: PolicyUpdateIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.finops.governance import update_policy as _update
        from app.finops.governed_cache import cache_invalidate_tenant
        result = await _update(db, tenant, policy_id,
                               {k: v for k, v in payload.model_dump().items() if v is not None},
                               actor=_user_id(current_user))
        await db.commit()
        await cache_invalidate_tenant(tenant)
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/gate/evaluate")
async def evaluate_gate(
    payload: GateIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.finops.governance import evaluate_operation as _evaluate
        result = await _evaluate(
            db, tenant, payload.identity or _user_id(current_user), payload.operation,
            estimated_cents=payload.estimated_cents, usage=payload.usage,
            workspace=payload.workspace, project=payload.project,
            model=payload.model, provider=payload.provider, reason=payload.reason)
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/reports/{report_type}")
async def generate_report(
    report_type: str, payload: ReportIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.finops.chargeback import generate_report as _generate
        result = await _generate(db, tenant, report_type, start=payload.start,
                                 end=payload.end, group_by=payload.group_by,
                                 actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/reports")
async def get_reports(
    report_type: str = "",
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.finops.chargeback import list_reports as _list
        return await _list(db, tenant, report_type=report_type)
    except Exception as exc:
        raise _err(exc) from exc
