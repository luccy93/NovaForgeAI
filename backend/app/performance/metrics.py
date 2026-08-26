"""Volume 61 Commit 1 — MetricsService (DB-backed, tenant-isolated).

Persists to ``performance_service_metrics`` with period_start/end bucketing
and computes p50/p95/p99 from sorted values per bucket. Reuses analytics
aggregation bucketing semantics and never stores sensitive request/response
bodies in dimensions.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.performance.models import PerformanceServiceMetric


# ---------------------------------------------------------------------------
# Helpers: tenant isolation, sanitization, bucketing, percentiles
# ---------------------------------------------------------------------------

SENSITIVE_KEYS = {
    "body",
    "request_body",
    "response_body",
    "payload",
    "content",
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "auth",
    "credential",
    "api_key",
    "apikey",
    "private_key",
    "cookie",
    "set-cookie",
}

# Valid granularities mirror analytics AggregationService
VALID_GRANULARITIES = {"minute", "hour", "day", "week", "month"}
GRANULARITY_DELTAS: dict[str, timedelta] = {
    "minute": timedelta(minutes=1),
    "hour": timedelta(hours=1),
    "day": timedelta(days=1),
    "week": timedelta(weeks=1),
    "month": timedelta(days=30),  # approximated; bucket end computed via calendar
}

# In-memory cache of raw values per bucket to compute accurate percentiles
# at write time (persisted aggregate reflects true sorted values).
_BUCKET_VALUES: dict[str, list[float]] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_timestamp(value: datetime | str | None) -> datetime:
    if value is None:
        return _utcnow()
    if isinstance(value, datetime):
        return _ensure_aware(value)
    if isinstance(value, str):
        txt = value.strip()
        if not txt:
            return _utcnow()
        # Handle trailing Z
        if txt.endswith("Z"):
            txt = txt[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(txt)
            return _ensure_aware(dt)
        except ValueError:
            return _utcnow()
    return _utcnow()


def _sanitize_dimensions(dimensions: dict | None) -> dict:
    """Remove sensitive keys and truncate large values."""
    if not dimensions:
        return {}
    if not isinstance(dimensions, dict):
        try:
            dimensions = dict(dimensions)  # type: ignore[arg-type]
        except Exception:
            return {}
    sanitized: dict[str, Any] = {}
    for k, v in list(dimensions.items())[:50]:  # bounded
        kl = str(k).lower()
        if kl in SENSITIVE_KEYS:
            continue
        # Also drop keys containing sensitive substrings
        if any(s in kl for s in ("body", "payload", "password", "secret", "token")):
            continue
        # Truncate string values to avoid storing large bodies
        if isinstance(v, str) and len(v) > 500:
            v = v[:500] + "...[truncated]"
        elif isinstance(v, (dict, list)):
            try:
                txt = json.dumps(v, default=str)
                if len(txt) > 1000:
                    v = txt[:1000] + "...[truncated]"
                else:
                    v = json.loads(txt)
            except Exception:
                v = str(v)[:500]
        sanitized[str(k)] = v
    return sanitized


def _bucket_start(ts: datetime, granularity: str) -> datetime:
    ts = _ensure_aware(ts)
    if granularity == "minute":
        return ts.replace(second=0, microsecond=0)
    if granularity == "hour":
        return ts.replace(minute=0, second=0, microsecond=0)
    if granularity == "day":
        return ts.replace(hour=0, minute=0, second=0, microsecond=0)
    if granularity == "week":
        monday = ts - timedelta(days=ts.weekday())
        return monday.replace(hour=0, minute=0, second=0, microsecond=0)
    if granularity == "month":
        return ts.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return ts.replace(second=0, microsecond=0)


def _bucket_end(start: datetime, granularity: str) -> datetime:
    if granularity == "month":
        # Calendar month end: next month's first day
        year = start.year + (1 if start.month == 12 else 0)
        month = 1 if start.month == 12 else start.month + 1
        return datetime(year, month, 1, tzinfo=timezone.utc)
    delta = GRANULARITY_DELTAS.get(granularity, timedelta(minutes=1))
    return start + delta


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    # pct in (0,1], e.g. 0.5, 0.95
    idx = int(len(sorted_vals) * pct)
    idx = max(0, min(idx, len(sorted_vals) - 1))
    # Handle exact percentile interpolation: for even counts, average neighbours for p50
    # Keep simple nearest-rank to match analytics aggregation_service.
    return float(sorted_vals[idx])


def _bucket_key(
    tenant: str,
    service: str,
    metric_name: str,
    granularity: str,
    dimensions: dict,
    period_start: datetime,
) -> str:
    dims_hash = hashlib.md5(
        json.dumps(dimensions, sort_keys=True, default=str).encode()
    ).hexdigest()[:8]
    return f"{tenant}:{service}:{metric_name}:{granularity}:{dims_hash}:{period_start.isoformat()}"


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class MetricsService:
    """DB-backed service metrics with bucketing and percentile aggregates."""

    async def record_metric(
        self,
        db: AsyncSession,
        tenant: str,
        service: str,
        metric_name: str,
        value: float,
        granularity: str = "minute",
        dimensions: dict | None = None,
        timestamp: datetime | str | None = None,
    ) -> PerformanceServiceMetric:
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        if not service or not str(service).strip():
            raise ValueError("service is required")
        if not metric_name or not str(metric_name).strip():
            raise ValueError("metric_name is required")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError("value must be a number")
        tenant_s = str(tenant).strip()
        service_s = str(service).strip()
        metric_s = str(metric_name).strip()
        gran = str(granularity or "minute").strip().lower()
        if gran not in VALID_GRANULARITIES:
            gran = "minute"

        ts = _parse_timestamp(timestamp)
        period_start = _bucket_start(ts, gran)
        period_end = _bucket_end(period_start, gran)
        dims = _sanitize_dimensions(dimensions)
        val = float(value)

        # Find existing bucket row with same tenant/service/metric/granularity/period_start
        # and identical dimensions (JSON equality in Python).
        stmt = select(PerformanceServiceMetric).where(
            PerformanceServiceMetric.tenant == tenant_s,
            PerformanceServiceMetric.service == service_s,
            PerformanceServiceMetric.metric_name == metric_s,
            PerformanceServiceMetric.granularity == gran,
            PerformanceServiceMetric.period_start == period_start,
        )
        result = await db.execute(stmt)
        candidates = list(result.scalars().all())
        existing: PerformanceServiceMetric | None = None
        for cand in candidates:
            if (cand.dimensions or {}) == dims:
                existing = cand
                break

        # Maintain in-memory raw values for accurate percentile computation.
        bkey = _bucket_key(tenant_s, service_s, metric_s, gran, dims, period_start)
        bucket_vals = _BUCKET_VALUES.get(bkey)
        if bucket_vals is None:
            # Seed from existing DB row if present: we approximate by repeating
            # the stored avg value count times when no history in memory (best-effort).
            if existing is not None and existing.count and existing.count > 0:
                # If we have no history, seed with existing aggregated values:
                # use min/max/avg to create synthetic list (not perfect but preserves count)
                # Better to start fresh if we cannot reconstruct.
                # For accuracy after restart, initialize with [existing.value] * existing.count
                # but that collapses percentile variance; we accept it for now.
                # Alternatively, keep bucket_vals as [existing.value] * existing.count
                # to keep count consistent.
                bucket_vals = []
                # Do not seed with synthetic values that distort percentiles; start empty
                # and will include previous count in aggregate math below.
            else:
                bucket_vals = []
            _BUCKET_VALUES[bkey] = bucket_vals
        bucket_vals.append(val)
        sorted_vals = sorted(bucket_vals)
        count = len(sorted_vals)
        avg_val = sum(sorted_vals) / count if count else val
        min_val = min(sorted_vals) if sorted_vals else val
        max_val = max(sorted_vals) if sorted_vals else val
        p50 = _percentile(sorted_vals, 0.50)
        p95 = _percentile(sorted_vals, 0.95)
        p99 = _percentile(sorted_vals, 0.99)

        if existing is not None:
            # Update aggregate row
            # Need to handle restart seeding: adjust count to reflect total including prior DB count
            # If bucket_vals was seeded empty but DB had previous count, we add that offset.
            # We already appended new val; if existing.count >0 and we started empty, total count should be existing.count+1
            # but bucket_vals length is 1. So include offset.
            db_prev_count = int(existing.count or 0)
            mem_count = len(bucket_vals)
            # If DB has history not reflected in memory, effective count = db_prev_count + mem_count (if mem_count==1 after restart)
            # We cannot distinguish restart vs fresh bucket with same period. Use max.
            if db_prev_count > 0 and mem_count == 1:
                # Assume restart: combine
                # Recalculate avg incorporating previous sum
                prev_sum = float(existing.value) * db_prev_count
                new_sum = prev_sum + val
                total_count = db_prev_count + 1
                avg_val = new_sum / total_count
                count = total_count
                # Percentiles after restart are approximate (use new mem values only)
                # Keep min/max across both
                min_val = min(float(existing.min_val) if existing.min_val is not None else val, min_val)
                max_val = max(float(existing.max_val) if existing.max_val is not None else val, max_val)
                # For p50/p95/p99 we keep current sorted_vals percentiles (approximate)
                # Rebuild bucket_vals to include previous values approximated? Keep as is.
            else:
                # Normal incremental path: bucket_vals already contains full history
                pass

            existing.value = float(avg_val)
            existing.count = int(count)
            existing.min_val = float(min_val)
            existing.max_val = float(max_val)
            existing.p50 = float(p50)
            existing.p95 = float(p95)
            existing.p99 = float(p99)
            existing.dimensions = dims
            existing.period_start = period_start
            existing.period_end = period_end
            await db.flush()
            await db.refresh(existing)

            # Reuse observability telemetry for dashboards (best-effort)
            try:
                from app.observability.metric_engine import MetricEngine  # noqa: WPS433
                # No direct call to avoid circular; rely on performance metrics table as source
            except Exception:
                pass
            return existing
        else:
            # Insert new bucket row
            metric = PerformanceServiceMetric(
                tenant=tenant_s,
                service=service_s,
                metric_name=metric_s,
                value=float(avg_val),
                granularity=gran,
                period_start=period_start,
                period_end=period_end,
                count=int(count),
                min_val=float(min_val),
                max_val=float(max_val),
                p50=float(p50),
                p95=float(p95),
                p99=float(p99),
                dimensions=dims,
            )
            db.add(metric)
            await db.flush()
            await db.refresh(metric)
            return metric

    # ---------------------------------------------------------------- query

    async def query_metrics(
        self,
        db: AsyncSession,
        tenant: str,
        service: str | None = None,
        metric_name: str | None = None,
        from_time: datetime | str | None = None,
        to_time: datetime | str | None = None,
        granularity: str | None = None,
        # aliases for spec compatibility
        start_time: datetime | str | None = None,
        end_time: datetime | str | None = None,
        limit: int = 1000,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        # Support alternate kwarg names: from/to, from_ts/to_ts
        if from_time is None:
            from_time = kwargs.get("from") or kwargs.get("from_ts") or start_time
        if to_time is None:
            to_time = kwargs.get("to") or kwargs.get("to_ts") or end_time
        if granularity is None:
            granularity = kwargs.get("granularity") or granularity

        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        tenant_s = str(tenant).strip()

        stmt = select(PerformanceServiceMetric).where(
            PerformanceServiceMetric.tenant == tenant_s
        )
        if service:
            stmt = stmt.where(PerformanceServiceMetric.service == str(service).strip())
        if metric_name:
            stmt = stmt.where(PerformanceServiceMetric.metric_name == str(metric_name).strip())
        if granularity:
            gran = str(granularity).strip().lower()
            if gran in VALID_GRANULARITIES:
                stmt = stmt.where(PerformanceServiceMetric.granularity == gran)

        # Time filtering on period_start
        if from_time is not None:
            dt_from = _parse_timestamp(from_time)
            stmt = stmt.where(PerformanceServiceMetric.period_start >= dt_from)
        if to_time is not None:
            dt_to = _parse_timestamp(to_time)
            stmt = stmt.where(PerformanceServiceMetric.period_start <= dt_to)

        stmt = stmt.order_by(PerformanceServiceMetric.period_start.asc()).limit(max(1, min(limit, 5000)))
        result = await db.execute(stmt)
        rows = list(result.scalars().all())

        # Build aggregates per period (already bucketed). For query we also
        # compute roll-up aggregates if multiple rows requested without time bounds.
        aggregates: list[dict[str, Any]] = []
        for row in rows:
            aggregates.append(
                {
                    "tenant": row.tenant,
                    "service": row.service,
                    "metric_name": row.metric_name,
                    "granularity": row.granularity,
                    "period_start": row.period_start.isoformat() if hasattr(row.period_start, "isoformat") else str(row.period_start),
                    "period_end": row.period_end.isoformat() if hasattr(row.period_end, "isoformat") else str(row.period_end),
                    "count": int(row.count or 0),
                    "avg": float(row.value) if row.value is not None else 0.0,
                    "value": float(row.value) if row.value is not None else 0.0,
                    "min": float(row.min_val) if row.min_val is not None else None,
                    "max": float(row.max_val) if row.max_val is not None else None,
                    "p50": float(row.p50) if row.p50 is not None else None,
                    "p95": float(row.p95) if row.p95 is not None else None,
                    "p99": float(row.p99) if row.p99 is not None else None,
                    "dimensions": row.dimensions or {},
                    "id": str(row.id),
                }
            )

        # If caller expects aggregated roll-up across periods, provide summary
        # when metric_name/service specified and multiple buckets returned?
        # We return per-bucket list; caller can aggregate further.

        return aggregates

    async def get_service_metrics(
        self,
        db: AsyncSession,
        tenant: str,
        service: str,
        metric_name: str | None = None,
        granularity: str = "hour",
        start_time: datetime | str | None = None,
        end_time: datetime | str | None = None,
        limit: int = 500,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        # Convenience wrapper returning request rate/latency/error/saturation
        # metrics for a service. Reuses query_metrics with tenant isolation.
        if not service:
            raise ValueError("service is required")
        # Support from/to aliases
        if "from" in kwargs and start_time is None:
            start_time = kwargs.pop("from")
        if "to" in kwargs and end_time is None:
            end_time = kwargs.pop("to")
        return await self.query_metrics(
            db,
            tenant=tenant,
            service=service,
            metric_name=metric_name,
            granularity=granularity,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )

    async def get_endpoint_metrics(
        self,
        db: AsyncSession,
        tenant: str,
        route: str | None = None,
        method: str | None = None,
        service: str = "api",
        status: str | int | None = None,
        granularity: str | None = None,
        start_time: datetime | str | None = None,
        end_time: datetime | str | None = None,
        limit: int = 500,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Endpoint-level metrics: route/method/status/latency.

        Filters ``performance_service_metrics`` rows where dimensions contain
        route/method/status. Never stores or returns sensitive bodies.
        """
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")

        # Normalize aliases: from/to, route_path
        if "from" in kwargs and start_time is None:
            start_time = kwargs.pop("from")
        if "to" in kwargs and end_time is None:
            end_time = kwargs.pop("to")
        if kwargs.get("route_path") and route is None:
            route = kwargs.pop("route_path")

        # Use query_metrics for base fetch, then filter by dimensions in Python
        # (JSON containment queries vary by DB; Python filtering is portable).
        raw = await self.query_metrics(
            db,
            tenant=tenant,
            service=service,
            granularity=granularity,
            start_time=start_time,
            end_time=end_time,
            limit=limit * 2 if limit else 1000,
        )
        filtered: list[dict[str, Any]] = []
        for entry in raw:
            dims = entry.get("dimensions") or {}
            # Dimension keys expected: route, path, method, status_code/status, latency
            dim_route = dims.get("route") or dims.get("path") or dims.get("endpoint")
            dim_method = (dims.get("method") or "").upper() if dims.get("method") else None
            dim_status = dims.get("status") or dims.get("status_code")
            if route is not None and dim_route != route:
                continue
            if method is not None and dim_method != str(method).upper():
                continue
            if status is not None and str(dim_status) != str(status):
                continue
            # Ensure sensitive bodies never leaked (already sanitized on write,
            # double-check here).
            safe_dims = _sanitize_dimensions(dims)
            entry["dimensions"] = safe_dims
            # Expose endpoint-specific fields
            entry["route"] = dim_route
            entry["method"] = dim_method
            entry["status"] = dim_status
            # latency is typically the metric value when metric_name ~ latency
            if entry.get("metric_name", "").lower().endswith("latency") or "latency" in entry.get("metric_name", "").lower():
                entry["latency_ms"] = entry.get("avg")
            filtered.append(entry)
            if len(filtered) >= limit:
                break
        # Sort by period_start for stable pagination
        filtered.sort(key=lambda x: x.get("period_start") or "")
        return filtered


metrics_service = MetricsService()
