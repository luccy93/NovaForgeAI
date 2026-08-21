"""Incident Response Platform -- Core Incident Service (Volume 49).

Full incident lifecycle with validated state machine, timeline events,
correlation, AI-assisted triage, postmortem generation, and recurrence detection.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.incident.constants import (
    INCIDENT_TRANSITIONS, INCIDENT_STATUSES, INCIDENT_ACTIVE_STATUSES,
    SEVERITY_RANK, SEVERITY_TARGET_MINUTES, SEVERITIES,
)


def validate_transition(current: str, target: str) -> bool:
    if current not in INCIDENT_TRANSITIONS:
        return False
    return target in INCIDENT_TRANSITIONS.get(current, ())


def compute_severity_rank(severity: str) -> int:
    return SEVERITY_RANK.get(severity, 99)


class IncidentService:
    """In-memory incident lifecycle manager."""

    def __init__(self):
        self._incidents: dict[str, dict[str, Any]] = {}
        self._events: dict[str, list[dict[str, Any]]] = {}

    def create(self, tenant: str, title: str, description: str = "",
               severity: str = "SEV2", source: str = "alert",
               incident_type: str = "availability", service: str = "",
               environment: str = "production", symptoms: list | None = None,
               impact: dict | None = None, fingerprint: str = "") -> dict[str, Any]:
        incident_id = str(uuid4())
        now = datetime.now(timezone.utc)
        incident = {
            "id": incident_id,
            "tenant": tenant,
            "title": title,
            "description": description,
            "severity": severity if severity in SEVERITIES else "SEV2",
            "status": "detected",
            "source": source,
            "incident_type": incident_type,
            "service": service,
            "environment": environment,
            "commander": "",
            "impact": impact or {},
            "symptoms": symptoms or [],
            "root_cause": "",
            "remediation": "",
            "fingerprint": fingerprint,
            "correlated_deployments": [],
            "correlated_commits": [],
            "correlated_alerts": [],
            "correlated_security_findings": [],
            "blast_radius": {},
            "ai_hypotheses": [],
            "timeline_summary": "",
            "metadata_extra": {},
            "detected_at": now.isoformat(),
            "acknowledged_at": None,
            "mitigated_at": None,
            "resolved_at": None,
            "closed_at": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        self._incidents[incident_id] = incident
        self._events[incident_id] = []
        self._add_event(incident_id, "incident_detected", "system", "alert",
                        f"Incident detected: {title}", {"severity": severity, "source": source})
        return incident

    def get(self, incident_id: str) -> dict[str, Any] | None:
        return self._incidents.get(incident_id)

    def list_incidents(self, tenant: str = "", service: str = "", status: str = "",
                       severity: str = "", environment: str = "", limit: int = 50,
                       offset: int = 0) -> list[dict[str, Any]]:
        results = []
        for inc in self._incidents.values():
            if tenant and inc.get("tenant") != tenant:
                continue
            if service and inc.get("service") != service:
                continue
            if status and inc.get("status") != status:
                continue
            if severity and inc.get("severity") != severity:
                continue
            if environment and inc.get("environment") != environment:
                continue
            results.append(inc)
        results.sort(key=lambda i: i.get("detected_at", ""), reverse=True)
        return results[offset:offset + limit]

    def transition(self, incident_id: str, target_status: str,
                   message: str = "", actor: str = "user") -> dict[str, Any]:
        incident = self._incidents.get(incident_id)
        if not incident:
            raise ValueError(f"Incident {incident_id} not found")
        current = incident["status"]
        if not validate_transition(current, target_status):
            raise ValueError(f"Invalid transition: {current} -> {target_status}")

        now = datetime.now(timezone.utc)
        incident["status"] = target_status
        incident["updated_at"] = now.isoformat()

        if target_status == "triaged":
            pass
        elif target_status == "investigating":
            pass
        elif target_status == "mitigating":
            incident["mitigated_at"] = now.isoformat()
        elif target_status == "monitoring":
            pass
        elif target_status == "resolved":
            incident["resolved_at"] = now.isoformat()
        elif target_status == "closed":
            incident["closed_at"] = now.isoformat()
        elif target_status == "postmortem":
            pass

        self._add_event(incident_id, f"status_{target_status}", actor, "lifecycle",
                        message or f"Status changed to {target_status}")
        return incident

    def acknowledge(self, incident_id: str, commander: str = "on-call") -> dict[str, Any]:
        incident = self._incidents.get(incident_id)
        if not incident:
            raise ValueError(f"Incident {incident_id} not found")
        incident["commander"] = commander
        incident["acknowledged_at"] = datetime.now(timezone.utc).isoformat()
        incident["updated_at"] = datetime.now(timezone.utc).isoformat()
        if incident["status"] == "detected":
            self.transition(incident_id, "triaged", f"Acknowledged by {commander}", commander)
        return incident

    def update(self, incident_id: str, **kwargs: Any) -> dict[str, Any] | None:
        incident = self._incidents.get(incident_id)
        if not incident:
            return None
        for key in ("severity", "commander", "description", "impact", "symptoms",
                     "root_cause", "remediation", "timeline_summary", "metadata_extra"):
            if key in kwargs and kwargs[key] is not None:
                incident[key] = kwargs[key]
        incident["updated_at"] = datetime.now(timezone.utc).isoformat()
        return incident

    def add_correlated_deployment(self, incident_id: str, deployment: dict) -> bool:
        incident = self._incidents.get(incident_id)
        if not incident:
            return False
        incident["correlated_deployments"].append(deployment)
        self._add_event(incident_id, "deployment_correlated", "correlation_engine",
                        "correlation", f"Deployment correlated: {deployment.get('deploy_id', '')}",
                        {"deployment": deployment})
        return True

    def add_correlated_commit(self, incident_id: str, commit: dict) -> bool:
        incident = self._incidents.get(incident_id)
        if not incident:
            return False
        incident["correlated_commits"].append(commit)
        return True

    def add_correlated_alert(self, incident_id: str, alert: dict) -> bool:
        incident = self._incidents.get(incident_id)
        if not incident:
            return False
        incident["correlated_alerts"].append(alert)
        return True

    def add_correlated_security_finding(self, incident_id: str, finding: dict) -> bool:
        incident = self._incidents.get(incident_id)
        if not incident:
            return False
        incident["correlated_security_findings"].append(finding)
        return True

    def get_events(self, incident_id: str) -> list[dict[str, Any]]:
        return sorted(self._events.get(incident_id, []), key=lambda e: e.get("occurred_at", ""))

    def _add_event(self, incident_id: str, event_type: str, actor: str,
                   source: str, message: str, evidence: dict | None = None) -> dict:
        event = {
            "id": str(uuid4()),
            "incident_id": incident_id,
            "event_type": event_type,
            "actor": actor,
            "source": source,
            "message": message,
            "evidence": evidence or {},
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }
        if incident_id not in self._events:
            self._events[incident_id] = []
        self._events[incident_id].append(event)
        return event

    def get_active_count(self, tenant: str = "") -> int:
        return sum(1 for inc in self._incidents.values()
                   if inc["status"] in INCIDENT_ACTIVE_STATUSES
                   and (not tenant or inc.get("tenant") == tenant))

    def get_by_severity(self, tenant: str = "") -> dict[str, int]:
        counts: dict[str, int] = {}
        for inc in self._incidents.values():
            if tenant and inc.get("tenant") != tenant:
                continue
            sev = inc.get("severity", "SEV2")
            counts[sev] = counts.get(sev, 0) + 1
        return counts

    def get_by_fingerprint(self, tenant: str, fingerprint: str) -> list[dict[str, Any]]:
        return [inc for inc in self._incidents.values()
                if inc.get("tenant") == tenant and inc.get("fingerprint") == fingerprint]
