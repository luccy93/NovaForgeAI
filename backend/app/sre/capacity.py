"""Capacity planning and saturation monitoring (Volume 35).

Tracks current/peak capacity, headroom, growth forecast (linear trend
on measured values) and expected exhaustion date. Saturation detection
feeds load-shedding and scaling decisions.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sre.constants import CAPACITY_ALERT_THRESHOLD_PERCENT, CAPACITY_CRITICAL_THRESHOLD_PERCENT
from app.sre.models import SRECapacityMetric

logger = logging.getLogger(__name__)


async def record_capacity(
    db: AsyncSession,
    *,
    service_id: str,
    metric: str,
    value: float,
    limit: float = 100.0,
    unit: str = "percent",
    region: str = "",
) -> SRECapacityMetric:
    row = SRECapacityMetric(
        service_id=service_id,
        metric=metric,
        value=value,
        limit=limit,
        unit=unit,
        region=region,
    )
    db.add(row)
    await db.flush()
    return row


def saturation_level(value: float, limit: float = 100.0) -> str:
    utilization = (value / limit * 100.0) if limit else 100.0
    if utilization >= CAPACITY_CRITICAL_THRESHOLD_PERCENT:
        return "critical"
    if utilization >= CAPACITY_ALERT_THRESHOLD_PERCENT:
        return "warning"
    return "normal"


async def capacity_trend(
    db: AsyncSession,
    *,
    service_id: str = "",
    metric: str = "cpu",
    days: int = 7,
) -> dict:
    """Current/peak/average capacity plus a linear-trend forecast with
    expected exhaustion date (None when not forecastable)."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = select(SRECapacityMetric).where(
        SRECapacityMetric.metric == metric,
        SRECapacityMetric.measured_at >= since,
    )
    if service_id:
        stmt = stmt.where(SRECapacityMetric.service_id == service_id)
    stmt = stmt.order_by(SRECapacityMetric.measured_at)
    rows = list((await db.execute(stmt)).scalars().all())
    if not rows:
        return {
            "service_id": service_id,
            "metric": metric,
            "samples": 0,
            "current": None,
            "peak": None,
            "average": None,
            "headroom_percent": None,
            "growth_per_day": None,
            "forecast_exhaustion_at": None,
            "saturation": "unknown",
        }
    values = [row.value for row in rows]
    current = values[-1]
    peak = max(values)
    average = sum(values) / len(values)
    limit = rows[-1].limit or 100.0
    headroom = max(0.0, (limit - current) / limit * 100.0) if limit else 0.0

    growth_per_day = None
    exhaustion_at = None
    if len(rows) >= 4:
        x0 = rows[0].measured_at.timestamp()
        x1 = rows[-1].measured_at.timestamp()
        delta_days = (x1 - x0) / 86400.0
        if delta_days > 0:
            growth_per_day = (values[-1] - values[0]) / delta_days
            if growth_per_day > 0:
                remaining = (limit - current) / growth_per_day
                exhaustion_at = (datetime.now(timezone.utc) + timedelta(days=remaining)).isoformat()

    return {
        "service_id": service_id,
        "metric": metric,
        "samples": len(rows),
        "current": round(current, 2),
        "peak": round(peak, 2),
        "average": round(average, 2),
        "limit": limit,
        "headroom_percent": round(headroom, 2),
        "growth_per_day": round(growth_per_day, 4) if growth_per_day is not None else None,
        "forecast_exhaustion_at": exhaustion_at,
        "saturation": saturation_level(current, limit),
    }


async def saturation_summary(db: AsyncSession, *, days: int = 1) -> list[dict]:
    """Per (service, metric) latest saturation state."""
    stmt = select(
        SRECapacityMetric.service_id,
        SRECapacityMetric.metric,
        SRECapacityMetric.value,
        SRECapacityMetric.limit,
        SRECapacityMetric.measured_at,
    ).where(SRECapacityMetric.measured_at >= datetime.now(timezone.utc) - timedelta(days=days))
    rows = list((await db.execute(stmt)).all())
    latest: dict[tuple[str, str], dict] = {}
    for service_id, metric, value, limit, measured_at in rows:
        key = (service_id or "platform", metric)
        entry = latest.setdefault(key, {"measured_at": None, "value": 0.0, "limit": 100.0})
        if entry["measured_at"] is None or measured_at > entry["measured_at"]:
            entry.update({"measured_at": measured_at, "value": float(value), "limit": float(limit or 100.0)})
    result = []
    for (service_id, metric), entry in latest.items():
        value = entry["value"]
        limit = entry["limit"]
        utilization = (value / limit * 100.0) if limit else 100.0
        result.append(
            {
                "service_id": service_id,
                "metric": metric,
                "value": round(value, 2),
                "limit": limit,
                "utilization_percent": round(utilization, 2),
                "saturation": saturation_level(value, limit),
                "measured_at": entry["measured_at"].isoformat() if entry["measured_at"] else None,
            }
        )
    return result