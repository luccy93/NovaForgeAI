"""Analytics Cache - query results, materialized views, Redis adapter, TTL invalidation."""
import time, os, json
from typing import Optional


class AnalyticsCache:
    """TTL-based result cache with optional Redis backend and stats."""

    def __init__(self, ttl_seconds: int = 300, max_entries: int = 10000, redis=None):
        self.ttl = ttl_seconds
        self.max_entries = max_entries
        self.redis = redis
        self._data: dict[str, tuple[float, object]] = {}
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[object]:
        now = time.time()
        if self.redis is not None:
            try:
                raw = self.redis.get(key)
                if raw is not None:
                    self.hits += 1
                    return json.loads(raw)
            except Exception:
                pass
            self.misses += 1
            return None
        entry = self._data.get(key)
        if entry is None:
            self.misses += 1
            return None
        expires, value = entry
        if now > expires:
            del self._data[key]
            self.misses += 1
            return None
        self.hits += 1
        return value

    def put(self, key: str, value: object, ttl: Optional[int] = None) -> None:
        expires = time.time() + (ttl if ttl is not None else self.ttl)
        if self.redis is not None:
            try:
                self.redis.setex(key, int(ttl or self.ttl), json.dumps(value, default=str))
            except Exception:
                self._data[key] = (expires, value)
            return
        self._data[key] = (expires, value)
        if len(self._data) > self.max_entries:
            oldest_key = min(self._data, key=lambda k: self._data[k][0])
            del self._data[oldest_key]

    def invalidate(self, key: str) -> None:
        self._data.pop(key, None)
        if self.redis is not None:
            try:
                self.redis.delete(key)
            except Exception:
                pass

    def invalidate_prefix(self, prefix: str) -> int:
        count = 0
        for key in list(self._data.keys()):
            if key.startswith(prefix):
                del self._data[key]
                count += 1
        return count

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {"hits": self.hits, "misses": self.misses,
                "hit_rate": round(self.hits / max(1, total), 4),
                "entries": len(self._data),
                "ttl_seconds": self.ttl}


class MaterializedView:
    """Precomputed aggregate that can be refreshed on schedule."""

    def __init__(self, name: str, olap, groups: list[str], aggregations: dict[str, str],
                 refresh_minutes: int = 60):
        self.name = name
        self.olap = olap
        self.groups = groups
        self.aggregations = aggregations
        self.refresh_minutes = refresh_minutes
        self.last_refresh = 0.0
        self.rows: list[dict] = []

    def refresh(self, table: str) -> list[dict]:
        buckets: dict = {}
        for r in self.olap.rows(table):
            key = tuple(r.get(g, "") for g in self.groups)
            buckets.setdefault(key, []).append(r)
        rows = []
        from .query_service import AGG_FUNCS
        for key, group in buckets.items():
            row = {g: key[i] for i, g in enumerate(self.groups)}
            row["count"] = len(group)
            for name, agg in self.aggregations.items():
                func, col = (agg.split(":", 1) if ":" in agg else (agg, name))
                row[name] = round(AGG_FUNCS[func](group, col), 6)
            rows.append(row)
        self.rows = rows
        self.last_refresh = time.time()
        return rows

    def stale(self) -> bool:
        return time.time() - self.last_refresh > self.refresh_minutes * 60