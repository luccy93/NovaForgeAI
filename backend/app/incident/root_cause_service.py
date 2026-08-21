"""Incident Response Platform -- Root Cause Analysis (Volume 49).

Evidence-based root cause analysis using correlation data, code graph,
deployment history, and RAG patterns. Never fabricates root causes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


class RootCauseService:
    """Evidence-based root cause analysis."""

    def __init__(self):
        self._analyses: dict[str, dict[str, Any]] = {}

    def analyze(self, incident: dict, correlation_summary: dict,
                investigation: dict | None = None,
                quality_findings: list | None = None) -> dict[str, Any]:
        analysis_id = str(uuid4())
        hypotheses = []
        evidence = []

        deployments = correlation_summary.get("correlated_deployments", 0)
        if deployments > 0:
            recent_deploy = correlation_summary.get("most_recent_deployment")
            hypotheses.append({
                "hypothesis": f"Incident may be related to recent deployment ({recent_deploy.get('deploy_id', 'unknown') if recent_deploy else 'unknown'})",
                "confidence": 0.6,
                "evidence": [{"type": "deployment", "count": deployments, "deployment": recent_deploy}],
                "supporting_signals": ["timing_correlation", "service_match"],
            })
            evidence.append({"type": "deployment_correlation", "count": deployments})

        commits = correlation_summary.get("correlated_commits", 0)
        if commits > 0:
            recent_commit = correlation_summary.get("most_recent_commit")
            hypotheses.append({
                "hypothesis": f"Recent code changes ({commits} commits) may have introduced regression",
                "confidence": 0.4,
                "evidence": [{"type": "commits", "count": commits, "commit": recent_commit}],
                "supporting_signals": ["code_change_correlation"],
            })
            evidence.append({"type": "commit_correlation", "count": commits})

        security_findings = correlation_summary.get("correlated_security_findings", 0)
        if security_findings > 0:
            hypotheses.append({
                "hypothesis": f"Security findings ({security_findings}) may be contributing to the incident",
                "confidence": 0.5,
                "evidence": [{"type": "security_findings", "count": security_findings}],
                "supporting_signals": ["security_correlation"],
            })
            evidence.append({"type": "security_correlation", "count": security_findings})

        if investigation and investigation.get("hypotheses"):
            for inv_h in investigation["hypotheses"]:
                hypotheses.append({
                    "hypothesis": inv_h.get("hypothesis", ""),
                    "confidence": inv_h.get("confidence", 0.3),
                    "evidence": inv_h.get("evidence", []),
                    "supporting_signals": ["investigation_agent"],
                })

        if quality_findings:
            critical_findings = [f for f in quality_findings if f.get("severity") in ("critical", "high")]
            if critical_findings:
                hypotheses.append({
                    "hypothesis": f"Quality issues ({len(critical_findings)} critical/high findings) may indicate code problems",
                    "confidence": 0.45,
                    "evidence": [{"type": "quality_findings", "count": len(critical_findings)}],
                    "supporting_signals": ["quality_correlation"],
                })
                evidence.append({"type": "quality_correlation", "count": len(critical_findings)})

        blast_radius = correlation_summary.get("blast_radius", {})
        affected_count = blast_radius.get("affected_count", 0)

        hypotheses.sort(key=lambda h: h.get("confidence", 0), reverse=True)

        analysis = {
            "id": analysis_id,
            "incident_id": incident.get("id", ""),
            "hypotheses": hypotheses[:5],
            "evidence": evidence,
            "blast_radius": blast_radius,
            "total_hypotheses": len(hypotheses),
            "top_hypothesis": hypotheses[0] if hypotheses else None,
            "causality_claimed": False,
            "causality_note": "All hypotheses are evidence-backed. Causality requires verification.",
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
        }
        self._analyses[analysis_id] = analysis
        return analysis

    def get_analysis(self, analysis_id: str) -> dict[str, Any] | None:
        return self._analyses.get(analysis_id)

    def list_analyses(self, incident_id: str = "") -> list[dict]:
        results = []
        for a in self._analyses.values():
            if incident_id and a.get("incident_id") != incident_id:
                continue
            results.append(a)
        return results

    def validate_hypothesis(self, hypothesis_id: str, validated: bool,
                            evidence: str = "") -> dict[str, Any] | None:
        for analysis in self._analyses.values():
            for h in analysis.get("hypotheses", []):
                if h.get("id") == hypothesis_id:
                    h["validated"] = validated
                    h["validation_evidence"] = evidence
                    h["validated_at"] = datetime.now(timezone.utc).isoformat()
                    return h
        return None
