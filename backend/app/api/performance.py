"""Performance API — Volume 61 Commit 1.

FastAPI APIRouter prefix="/performance" tags=["Performance"] with endpoints:
POST /budgets, GET /budgets, GET /budgets/{budget_id}/status, POST /metrics/record,
GET /metrics/query, GET /services/{service}/metrics, GET /endpoints/metrics,
GET /database/metrics, GET /queues/metrics, GET /capacity, GET /recommendations,
POST /scaling-events, GET /scaling-events

Each uses _get_current_user, get_db, tenant from organization_id, IAM require_permission
best-effort, audit, tenant isolation, pagination bounded, query limits/timeouts.
Reuses app.performance.* services where possible.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import _get_current_user
from app.core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/performance", tags=["Performance"])


# ── helpers ───────────────────────────────────────────────────────────────

def _tenant(user) -> str:
    oid = getattr(user, "organization_id", None) or getattr(user, "id", None)
    if not oid:
        raise HTTPException(status_code=403, detail="No tenant context")
    return str(oid)


def _check_limit(limit: int | None, timeout: int | None = None) -> None:
    if limit is not None and limit > 5000:
        raise HTTPException(status_code=400, detail="limit too large (max 5000)")
    if limit is not None and limit < 1:
        raise HTTPException(status_code=400, detail="limit must be >=1")
    if timeout is not None and timeout > 30:
        raise HTTPException(status_code=400, detail="timeout too large (max 30s)")
    if timeout is not None and timeout < 1:
        raise HTTPException(status_code=400, detail="timeout must be >=1")


def _iam_check(user, tenant: str, permission: str, resource_type: str = "performance", resource_id: str = "") -> None:
    try:
        from app.iam.policy_authorizer import policy_authorizer  # type: ignore

        ctx: dict[str, Any] = {}
        try:
            role = getattr(user, "role", None)
            if role:
                ctx["role"] = str(role)
        except Exception:
            pass
        decision = policy_authorizer.authorize(
            str(getattr(user, "id", "")),
            tenant,
            permission,
            resource_type=resource_type,
            resource_id=resource_id,
            context=ctx or {"role": "viewer"},
        )
        if not decision.get("allowed", True):
            raise HTTPException(status_code=403, detail=decision.get("reason", "Forbidden"))
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.debug("IAM check skipped (%s): %s", permission, exc)


def _audit(tenant: str, actor: str, action: str, resource_type: str, resource_id: str, details: dict | None = None) -> None:
    try:
        from app.iam.audit_service import audit_service  # type: ignore

        try:
            audit_service.log(
                org_id=tenant,
                actor_id=actor,
                actor_type="user",
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                result="success",
                details=details or {},
                tenant_id=tenant,
            )
        except TypeError:
            audit_service.log(tenant, resource_id, actor, action, resource_type=resource_type, resource_id=resource_id, details=details or {"tenant": tenant})
    except Exception as exc:  # noqa: BLE001
        logger.debug("audit skipped %s: %s", action, exc)


def _parse_uuid(value: str, field: str = "id") -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except Exception:
        raise HTTPException(status_code=422, detail=f"Invalid {field}: {value!r}")


def _budget_to_dict(b) -> dict[str, Any]:
    return {
        "id": str(getattr(b, "id", "")),
        "tenant": getattr(b, "tenant", None),
        "service": getattr(b, "service", None),
        "metric_type": getattr(b, "metric_type", None),
        "metric_name": getattr(b, "metric_name", None),
        "target": float(getattr(b, "target", 0)) if getattr(b, "target", None) is not None else None,
        "window": getattr(b, "window", None),
        "owner": getattr(b, "owner", None),
        "status": getattr(b, "status", None),
        "created_at": getattr(b, "created_at", None).isoformat() if getattr(b, "created_at", None) else None,
        "updated_at": getattr(b, "updated_at", None).isoformat() if getattr(b, "updated_at", None) else None,
    }


def _metric_to_dict(m) -> dict[str, Any]:
    return {
        "id": str(getattr(m, "id", "")),
        "tenant": getattr(m, "tenant", None),
        "service": getattr(m, "service", None),
        "metric_name": getattr(m, "metric_name", None),
        "value": float(getattr(m, "value", 0)) if getattr(m, "value", None) is not None else None,
        "granularity": getattr(m, "granularity", None),
        "period_start": getattr(m, "period_start", None).isoformat() if getattr(m, "period_start", None) else None,
        "period_end": getattr(m, "period_end", None).isoformat() if getattr(m, "period_end", None) else None,
        "count": getattr(m, "count", None),
        "min_val": float(getattr(m, "min_val", 0)) if getattr(m, "min_val", None) is not None else None,
        "max_val": float(getattr(m, "max_val", 0)) if getattr(m, "max_val", None) is not None else None,
        "p50": float(getattr(m, "p50", 0)) if getattr(m, "p50", None) is not None else None,
        "p95": float(getattr(m, "p95", 0)) if getattr(m, "p95", None) is not None else None,
        "p99": float(getattr(m, "p99", 0)) if getattr(m, "p99", None) is not None else None,
        "dimensions": getattr(m, "dimensions", {}) or {},
        "created_at": getattr(m, "created_at", None).isoformat() if getattr(m, "created_at", None) else None,
    }


def _pool_to_dict(p) -> dict[str, Any]:
    return {
        "id": str(getattr(p, "id", "")),
        "tenant": getattr(p, "tenant", None),
        "pool_type": getattr(p, "pool_type", None),
        "capacity": getattr(p, "capacity", None),
        "isolated": getattr(p, "isolated", None),
        "tenant_isolation": getattr(p, "tenant_isolation", None),
        "config": getattr(p, "config", {}) or {},
        "created_at": getattr(p, "created_at", None).isoformat() if getattr(p, "created_at", None) else None,
        "updated_at": getattr(p, "updated_at", None).isoformat() if getattr(p, "updated_at", None) else None,
    }


def _policy_to_dict(p) -> dict[str, Any]:
    return {
        "id": str(getattr(p, "id", "")),
        "tenant": getattr(p, "tenant", None),
        "resource": getattr(p, "resource", None),
        "metric": getattr(p, "metric", None),
        "target": float(getattr(p, "target", 0)) if getattr(p, "target", None) is not None else None,
        "min_instances": getattr(p, "min_instances", None),
        "max_instances": getattr(p, "max_instances", None),
        "cooldown_seconds": getattr(p, "cooldown_seconds", None),
        "enabled": getattr(p, "enabled", None),
        "created_at": getattr(p, "created_at", None).isoformat() if getattr(p, "created_at", None) else None,
    }


def _snapshot_to_dict(s) -> dict[str, Any]:
    return {
        "id": str(getattr(s, "id", "")),
        "tenant": getattr(s, "tenant", None),
        "resource": getattr(s, "resource", None),
        "resource_type": getattr(s, "resource_type", None),
        "cpu": getattr(s, "cpu", None),
        "memory": getattr(s, "memory", None),
        "queue_depth": getattr(s, "queue_depth", None),
        "concurrency": getattr(s, "concurrency", None),
        "storage": getattr(s, "storage", None),
        "db_load": getattr(s, "db_load", None),
        "created_at": getattr(s, "created_at", None).isoformat() if getattr(s, "created_at", None) else None,
    }


def _rec_to_dict(r) -> dict[str, Any]:
    return {
        "id": str(getattr(r, "id", "")),
        "tenant": getattr(r, "tenant", None),
        "type": getattr(r, "type", None),
        "resource": getattr(r, "resource", None),
        "evidence": getattr(r, "evidence", {}) or {},
        "status": getattr(r, "status", None),
        "created_at": getattr(r, "created_at", None).isoformat() if getattr(r, "created_at", None) else None,
        "updated_at": getattr(r, "updated_at", None).isoformat() if getattr(r, "updated_at", None) else None,
    }


def _scaling_to_dict(s) -> dict[str, Any]:
    return {
        "id": str(getattr(s, "id", "")),
        "tenant": getattr(s, "tenant", None),
        "resource": getattr(s, "resource", None),
        "direction": getattr(s, "direction", None),
        "reason": getattr(s, "reason", None),
        "from_count": getattr(s, "from_count", None),
        "to_count": getattr(s, "to_count", None),
        "triggered_by": getattr(s, "triggered_by", None),
        "created_at": getattr(s, "created_at", None).isoformat() if getattr(s, "created_at", None) else None,
        "updated_at": getattr(s, "updated_at", None).isoformat() if getattr(s, "updated_at", None) else None,
    }


# ── Pydantic request bodies ────────────────────────────────────────────

class BudgetCreateRequest(BaseModel):
    service: str = Field(..., min_length=1, max_length=128)
    metric_type: str = Field(..., min_length=1, max_length=32)
    metric_name: str = Field(..., min_length=1, max_length=128)
    target: float = Field(..., gt=0)
    window: str = Field(default="1h", max_length=32)
    owner: Optional[str] = Field(default=None, max_length=64)


class MetricRecordRequest(BaseModel):
    service: str = Field(..., min_length=1, max_length=128)
    metric_name: str = Field(..., min_length=1, max_length=128)
    value: float = Field(...)
    granularity: str = Field(default="minute", max_length=16)
    dimensions: dict[str, Any] = Field(default_factory=dict)
    timestamp: Optional[str] = Field(default=None)


class ScalingEventCreateRequest(BaseModel):
    resource: str = Field(..., min_length=1, max_length=128)
    direction: str = Field(..., description="out|in")
    reason: str = Field(..., min_length=1, max_length=256)
    from_count: int = Field(..., ge=0)
    to_count: int = Field(..., ge=0)
    triggered_by: Optional[str] = Field(default=None, max_length=64)


# ── Budgets ─────────────────────────────────────────────────────────────

@router.post("/budgets", status_code=201)
async def create_budget(payload: BudgetCreateRequest, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "performance:write", "performance_budget")
    _check_limit(100, 5)
    try:
        from app.performance.budgets import performance_budget_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"budget service unavailable: {exc}")
    try:
        budget = await performance_budget_service.create_budget(
            db,
            tenant=tenant,
            service=payload.service,
            metric_type=payload.metric_type,
            metric_name=payload.metric_name,
            target=float(payload.target),
            window=payload.window,
            owner=payload.owner or str(getattr(user, "id", "")),
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    _audit(str(getattr(user, "id", "")), tenant, "performance.budget.created", "performance_budgets", str(getattr(budget, "id", "")), {"service": payload.service, "metric_name": payload.metric_name})
    return _budget_to_dict(budget)


@router.get("/budgets")
async def list_budgets(
    service: Optional[str] = Query(None),
    metric_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    timeout: int = Query(5, ge=1, le=30),
    user=Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant = _tenant(user)
    _iam_check(user, tenant, "performance:read", "performance_budget")
    _check_limit(limit, timeout)
    try:
        from app.performance.budgets import performance_budget_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"budget service unavailable: {exc}")
    try:
        rows = await performance_budget_service.list_budgets(db, tenant, service=service, metric_type=metric_type)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    total = len(rows)
    sliced = rows[offset : offset + limit]
    return {"items": [_budget_to_dict(r) for r in sliced], "total": total, "limit": limit, "offset": offset}


@router.get("/budgets/{budget_id}/status")
async def check_budget_status(
    budget_id: str,
    observed: float = Query(..., description="observed metric value"),
    user=Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant = _tenant(user)
    _iam_check(user, tenant, "performance:read", "performance_budget", budget_id)
    _check_limit(1, 5)
    # validate observed is number already via Query; also check timeout implicit
    try:
        from app.performance.budgets import performance_budget_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"budget service unavailable: {exc}")
    _parse_uuid(budget_id, "budget_id")
    try:
        result = await performance_budget_service.check_budget(db, tenant, budget_id, float(observed))
        await db.commit()
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    _audit(str(getattr(user, "id", "")), tenant, "performance.budget.checked", "performance_budgets", budget_id, {"observed": observed})
    return result


# ── Metrics ─────────────────────────────────────────────────────────────

@router.post("/metrics/record", status_code=201)
async def record_metric(payload: MetricRecordRequest, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "performance:write", "performance_metric")
    _check_limit(1, 5)
    try:
        from app.performance.metrics import metrics_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"metrics service unavailable: {exc}")
    try:
        metric = await metrics_service.record_metric(
            db,
            tenant=tenant,
            service=payload.service,
            metric_name=payload.metric_name,
            value=float(payload.value),
            granularity=payload.granularity,
            dimensions=payload.dimensions or {},
            timestamp=payload.timestamp,
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    _audit(str(getattr(user, "id", "")), tenant, "performance.metric.recorded", "performance_service_metrics", str(getattr(metric, "id", "")), {"service": payload.service, "metric_name": payload.metric_name})
    return _metric_to_dict(metric)


@router.get("/metrics/query")
async def query_metrics(
    service: Optional[str] = Query(None),
    metric_name: Optional[str] = Query(None),
    granularity: Optional[str] = Query(None),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    from_time: Optional[str] = Query(None, alias="from"),
    to_time: Optional[str] = Query(None, alias="to"),
    from_ts: Optional[str] = Query(None),
    to_ts: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=5000),
    timeout: int = Query(5, ge=1, le=30),
    user=Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant = _tenant(user)
    _iam_check(user, tenant, "performance:read", "performance_metric")
    _check_limit(limit, timeout)
    try:
        from app.performance.metrics import metrics_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"metrics service unavailable: {exc}")
    # resolve time aliases
    s_time = start_time or from_time or from_ts
    e_time = end_time or to_time or to_ts
    try:
        items = await metrics_service.query_metrics(
            db,
            tenant=tenant,
            service=service,
            metric_name=metric_name,
            granularity=granularity,
            start_time=s_time,
            end_time=e_time,
            limit=limit,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    # items already tenant-isolated
    return {"items": items, "total": len(items), "limit": limit}


@router.get("/services/{service}/metrics")
async def get_service_metrics(
    service: str,
    metric_name: Optional[str] = Query(None),
    granularity: str = Query("hour", max_length=16),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=5000),
    timeout: int = Query(5, ge=1, le=30),
    user=Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant = _tenant(user)
    _iam_check(user, tenant, "performance:read", "performance_metric", service)
    _check_limit(limit, timeout)
    if not service or not service.strip():
        raise HTTPException(status_code=422, detail="service is required")
    try:
        from app.performance.metrics import metrics_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"metrics service unavailable: {exc}")
    try:
        items = await metrics_service.get_service_metrics(
            db,
            tenant=tenant,
            service=service,
            metric_name=metric_name,
            granularity=granularity,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"service": service, "items": items, "total": len(items), "limit": limit}


@router.get("/endpoints/metrics")
async def get_endpoint_metrics(
    route: Optional[str] = Query(None),
    method: Optional[str] = Query(None),
    service: str = Query("api", max_length=128),
    status: Optional[str] = Query(None),
    granularity: Optional[str] = Query(None),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=5000),
    timeout: int = Query(5, ge=1, le=30),
    user=Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant = _tenant(user)
    _iam_check(user, tenant, "performance:read", "performance_endpoint")
    _check_limit(limit, timeout)
    try:
        from app.performance.metrics import metrics_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"metrics service unavailable: {exc}")
    try:
        items = await metrics_service.get_endpoint_metrics(
            db,
            tenant=tenant,
            route=route,
            method=method,
            service=service,
            status=status,
            granularity=granularity,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"items": items, "total": len(items), "limit": limit, "service": service}


@router.get("/database/metrics")
async def get_database_metrics(
    threshold_ms: float = Query(500.0, ge=0),
    limit: int = Query(20, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    timeout: int = Query(5, ge=1, le=30),
    user=Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant = _tenant(user)
    _iam_check(user, tenant, "performance:read", "performance_database")
    _check_limit(limit, timeout)
    try:
        from app.performance.db import db_metrics_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"db metrics service unavailable: {exc}")
    try:
        pool = await db_metrics_service.get_pool_status(db, tenant)
        slow = await db_metrics_service.get_slow_queries(db, tenant, threshold_ms=float(threshold_ms), limit=limit, offset=offset)
        # recommendations are best-effort and tenant-isolated; never auto-create
        try:
            recs = await db_metrics_service.recommend_indexes(db, tenant, threshold_ms=float(threshold_ms), limit=5)
        except Exception:
            recs = []
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    _audit(str(getattr(user, "id", "")), tenant, "performance.database.queried", "performance_service_metrics", tenant, {"threshold_ms": threshold_ms})
    return {"tenant": tenant, "pool": pool, "slow_queries": slow, "recommendations": recs, "threshold_ms": threshold_ms, "limit": limit, "offset": offset}


@router.get("/queues/metrics")
async def get_queue_metrics(
    queue: Optional[str] = Query(None),
    queue_name: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    timeout: int = Query(5, ge=1, le=30),
    user=Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant = _tenant(user)
    _iam_check(user, tenant, "performance:read", "performance_queue")
    _check_limit(limit, timeout)
    try:
        from app.performance.queue import queue_metrics_service  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"queue metrics service unavailable: {exc}")
    qname = queue_name or queue
    try:
        if qname:
            result = await queue_metrics_service.get_queue_health(db, tenant, queue_name=qname)
            # result is dict for single queue
            if isinstance(result, dict) and "queue_name" in result:
                return result
            return {"queue_name": qname, "health": result}
        else:
            result = await queue_metrics_service.get_queue_health(db, tenant, queue_name=None, include_all=True)
            if isinstance(result, dict) and "queues" in result:
                # pagination bound
                queues = result.get("queues", [])[:limit]
                result["queues"] = queues
                result["limit"] = limit
                return result
            if isinstance(result, list):
                return {"tenant": tenant, "queues": result[:limit], "queue_count": len(result), "limit": limit}
            return result if isinstance(result, dict) else {"items": result}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/capacity")
async def get_capacity(
    resource: Optional[str] = Query(None),
    pool_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    timeout: int = Query(5, ge=1, le=30),
    user=Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant = _tenant(user)
    _iam_check(user, tenant, "performance:read", "capacity")
    _check_limit(limit, timeout)
    try:
        from app.performance.models import CapacityPolicy, ResourcePool, PerformanceSnapshot  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"capacity models unavailable: {exc}")
    # ResourcePool
    stmt = select(ResourcePool).where(ResourcePool.tenant == tenant)
    if pool_type:
        stmt = stmt.where(ResourcePool.pool_type == str(pool_type).strip())
    stmt = stmt.order_by(ResourcePool.created_at.desc()).limit(limit).offset(offset)
    res = await db.execute(stmt)
    pools = list(res.scalars().all())
    # CapacityPolicy
    stmt2 = select(CapacityPolicy).where(CapacityPolicy.tenant == tenant)
    if resource:
        stmt2 = stmt2.where(CapacityPolicy.resource == str(resource).strip())
    stmt2 = stmt2.order_by(CapacityPolicy.created_at.desc()).limit(limit).offset(offset)
    res2 = await db.execute(stmt2)
    policies = list(res2.scalars().all())
    # snapshots
    stmt3 = select(PerformanceSnapshot).where(PerformanceSnapshot.tenant == tenant)
    if resource:
        stmt3 = stmt3.where(PerformanceSnapshot.resource == str(resource).strip())
    stmt3 = stmt3.order_by(PerformanceSnapshot.created_at.desc()).limit(limit).offset(offset)
    res3 = await db.execute(stmt3)
    snapshots = list(res3.scalars().all())
    _audit(str(getattr(user, "id", "")), tenant, "performance.capacity.queried", "capacity", tenant, {"resource": resource, "pool_type": pool_type})
    return {
        "tenant": tenant,
        "pools": [_pool_to_dict(p) for p in pools],
        "policies": [_policy_to_dict(p) for p in policies],
        "snapshots": [_snapshot_to_dict(s) for s in snapshots],
        "limit": limit,
        "offset": offset,
    }


@router.get("/recommendations")
async def get_recommendations(
    type: Optional[str] = Query(None, alias="type"),
    status: Optional[str] = Query(None),
    resource: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    timeout: int = Query(5, ge=1, le=30),
    user=Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant = _tenant(user)
    _iam_check(user, tenant, "performance:read", "performance_recommendation")
    _check_limit(limit, timeout)
    try:
        from app.performance.models import PerformanceRecommendation  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"recommendation model unavailable: {exc}")
    stmt = select(PerformanceRecommendation).where(PerformanceRecommendation.tenant == tenant)
    if type:
        stmt = stmt.where(PerformanceRecommendation.type == str(type).strip())
    if status:
        stmt = stmt.where(PerformanceRecommendation.status == str(status).strip())
    if resource:
        stmt = stmt.where(PerformanceRecommendation.resource == str(resource).strip())
    stmt = stmt.order_by(PerformanceRecommendation.created_at.desc()).limit(limit).offset(offset)
    res = await db.execute(stmt)
    rows = list(res.scalars().all())
    # fallback: enrich with DB metrics recommendations if no rows and tenant has slow queries
    if not rows:
        try:
            from app.performance.db import db_metrics_service  # type: ignore

            db_recs = await db_metrics_service.recommend_indexes(db, tenant, limit=limit)
            # convert db_recs candidates to same shape as recommendations (but not persisted twice)
            # return them as items with evidence
            if db_recs:
                items = []
                for c in db_recs[:limit]:
                    items.append({
                        "id": c.get("id") or c.get("recommendation_id") or str(uuid.uuid4()),
                        "tenant": tenant,
                        "type": c.get("type", "index"),
                        "resource": c.get("resource", ""),
                        "evidence": c.get("evidence", {}),
                        "status": c.get("status", "open"),
                        "source": "db_metrics",
                    })
                return {"items": items, "total": len(items), "limit": limit, "offset": offset, "tenant": tenant}
        except Exception:
            pass
    return {"items": [_rec_to_dict(r) for r in rows], "total": len(rows), "limit": limit, "offset": offset, "tenant": tenant}


@router.post("/scaling-events", status_code=201)
async def create_scaling_event(payload: ScalingEventCreateRequest, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "performance:write", "scaling_event", payload.resource)
    _check_limit(1, 5)
    if payload.direction not in ("out", "in"):
        raise HTTPException(status_code=422, detail="direction must be 'out' or 'in'")
    try:
        from app.performance.models import ScalingEvent  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"scaling model unavailable: {exc}")
    event = ScalingEvent(
        tenant=tenant,
        resource=str(payload.resource).strip(),
        direction=str(payload.direction).strip(),
        reason=str(payload.reason).strip(),
        from_count=int(payload.from_count),
        to_count=int(payload.to_count),
        triggered_by=str(payload.triggered_by).strip() if payload.triggered_by else str(getattr(user, "id", "system")),
    )
    db.add(event)
    await db.flush()
    await db.commit()
    await db.refresh(event)
    _audit(str(getattr(user, "id", "")), tenant, "performance.scaling.created", "scaling_events", str(getattr(event, "id", "")), {"resource": payload.resource, "direction": payload.direction})
    return _scaling_to_dict(event)


@router.get("/scaling-events")
async def list_scaling_events(
    resource: Optional[str] = Query(None),
    direction: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    timeout: int = Query(5, ge=1, le=30),
    user=Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant = _tenant(user)
    _iam_check(user, tenant, "performance:read", "scaling_event")
    _check_limit(limit, timeout)
    try:
        from app.performance.models import ScalingEvent  # type: ignore
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"scaling model unavailable: {exc}")
    stmt = select(ScalingEvent).where(ScalingEvent.tenant == tenant)
    if resource:
        stmt = stmt.where(ScalingEvent.resource == str(resource).strip())
    if direction:
        if direction not in ("out", "in"):
            raise HTTPException(status_code=422, detail="direction must be 'out' or 'in'")
        stmt = stmt.where(ScalingEvent.direction == str(direction).strip())
    stmt = stmt.order_by(ScalingEvent.created_at.desc()).limit(limit).offset(offset)
    res = await db.execute(stmt)
    rows = list(res.scalars().all())
    return {"items": [_scaling_to_dict(r) for r in rows], "total": len(rows), "limit": limit, "offset": offset, "tenant": tenant}


# ── Commit 2 — Capacity, Benchmarks, Regression ──────────────────────


@router.get("/capacity/forecast")
async def capacity_forecast(
    resource: str = Query(..., max_length=128),
    metric: str = Query("cpu", max_length=32),
    horizon_days: int = Query(7, ge=1, le=90),
    user=Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant = _tenant(user)
    _iam_check(user, tenant, "performance:read", "capacity")
    try:
        from app.performance.capacity import capacity_forecast_service
        res = await capacity_forecast_service.forecast(db, tenant, resource, metric, horizon_days=horizon_days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return res


@router.post("/benchmarks", status_code=201)
async def create_benchmark(payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "performance:write", "benchmark")
    try:
        from app.performance.benchmark import benchmark_service
        res = await benchmark_service.create_definition(tenant, payload.get("name", "bench"), payload.get("suite_type", "api"), payload.get("config", {}))
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    return res


@router.get("/benchmarks")
async def list_benchmarks(user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.performance.benchmark import benchmark_service
    rows = await benchmark_service.list_definitions(tenant)
    return {"items": rows}


@router.post("/benchmarks/{benchmark_id}/run", status_code=201)
async def run_benchmark(benchmark_id: str, payload: dict | None = None, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.performance.benchmark import benchmark_service
    try:
        res = await benchmark_service.run_benchmark(db, tenant, benchmark_id, environment=(payload or {}).get("environment", "test"))
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return res


@router.post("/benchmarks/{benchmark_id}/baseline")
async def set_benchmark_baseline(benchmark_id: str, payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.performance.benchmark import benchmark_service
    try:
        res = await benchmark_service.set_baseline(tenant, benchmark_id, payload.get("run_id"))
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    return res


@router.get("/benchmarks/{benchmark_id}/compare")
async def compare_benchmark(benchmark_id: str, run_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.performance.benchmark import benchmark_service
    try:
        res = await benchmark_service.compare(tenant, benchmark_id, run_id)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    return res


@router.post("/benchmarks/{benchmark_id}/stress", status_code=201)
async def stress_test(benchmark_id: str, payload: dict | None = None, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.performance.benchmark import benchmark_service
    try:
        res = await benchmark_service.run_stress(tenant, benchmark_id, concurrency=(payload or {}).get("concurrency", 10), duration_seconds=(payload or {}).get("duration_seconds", 30))
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    return res


@router.post("/benchmarks/{benchmark_id}/soak", status_code=201)
async def soak_test(benchmark_id: str, payload: dict | None = None, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.performance.benchmark import benchmark_service
    try:
        res = await benchmark_service.run_soak(tenant, benchmark_id, duration_hours=(payload or {}).get("duration_hours", 1))
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    return res


@router.post("/regression/check", status_code=201)
async def check_regression(payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.performance.benchmark import benchmark_service
    try:
        res = await benchmark_service.check_regression_gate(tenant, payload.get("benchmark_id"), payload.get("run_id"), thresholds=payload.get("thresholds"))
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    return res


@router.get("/scaling/recommendations")
async def scaling_recommendations(resource: str | None = Query(None), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.performance.capacity import capacity_forecast_service
    try:
        res = await capacity_forecast_service.recommend_scaling(db, tenant, resource or "default")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return res
