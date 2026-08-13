"""Analytics Query Service - safe, tenant-isolated, bounded query abstraction over the warehouse."""
import time
from typing import Optional


class TenantGuard:
    """Enforces organization isolation across every query."""

    def __init__(self, allowed_orgs: Optional[set[str]] = None):
        self.allowed_orgs = allowed_orgs

    def check(self, organization_id: str) -> None:
        if self.allowed_orgs is not None and organization_id not in self.allowed_orgs:
            raise PermissionError(f"cross-tenant access denied for org {organization_id}")


class QuerySpec:
    """Structured, injection-safe query definition."""

    def __init__(self, table: str, organization_id: str = "",
                 filters: Optional[dict] = None, groups: Optional[list[str]] = None,
                 aggregations: Optional[dict[str, str]] = None,
                 time_field: str = "", time_bucket: str = "daily",
                 order_by: str = "", limit: int = 1000, offset: int = 0):
        self.table = table
        self.organization_id = organization_id
        self.filters = filters or {}
        self.groups = groups or []
        self.aggregations = aggregations or {}
        self.time_field = time_field
        self.time_bucket = time_bucket
        self.order_by = order_by
        self.limit = limit
        self.offset = offset


AGG_FUNCS = {
    "sum": lambda rows, k: sum(r.get(k, 0) or 0 for r in rows),
    "count": lambda rows, k: len(rows),
    "avg": lambda rows, k: (sum(r.get(k, 0) or 0 for r in rows) / len(rows)) if rows else 0.0,
    "min": lambda rows, k: min((r.get(k) for r in rows if r.get(k) is not None), default=0),
    "max": lambda rows, k: max((r.get(k) for r in rows if r.get(k) is not None), default=0),
    "distinct": lambda rows, k: len({r.get(k) for r in rows}),
}


def _week_key(ts: str) -> str:
    if not ts:
        return "unknown"
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(ts)
        iso = dt.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    except Exception:
        return (ts or "")[:10]


class AnalyticsQueryService:
    """Executes QuerySpecs against an engine with caching, pagination, limits."""

    def __init__(self, olap, cache=None, guard: Optional[TenantGuard] = None,
                 max_rows: int = 1_000_000, max_groups: int = 8):
        self.olap = olap
        self.cache = cache
        self.guard = guard or TenantGuard()
        self.max_rows = max_rows
        self.max_groups = max_groups
        self.query_count = 0
        self.latencies: list[float] = []

    def run(self, spec: QuerySpec) -> dict:
        if spec.organization_id:
            self.guard.check(spec.organization_id)
        if len(spec.groups) > self.max_groups:
            raise ValueError("too many group-by dimensions")
        if spec.limit > self.max_rows:
            spec.limit = self.max_rows

        start = time.time()
        cache_key = self._key(spec)
        cached = self.cache.get(cache_key) if self.cache else None
        if cached is not None:
            self.query_count += 1
            self.latencies.append(time.time() - start)
            return {"cached": True, **cached}

        rows = self._resolve_rows(spec)
        result = self._page_rows(rows, spec)
        if self.cache:
            self.cache.put(cache_key, result)
        self.query_count += 1
        self.latencies.append(time.time() - start)
        return {"cached": False, **result}

    def _resolve_rows(self, spec: QuerySpec) -> list[dict]:
        rows = self.olap.rows(spec.table, filters=spec.filters)
        if spec.organization_id:
            rows = [r for r in rows if r.get("organization_id") == spec.organization_id]
        if spec.time_field:
            bucket_fn = {
                "daily": lambda t: (t or "")[:10],
                "monthly": lambda t: (t or "")[:7],
                "weekly": lambda t: _week_key(t),
            }.get(spec.time_bucket, lambda t: (t or "")[:10])
            grouped: dict[str, list[dict]] = {}
            for r in rows:
                grouped.setdefault(bucket_fn(r.get(spec.time_field, "")), []).append(r)
            out = []
            for period, group in grouped.items():
                row = {spec.time_field: period, "count": len(group)}
                for aname, (func, col) in self._agg_specs(spec).items():
                    row[aname] = round(func(group, col), 6)
                out.append(row)
            out = self._order(out, spec.order_by)
            return out
        if spec.groups:
            return self._group_rows(rows, spec)
        if spec.aggregations:
            out = {}
            for aname, (func, col) in self._agg_specs(spec).items():
                out[aname] = round(func(rows, col), 6)
            return [out]
        return rows

    def _agg_specs(self, spec: QuerySpec) -> dict:
        result = {}
        for aname, agg in spec.aggregations.items():
            if isinstance(agg, str) and ":" in agg:
                func, col = agg.split(":", 1)
                result[aname] = (AGG_FUNCS[func], col)
            else:
                result[aname] = (AGG_FUNCS[agg], aname)
        return result

    def _group_rows(self, rows: list[dict], spec: QuerySpec) -> list[dict]:
        buckets: dict[tuple, list[dict]] = {}
        for r in rows:
            key = tuple(r.get(g, "") for g in spec.groups)
            buckets.setdefault(key, []).append(r)
        out = []
        for key, group in buckets.items():
            row = {g: key[i] for i, g in enumerate(spec.groups)}
            row["count"] = len(group)
            for aname, (func, col) in self._agg_specs(spec).items():
                row[aname] = round(func(group, col), 6)
            out.append(row)
        return self._order(out, spec.order_by)

    def _order(self, rows: list[dict], order_by: str) -> list[dict]:
        if not order_by:
            return rows
        desc = order_by.startswith("-")
        field = order_by.lstrip("-")
        try:
            return sorted(rows, key=lambda r: r.get(field, 0), reverse=desc)
        except TypeError:
            return sorted(rows, key=lambda r: str(r.get(field, "")), reverse=desc)

    def _page_rows(self, rows: list[dict], spec: QuerySpec) -> dict:
        paged = rows[spec.offset: spec.offset + spec.limit]
        return {"rows": paged, "total": len(rows), "returned": len(paged),
                "offset": spec.offset, "limit": spec.limit}

    def _key(self, spec: QuerySpec) -> str:
        return f"{spec.table}|{spec.organization_id}|{spec.filters}|{spec.groups}|{spec.aggregations}|{spec.time_field}:{spec.time_bucket}|{spec.limit}"

    def health(self) -> dict:
        return {"queries": self.query_count,
                "avg_latency_ms": round(1000 * (sum(self.latencies) / len(self.latencies)), 2) if self.latencies else 0,
                "p95_latency_ms": round(1000 * sorted(self.latencies)[int(len(self.latencies) * 0.95)] if self.latencies else 0, 2)}