"""Incident Response Platform -- Triage Service (Volume 49).

Automated incident triage: generates summary, severity suggestion,
affected services, suspected components, recent changes, investigation steps.
Distinguishes facts from hypotheses.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class TriageService:
    """Automated incident triage."""

    def __init__(self):
        self._triages: dict[str, dict[str, Any]] = {}

    def triage(self, incident: dict, correlation_summary: dict,
               investigation: dict | None = None) -> dict[str, Any]:
        incident_id = incident.get("id", "")
        service = incident.get("service", "")
        severity = incident.get("severity", "SEV2")
        source = incident.get("source", "alert")
        status = incident.get("status", "detected")

        facts = []
        hypotheses = []

        facts.append(f"Incident detected at {incident.get('detected_at', 'unknown')}")
        facts.append(f"Source: {source}")
        facts.append(f"Current severity: {severity}")
        facts.append(f"Current status: {status}")

        deployments = correlation_summary.get("correlated_deployments", 0)
        if deployments > 0:
            facts.append(f"{deployments} deployment(s) correlated within 24h window")
            hypotheses.append("Recent deployment may be contributing factor")

        commits = correlation_summary.get("correlated_commits", 0)
        if commits > 0:
            facts.append(f"{commits} commit(s) correlated within 48h window")

        security = correlation_summary.get("correlated_security_findings", 0)
        if security > 0:
            facts.append(f"{security} security finding(s) correlated")
            hypotheses.append("Security findings may be related")

        blast_radius = correlation_summary.get("blast_radius", {})
        affected = blast_radius.get("affected_services", [])
        if affected:
            facts.append(f"Affected services: {', '.join(affected)}")

        severity_suggestion = self._suggest_severity(incident, correlation_summary, investigation)

        investigation_steps = self._recommend_steps(incident, correlation_summary, investigation)

        suspected_components = [service] if service else []
        if any("deployment" in str(c).lower() for c in incident.get("correlated_deployments", [])):
            suspected_components.append("deployment_pipeline")
        if security > 0:
            suspected_components.append("security")

        triage = {
            "incident_id": incident_id,
            "facts": facts,
            "hypotheses": hypotheses,
            "severity_suggestion": severity_suggestion,
            "affected_services": affected or ([service] if service else []),
            "suspected_components": suspected_components,
            "recent_changes": correlation_summary.get("changes", []),
            "investigation_steps": investigation_steps,
            "triaged_at": datetime.now(timezone.utc).isoformat(),
            "triage_confidence": 0.7 if investigation else 0.4,
        }
        self._triages[incident_id] = triage
        return triage

    def get_triage(self, incident_id: str) -> dict[str, Any] | None:
        return self._triages.get(incident_id)

    def _suggest_severity(self, incident: dict, correlation: dict,
                          investigation: dict | None) -> str:
        current = incident.get("severity", "SEV2")
        blast = correlation.get("blast_radius", {})
        affected = blast.get("affected_count", 0)
        deployments = correlation.get("correlated_deployments", 0)

        if affected > 5 or current == "SEV0":
            return "SEV0"
        if affected > 2 or (deployments > 0 and current in ("SEV0", "SEV1")):
            return "SEV1"
        if current in ("SEV2", "SEV3"):
            return current
        return "SEV2"

    def _recommend_steps(self, incident: dict, correlation: dict,
                         investigation: dict | None) -> list[str]:
        steps = []
        steps.append("1. Review incident timeline and correlated events")
        if correlation.get("correlated_deployments", 0) > 0:
            steps.append("2. Investigate recent deployment for potential regression")
            steps.append("3. Consider rollback if deployment is suspected cause")
        else:
            steps.append("2. Check service health metrics and error rates")
        if correlation.get("correlated_security_findings", 0) > 0:
            steps.append("4. Review correlated security findings")
        if not investigation:
            steps.append(f"{len(steps)+1}. Run AI investigation for deeper analysis")
        steps.append(f"{len(steps)+1}. Update status and communicate to stakeholders")
        return steps
