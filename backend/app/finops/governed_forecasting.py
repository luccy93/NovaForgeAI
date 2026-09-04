"""Bounded deterministic cost forecasting — Volume 69 Commit 2.

Baseline: mean daily spend plus linear trend over recent daily buckets.
Minimum 7 daily buckets required; otherwise an explicit INSUFFICIENT_DATA
state is returned and no forecast row is fabricated. Horizon is capped at
90 days. Budget exhaustion is derived from month-to-date spend plus the
projected daily rate.

NOTE: the legacy file-backed `app.finops.forecasting` module is untouched;
this governed layer persists to PostgreSQL.
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.finops.governed_common import (
    ValidationError,
    _ensure_aware,
    _utcnow,
    clamp_range,
    dimensions_hash,
    parse_time,
)
from app.finops.governed_models import FinOpsCostRecord
from app.finops.governed_models_c2 import FinOpsForecast

MIN_BUCKETS = 7
MAX_HORIZON_DAYS = 90
LOOKBACK_DAYS = 30


def _serialize(row: FinOpsForecast) -> dict:
    return {
        "id": str(row.id),
        "tenant": row.tenant,
        "forecast_type": row.forecast_type,
        "dimensions": row.dimensions or {},
        "horizon_days": row.horizon_days,
        "period_start": row.period_start.isoformat() if row.period_start else None,
        "predicted_cents": row.predicted_cents,
        "daily_rate_cents": row.daily_rate_cents,
        "confidence": row.confidence,
        "quality": row.quality,
        "method": row.method,
        "basis_buckets": row.basis_buckets,
        "budget_exhaustion_date": row.budget_exhaustion_date.isoformat() if row.budget_exhaustion_date else None,
        "status": row.status,
    }


async def _daily_series(db: AsyncSession, tenant: str, dimensions: dict, days: int) -> list[tuple[datetime, int]]:
    end = _utcnow()
    start = end - timedelta(days=days)
    stmt = select(FinOpsCostRecord).where(
        FinOpsCostRecord.tenant == tenant,
        FinOpsCostRecord.occurred_at >= start,
        FinOpsCostRecord.occurred_at <= end,
    )
    for key in ("provider", "model", "workspace", "project", "service", "environment"):
        value = dimensions.get(key)
        if value:
            stmt = stmt.where(getattr(FinOpsCostRecord, key) == value)
    records = (await db.execute(stmt)).scalars().all()
    buckets: dict[str, int] = {}
    for record in records:
        day = _ensure_aware(record.occurred_at).replace(hour=0, minute=0, second=0, microsecond=0)
        buckets[day.isoformat()] = buckets.get(day.isoformat(), 0) + (record.amount_cents or 0)
    series = [(datetime.fromisoformat(k), v) for k, v in sorted(buckets.items())]
    return [(d, v) for d, v in series if v > 0]


def _trend(daily: list[int]) -> tuple[float, float]:
    n = len(daily)
    mean = sum(daily) / n
    if n < 2:
        return mean, 0.0
    xs = list(range(n))
    xmean = sum(xs) / n
    denom = sum((x - xmean) ** 2 for x in xs)
    slope = sum((x - xmean) * (y - mean) for x, y in zip(xs, daily)) / denom if denom else 0.0
    return mean, slope


async def generate_forecast(
    db: AsyncSession,
    tenant: str,
    *,
    horizon_days: int = 30,
    dimensions: Optional[dict] = None,
    budget_id=None,
    actor: str = "",
) -> dict:
    if not tenant:
        raise ValidationError("tenant required")
    horizon_days = int(horizon_days or 30)
    if horizon_days < 1 or horizon_days > MAX_HORIZON_DAYS:
        raise ValidationError(f"horizon_days must be 1-{MAX_HORIZON_DAYS}")
    dimensions = {k: (v or "") for k, v in (dimensions or {}).items() if k}
    dim_hash = dimensions_hash(dimensions)

    series = await _daily_series(db, tenant, dimensions, LOOKBACK_DAYS)
    if len(series) < MIN_BUCKETS:
        return {"status": "INSUFFICIENT_DATA",
                "reason": f"need at least {MIN_BUCKETS} days with spend, found {len(series)}",
                "basis_buckets": len(series)}

    daily = [total for _, total in series]
    mean, slope = _trend(daily)
    daily_rate = max(mean + slope * (horizon_days / 2), 0.0)
    predicted = int(round(daily_rate * horizon_days))
    variance = sum((y - mean) ** 2 for y in daily) / len(daily)
    cv = (math.sqrt(variance) / mean) if mean > 0 else 1.0
    confidence = round(max(0.0, min(0.99, 1.0 - cv)), 4)
    quality = "HIGH" if confidence >= 0.7 else ("MEDIUM" if confidence >= 0.4 else "LOW")

    exhaustion = None
    if budget_id:
        from app.finops.budgets import evaluate_budget
        try:
            status = await evaluate_budget(db, tenant, budget_id, actor=actor)
            remaining = max(int(status.get("amount_cents", 0)) - int(status.get("spend_cents", 0)), 0)
            if daily_rate > 0 and remaining > 0:
                days_out = remaining / daily_rate
                # Beyond a plannable horizon there is effectively no exhaustion.
                exhaustion = _utcnow() + timedelta(days=days_out) if days_out <= 3650 else None
        except Exception:
            exhaustion = None

    now = _utcnow()
    row = FinOpsForecast(
        id=uuid.uuid4(), tenant=tenant, forecast_type="spend",
        dimensions=dimensions, dimensions_hash=dim_hash, horizon_days=horizon_days,
        period_start=now, predicted_cents=predicted, daily_rate_cents=round(daily_rate, 2),
        confidence=confidence, quality=quality, method="linear_baseline",
        basis_buckets=len(series), budget_exhaustion_date=exhaustion, status="READY",
    )
    try:
        async with db.begin_nested():
            db.add(row)
            await db.flush()
    except IntegrityError:
        dup_stmt = select(FinOpsForecast).where(
            FinOpsForecast.tenant == tenant, FinOpsForecast.forecast_type == "spend",
            FinOpsForecast.dimensions_hash == dim_hash,
            FinOpsForecast.horizon_days == horizon_days, FinOpsForecast.period_start == now,
        )
        existing = (await db.execute(dup_stmt)).scalar_one_or_none()
        if existing is None:
            raise
        return {**_serialize(existing), "deduplicated": True}

    from app.finops.governed_models import FinOpsAuditLog
    db.add(FinOpsAuditLog(
        tenant=tenant, actor=actor or "", action="forecast.generate",
        resource_type="forecast", resource_id=str(row.id),
        details={"horizon_days": horizon_days, "predicted_cents": predicted}, status="SUCCESS",
    ))
    await db.flush()
    try:
        from app.finops.governed_events import forecast_generated
        await forecast_generated(tenant, {"id": str(row.id), "predicted_cents": predicted})
    except Exception:
        pass
    return _serialize(row)


async def list_forecasts(db: AsyncSession, tenant: str, *, limit: int = 50) -> dict:
    limit = min(max(int(limit or 50), 1), 1000)
    rows = (await db.execute(
        select(FinOpsForecast).where(FinOpsForecast.tenant == tenant)
        .order_by(desc(FinOpsForecast.created_at)).limit(limit)
    )).scalars().all()
    return {"items": [_serialize(r) for r in rows], "total": len(rows)}
