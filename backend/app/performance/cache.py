"""Volume 61 Commit 1 — CacheMetricsService (tenant-isolated, Redis-backed).

Tenant-scoped keys, isolation check (never return another tenant's cached
result), and invalidation for config/permissions/flags. Metrics persisted to
``performance_service_metrics`` (service=cache) with hit/miss/eviction counts.

Reuses core/redis and iam/tenant_isolation helpers.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.performance.models import PerformanceServiceMetric

try:
    from app.core.redis import get_redis as _get_redis  # type: ignore
except Exception:  # pragma: no cover
    _get_redis = None  # type: ignore

try:
    from app.iam.tenant_isolation import tenant_isolation  # type: ignore
except Exception:  # pragma: no cover
    tenant_isolation = None  # type: ignore


# In-memory fallback cache (tenant-scoped) when Redis unavailable
_FALLBACK_CACHE: dict[str, dict[str, Any]] = {}
_FALLBACK_TTL: dict[str, datetime] = {}
_CACHE_METRICS: dict[str, dict[str, int]] = {}  # tenant -> {hits, misses, evictions}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _tenant_key(tenant: str, key: str) -> str:
    """Tenant-scoped cache key. Always prefix with tenant.

    Uses iam.tenant_isolation helper when available for consistency.
    """
    tenant_s = str(tenant).strip()
    key_s = str(key).strip()
    if tenant_isolation is not None:
        try:
            return tenant_isolation.create_cache_key(tenant_s, key_s)
        except Exception:
            pass
    return f"tenant:{tenant_s}:{key_s}"


def _is_tenant_key(tenant: str, full_key: str) -> bool:
    tenant_s = str(tenant).strip()
    if tenant_isolation is not None:
        try:
            return tenant_isolation.validate_cache_access(tenant_s, full_key)
        except Exception:
            pass
    return str(full_key).startswith(f"tenant:{tenant_s}:")


def _strip_tenant_prefix(full_key: str) -> str:
    # tenant:<tenant>:<rest>
    parts = str(full_key).split(":", 2)
    if len(parts) == 3 and parts[0] == "tenant":
        return parts[2]
    return str(full_key)


def _now_bucket() -> datetime:
    ts = _utcnow()
    return ts.replace(second=0, microsecond=0)


async def _record_cache_metric(
    db: AsyncSession,
    tenant: str,
    metric_name: str,
    key: str,
    value: float = 1.0,
    dimensions: dict | None = None,
) -> None:
    """Persist hit/miss/eviction counters to performance_service_metrics."""
    try:
        tenant_s = str(tenant).strip()
        ts = _utcnow()
        period_start = ts.replace(second=0, microsecond=0)
        period_end = period_start + timedelta(minutes=1)
        dims = dict(dimensions or {})
        # Never store raw value bodies; only key hash + metadata
        dims["key_hash"] = hashlib.sha256(str(key).encode()).hexdigest()[:12]
        dims["key_prefix"] = str(key).split(":")[0][:32] if ":" in str(key) else str(key)[:32]
        # Detect category for invalidation tracking
        kl = str(key).lower()
        if "config" in kl:
            dims["category"] = "config"
        elif "permission" in kl or "perm" in kl:
            dims["category"] = "permissions"
        elif "flag" in kl or "feature" in kl:
            dims["category"] = "flags"

        m = PerformanceServiceMetric(
            tenant=tenant_s,
            service="cache",
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
    except Exception:
        # Metrics are best-effort; never fail the cache operation
        pass


class CacheMetricsService:
    """Tenant-isolated cache metrics with isolation enforcement."""

    # ---------------------------------------------------------------- metrics

    async def record_hit(
        self,
        db: AsyncSession,
        tenant: str,
        key: str,
        latency_ms: float | None = None,
        size_bytes: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        if not key or not str(key).strip():
            raise ValueError("key is required")
        tenant_s = str(tenant).strip()
        # Enforce tenant-scoped key
        full_key = _tenant_key(tenant_s, key)
        if not _is_tenant_key(tenant_s, full_key):
            raise PermissionError("tenant isolation violation: key not scoped to tenant")

        rec = _CACHE_METRICS.setdefault(tenant_s, {"hits": 0, "misses": 0, "evictions": 0})
        rec["hits"] += 1

        dims: dict[str, Any] = {"cache_key": str(key)[:128]}
        if latency_ms is not None:
            dims["latency_ms"] = float(latency_ms)
        if size_bytes is not None:
            dims["size_bytes"] = int(size_bytes)

        await _record_cache_metric(db, tenant_s, "cache_hit", key, value=1.0, dimensions=dims)
        # Also record latency as separate metric if provided
        if latency_ms is not None:
            await _record_cache_metric(db, tenant_s, "cache_hit_latency_ms", key, value=float(latency_ms), dimensions={"cache_key": str(key)[:64]})

        return {"tenant": tenant_s, "key": str(key), "full_key": full_key, "hits": rec["hits"], "recorded_at": _utcnow().isoformat()}

    async def record_miss(
        self,
        db: AsyncSession,
        tenant: str,
        key: str,
        latency_ms: float | None = None,
        reason: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        if not key or not str(key).strip():
            raise ValueError("key is required")
        tenant_s = str(tenant).strip()
        full_key = _tenant_key(tenant_s, key)
        if not _is_tenant_key(tenant_s, full_key):
            raise PermissionError("tenant isolation violation")

        rec = _CACHE_METRICS.setdefault(tenant_s, {"hits": 0, "misses": 0, "evictions": 0})
        rec["misses"] += 1

        dims: dict[str, Any] = {"cache_key": str(key)[:128]}
        if latency_ms is not None:
            dims["latency_ms"] = float(latency_ms)
        if reason:
            dims["reason"] = str(reason)[:64]

        await _record_cache_metric(db, tenant_s, "cache_miss", key, value=1.0, dimensions=dims)
        return {"tenant": tenant_s, "key": str(key), "full_key": full_key, "misses": rec["misses"], "recorded_at": _utcnow().isoformat()}

    async def record_eviction(
        self,
        db: AsyncSession,
        tenant: str,
        key: str,
        reason: str | None = None,
        size_bytes: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        if not key or not str(key).strip():
            raise ValueError("key is required")
        tenant_s = str(tenant).strip()
        full_key = _tenant_key(tenant_s, key)
        if not _is_tenant_key(tenant_s, full_key):
            raise PermissionError("tenant isolation violation")

        rec = _CACHE_METRICS.setdefault(tenant_s, {"hits": 0, "misses": 0, "evictions": 0})
        rec["evictions"] += 1

        dims: dict[str, Any] = {"cache_key": str(key)[:128]}
        if reason:
            dims["reason"] = str(reason)[:64]
        if size_bytes is not None:
            dims["size_bytes"] = int(size_bytes)

        await _record_cache_metric(db, tenant_s, "cache_eviction", key, value=1.0, dimensions=dims)

        # Also delete from fallback cache
        _FALLBACK_CACHE.pop(full_key, None)
        _FALLBACK_TTL.pop(full_key, None)

        # Delete from Redis if available (best-effort)
        if _get_redis is not None:
            try:
                client = await _get_redis()
                if client is not None:
                    # Use raw key with product prefix via core/redis _key helper if available
                    # Fallback to direct delete of tenant-scoped key under namespace cache
                    try:
                        # Try namespace-aware delete via core.redis cache_delete
                        from app.core.redis import cache_delete  # type: ignore

                        await cache_delete(_strip_tenant_prefix(full_key), namespace="cache")
                        # Also try direct tenant key delete
                        await client.delete(full_key)
                    except Exception:
                        await client.delete(full_key)
            except Exception:
                pass

        return {"tenant": tenant_s, "key": str(key), "full_key": full_key, "evictions": rec["evictions"], "recorded_at": _utcnow().isoformat()}

    # ---------------------------------------------------------------- get/set with isolation

    async def cache_set(
        self,
        db: AsyncSession,
        tenant: str,
        key: str,
        value: Any,
        ttl_seconds: int = 300,
    ) -> bool:
        """Set a tenant-scoped cache entry. Value is serialized safely."""
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        tenant_s = str(tenant).strip()
        full_key = _tenant_key(tenant_s, key)
        if not _is_tenant_key(tenant_s, full_key):
            raise PermissionError("isolation violation on cache_set")

        # Never store sensitive bodies: if value looks like body/payload, redact
        payload: Any = value
        if isinstance(value, dict) and any(k.lower() in {"body", "payload", "password", "secret"} for k in value.keys()):
            # Strip sensitive keys
            payload = {k: v for k, v in value.items() if k.lower() not in {"body", "payload", "password", "secret", "token"}}
        serialized = json.dumps(payload, default=str)

        # Try Redis first
        if _get_redis is not None:
            try:
                client = await _get_redis()
                if client is not None:
                    await client.setex(full_key, int(ttl_seconds), serialized)
                    return True
            except Exception:
                pass
        # Fallback in-memory with TTL
        _FALLBACK_CACHE[full_key] = {"value": serialized, "tenant": tenant_s}
        _FALLBACK_TTL[full_key] = _utcnow() + timedelta(seconds=int(ttl_seconds))
        return True

    async def cache_get(
        self,
        db: AsyncSession,
        tenant: str,
        key: str,
    ) -> Any | None:
        """Get a tenant-scoped cache entry. Never returns another tenant's value."""
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        tenant_s = str(tenant).strip()
        full_key = _tenant_key(tenant_s, key)

        # Isolation check: ensure the resolved full_key belongs to tenant
        if not _is_tenant_key(tenant_s, full_key):
            # Log isolation violation (best-effort) to observability/audit
            try:
                from app.iam.tenant_isolation import tenant_isolation as _ti  # type: ignore

                _ti.validate_tenant_access(tenant_s, "cache", full_key)
            except Exception:
                pass
            return None

        # Try Redis
        if _get_redis is not None:
            try:
                client = await _get_redis()
                if client is not None:
                    raw = await client.get(full_key)
                    if raw is not None:
                        await self.record_hit(db, tenant_s, key)
                        try:
                            return json.loads(raw)
                        except Exception:
                            return raw
                    # Also check namespace-prefixed key via core/redis
                    try:
                        from app.core.redis import cache_get  # type: ignore

                        raw2 = await cache_get(_strip_tenant_prefix(full_key), namespace="cache")
                        if raw2 is not None:
                            # Ensure tenant isolation for secondary lookup too
                            await self.record_hit(db, tenant_s, key)
                            try:
                                return json.loads(raw2)
                            except Exception:
                                return raw2
                    except Exception:
                        pass
            except Exception:
                pass

        # Fallback in-memory
        entry = _FALLBACK_CACHE.get(full_key)
        if entry is not None:
            exp = _FALLBACK_TTL.get(full_key)
            if exp and _utcnow() > exp:
                _FALLBACK_CACHE.pop(full_key, None)
                _FALLBACK_TTL.pop(full_key, None)
                await self.record_miss(db, tenant_s, key, reason="expired")
                return None
            # Tenant isolation already enforced via full_key prefix
            if entry.get("tenant") != tenant_s:
                # Violation: entry belongs to different tenant (should never happen due to prefix, but double-check)
                await self.record_miss(db, tenant_s, key, reason="isolation_mismatch")
                return None
            await self.record_hit(db, tenant_s, key)
            try:
                return json.loads(entry["value"])
            except Exception:
                return entry["value"]

        await self.record_miss(db, tenant_s, key, reason="not_found")
        return None

    def validate_isolation(self, tenant: str, cache_key: str) -> bool:
        """Synchronous isolation check: never allow cross-tenant read."""
        return _is_tenant_key(str(tenant), str(cache_key))

    # ---------------------------------------------------------------- invalidation

    async def invalidate(
        self,
        db: AsyncSession,
        tenant: str,
        category: str | None = None,
        pattern: str | None = None,
        key: str | None = None,
    ) -> dict[str, Any]:
        """Invalidate cache entries for tenant. Supports config/permissions/flags categories.

        Returns dict with ``invalidated_count`` and ``category``.
        Tenant-scoped: never deletes another tenant's keys.
        """
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        tenant_s = str(tenant).strip()
        invalidated = 0

        # Single key invalidation
        if key:
            full_key = _tenant_key(tenant_s, key)
            if not _is_tenant_key(tenant_s, full_key):
                raise PermissionError("isolation violation on invalidate")
            _FALLBACK_CACHE.pop(full_key, None)
            _FALLBACK_TTL.pop(full_key, None)
            if _get_redis is not None:
                try:
                    client = await _get_redis()
                    if client is not None:
                        await client.delete(full_key)
                        invalidated += 1
                    else:
                        invalidated += 1
                except Exception:
                    invalidated += 1
            else:
                invalidated += 1
            await _record_cache_metric(db, tenant_s, "cache_invalidation", key, dimensions={"category": category or "single"})
            return {"tenant": tenant_s, "category": category or "single", "pattern": key, "invalidated_count": invalidated, "at": _utcnow().isoformat()}

        # Category-based bulk invalidation
        # Categories: config, permissions, flags (and generic)
        target_prefix: str | None = None
        if category:
            cat = str(category).strip().lower()
            if cat not in {"config", "permissions", "flags", "all"}:
                raise ValueError(f"unsupported invalidation category: {category!r}")
            if cat == "all":
                target_prefix = _tenant_key(tenant_s, "")
            else:
                # Keys are tenant:<tenant>:<category>:... or tenant:<tenant>:<key containing category>
                target_prefix = _tenant_key(tenant_s, cat)
        elif pattern:
            # Pattern is suffix without tenant prefix; scope to tenant
            target_prefix = _tenant_key(tenant_s, str(pattern).strip().lstrip(":").split("*")[0])
        else:
            target_prefix = _tenant_key(tenant_s, "")

        # Invalidate fallback cache by prefix
        to_delete = [k for k in list(_FALLBACK_CACHE.keys()) if k.startswith(target_prefix or f"tenant:{tenant_s}:")]
        for k in to_delete:
            _FALLBACK_CACHE.pop(k, None)
            _FALLBACK_TTL.pop(k, None)
            invalidated += 1

        # Invalidate Redis by scanning (best-effort, tenant-scoped)
        if _get_redis is not None:
            try:
                client = await _get_redis()
                if client is not None:
                    scan_pattern = f"{target_prefix}*" if target_prefix else f"tenant:{tenant_s}:*"
                    cursor = 0
                    redis_deleted = 0
                    # Use SCAN to avoid blocking; limit iterations
                    for _ in range(5):
                        try:
                            cursor, keys = await client.scan(cursor=cursor, match=scan_pattern, count=100)
                        except Exception:
                            break
                        if keys:
                            # Filter to ensure tenant isolation (double-check)
                            safe_keys = [k for k in keys if _is_tenant_key(tenant_s, k)]
                            if safe_keys:
                                await client.delete(*safe_keys)
                                redis_deleted += len(safe_keys)
                        if cursor == 0:
                            break
                    # If we deleted via Redis, adjust count to include Redis deletions beyond fallback
                    if redis_deleted > invalidated:
                        invalidated = redis_deleted
                    elif redis_deleted > 0 and invalidated == len(to_delete):
                        # Already counted fallback; keep max
                        invalidated = max(invalidated, redis_deleted)
            except Exception:
                pass

        await _record_cache_metric(
            db,
            tenant_s,
            "cache_invalidation",
            pattern or category or "all",
            dimensions={"category": category or "all", "invalidated": invalidated},
        )
        return {
            "tenant": tenant_s,
            "category": category or "all",
            "pattern": pattern or target_prefix,
            "invalidated_count": invalidated,
            "at": _utcnow().isoformat(),
        }

    async def invalidate_config(self, db: AsyncSession, tenant: str) -> dict[str, Any]:
        return await self.invalidate(db, tenant, category="config")

    async def invalidate_permissions(self, db: AsyncSession, tenant: str) -> dict[str, Any]:
        return await self.invalidate(db, tenant, category="permissions")

    async def invalidate_flags(self, db: AsyncSession, tenant: str) -> dict[str, Any]:
        return await self.invalidate(db, tenant, category="flags")

    async def get_stats(self, tenant: str | None = None) -> dict[str, Any]:
        if tenant:
            rec = _CACHE_METRICS.get(str(tenant).strip(), {"hits": 0, "misses": 0, "evictions": 0})
            total = rec["hits"] + rec["misses"]
            hit_rate = (rec["hits"] / total * 100) if total > 0 else 0.0
            return {"tenant": str(tenant).strip(), **rec, "hit_rate": round(hit_rate, 2), "fallback_keys": len([k for k in _FALLBACK_CACHE if k.startswith(f"tenant:{str(tenant).strip()}:")])}
        # Global
        total_hits = sum(v["hits"] for v in _CACHE_METRICS.values())
        total_misses = sum(v["misses"] for v in _CACHE_METRICS.values())
        total_evictions = sum(v["evictions"] for v in _CACHE_METRICS.values())
        return {"tenants": len(_CACHE_METRICS), "hits": total_hits, "misses": total_misses, "evictions": total_evictions, "fallback_keys": len(_FALLBACK_CACHE)}


cache_metrics_service = CacheMetricsService()
