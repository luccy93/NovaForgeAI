"""Support analytics service — metrics, deflection, knowledge gap detection (Volume 54)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class SupportAnalyticsService:
    def __init__(self):
        self._feedback_records: list[dict] = []
        self._telemetry = {"queries": 0}

    def get_ticket_analytics(self, ticket_service, tenant_id: Optional[str] = None) -> dict:
        all_tickets = ticket_service.list_tickets(tenant_id=tenant_id, limit=10000)
        total = len(all_tickets)
        if total == 0:
            return {"total": 0, "by_status": {}, "by_priority": {}, "by_category": {},
                    "avg_first_response_minutes": 0, "avg_resolution_minutes": 0,
                    "sla_compliance": 100.0, "reopen_rate": 0.0, "ai_deflection_rate": 0.0}

        by_status = {}
        by_priority = {}
        by_category = {}
        response_times = []
        resolution_times = []
        resolved_count = 0
        reopened_count = 0

        for t in all_tickets:
            by_status[t["status"]] = by_status.get(t["status"], 0) + 1
            by_priority[t["priority"]] = by_priority.get(t["priority"], 0) + 1
            by_category[t["category"]] = by_category.get(t["category"], 0) + 1

            if t.get("first_response_at") and t.get("created_at"):
                try:
                    created = datetime.fromisoformat(t["created_at"])
                    responded = datetime.fromisoformat(t["first_response_at"])
                    response_times.append((responded - created).total_seconds() / 60)
                except (ValueError, TypeError):
                    pass

            if t.get("resolved_at") and t.get("created_at"):
                try:
                    created = datetime.fromisoformat(t["created_at"])
                    resolved = datetime.fromisoformat(t["resolved_at"])
                    resolution_times.append((resolved - created).total_seconds() / 60)
                    resolved_count += 1
                except (ValueError, TypeError):
                    pass

            if t["status"] == "reopened":
                reopened_count += 1

        avg_response = sum(response_times) / len(response_times) if response_times else 0
        avg_resolution = sum(resolution_times) / len(resolution_times) if resolution_times else 0
        reopen_rate = (reopened_count / total * 100) if total > 0 else 0
        return {
            "total": total,
            "by_status": by_status,
            "by_priority": by_priority,
            "by_category": by_category,
            "avg_first_response_minutes": round(avg_response, 1),
            "avg_resolution_minutes": round(avg_resolution, 1),
            "reopen_rate": round(reopen_rate, 1),
        }

    def get_deflection_rate(self, ticket_service, ai_service) -> dict:
        all_tickets = ticket_service.list_tickets(limit=10000)
        total = len(all_tickets)
        ai_resolved = 0
        human_handoffs = 0
        for t in all_tickets:
            if t.get("ai_confidence", 0) >= 0.8 and t["status"] in ("resolved", "closed"):
                ai_resolved += 1
            if t.get("ai_confidence") is not None and t["status"] == "escalated":
                human_handoffs += 1
        deflection_rate = (ai_resolved / total * 100) if total > 0 else 0
        return {
            "total_tickets": total,
            "ai_resolved": ai_resolved,
            "human_handoffs": human_handoffs,
            "deflection_rate": round(deflection_rate, 1),
        }

    def get_csat_summary(self) -> dict:
        if not self._feedback_records:
            return {"total_responses": 0, "avg_rating": 0, "distribution": {}}
        csat_records = [f for f in self._feedback_records if f.get("feedback_type") == "csat"]
        total = len(csat_records)
        if total == 0:
            return {"total_responses": 0, "avg_rating": 0, "distribution": {}}
        ratings = [f["rating"] for f in csat_records]
        dist = {}
        for r in ratings:
            dist[r] = dist.get(r, 0) + 1
        return {
            "total_responses": total,
            "avg_rating": round(sum(ratings) / total, 2),
            "distribution": dist,
        }

    def record_feedback(self, ticket_id: str, rating: int, feedback_type: str,
                        comment: Optional[str] = None) -> dict:
        record = {
            "ticket_id": ticket_id, "rating": rating,
            "feedback_type": feedback_type, "comment": comment,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._feedback_records.append(record)
        return record

    def get_volume_trends(self, ticket_service, days: int = 30) -> dict:
        all_tickets = ticket_service.list_tickets(limit=10000)
        now = datetime.now(timezone.utc)
        daily_counts = {}
        for i in range(days):
            day = (now - timedelta(days=i)).strftime("%Y-%m-%d")
            daily_counts[day] = 0
        for t in all_tickets:
            try:
                created = datetime.fromisoformat(t["created_at"])
                day = created.strftime("%Y-%m-%d")
                if day in daily_counts:
                    daily_counts[day] += 1
            except (ValueError, TypeError):
                pass
        return {"daily_counts": daily_counts, "period_days": days}

    def get_telemetry(self) -> dict:
        return dict(self._telemetry)


support_analytics_service = SupportAnalyticsService()
