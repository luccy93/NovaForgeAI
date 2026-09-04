"""Deterministic cost calculation and recording — Volume 69 Commit 1.

Costs are computed in integer cents from an explicit pricing version.
When no pricing is effective, the record is stored as UNPRICED with zero
amount — a number is never invented. Recording is idempotent on
(tenant, idempotency_key): retries return the existing record.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import and_, desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.finops.governed_common import (
    COST_BASIS_ACTUAL,
    COST_BASIS_ESTIMATED,
    COST_BASIS_UNPRICED,
    NotFoundError,
    ValidationError,
    _ensure_aware,
    _utcnow,
    clamp_range,
    idempotency_key,
    parse_time,
    sanitize_metadata,
)
from app.finops.governed_models import FinOpsAuditLog, FinOpsCostRecord
from app.finops.pricing import get_effective_pricing

DIMENSION_FIELDS = (
    "workspace", "project", "service", "workflow", "model",
    "provider", "environment", "region", "resource", "operation", "actor",
)


def compute_cost_cents(
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    requests: int = 0,
    pricing: Optional[dict] = None,
) -> tuple[int, str, dict]:
    """Deterministic cost. Returns (amount_cents, basis, snapshot).

    Missing pricing -> (0, UNPRICED, {}). Never raises for missing data.
    """
    input_tokens = max(int(input_tokens or 0), 0)
    output_tokens = max(int(output_tokens or 0), 0)
    requests = max(int(requests or 0), 0)
    if pricing is None:
        return 0, COST_BASIS_UNPRICED, {}
    amount = (
        input_tokens * float(pricing.get("input_price_cents_per_m", 0.0))
        + output_tokens * float(pricing.get("output_price_cents_per_m", 0.0))
    ) / 1_000_000.0 + requests * float(pricing.get("request_price_cents", 0.0))
    snapshot = {
        "pricing_version_id": pricing.get("id"),
        "pricing_version": pricing.get("version"),
        "input_price_cents_per_m": pricing.get("input_price_cents_per_m"),
        "output_price_cents_per_m": pricing.get("output_price_cents_per_m"),
        "request_price_cents": pricing.get("request_price_cents"),
        "currency": pricing.get("currency", "USD"),
    }
    return int(round(amount)), COST_BASIS_ACTUAL, snapshot


def _serialize(row: FinOpsCostRecord) -> dict:
    return {
        "id": str(row.id),
        "tenant": row.tenant,
        "workspace": row.workspace or "",
        "project": row.project or "",
        "service": row.service or "",
        "workflow": row.workflow or "",
        "model": row.model or "",
        "provider": row.provider or "",
        "environment": row.environment or "",
        "region": row.region or "",
        "resource": row.resource or "",
        "operation": row.operation or "",
        "actor": row.actor or "",
        "input_tokens": row.input_tokens,
        "output_tokens": row.output_tokens,
        "cached_tokens": row.cached_tokens,
        "requests": row.requests,
        "latency_ms": row.latency_ms,
        "amount_cents": row.amount_cents,
        "currency": row.currency,
        "cost_basis": row.cost_basis,
        "pricing_version_id": str(row.pricing_version_id) if row.pricing_version_id else None,
        "source_type": row.source_type,
        "source_id": row.source_id,
        "idempotency_key": row.idempotency_key,
        "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
    }


async def _find_by_key(db: AsyncSession, tenant: str, key: str) -> Optional[FinOpsCostRecord]:
    stmt = select(FinOpsCostRecord).where(FinOpsCostRecord.tenant == tenant, FinOpsCostRecord.idempotency_key == key)
    return (await db.execute(stmt)).scalar_one_or_none()


async def record_usage_cost(
    db: AsyncSession,
    tenant: str,
    usage: dict,
    *,
    actor: str = "",
) -> dict:
    """Normalize one authoritative usage event into a cost record.

    Expected usage keys: provider, model, input_tokens, output_tokens,
    cached_tokens, requests, latency_ms, occurred_at, source_type,
    source_id, dimensions{workspace,project,service,workflow,environment,
    region,resource,operation,actor}, estimated (bool), idempotency_key?.
    """
    if not tenant:
        raise ValidationError("tenant required")
    source_type = str(usage.get("source_type") or "").strip()
    source_id = str(usage.get("source_id") or "").strip()
    if not source_type or not source_id:
        raise ValidationError("source_type and source_id required")
    dims = usage.get("dimensions") or {}
    provider = str(usage.get("provider") or dims.get("provider") or "")
    model = str(usage.get("model") or dims.get("model") or "")
    occurred = _ensure_aware(parse_time(usage.get("occurred_at")) or _utcnow())
    key = str(usage.get("idempotency_key") or idempotency_key(tenant, source_type, source_id))

    existing = await _find_by_key(db, tenant, key)
    if existing is not None:
        return {**_serialize(existing), "deduplicated": True}

    pricing = await get_effective_pricing(db, tenant, provider, model=model, at=occurred) if provider else None
    amount, basis, snapshot = compute_cost_cents(
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        requests=usage.get("requests", 0),
        pricing=pricing,
    )
    if basis == COST_BASIS_ACTUAL and bool(usage.get("estimated")):
        basis = COST_BASIS_ESTIMATED

    row = FinOpsCostRecord(
        id=uuid.uuid4(), tenant=tenant,
        workspace=str(dims.get("workspace") or ""), project=str(dims.get("project") or ""),
        service=str(dims.get("service") or ""), workflow=str(dims.get("workflow") or ""),
        model=model, provider=provider,
        environment=str(dims.get("environment") or ""), region=str(dims.get("region") or ""),
        resource=str(dims.get("resource") or ""), operation=str(dims.get("operation") or usage.get("operation") or ""),
        actor=str(dims.get("actor") or actor or ""),
        input_tokens=max(int(usage.get("input_tokens") or 0), 0),
        output_tokens=max(int(usage.get("output_tokens") or 0), 0),
        cached_tokens=max(int(usage.get("cached_tokens") or 0), 0),
        requests=max(int(usage.get("requests") or 0), 0),
        latency_ms=usage.get("latency_ms"),
        amount_cents=amount, currency=str(usage.get("currency") or "USD").upper(),
        cost_basis=basis,
        pricing_version_id=uuid.UUID(snapshot["pricing_version_id"]) if snapshot.get("pricing_version_id") else None,
        pricing_snapshot=snapshot,
        source_type=source_type, source_id=source_id, idempotency_key=key,
        occurred_at=occurred, metadata_=sanitize_metadata(usage.get("metadata")),
    )
    try:
        async with db.begin_nested():
            db.add(row)
            await db.flush()
    except IntegrityError:
        existing = await _find_by_key(db, tenant, key)
        if existing is None:
            raise
        return {**_serialize(existing), "deduplicated": True}

    db.add(FinOpsAuditLog(
        tenant=tenant, actor=actor or "", action="cost.record",
        resource_type="cost_record", resource_id=str(row.id),
        details={"source_type": source_type, "source_id": source_id, "basis": basis, "amount_cents": amount},
        status="SUCCESS",
    ))
    await db.flush()

    try:
        from app.finops.governed_events import cost_calculated
        await cost_calculated(tenant, {"id": str(row.id), "amount_cents": amount, "basis": basis})
    except Exception:
        pass
    return _serialize(row)


async def record_ai_usage_cost(db: AsyncSession, tenant: str, ai: dict, *, actor: str = "") -> dict:
    """Adapter for AI Gateway / CodeAIUsage-shaped execution metadata."""
    usage = {
        "provider": ai.get("provider") or ai.get("model_provider") or "",
        "model": ai.get("model") or "",
        "input_tokens": ai.get("prompt_tokens", ai.get("input_tokens", 0)),
        "output_tokens": ai.get("completion_tokens", ai.get("output_tokens", 0)),
        "cached_tokens": ai.get("cached_tokens", 0),
        "requests": ai.get("requests", 1),
        "latency_ms": ai.get("latency_ms"),
        "occurred_at": ai.get("occurred_at") or ai.get("timestamp"),
        "source_type": ai.get("source_type") or "ai_execution",
        "source_id": ai.get("source_id") or ai.get("request_id") or idempotency_key(tenant, str(ai.get("model")), str(ai.get("occurred_at"))),
        "estimated": bool(ai.get("estimated", False)),
        "dimensions": {
            "workspace": ai.get("workspace") or ai.get("workspace_id") or "",
            "project": ai.get("project") or ai.get("project_id") or "",
            "service": ai.get("service") or "",
            "workflow": ai.get("workflow") or ai.get("workflow_id") or "",
            "environment": ai.get("environment") or "",
            "region": ai.get("region") or "",
            "resource": ai.get("resource") or ai.get("repository_id") or "",
            "operation": ai.get("operation") or ai.get("action") or "",
            "actor": ai.get("actor") or ai.get("user_id") or "",
        },
        "metadata": ai.get("metadata"),
    }
    return await record_usage_cost(db, tenant, usage, actor=actor)


async def list_costs(
    db: AsyncSession, tenant: str, *, filters: Optional[dict] = None, limit: int = 100, offset: int = 0,
) -> dict:
    filters = filters or {}
    start = parse_time(filters.get("start"))
    end = parse_time(filters.get("end"))
    if start or end:
        start, end = clamp_range(start, end)
    stmt = select(FinOpsCostRecord).where(FinOpsCostRecord.tenant == tenant)
    for field in ("provider", "model", "workspace", "project", "service", "workflow", "environment", "region", "operation", "cost_basis"):
        value = filters.get(field)
        if value:
            stmt = stmt.where(getattr(FinOpsCostRecord, field) == value)
    if start:
        stmt = stmt.where(FinOpsCostRecord.occurred_at >= start)
    if end:
        stmt = stmt.where(FinOpsCostRecord.occurred_at <= end)
    limit = min(max(int(limit or 100), 1), 1000)
    offset = max(int(offset or 0), 0)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    rows = (await db.execute(stmt.order_by(desc(FinOpsCostRecord.occurred_at)).limit(limit).offset(offset))).scalars().all()
    items = [_serialize(r) for r in rows]
    return {
        "items": items, "total": total, "limit": limit, "offset": offset,
        "spend_cents": sum(i["amount_cents"] for i in items),
    }


async def usage_summary(db: AsyncSession, tenant: str, *, start=None, end=None) -> dict:
    """Tenant usage summary combining governed cost records with CodeAIUsage totals (best-effort)."""
    start_p, end_p = clamp_range(parse_time(start), parse_time(end)) if (start or end) else (None, None)
    stmt = select(
        func.count(FinOpsCostRecord.id),
        func.coalesce(func.sum(FinOpsCostRecord.amount_cents), 0),
        func.coalesce(func.sum(FinOpsCostRecord.input_tokens + FinOpsCostRecord.output_tokens), 0),
    ).where(FinOpsCostRecord.tenant == tenant)
    if start_p:
        stmt = stmt.where(FinOpsCostRecord.occurred_at >= start_p)
    if end_p:
        stmt = stmt.where(FinOpsCostRecord.occurred_at <= end_p)
    count, spend, tokens = (await db.execute(stmt)).one()
    summary: dict = {
        "tenant": tenant,
        "cost_records": int(count or 0),
        "spend_cents": int(spend or 0),
        "total_tokens": int(tokens or 0),
        "ai_executions": 0,
        "ai_tokens": 0,
        "ai_cost_cents": 0.0,
    }
    try:
        from app.ai_dev.usage import usage_totals as _ai_totals
        ai = await _ai_totals(db, tenant)
        summary["ai_executions"] = int(ai.get("requests") or 0)
        summary["ai_tokens"] = int(ai.get("total_tokens") or 0)
        summary["ai_cost_cents"] = float(ai.get("cost_cents") or 0.0)
    except Exception:
        pass
    return summary
