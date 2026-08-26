"""Capacity Forecasting & Planning — Volume 61 Commit 2."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.performance.models import PerformanceServiceMetric, CapacityPolicy, ResourcePool


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CapacityForecastService:
    async def forecast(self, db: AsyncSession, tenant: str, resource: str, metric: str = "cpu", horizon_days: int = 7, granularity: str = "day") -> dict:
        # Use recent metrics for trend
        since = _now() - timedelta(days=14)
        stmt = select(PerformanceServiceMetric).where(
            PerformanceServiceMetric.tenant == tenant,
            PerformanceServiceMetric.service == resource,
            PerformanceServiceMetric.metric_name == metric,
            PerformanceServiceMetric.period_start >= since,
        ).order_by(PerformanceServiceMetric.period_start.asc()).limit(500)
        res = await db.execute(stmt)
        rows = list(res.scalars().all())
        if len(rows) < 4:
            return {"resource": resource, "metric": metric, "forecast": None, "uncertainty": "insufficient_data", "confidence": 0.0, "note": "need >=4 samples"}

        xs = list(range(len(rows)))
        ys = [float(r.value) for r in rows]
        n = len(xs)
        mean_x = sum(xs) / n
        mean_y = sum(ys) / n
        num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        den = sum((x - mean_x) ** 2 for x in xs) or 1
        slope = num / den
        intercept = mean_y - slope * mean_x
        # Forecast horizon
        future = [slope * (n + i) + intercept for i in range(1, horizon_days + 1)]
        # Uncertainty band via residual std
        residuals = [y - (slope * x + intercept) for x, y in zip(xs, ys)]
        std = math.sqrt(sum(r * r for r in residuals) / n) if n > 1 else 0
        lower = [max(0, f - 1.96 * std) for f in future]
        upper = [f + 1.96 * std for f in future]
        # Confidence based on data amount and std
        confidence = max(0.0, min(0.95, 0.5 + 0.1 * math.log10(n) - 0.1 * (std / (mean_y or 1))))
        return {
            "resource": resource, "metric": metric, "horizon_days": horizon_days,
            "forecast": [round(f, 2) for f in future], "lower": [round(f, 2) for f in lower],
            "upper": [round(f, 2) for f in upper], "uncertainty": f"±{round(1.96*std,2)} (95% band)",
            "confidence": round(confidence, 2), "model": "linear_regression", "note": "statistical estimate, not guaranteed",
        }

    async def forecast_growth(self, db: AsyncSession, tenant: str, dimension: str = "users") -> dict:
        # Count growth from existing tables
        counts = {}
        try:
            from sqlalchemy import text
            # Try to count from various sources
            for tbl, col in [("governance_data_assets", "tenant"), ("analytics_events", "tenant"), ("repositories", "tenant")]:
                try:
                    res = await db.execute(select(func.count()).select_from(text(tbl)).where(text(f"{col} = '{tenant}'")))
                    counts[tbl] = res.scalar() or 0
                except Exception:
                    counts[tbl] = 0
        except Exception:
            pass
        total = sum(counts.values())
        growth_rate = 0.05 if total > 0 else 0.0  # placeholder 5% if data exists
        return {"tenant": tenant, "dimension": dimension, "current": total, "growth_rate_weekly": round(growth_rate, 4), "forecast_next_week": int(total * (1 + growth_rate)), "counts": counts}

    async def forecast_resource(self, db: AsyncSession, tenant: str, resource_type: str = "cpu") -> dict:
        # Generic resource forecast
        return await self.forecast(db, tenant, resource=resource_type, metric=resource_type, horizon_days=7)

    async def get_headroom(self, db: AsyncSession, tenant: str, resource: str) -> dict:
        # Find capacity policy for resource
        res = await db.execute(select(CapacityPolicy).where(CapacityPolicy.tenant == tenant, CapacityPolicy.resource == resource).limit(1))
        policy = res.scalars().first()
        if not policy:
            return {"resource": resource, "headroom": None, "safe": None, "note": "no capacity policy"}
        # Get latest snapshot
        from app.performance.models import PerformanceSnapshot
        stmt = select(PerformanceSnapshot).where(PerformanceSnapshot.tenant == tenant, PerformanceSnapshot.resource == resource).order_by(PerformanceSnapshot.created_at.desc()).limit(1)
        snap_res = await db.execute(stmt)
        snap = snap_res.scalars().first()
        current = getattr(snap, "cpu", None) or getattr(snap, "memory", None) or 0
        limit = policy.max_instances * 100  # simplified
        headroom = (limit - (current or 0)) / limit if limit else 1.0
        safe = headroom >= 0.2
        return {"resource": resource, "current": current, "limit": limit, "headroom": round(headroom, 3), "safe": safe, "warning": not safe, "note": "100% utilization not safe"}

    async def recommend_scaling(self, db: AsyncSession, tenant: str, resource: str) -> dict:
        headroom = await self.get_headroom(db, tenant, resource)
        forecast = await self.forecast(db, tenant, resource, metric=resource)
        recs = []
        if not headroom.get("safe", True):
            recs.append({"action": "scale_out", "evidence": {"headroom": headroom.get("headroom"), "forecast": forecast.get("forecast", [])[:3]}, "urgency": "high"})
        if forecast.get("forecast") and max(forecast["forecast"] or [0]) > 80:
            recs.append({"action": "scale_up", "evidence": {"forecast_max": max(forecast["forecast"])}, "urgency": "medium"})
        if not recs:
            recs.append({"action": "optimize", "evidence": {"headroom": headroom.get("headroom")}, "urgency": "low"})
        return {"resource": resource, "recommendations": recs, "headroom": headroom, "forecast": forecast}


capacity_forecast_service = CapacityForecastService()
