"""Incident Response Platform -- Correlation Service (Volume 49).

Cross-signal correlation: incident ↔ deployments, commits, security findings,
quality findings. Uses time-window matching and service identity.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any


class CorrelationService:
    """Correlate incidents with deployments, commits, security findings."""

    def __init__(self):
        self._deployments: list[dict[str, Any]] = []
        self._commits: list[dict[str, Any]] = []
        self._security_findings: list[dict[str, Any]] = []

    def record_deployment(self, deploy_id: str, service: str, environment: str,
                          version: str = "", commit_sha: str = "",
                          deployed_at: str = "", status: str = "completed",
                          metadata: dict | None = None) -> dict:
        dep = {"deploy_id": deploy_id, "service": service, "environment": environment,
               "version": version, "commit_sha": commit_sha, "deployed_at": deployed_at,
               "status": status, "metadata": metadata or {}}
        self._deployments.append(dep)
        return dep

    def record_commit(self, commit_sha: str, service: str, repository: str,
                      author: str = "", message: str = "",
                      committed_at: str = "", files_changed: list | None = None) -> dict:
        c = {"commit_sha": commit_sha, "service": service, "repository": repository,
             "author": author, "message": message, "committed_at": committed_at,
             "files_changed": files_changed or []}
        self._commits.append(c)
        return c

    def record_security_finding(self, finding_id: str, service: str,
                                severity: str = "medium", title: str = "",
                                file_path: str = "", detected_at: str = "",
                                metadata: dict | None = None) -> dict:
        f = {"finding_id": finding_id, "service": service, "severity": severity,
             "title": title, "file_path": file_path, "detected_at": detected_at,
             "metadata": metadata or {}}
        self._security_findings.append(f)
        return f

    def correlate_deployments(self, incident: dict, window_hours: int = 24,
                              max_results: int = 10) -> list[dict[str, Any]]:
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
        for dep in self._deployments:
            if service and dep.get("service") != service:
                continue
            if environment and dep.get("environment") != environment:
                continue
            try:
                dep_time = datetime.fromisoformat(dep.get("deployed_at", ""))
                if window_start <= dep_time <= incident_time:
                    dep["_correlation_type"] = "deployment"
                    dep["_time_delta_minutes"] = (incident_time - dep_time).total_seconds() / 60
                    matches.append(dep)
            except (ValueError, TypeError):
                continue
        matches.sort(key=lambda d: d.get("_time_delta_minutes", 9999))
        return matches[:max_results]

    def correlate_commits(self, incident: dict, window_hours: int = 48,
                          max_results: int = 20) -> list[dict[str, Any]]:
        service = incident.get("service", "")
        detected_at = incident.get("detected_at", "")
        if not detected_at:
            return []
        try:
            incident_time = datetime.fromisoformat(detected_at)
        except (ValueError, TypeError):
            return []

        window_start = incident_time - timedelta(hours=window_hours)
        matches = []
        for commit in self._commits:
            if service and commit.get("service") != service:
                continue
            try:
                c_time = datetime.fromisoformat(commit.get("committed_at", ""))
                if window_start <= c_time <= incident_time:
                    commit["_correlation_type"] = "commit"
                    commit["_time_delta_minutes"] = (incident_time - c_time).total_seconds() / 60
                    matches.append(commit)
            except (ValueError, TypeError):
                continue
        matches.sort(key=lambda c: c.get("_time_delta_minutes", 9999))
        return matches[:max_results]

    def correlate_security_findings(self, incident: dict,
                                    max_results: int = 10) -> list[dict[str, Any]]:
        service = incident.get("service", "")
        matches = []
        for finding in self._security_findings:
            if service and finding.get("service") != service:
                continue
            if finding.get("severity") in ("critical", "high"):
                finding["_correlation_type"] = "security_finding"
                matches.append(finding)
        return matches[:max_results]

    def compute_blast_radius(self, incident: dict) -> dict[str, Any]:
        service = incident.get("service", "")
        environment = incident.get("environment", "")
        affected_services = {service} if service else set()
        for dep in self._deployments:
            if dep.get("service") == service and dep.get("environment") == environment:
                affected_services.add(dep["service"])
        return {
            "primary_service": service,
            "environment": environment,
            "affected_services": list(affected_services),
            "affected_count": len(affected_services),
            "estimated_scope": "contained" if len(affected_services) <= 2 else "widespread",
        }

    def get_recent_deployments(self, service: str = "", hours: int = 24) -> list[dict]:
        now = datetime.now(timezone.utc)
        results = []
        for dep in self._deployments:
            if service and dep.get("service") != service:
                continue
            try:
                dep_time = datetime.fromisoformat(dep.get("deployed_at", ""))
                if (now - dep_time).total_seconds() < hours * 3600:
                    results.append(dep)
            except (ValueError, TypeError):
                continue
        return results

    def get_summary(self, incident: dict) -> dict[str, Any]:
        deployments = self.correlate_deployments(incident)
        commits = self.correlate_commits(incident)
        security = self.correlate_security_findings(incident)
        return {
            "correlated_deployments": len(deployments),
            "correlated_commits": len(commits),
            "correlated_security_findings": len(security),
            "blast_radius": self.compute_blast_radius(incident),
            "most_recent_deployment": deployments[0] if deployments else None,
            "most_recent_commit": commits[0] if commits else None,
        }
