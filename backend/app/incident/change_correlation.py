"""Incident Response Platform -- Change Correlation (Volume 49).

Links incidents to recent deployments, commits, and PRs using time-window
and service-identity matching. Does not claim causality without evidence.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any


class ChangeCorrelationService:
    """Identify recent changes associated with an incident."""

    def __init__(self):
        self._changes: list[dict[str, Any]] = []

    def record_change(self, change_type: str, service: str, environment: str,
                      change_id: str, description: str = "",
                      author: str = "", changed_at: str = "",
                      files_changed: list | None = None,
                      metadata: dict | None = None) -> dict:
        change = {"change_type": change_type, "service": service,
                  "environment": environment, "change_id": change_id,
                  "description": description, "author": author,
                  "changed_at": changed_at, "files_changed": files_changed or [],
                  "metadata": metadata or {}}
        self._changes.append(change)
        return change

    def find_related_changes(self, incident: dict, window_hours: int = 48,
                             max_results: int = 15) -> list[dict[str, Any]]:
        service = incident.get("service", "")
        environment = incident.get("environment", "")
        detected_at = incident.get("detected_at", "")
        if not detected_at:
            return []
        try:
            incident_time = datetime.fromisoformat(detected_at)
        except (ValueError, TypeError):
            return []

        window_start = incident_time - timedelta(hours=window_hours)
        matches = []
        for change in self._changes:
            if service and change.get("service") != service:
                continue
            if environment and change.get("environment") != environment:
                continue
            try:
                change_time = datetime.fromisoformat(change.get("changed_at", ""))
                if window_start <= change_time <= incident_time:
                    delta = (incident_time - change_time).total_seconds() / 60
                    matches.append({**change, "_time_delta_minutes": delta})
            except (ValueError, TypeError):
                continue
        matches.sort(key=lambda c: c.get("_time_delta_minutes", 9999))
        return matches[:max_results]

    def classify_change_risk(self, change: dict) -> dict[str, Any]:
        risk_factors = []
        risk_score = 0.0

        change_type = change.get("change_type", "")
        if change_type == "deployment":
            risk_score += 0.4
            risk_factors.append("deployment_change")
        elif change_type == "config":
            risk_score += 0.2
            risk_factors.append("config_change")
        elif change_type == "dependency":
            risk_score += 0.3
            risk_factors.append("dependency_update")

        files = change.get("files_changed", [])
        if len(files) > 10:
            risk_score += 0.2
            risk_factors.append("large_change_set")
        if any("migration" in f.lower() for f in files):
            risk_score += 0.3
            risk_factors.append("database_migration")
        if any("security" in f.lower() for f in files):
            risk_score += 0.1
            risk_factors.append("security_related")

        return {
            "risk_score": min(risk_score, 1.0),
            "risk_factors": risk_factors,
            "risk_level": "high" if risk_score > 0.6 else "moderate" if risk_score > 0.3 else "low",
        }

    def get_change_summary(self, incident: dict) -> dict[str, Any]:
        changes = self.find_related_changes(incident)
        if not changes:
            return {"total_changes": 0, "risk_assessment": "no_recent_changes"}

        risk_assessments = [self.classify_change_risk(c) for c in changes]
        avg_risk = sum(r["risk_score"] for r in risk_assessments) / len(risk_assessments)
        all_factors = []
        for r in risk_assessments:
            all_factors.extend(r["risk_factors"])

        return {
            "total_changes": len(changes),
            "change_types": list(set(c.get("change_type", "") for c in changes)),
            "avg_risk_score": round(avg_risk, 3),
            "risk_assessment": "high_risk" if avg_risk > 0.6 else "moderate_risk" if avg_risk > 0.3 else "low_risk",
            "risk_factors": list(set(all_factors)),
            "changes": changes,
            "causality_claimed": False,
            "causality_note": "Correlation does not imply causation. Evidence required.",
        }
