"""Incident correlation — match tickets to active incidents, customer-safe status (Volume 54)."""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class IncidentCorrelationService:
    def __init__(self):
        self._correlations: dict[str, dict] = {}
        self._telemetry = {"correlated": 0, "matched": 0}

    def correlate_ticket(self, ticket_id: str, tenant_id: str,
                         service_affected: Optional[str] = None,
                         environment: Optional[str] = None,
                         incident_fingerprint: Optional[str] = None,
                         active_incidents: Optional[list[dict]] = None) -> dict:
        matches = []
        for inc in (active_incidents or []):
            score = 0
            if service_affected and inc.get("service") == service_affected:
                score += 2
            if environment and inc.get("environment") == environment:
                score += 1
            if incident_fingerprint and inc.get("fingerprint") == incident_fingerprint:
                score += 3
            if score >= 2:
                matches.append({"incident_id": inc["id"], "score": score,
                                "title": inc.get("title"), "severity": inc.get("severity")})
        matches.sort(key=lambda m: m["score"], reverse=True)
        result = {
            "ticket_id": ticket_id, "matches": matches,
            "best_match": matches[0] if matches else None,
            "should_link": len(matches) > 0 and matches[0]["score"] >= 3,
        }
        self._correlations[ticket_id] = result
        self._telemetry["correlated"] += 1
        if matches:
            self._telemetry["matched"] += 1
        return result

    def get_customer_safe_incident_status(self, incident: dict) -> dict:
        return {
            "id": incident.get("id"),
            "title": incident.get("title"),
            "severity": incident.get("severity"),
            "status": incident.get("status"),
            "service": incident.get("service"),
            "started_at": incident.get("detected_at"),
            "resolved_at": incident.get("resolved_at"),
            "impact_summary": incident.get("impact", {}).get("summary", "Investigating"),
        }

    def detect_ticket_cluster(self, tenant_id: str, service: str,
                              tickets: list[dict], window_hours: int = 24) -> dict:
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        cutoff = (now - timedelta(hours=window_hours)).isoformat()
        related = [t for t in tickets
                   if t.get("tenant_id") == tenant_id
                   and t.get("service_affected") == service
                   and t.get("created_at", "") >= cutoff]
        return {
            "service": service, "ticket_count": len(related),
            "tickets": [t["id"] for t in related[:20]],
            "suggests_incident": len(related) >= 3,
        }

    def get_correlation(self, ticket_id: str) -> Optional[dict]:
        return self._correlations.get(ticket_id)

    def get_telemetry(self) -> dict:
        return dict(self._telemetry)


incident_correlation_service = IncidentCorrelationService()
