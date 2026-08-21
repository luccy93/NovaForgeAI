"""Unified Analytics Platform -- Marketplace Analytics (Volume 50)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


class MarketplaceAnalyticsService:
    """Marketplace analytics integrating Volume 44 data."""

    def __init__(self):
        self._events: list[dict[str, Any]] = []

    def record_marketplace_event(self, tenant: str, event_type: str,
                                 package_name: str = "", package_id: str = "",
                                 version: str = "", user_id: str = "",
                                 metadata: dict | None = None) -> dict:
        event = {"id": f"mkt_{uuid4().hex[:12]}", "tenant": tenant,
                 "event_type": event_type, "package_name": package_name,
                 "package_id": package_id, "version": version,
                 "user_id": user_id, "metadata": metadata or {},
                 "recorded_at": datetime.now(timezone.utc).isoformat()}
        self._events.append(event)
        return event

    def get_package_analytics(self, tenant: str, package_id: str = "",
                              start_time: str = "", end_time: str = "") -> dict:
        events = self._filter(tenant, package_id=package_id,
                              start_time=start_time, end_time=end_time)
        types = {}
        for e in events:
            t = e["event_type"]
            types[t] = types.get(t, 0) + 1
        return {"package_id": package_id, "total_events": len(events),
                "by_type": types, "unique_users": len(set(e["user_id"] for e in events if e["user_id"]))}

    def get_publisher_analytics(self, tenant: str, publisher: str = "",
                                start_time: str = "", end_time: str = "") -> dict:
        events = self._filter(tenant, start_time=start_time, end_time=end_time)
        return {"publisher": publisher, "total_events": len(events)}

    def get_marketplace_summary(self, tenant: str = "",
                                start_time: str = "", end_time: str = "") -> dict:
        events = self._filter(tenant, start_time=start_time, end_time=end_time)
        packages = set(e["package_id"] for e in events if e["package_id"])
        users = set(e["user_id"] for e in events if e["user_id"])
        types = {}
        for e in events:
            types[e["event_type"]] = types.get(e["event_type"], 0) + 1
        return {"total_events": len(events), "unique_packages": len(packages),
                "unique_users": len(users), "by_type": types}

    def get_popular_packages(self, tenant: str = "", limit: int = 10) -> list[dict]:
        counts: dict[str, int] = {}
        for e in self._filter(tenant):
            pid = e.get("package_id") or e.get("package_name", "")
            if pid:
                counts[pid] = counts.get(pid, 0) + 1
        ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        return [{"package": p, "count": c} for p, c in ranked[:limit]]

    def get_usage_trends(self, tenant: str, package_id: str = "",
                         granularity: str = "day", start_time: str = "",
                         end_time: str = "") -> list[dict]:
        events = self._filter(tenant, package_id=package_id,
                              start_time=start_time, end_time=end_time)
        buckets: dict[str, int] = {}
        for e in events:
            bucket = e.get("recorded_at", "")[:10] if granularity == "day" else e.get("recorded_at", "")[:13]
            buckets[bucket] = buckets.get(bucket, 0) + 1
        return [{"period": k, "count": v} for k, v in sorted(buckets.items())]

    def _filter(self, tenant: str, package_id: str = "",
                start_time: str = "", end_time: str = "") -> list[dict]:
        results = []
        for e in self._events:
            if e["tenant"] != tenant:
                continue
            if package_id and e.get("package_id") != package_id:
                continue
            if start_time and e.get("recorded_at", "") < start_time:
                continue
            if end_time and e.get("recorded_at", "") > end_time:
                continue
            results.append(e)
        return results


marketplace_analytics_service = MarketplaceAnalyticsService()
