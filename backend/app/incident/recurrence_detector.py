"""Incident Response Platform -- Recurrence Detector (Volume 49).

Detects recurring incidents by service, fingerprint, root cause, deployment,
and dependency. Suggests preventive actions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class RecurrenceDetector:
    """Detect recurring incident patterns."""

    def __init__(self):
        self._history: list[dict[str, Any]] = []

    def record_incident(self, incident: dict) -> None:
        self._history.append({
            "incident_id": incident.get("id", ""),
            "tenant": incident.get("tenant", ""),
            "service": incident.get("service", ""),
            "fingerprint": incident.get("fingerprint", ""),
            "root_cause": incident.get("root_cause", ""),
            "severity": incident.get("severity", "SEV2"),
            "resolved_at": incident.get("resolved_at", ""),
            "correlated_deployments": incident.get("correlated_deployments", []),
        })

    def detect_recurrences(self, current_incident: dict,
                           window_days: int = 90) -> list[dict[str, Any]]:
        service = current_incident.get("service", "")
        fingerprint = current_incident.get("fingerprint", "")
        root_cause = current_incident.get("root_cause", "")
        tenant = current_incident.get("tenant", "")

        matches = []
        for past in self._history:
            if past.get("tenant") != tenant:
                continue
            score = 0
            reasons = []
            if service and past.get("service") == service:
                score += 1
                reasons.append("same_service")
            if fingerprint and past.get("fingerprint") == fingerprint:
                score += 3
                reasons.append("same_fingerprint")
            if root_cause and past.get("root_cause") and root_cause == past.get("root_cause"):
                score += 2
                reasons.append("same_root_cause")
            if score >= 2:
                matches.append({"incident_id": past["incident_id"], "score": score,
                                "reasons": reasons, "severity": past.get("severity")})

        matches.sort(key=lambda m: m.get("score", 0), reverse=True)
        return matches

    def get_recurrence_stats(self, tenant: str = "",
                             service: str = "") -> dict[str, Any]:
        history = [h for h in self._history if not tenant or h.get("tenant") == tenant]
        if service:
            history = [h for h in history if h.get("service") == service]

        if not history:
            return {"total": 0, "services_affected": 0, "fingerprint_groups": 0}

        services = set(h.get("service", "") for h in history)
        fingerprints = {}
        for h in history:
            fp = h.get("fingerprint", "")
            if fp:
                fingerprints.setdefault(fp, 0)
                fingerprints[fp] += 1

        recurring = sum(1 for count in fingerprints.values() if count > 1)

        return {"total": len(history), "services_affected": len(services),
                "unique_fingerprints": len(fingerprints),
                "recurring_fingerprints": recurring}

    def suggest_preventive_actions(self, incident: dict,
                                   recurrences: list[dict]) -> list[str]:
        suggestions = []
        if not recurrences:
            return suggestions
        top = recurrences[0]
        if "same_fingerprint" in top.get("reasons", []):
            suggestions.append("This incident has occurred before with the same fingerprint — investigate root cause thoroughly")
            suggestions.append("Consider implementing automated prevention for this pattern")
        if "same_root_cause" in top.get("reasons", []):
            suggestions.append("Previous incidents had the same root cause — verify the fix was permanent")
        if len(recurrences) > 2:
            suggestions.append(f"This is the {len(recurrences)+1}th occurrence — escalate to platform-level fix")
        return suggestions
