"""Incident Response Platform -- Timeline Service (Volume 49).

Builds chronological timeline from incident events. Every timeline event
must have a source.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


class TimelineService:
    """Build and manage incident timelines."""

    def __init__(self):
        self._timelines: dict[str, list[dict[str, Any]]] = {}

    def add_event(self, incident_id: str, event_type: str, source: str,
                  message: str, actor: str = "system",
                  evidence: dict | None = None,
                  timestamp: str = "") -> dict:
        event = {
            "id": str(uuid4()),
            "incident_id": incident_id,
            "event_type": event_type,
            "source": source,
            "message": message,
            "actor": actor,
            "evidence": evidence or {},
            "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        }
        if incident_id not in self._timelines:
            self._timelines[incident_id] = []
        self._timelines[incident_id].append(event)
        return event

    def get_timeline(self, incident_id: str) -> list[dict[str, Any]]:
        events = self._timelines.get(incident_id, [])
        return sorted(events, key=lambda e: e.get("timestamp", ""))

    def build_from_incident(self, incident: dict,
                            events: list[dict] | None = None) -> list[dict[str, Any]]:
        incident_id = incident.get("id", "")

        self._timelines[incident_id] = []

        self.add_event(incident_id, "incident_detected", "system",
                       f"Incident detected: {incident.get('title', 'Unknown')}",
                       evidence={"severity": incident.get("severity"), "source": incident.get("source")})

        if incident.get("acknowledged_at"):
            self.add_event(incident_id, "incident_acknowledged", incident.get("commander", "system"),
                           f"Incident acknowledged by {incident.get('commander', 'unknown')}",
                           timestamp=incident["acknowledged_at"])

        for deploy in incident.get("correlated_deployments", []):
            self.add_event(incident_id, "deployment_correlated", "correlation_engine",
                           f"Deployment {deploy.get('deploy_id', '')} correlated",
                           evidence={"deployment": deploy})

        for commit in incident.get("correlated_commits", [])[:5]:
            self.add_event(incident_id, "commit_correlated", "correlation_engine",
                           f"Commit {commit.get('commit_sha', '')[:8]} correlated",
                           evidence={"commit": commit})

        if events:
            for event in events:
                self.add_event(incident_id, event.get("event_type", "note"),
                               event.get("source", "manual"),
                               event.get("message", ""),
                               actor=event.get("actor", "user"),
                               evidence=event.get("evidence"))

        if incident.get("resolved_at"):
            self.add_event(incident_id, "incident_resolved", "system",
                           "Incident resolved",
                           timestamp=incident["resolved_at"])

        return self.get_timeline(incident_id)

    def generate_summary(self, incident_id: str) -> str:
        timeline = self.get_timeline(incident_id)
        if not timeline:
            return "No timeline events recorded."

        parts = []
        for event in timeline[:20]:
            ts = event.get("timestamp", "")[:19]
            parts.append(f"[{ts}] {event.get('event_type', '')}: {event.get('message', '')}")
        return "\n".join(parts)

    def get_event_count(self, incident_id: str) -> int:
        return len(self._timelines.get(incident_id, []))

    def get_events_by_type(self, incident_id: str, event_type: str) -> list[dict]:
        return [e for e in self._timelines.get(incident_id, [])
                if e.get("event_type") == event_type]
