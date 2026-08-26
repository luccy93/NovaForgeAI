"""Volume 61 Commit 1 — QueueMetricsService (DB-backed, tenant-isolated).

Tracks DistributedQueue depth/lag/processing_rate/retry/dead_letters with
backpressure detection. Persists to ``performance_service_metrics``
(service=queue) and ``performance_snapshots`` (queue_depth).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import Any
from collections import defaultdict, deque

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.performance.models import PerformanceServiceMetric, PerformanceSnapshot


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# In-memory queue state (tenant-isolated, bounded)
_QUEUE_STATE: dict[str, dict[str, Any]] = {}
# Per-queue timestamped history for rate/lag calculation
_QUEUE_TIMESTAMPS: dict[str, deque[datetime]] = defaultdict(lambda: deque(maxlen=2000))
_QUEUE_PROCESSED_TS: dict[str, deque[datetime]] = defaultdict(lambda: deque(maxlen=2000))
_MAX_TENANT_QUEUES = 50
_BACKPRESSURE_DEPTH_THRESHOLD = 1000
_BACKPRESSURE_LAG_THRESHOLD_S = 60.0


def _qkey(tenant: str, queue_name: str) -> str:
    return f"{str(tenant).strip()}:{str(queue_name).strip()}"


def _ensure_state(tenant: str, queue_name: str) -> dict[str, Any]:
    tenant_s = str(tenant).strip()
    qname = str(queue_name).strip()
    key = _qkey(tenant_s, qname)
    if key not in _QUEUE_STATE:
        # Enforce bounded number of queues per tenant (avoid unbounded growth)
        tenant_queues = [k for k in _QUEUE_STATE if k.startswith(f"{tenant_s}:")]
        if len(tenant_queues) >= _MAX_TENANT_QUEUES:
            # Evict oldest
            oldest = sorted(tenant_queues, key=lambda k: _QUEUE_STATE[k].get("created_at", ""))[0]
            _QUEUE_STATE.pop(oldest, None)
            _QUEUE_TIMESTAMPS.pop(oldest, None)
            _QUEUE_PROCESSED_TS.pop(oldest, None)
        _QUEUE_STATE[key] = {
            "tenant": tenant_s,
            "queue_name": qname,
            "depth": 0,
            "enqueued_total": 0,
            "processed_total": 0,
            "processing_rate": 0.0,
            "retry_total": 0,
            "dead_letters": 0,
            "lag_seconds": 0.0,
            "created_at": _utcnow().isoformat(),
            "updated_at": _utcnow().isoformat(),
        }
    return _QUEUE_STATE[key]


async def _persist_queue_metric(
    db: AsyncSession,
    tenant: str,
    queue_name: str,
    metric_name: str,
    value: float,
    dimensions: dict | None = None,
) -> None:
    try:
        ts = _utcnow()
        period_start = ts.replace(second=0, microsecond=0)
        period_end = period_start + timedelta(minutes=1)
        dims = {"queue": str(queue_name)[:64], **(dimensions or {})}
        m = PerformanceServiceMetric(
            tenant=str(tenant).strip(),
            service="queue",
            metric_name=str(metric_name),
            value=float(value),
            granularity="minute",
            period_start=period_start,
            period_end=period_end,
            count=1,
            min_val=float(value),
            max_val=float(value),
            p50=float(value),
            p95=float(value),
            p99=float(value),
            dimensions=dims,
        )
        db.add(m)
        await db.flush()
        # Also snapshot queue depth for capacity planning
        if metric_name == "queue_depth":
            snap = PerformanceSnapshot(
                tenant=str(tenant).strip(),
                resource=str(queue_name)[:128],
                resource_type="queue",
                queue_depth=int(value),
                concurrency=None,
            )
            db.add(snap)
            await db.flush()
    except Exception:
        pass


class QueueMetricsService:
    """Tenant-isolated queue health tracking."""

    async def record_enqueue(
        self,
        db: AsyncSession,
        tenant: str,
        queue_name: str,
        job_id: str | None = None,
        priority: str | None = None,
        payload_size: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        if not queue_name or not str(queue_name).strip():
            raise ValueError("queue_name is required")
        tenant_s = str(tenant).strip()
        qname = str(queue_name).strip()
        state = _ensure_state(tenant_s, qname)
        state["depth"] = int(state.get("depth", 0)) + 1
        state["enqueued_total"] = int(state.get("enqueued_total", 0)) + 1
        state["updated_at"] = _utcnow().isoformat()

        # Track timestamp for lag/rate
        key = _qkey(tenant_s, qname)
        now = _utcnow()
        _QUEUE_TIMESTAMPS[key].append(now)

        # Persist depth metric
        await _persist_queue_metric(db, tenant_s, qname, "queue_depth", float(state["depth"]), dimensions={"job_id": str(job_id)[:36] if job_id else None, "priority": str(priority)[:16] if priority else None})
        await _persist_queue_metric(db, tenant_s, qname, "queue_enqueue", 1.0, dimensions={"priority": str(priority)[:16] if priority else "NORMAL"})

        return {
            "tenant": tenant_s,
            "queue_name": qname,
            "job_id": str(job_id) if job_id else str(uuid.uuid4()),
            "depth": state["depth"],
            "enqueued_total": state["enqueued_total"],
            "at": now.isoformat(),
        }

    async def record_processed(
        self,
        db: AsyncSession,
        tenant: str,
        queue_name: str,
        job_id: str | None = None,
        duration_ms: float | None = None,
        success: bool = True,
        retry_count: int = 0,
        dead_letter: bool = False,
        error: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        if not queue_name or not str(queue_name).strip():
            raise ValueError("queue_name is required")
        tenant_s = str(tenant).strip()
        qname = str(queue_name).strip()
        state = _ensure_state(tenant_s, qname)
        # Depth decrements but never below 0
        state["depth"] = max(0, int(state.get("depth", 0)) - 1)
        state["processed_total"] = int(state.get("processed_total", 0)) + 1
        if int(retry_count) > 0:
            state["retry_total"] = int(state.get("retry_total", 0)) + int(retry_count)
        if dead_letter:
            state["dead_letters"] = int(state.get("dead_letters", 0)) + 1
        state["updated_at"] = _utcnow().isoformat()

        key = _qkey(tenant_s, qname)
        now = _utcnow()
        _QUEUE_PROCESSED_TS[key].append(now)

        # Update processing rate (jobs per minute over last 60s)
        # Compute rate from processed timestamps in last minute
        cutoff = now - timedelta(seconds=60)
        recent = [t for t in _QUEUE_PROCESSED_TS[key] if t >= cutoff]
        rate_per_min = float(len(recent)) * (60.0 / 60.0)  # per minute
        state["processing_rate"] = rate_per_min

        # Update lag: time since oldest enqueued not yet processed (approximate)
        # Use oldest timestamp in enqueue deque that hasn't been processed
        # Simplified: lag = now - oldest enqueue ts if depth >0
        lag_s = 0.0
        if state["depth"] > 0 and _QUEUE_TIMESTAMPS[key]:
            oldest = _QUEUE_TIMESTAMPS[key][0]
            lag_s = (now - oldest).total_seconds()
            # Trim deque to approximate depth size (keep depth items)
            while len(_QUEUE_TIMESTAMPS[key]) > state["depth"]:
                _QUEUE_TIMESTAMPS[key].popleft()
        state["lag_seconds"] = round(lag_s, 2)

        # Persist metrics
        await _persist_queue_metric(db, tenant_s, qname, "queue_depth", float(state["depth"]))
        await _persist_queue_metric(db, tenant_s, qname, "queue_processed", 1.0, dimensions={"success": bool(success), "dead_letter": bool(dead_letter)})
        if duration_ms is not None:
            await _persist_queue_metric(db, tenant_s, qname, "queue_processing_latency_ms", float(duration_ms))
        if dead_letter:
            await _persist_queue_metric(db, tenant_s, qname, "queue_dead_letter", 1.0)
        if retry_count:
            await _persist_queue_metric(db, tenant_s, qname, "queue_retry", float(retry_count))

        return {
            "tenant": tenant_s,
            "queue_name": qname,
            "job_id": str(job_id) if job_id else None,
            "depth": state["depth"],
            "processed_total": state["processed_total"],
            "processing_rate_per_min": rate_per_min,
            "lag_seconds": state["lag_seconds"],
            "success": bool(success),
            "dead_letter": bool(dead_letter),
            "at": now.isoformat(),
        }

    async def get_queue_health(
        self,
        db: AsyncSession,
        tenant: str,
        queue_name: str | None = None,
        include_all: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Return health for one queue or all queues for tenant.

        Returns ``depth, lag_seconds, processing_rate, retry_total, dead_letters``
        with backpressure detection:

        - backpressure = depth > 1000 OR lag > 60s OR enqueue_rate > processing_rate*1.5
        """
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        tenant_s = str(tenant).strip()

        # Support alternate param name: queue or name
        if queue_name is None:
            queue_name = kwargs.get("queue") or kwargs.get("name")

        if queue_name:
            # Single queue
            state = _ensure_state(tenant_s, str(queue_name))
            key = _qkey(tenant_s, str(queue_name))
            # Refresh rate/lag calculations
            now = _utcnow()
            cutoff = now - timedelta(seconds=60)
            recent_processed = [t for t in _QUEUE_PROCESSED_TS[key] if t >= cutoff]
            recent_enqueued = [t for t in _QUEUE_TIMESTAMPS[key] if t >= cutoff]
            processing_rate = float(len(recent_processed))
            enqueue_rate = float(len(recent_enqueued))
            lag = float(state.get("lag_seconds", 0.0))
            depth = int(state.get("depth", 0))

            # Backpressure detection
            backpressure = False
            reason: str | None = None
            if depth >= _BACKPRESSURE_DEPTH_THRESHOLD:
                backpressure = True
                reason = f"depth {depth} >= {_BACKPRESSURE_DEPTH_THRESHOLD}"
            elif lag >= _BACKPRESSURE_LAG_THRESHOLD_S:
                backpressure = True
                reason = f"lag {lag:.1f}s >= {_BACKPRESSURE_LAG_THRESHOLD_S}s"
            elif enqueue_rate > 0 and processing_rate > 0 and enqueue_rate > processing_rate * 1.5:
                backpressure = True
                reason = f"enqueue_rate {enqueue_rate}/min > 1.5*processing_rate {processing_rate}/min"
            elif enqueue_rate > 0 and processing_rate == 0 and depth > 0:
                backpressure = True
                reason = "processing stalled (0/min) while enqueues arrive"

            # Try DB fallback for depth if memory empty
            if depth == 0 and not _QUEUE_TIMESTAMPS[key] and not _QUEUE_PROCESSED_TS[key]:
                try:
                    stmt = (
                        select(PerformanceServiceMetric)
                        .where(
                            PerformanceServiceMetric.tenant == tenant_s,
                            PerformanceServiceMetric.service == "queue",
                            PerformanceServiceMetric.metric_name == "queue_depth",
                        )
                        .order_by(PerformanceServiceMetric.period_start.desc())
                        .limit(5)
                    )
                    if queue_name:
                        # Filter by dimensions queue name (Python side due to JSON)
                        pass
                    result = await db.execute(stmt)
                    rows = list(result.scalars().all())
                    for row in rows:
                        dims = row.dimensions or {}
                        if dims.get("queue") == str(queue_name).strip():
                            depth = int(row.value)
                            state["depth"] = depth
                            break
                except Exception:
                    pass

            health = {
                "tenant": tenant_s,
                "queue_name": str(queue_name).strip(),
                "depth": depth,
                "lag_seconds": round(lag, 2),
                "processing_rate_per_min": round(processing_rate, 2),
                "enqueue_rate_per_min": round(enqueue_rate, 2),
                "retry_total": int(state.get("retry_total", 0)),
                "dead_letters": int(state.get("dead_letters", 0)),
                "enqueued_total": int(state.get("enqueued_total", 0)),
                "processed_total": int(state.get("processed_total", 0)),
                "backpressure": backpressure,
                "backpressure_reason": reason,
                "updated_at": state.get("updated_at"),
                "checked_at": now.isoformat(),
            }
            return health
        else:
            # All queues for tenant
            keys = [k for k in _QUEUE_STATE if k.startswith(f"{tenant_s}:")]
            if not keys and include_all:
                # Try DB enumeration
                try:
                    stmt = (
                        select(PerformanceServiceMetric.dimensions)
                        .where(
                            PerformanceServiceMetric.tenant == tenant_s,
                            PerformanceServiceMetric.service == "queue",
                        )
                        .limit(100)
                    )
                    result = await db.execute(stmt)
                    # Fallback to memory empty list
                except Exception:
                    pass
                return []
            results: list[dict[str, Any]] = []
            for k in keys:
                qname = k.split(":", 1)[1] if ":" in k else k
                h = await self.get_queue_health(db, tenant_s, queue_name=qname)
                if isinstance(h, dict):
                    results.append(h)
            # Overall backpressure if any queue has it
            any_bp = any(r.get("backpressure") for r in results)
            return {
                "tenant": tenant_s,
                "queues": results,
                "queue_count": len(results),
                "any_backpressure": any_bp,
                "checked_at": _utcnow().isoformat(),
            }


queue_metrics_service = QueueMetricsService()
