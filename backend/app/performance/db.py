"""Volume 61 Commit 1 — DBMetricsService (DB-backed, tenant-isolated).

Records per-query metrics to ``performance_service_metrics`` (service=db),
tracks pool status via in-memory + ``performance_snapshots`` best-effort,
detects slow queries, and produces index recommendations with evidence.
Never auto-creates indexes without approval.
"""

from __future__ import annotations

import hashlib
import uuid
from collections import defaultdict, Counter
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.performance.models import (
    PerformanceRecommendation,
    PerformanceServiceMetric,
    PerformanceSnapshot,
)

SLOW_THRESHOLD_MS_DEFAULT = 500.0
POOL_METRIC_NAMES = {
    "pool_active": "db_pool_active",
    "pool_idle": "db_pool_idle",
    "pool_waiting": "db_pool_waiting",
    "locks": "db_locks",
    "deadlocks": "db_deadlocks",
    "cache_hit_rate": "db_cache_hit_rate",
}

# In-memory caches for quick retrieval (tenant-scoped, bounded)
_QUERY_HISTORY: dict[str, list[dict[str, Any]]] = defaultdict(list)
_POOL_SNAPSHOT: dict[str, dict[str, Any]] = {}
_MAX_HISTORY_PER_TENANT = 2000


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _tenant_key(tenant: str) -> str:
    return str(tenant).strip()


def _hash_query(query_hash: str | None, fallback: str = "") -> str:
    if query_hash and str(query_hash).strip():
        return str(query_hash).strip()[:128]
    return hashlib.sha256(fallback.encode()).hexdigest()[:16]


