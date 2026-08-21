"""Incident Response Platform -- AI Incident Detector (Volume 49).

Detects AI-specific incidents: model outage, provider failure, token
exhaustion, RAG failure, agent failure, tool failure, unsafe behavior.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


class AIIncidentDetector:
    """Detect AI-specific incidents from telemetry."""

    def __init__(self):
        self._ai_events: list[dict[str, Any]] = []
        self._detected_incidents: list[dict[str, Any]] = []

    def record_event(self, event_type: str, service: str, provider: str = "",
                     model: str = "", success: bool = True,
                     error_message: str = "", latency_ms: float = 0,
                     tokens_used: int = 0, metadata: dict | None = None) -> dict:
        event = {"event_type": event_type, "service": service, "provider": provider,
                 "model": model, "success": success, "error_message": error_message,
                 "latency_ms": latency_ms, "tokens_used": tokens_used,
                 "metadata": metadata or {},
                 "recorded_at": datetime.now(timezone.utc).isoformat()}
        self._ai_events.append(event)
        return event

    def analyze(self, service: str = "", window_size: int = 20) -> list[dict[str, Any]]:
        events = self._ai_events
        if service:
            events = [e for e in events if e.get("service") == service]
        if not events:
            return []

        recent = events[-window_size:]
        incidents = []

        provider_failures: dict[str, list] = {}
        for e in recent:
            if not e.get("success"):
                provider = e.get("provider", "unknown")
                provider_failures.setdefault(provider, []).append(e)

        for provider, failures in provider_failures.items():
            failure_rate = len(failures) / max(len(recent), 1)
            if failure_rate > 0.5:
                incidents.append(self._create_incident(
                    "ai_provider_outage", service or "global",
                    f"AI provider '{provider}' has {failure_rate:.0%} failure rate",
                    "critical" if failure_rate > 0.8 else "high",
                    {"provider": provider, "failure_rate": failure_rate, "failure_count": len(failures)}))

        total_tokens = sum(e.get("tokens_used", 0) for e in recent)
        if total_tokens > 100000:
            incidents.append(self._create_incident(
                "ai_token_exhaustion", service or "global",
                f"High token consumption: {total_tokens} tokens in recent window",
                "high", {"total_tokens": total_tokens}))

        rag_events = [e for e in recent if e.get("event_type") == "rag_failure"]
        if len(rag_events) > 3:
            incidents.append(self._create_incident(
                "ai_rag_failure", service or "global",
                f"Multiple RAG failures: {len(rag_events)} in recent window",
                "high", {"rag_failure_count": len(rag_events)}))

        agent_failures = [e for e in recent if e.get("event_type") == "agent_failure"]
        if len(agent_failures) > 2:
            incidents.append(self._create_incident(
                "ai_agent_failure", service or "global",
                f"Multiple agent failures: {len(agent_failures)} in recent window",
                "high", {"agent_failure_count": len(agent_failures)}))

        tool_failures = [e for e in recent if e.get("event_type") == "tool_failure"]
        if len(tool_failures) > 3:
            incidents.append(self._create_incident(
                "ai_tool_failure", service or "global",
                f"Multiple tool failures: {len(tool_failures)} in recent window",
                "medium", {"tool_failure_count": len(tool_failures)}))

        unsafe_events = [e for e in recent if e.get("event_type") == "unsafe_behavior"]
        if unsafe_events:
            incidents.append(self._create_incident(
                "ai_unsafe_behavior", service or "global",
                f"Unsafe agent behavior detected: {len(unsafe_events)} events",
                "critical", {"unsafe_count": len(unsafe_events)}))

        self._detected_incidents.extend(incidents)
        return incidents

    def _create_incident(self, incident_type: str, service: str,
                         description: str, severity: str,
                         evidence: dict) -> dict:
        return {
            "id": str(uuid4()),
            "type": incident_type,
            "service": service,
            "description": description,
            "severity": severity,
            "source": "ai_incident_detector",
            "evidence": evidence,
            "detected_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_detected(self, service: str = "", limit: int = 50) -> list[dict]:
        results = self._detected_incidents
        if service:
            results = [i for i in results if i.get("service") == service]
        return results[:limit]

    def get_event_stats(self, service: str = "") -> dict[str, Any]:
        events = self._ai_events
        if service:
            events = [e for e in events if e.get("service") == service]
        total = len(events)
        failures = sum(1 for e in events if not e.get("success"))
        return {"total_events": total, "failures": failures,
                "failure_rate": failures / max(total, 1)}
