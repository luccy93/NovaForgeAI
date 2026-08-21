"""Unified Analytics Platform -- Metric Aggregation (Volume 50)."""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import uuid4


def _bucket_start(ts: datetime, granularity: str) -> datetime:
    if granularity == "minute":
        return ts.replace(second=0, microsecond=0)
    elif granularity == "hour":
        return ts.replace(minute=0, second=0, microsecond=0)
    elif granularity == "day":
        return ts.replace(hour=0, minute=0, second=0, microsecond=0)
    elif granularity == "week":
        day = ts - timedelta(days=ts.weekday())
        return day.replace(hour=0, minute=0, second=0, microsecond=0)
    elif granularity == "month":
        return ts.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return ts


class AggregationService:
    """Aggregate normalized events into time-bucketed metric values."""

    def __init__(self):
        self._data_points: dict[str, list[dict[str, Any]]] = {}
        self._aggregates: dict[str, dict[str, Any]] = {}

    def record_metric(self, tenant: str, metric_name: str, value: float,
                      dimensions: dict | None = None, timestamp: str = "",
                      granularity: str = "hour") -> dict:
        ts_str = timestamp or datetime.now(timezone.utc).isoformat()
        try:
            ts = datetime.fromisoformat(ts_str)
        except (ValueError, TypeError):
            ts = datetime.now(timezone.utc)

        bucket = _bucket_start(ts, granularity)
        dims = dimensions or {}
        key = self._key(tenant, metric_name, granularity, dims, bucket)

        dp = {"tenant": tenant, "metric_name": metric_name, "value": value,
              "dimensions": dims, "timestamp": ts_str, "granularity": granularity,
              "bucket_start": bucket.isoformat()}

        if key not in self._data_points:
            self._data_points[key] = []
        self._data_points[key].append(dp)

        agg = self._aggregates.get(key, {"values": [], "count": 0, "sum": 0,
                                          "min": float("inf"), "max": float("-inf")})
        agg["values"].append(value)
        agg["count"] += 1
        agg["sum"] += value
        agg["min"] = min(agg["min"], value)
        agg["max"] = max(agg["max"], value)
        self._aggregates[key] = agg

        return dp

    def query_metric(self, tenant: str, metric_name: str, granularity: str = "hour",
                     dimensions: dict | None = None, start_time: str = "",
                     end_time: str = "", limit: int = 1000) -> list[dict]:
        results = []
        dims = dimensions or {}
        for key, agg in self._aggregates.items():
            if not key.startswith(f"{tenant}:{metric_name}:{granularity}"):
                continue
            bucket_start = key.split(":")[-1]
            if start_time and bucket_start < start_time:
                continue
            if end_time and bucket_start > end_time:
                continue
            values = agg["values"]
            avg = agg["sum"] / agg["count"] if agg["count"] else 0
            sorted_vals = sorted(values)
            p95 = self._percentile(sorted_vals, 0.95)
            p99 = self._percentile(sorted_vals, 0.99)
            results.append({"tenant": tenant, "metric_name": metric_name,
                            "granularity": granularity, "dimensions": dims,
                            "period_start": bucket_start, "value": agg["sum"],
                            "count": agg["count"], "min": agg["min"],
                            "max": agg["max"], "avg": avg,
                            "p95": p95, "p99": p99})
        results.sort(key=lambda r: r["period_start"])
        return results[:limit]

    def aggregate(self, tenant: str, metric_name: str, start_time: str,
                  end_time: str, granularity: str = "hour",
                  dimensions: dict | None = None) -> dict:
        points = self.query_metric(tenant, metric_name, granularity,
                                   dimensions, start_time, end_time, limit=10000)
        if not points:
            return {"tenant": tenant, "metric_name": metric_name,
                    "sum": 0, "avg": 0, "min": 0, "max": 0,
                    "count": 0, "p95": 0, "p99": 0}
        all_values = []
        for p in points:
            all_values.extend([p["value"]] * p["count"])
        sorted_vals = sorted(all_values) if all_values else [0]
        total = sum(all_values)
        count = len(all_values)
        return {"tenant": tenant, "metric_name": metric_name,
                "sum": total, "avg": total / count if count else 0,
                "min": min(all_values) if all_values else 0,
                "max": max(all_values) if all_values else 0,
                "count": count,
                "p95": self._percentile(sorted_vals, 0.95),
                "p99": self._percentile(sorted_vals, 0.99)}

    def get_trend(self, tenant: str, metric_names: list[str],
                  granularity: str = "day", start_time: str = "",
                  end_time: str = "") -> list[dict]:
        results = []
        for name in metric_names:
            points = self.query_metric(tenant, name, granularity,
                                       start_time=start_time, end_time=end_time)
            for p in points:
                results.append({"metric_name": name, **p})
        return results

    def get_latest(self, tenant: str, metric_name: str,
                   dimensions: dict | None = None) -> dict | None:
        points = self.query_metric(tenant, metric_name, "hour",
                                   dimensions, limit=1)
        return points[-1] if points else None

    def list_metrics(self, tenant: str = "") -> list[str]:
        metrics: set[str] = set()
        for key in self._data_points:
            parts = key.split(":")
            if len(parts) >= 2:
                m = parts[1]
                if not tenant or key.startswith(tenant):
                    metrics.add(m)
        return sorted(metrics)

    @staticmethod
    def _key(tenant: str, metric_name: str, granularity: str,
             dimensions: dict, bucket_start: datetime) -> str:
        dims_hash = hashlib.md5(json.dumps(dimensions, sort_keys=True, default=str).encode()).hexdigest()[:8]
        return f"{tenant}:{metric_name}:{granularity}:{dims_hash}:{bucket_start.isoformat()}"

    @staticmethod
    def _percentile(sorted_vals: list[float], pct: float) -> float:
        if not sorted_vals:
            return 0.0
        idx = int(len(sorted_vals) * pct)
        idx = min(idx, len(sorted_vals) - 1)
        return sorted_vals[idx]


import hashlib

aggregation_service = AggregationService()