class DBMetricsService:
    """Database performance metrics and recommendations."""

    # ---------------------------------------------------------------- record

    async def record_query(
        self,
        db: AsyncSession,
        tenant: str,
        query_hash: str,
        duration_ms: float,
        pool_active: int | None = None,
        pool_idle: int | None = None,
        pool_waiting: int | None = None,
        locks: int | None = None,
        deadlocks: int | None = None,
        cache_hit_rate: float | None = None,
        # optional enrichments (ignored if sensitive)
        query: str | None = None,
        table: str | None = None,
        **kwargs: Any,
    ) -> PerformanceServiceMetric:
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        if not isinstance(duration_ms, (int, float)) or isinstance(duration_ms, bool):
            raise ValueError("duration_ms must be a number")
        if float(duration_ms) < 0:
            raise ValueError("duration_ms must be >= 0")

        tenant_s = _tenant_key(tenant)
        qhash = _hash_query(query_hash, fallback=str(query or table or "unknown"))
        ts = _utcnow()
        period_start = ts.replace(second=0, microsecond=0)
        period_end = period_start.replace(microsecond=0) + __import__("datetime").timedelta(minutes=1)

        # Persist query duration as performance_service_metrics row
        # Use metric_name=db_query_duration with dimensions containing qhash.
        # Pool metrics are also persisted as separate metric_names for get_pool_status aggregation.
        dims: dict[str, Any] = {
            "query_hash": qhash,
            "duration_ms": float(duration_ms),
        }
        if table:
            dims["table"] = str(table)[:128]
        # Include pool snapshot in dimensions for correlation, but also persist separately
        if pool_active is not None:
            dims["pool_active"] = int(pool_active)
        if pool_idle is not None:
            dims["pool_idle"] = int(pool_idle)
        if pool_waiting is not None:
            dims["pool_waiting"] = int(pool_waiting)
        if locks is not None:
            dims["locks"] = int(locks)
        if deadlocks is not None:
            dims["deadlocks"] = int(deadlocks)
        if cache_hit_rate is not None:
            dims["cache_hit_rate"] = float(cache_hit_rate)

        # Never store raw query body if it looks sensitive / too large
        # (we only store hash + optional table excerpt, not full SQL)
        if query and len(str(query)) < 500 and "password" not in str(query).lower():
            # Store truncated, non-sensitive prefix for evidence (optional)
            dims["query_prefix"] = str(query)[:200]

        metric = PerformanceServiceMetric(
            tenant=tenant_s,
            service="db",
            metric_name="db_query_duration",
            value=float(duration_ms),
            granularity="minute",
            period_start=period_start,
            period_end=period_end,
            count=1,
            min_val=float(duration_ms),
            max_val=float(duration_ms),
            p50=float(duration_ms),
            p95=float(duration_ms),
            p99=float(duration_ms),
            dimensions=dims,
        )
        db.add(metric)
        await db.flush()
        await db.refresh(metric)

        # Also persist pool status as performance_snapshots row (best-effort)
        try:
            snap = PerformanceSnapshot(
                tenant=tenant_s,
                resource=f"db_pool:{tenant_s}",
                resource_type="database",
                cpu=float(cache_hit_rate) if cache_hit_rate is not None else None,
                memory=float(locks) if locks is not None else None,
                queue_depth=int(pool_waiting) if pool_waiting is not None else None,
                concurrency=int(pool_active) if pool_active is not None else None,
                storage=float(pool_idle) if pool_idle is not None else None,
                db_load=float(duration_ms),
            )
            db.add(snap)
            await db.flush()
        except Exception:
            pass

        # Update in-memory history (bounded, tenant-isolated)
        hist = _QUERY_HISTORY[tenant_s]
        hist.append(
            {
                "query_hash": qhash,
                "duration_ms": float(duration_ms),
                "pool_active": pool_active,
                "pool_idle": pool_idle,
                "pool_waiting": pool_waiting,
                "locks": locks,
                "deadlocks": deadlocks,
                "cache_hit_rate": cache_hit_rate,
                "table": table,
                "timestamp": ts.isoformat(),
                "metric_id": str(metric.id),
            }
        )
        if len(hist) > _MAX_HISTORY_PER_TENANT:
            # Keep most recent
            _QUERY_HISTORY[tenant_s] = hist[-_MAX_HISTORY_PER_TENANT:]

        # Update latest pool snapshot for get_pool_status
        _POOL_SNAPSHOT[tenant_s] = {
            "tenant": tenant_s,
            "pool_active": int(pool_active) if pool_active is not None else 0,
            "pool_idle": int(pool_idle) if pool_idle is not None else 0,
            "pool_waiting": int(pool_waiting) if pool_waiting is not None else 0,
            "locks": int(locks) if locks is not None else 0,
            "deadlocks": int(deadlocks) if deadlocks is not None else 0,
            "cache_hit_rate": float(cache_hit_rate) if cache_hit_rate is not None else None,
            "last_query_hash": qhash,
            "last_duration_ms": float(duration_ms),
            "updated_at": ts.isoformat(),
        }

        # Optionally push to observability telemetry (best-effort reuse)
        try:
            from app.observability.service import svc as _obs  # noqa: WPS433
            if hasattr(_obs, "metrics"):
                _obs.metrics.ingest("db.query_duration", float(duration_ms), {"tenant": tenant_s, "query_hash": qhash})
        except Exception:
            pass

        return metric

    # ---------------------------------------------------------------- slow queries

    async def get_slow_queries(
        self,
        db: AsyncSession,
        tenant: str,
        threshold_ms: float = SLOW_THRESHOLD_MS_DEFAULT,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        tenant_s = _tenant_key(tenant)
        thr = float(threshold_ms)
        lim = max(1, min(int(limit), 100))
        off = max(0, int(offset))

        stmt = (
            select(PerformanceServiceMetric)
            .where(
                PerformanceServiceMetric.tenant == tenant_s,
                PerformanceServiceMetric.service == "db",
                PerformanceServiceMetric.metric_name == "db_query_duration",
                PerformanceServiceMetric.value >= thr,
            )
            .order_by(PerformanceServiceMetric.value.desc())
            .offset(off)
            .limit(lim)
        )
        result = await db.execute(stmt)
        rows = list(result.scalars().all())
        out: list[dict[str, Any]] = []
        for row in rows:
            dims = row.dimensions or {}
            out.append(
                {
                    "id": str(row.id),
                    "tenant": row.tenant,
                    "query_hash": dims.get("query_hash"),
                    "duration_ms": float(row.value),
                    "table": dims.get("table"),
                    "pool_active": dims.get("pool_active"),
                    "pool_waiting": dims.get("pool_waiting"),
                    "cache_hit_rate": dims.get("cache_hit_rate"),
                    "period_start": row.period_start.isoformat() if hasattr(row.period_start, "isoformat") else str(row.period_start),
                    "dimensions": dims,
                }
            )
        # Fallback to in-memory history if DB empty (e.g., before flush)
        if not out:
            hist = [h for h in _QUERY_HISTORY.get(tenant_s, []) if float(h.get("duration_ms", 0)) >= thr]
            hist.sort(key=lambda x: float(x.get("duration_ms", 0)), reverse=True)
            for h in hist[off : off + lim]:
                out.append({**h, "source": "memory"})
        return out

    # ---------------------------------------------------------------- recommendations

    async def recommend_indexes(
        self,
        db: AsyncSession,
        tenant: str,
        threshold_ms: float = SLOW_THRESHOLD_MS_DEFAULT,
        min_occurrences: int = 3,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Generate candidate index recommendations with evidence.

        Never auto-creates indexes — returns candidates with evidence and
        persists them as ``performance_recommendations`` with type=index and
        status=open for human approval.
        """
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        tenant_s = _tenant_key(tenant)
        slow = await self.get_slow_queries(db, tenant_s, threshold_ms=threshold_ms, limit=200)

        # Group by query_hash / table
        by_hash: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for entry in slow:
            qh = entry.get("query_hash") or entry.get("dimensions", {}).get("query_hash") or "unknown"
            by_hash[str(qh)].append(entry)

        candidates: list[dict[str, Any]] = []
        for qhash, entries in by_hash.items():
            if len(entries) < int(min_occurrences):
                continue
            # Evidence: avg duration, p95, count, tables
            durations = [float(e.get("duration_ms") or e.get("dimensions", {}).get("duration_ms", 0)) for e in entries]
            durations.sort()
            avg = sum(durations) / len(durations) if durations else 0
            p95_idx = min(int(len(durations) * 0.95), len(durations) - 1) if durations else 0
            p95 = durations[p95_idx] if durations else 0
            tables = list({e.get("table") or e.get("dimensions", {}).get("table") for e in entries if e.get("table") or e.get("dimensions", {}).get("table")})
            # Heuristic: suggest index on table if not already present
            # We synthesize column candidates from hash/tables; real system would parse SQL.
            table = tables[0] if tables else f"table_{qhash[:6]}"
            # Evidence includes cache hit rate and locks
            avg_cache_hit = None
            hit_rates = [float(e.get("cache_hit_rate") or e.get("dimensions", {}).get("cache_hit_rate", 0)) for e in entries if e.get("cache_hit_rate") is not None or e.get("dimensions", {}).get("cache_hit_rate") is not None]
            if hit_rates:
                avg_cache_hit = sum(hit_rates) / len(hit_rates)

            evidence = {
                "query_hash": qhash,
                "occurrences": len(entries),
                "avg_duration_ms": round(avg, 2),
                "p95_duration_ms": round(float(p95), 2),
                "max_duration_ms": round(max(durations) if durations else 0, 2),
                "tables": tables,
                "table": table,
                "avg_cache_hit_rate": round(float(avg_cache_hit), 3) if avg_cache_hit is not None else None,
                "threshold_ms": float(threshold_ms),
                "period": "recent",
                "candidate_reason": "repeated slow queries (> threshold) grouped by query_hash",
            }

            # Candidate index definition (never auto-executed)
            candidate = {
                "id": str(uuid.uuid4()),
                "tenant": tenant_s,
                "type": "index",
                "resource": f"{table}.idx_{qhash[:8]}",
                "table": table,
                "columns": ["created_at", "tenant"],  # generic evidence-based placeholder; real would parse WHERE clause
                "query_hash": qhash,
                "evidence": evidence,
                "status": "open",
                "requires_approval": True,
                "auto_create": False,
                "ddl_preview": f"CREATE INDEX CONCURRENTLY idx_{qhash[:8]} ON {table} (tenant, created_at); -- requires approval",
            }

            # Persist as PerformanceRecommendation (best-effort, additive)
            try:
                rec = PerformanceRecommendation(
                    tenant=tenant_s,
                    type="index",
                    resource=candidate["resource"],
                    evidence=evidence,
                    status="open",
                )
                db.add(rec)
                await db.flush()
                candidate["recommendation_id"] = str(rec.id)
            except Exception:
                candidate["recommendation_id"] = None

            candidates.append(candidate)
            if len(candidates) >= int(limit):
                break

        # Sort by avg_duration desc (most impactful first)
        candidates.sort(key=lambda c: c["evidence"].get("avg_duration_ms", 0), reverse=True)
        return candidates

    # ---------------------------------------------------------------- pool

    async def get_pool_status(
        self,
        db: AsyncSession,
        tenant: str,
    ) -> dict[str, Any]:
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        tenant_s = _tenant_key(tenant)

        # Prefer in-memory latest snapshot (most recent)
        mem = _POOL_SNAPSHOT.get(tenant_s)
        if mem:
            # Enrich with DB snapshot if available
            try:
                stmt = (
                    select(PerformanceSnapshot)
                    .where(
                        PerformanceSnapshot.tenant == tenant_s,
                        PerformanceSnapshot.resource == f"db_pool:{tenant_s}",
                    )
                    .order_by(PerformanceSnapshot.created_at.desc())
                    .limit(1)
                )
                result = await db.execute(stmt)
                snap = result.scalars().first()
                if snap:
                    db_pool = {
                        "pool_active": int(snap.concurrency) if snap.concurrency is not None else mem.get("pool_active"),
                        "pool_idle": int(snap.storage) if snap.storage is not None else mem.get("pool_idle"),
                        "pool_waiting": int(snap.queue_depth) if snap.queue_depth is not None else mem.get("pool_waiting"),
                        "locks": int(snap.memory) if snap.memory is not None else mem.get("locks"),
                        "cache_hit_rate": float(snap.cpu) if snap.cpu is not None else mem.get("cache_hit_rate"),
                        "db_load": float(snap.db_load) if snap.db_load is not None else None,
                        "snapshot_at": snap.created_at.isoformat() if hasattr(snap.created_at, "isoformat") else str(snap.created_at),
                    }
                    return {**mem, "db_snapshot": db_pool, "source": "memory+db"}
            except Exception:
                pass
            return {**mem, "source": "memory"}

        # Fallback to DB lookup
        try:
            stmt = (
                select(PerformanceSnapshot)
                .where(
                    PerformanceSnapshot.tenant == tenant_s,
                    PerformanceSnapshot.resource == f"db_pool:{tenant_s}",
                )
                .order_by(PerformanceSnapshot.created_at.desc())
                .limit(1)
            )
            result = await db.execute(stmt)
            snap = result.scalars().first()
            if snap:
                return {
                    "tenant": tenant_s,
                    "pool_active": int(snap.concurrency or 0),
                    "pool_idle": int(snap.storage or 0) if snap.storage is not None else 0,
                    "pool_waiting": int(snap.queue_depth or 0) if snap.queue_depth is not None else 0,
                    "locks": int(snap.memory or 0) if snap.memory is not None else 0,
                    "deadlocks": 0,
                    "cache_hit_rate": float(snap.cpu) if snap.cpu is not None else None,
                    "db_load": float(snap.db_load) if snap.db_load is not None else None,
                    "snapshot_at": snap.created_at.isoformat() if hasattr(snap.created_at, "isoformat") else str(snap.created_at),
                    "source": "db",
                }
        except Exception:
            pass

        # No data yet
        return {
            "tenant": tenant_s,
            "pool_active": 0,
            "pool_idle": 0,
            "pool_waiting": 0,
            "locks": 0,
            "deadlocks": 0,
            "cache_hit_rate": None,
            "updated_at": None,
            "source": "empty",
        }


db_metrics_service = DBMetricsService()
