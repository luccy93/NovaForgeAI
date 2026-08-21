"""Incident Response Platform -- SDK (Volume 49)."""

from __future__ import annotations

from typing import Any, Optional


class IncidentMixin:
    """Sync SDK methods for the Incident Response Platform."""

    def incident_create_incident(self, tenant: str = "default", title: str = "",
                                  severity: str = "SEV2", service: str = "",
                                  incident_type: str = "technical", source: str = "sdk",
                                  description: str = "", environment: str = "",
                                  symptoms: str = "", impact: str = "") -> dict:
        return self._post("/incident/incidents", json={
            "tenant": tenant, "title": title, "severity": severity, "service": service,
            "incident_type": incident_type, "source": source, "description": description,
            "environment": environment, "symptoms": symptoms, "impact": impact})

    def incident_list_incidents(self, tenant: str = "default", service: str = "",
                                 status: str = "", severity: str = "",
                                 environment: str = "", limit: int = 50,
                                 offset: int = 0) -> list:
        params: dict[str, Any] = {"tenant": tenant, "limit": limit, "offset": offset}
        for k, v in [("service", service), ("status", status),
                     ("severity", severity), ("environment", environment)]:
            if v:
                params[k] = v
        return self._get("/incident/incidents", params=params)

    def incident_get_incident(self, incident_id: str) -> dict:
        return self._get(f"/incident/incidents/{incident_id}")

    def incident_acknowledge(self, incident_id: str, commander: str = "") -> dict:
        return self._post(f"/incident/incidents/{incident_id}/acknowledge",
                          json={"commander": commander})

    def incident_transition(self, incident_id: str, status: str, message: str = "",
                            actor: str = "sdk") -> dict:
        return self._post(f"/incident/incidents/{incident_id}/transition",
                          json={"status": status, "message": message, "actor": actor})

    def incident_update(self, incident_id: str, severity: str = "",
                        commander: str = "", description: str = "") -> dict:
        payload: dict[str, Any] = {}
        if severity:
            payload["severity"] = severity
        if commander:
            payload["commander"] = commander
        if description:
            payload["description"] = description
        return self._put(f"/incident/incidents/{incident_id}", json=payload)

    def incident_get_status(self, incident_id: str) -> dict:
        return self._get(f"/incident/incidents/{incident_id}/status")

    def incident_get_active_count(self, tenant: str = "default") -> dict:
        return self._get("/incident/incidents/active/count", params={"tenant": tenant})

    def incident_ingest_alert(self, tenant: str = "default", alert_source: str = "",
                               alert_id: str = "", rule_name: str = "",
                               severity: str = "medium", service: str = "",
                               environment: str = "", message: str = "",
                               raw_payload: dict | None = None,
                               labels: dict | None = None) -> dict:
        return self._post("/incident/alerts/ingest", json={
            "tenant": tenant, "alert_source": alert_source, "alert_id": alert_id,
            "rule_name": rule_name, "severity": severity, "service": service,
            "environment": environment, "message": message,
            "raw_payload": raw_payload or {}, "labels": labels or {}})

    def incident_list_alerts(self, tenant: str = "default", service: str = "",
                              status: str = "", environment: str = "",
                              limit: int = 50) -> list:
        params: dict[str, Any] = {"tenant": tenant, "limit": limit}
        for k, v in [("service", service), ("status", status),
                     ("environment", environment)]:
            if v:
                params[k] = v
        return self._get("/incident/alerts", params=params)

    def incident_acknowledge_alert(self, alert_id: str) -> dict:
        return self._post(f"/incident/alerts/{alert_id}/acknowledge")

    def incident_resolve_alert(self, alert_id: str) -> dict:
        return self._post(f"/incident/alerts/{alert_id}/resolve")

    def incident_get_timeline(self, incident_id: str) -> dict:
        return self._get(f"/incident/incidents/{incident_id}/timeline")

    def incident_investigate(self, incident_id: str,
                              focus_areas: list | None = None) -> dict:
        return self._post("/incident/investigate", json={
            "incident_id": incident_id, "focus_areas": focus_areas or []})

    def incident_analyze_root_cause(self, incident_id: str) -> dict:
        return self._post(f"/incident/incidents/{incident_id}/analyze")

    def incident_triage(self, incident_id: str) -> dict:
        return self._post(f"/incident/incidents/{incident_id}/triage")

    def incident_get_correlation(self, incident_id: str) -> dict:
        return self._get(f"/incident/incidents/{incident_id}/correlation")

    def incident_get_blast_radius(self, incident_id: str) -> dict:
        return self._get(f"/incident/incidents/{incident_id}/blast-radius")

    def incident_create_action(self, incident_id: str, action_type: str = "",
                                description: str = "", risk_level: str = "low") -> dict:
        return self._post("/incident/actions", json={
            "incident_id": incident_id, "action_type": action_type,
            "description": description, "risk_level": risk_level})

    def incident_approve_action(self, action_id: str, approver: str = "") -> dict:
        return self._post(f"/incident/actions/{action_id}/approve",
                          json={"approver": approver})

    def incident_execute_action(self, action_id: str, dry_run: bool = True) -> dict:
        return self._post(f"/incident/actions/{action_id}/execute",
                          json={"dry_run": dry_run})

    def incident_create_runbook(self, tenant: str = "default", name: str = "",
                                 incident_type: str = "", description: str = "",
                                 steps: list | None = None) -> dict:
        return self._post("/incident/runbooks", json={
            "tenant": tenant, "name": name, "incident_type": incident_type,
            "description": description, "steps": steps or []})

    def incident_list_runbooks(self, tenant: str = "default",
                                incident_type: str = "") -> list:
        params: dict[str, Any] = {"tenant": tenant}
        if incident_type:
            params["incident_type"] = incident_type
        return self._get("/incident/runbooks", params=params)

    def incident_execute_runbook(self, runbook_id: str, incident_id: str = "",
                                  dry_run: bool = True) -> dict:
        params: dict[str, Any] = {"dry_run": dry_run}
        if incident_id:
            params["incident_id"] = incident_id
        return self._post(f"/incident/runbooks/{runbook_id}/execute", params=params)

    def incident_create_postmortem(self, incident_id: str, summary: str = "",
                                    root_cause: str = "", impact: str = "") -> dict:
        return self._post("/incident/postmortems", json={
            "incident_id": incident_id, "summary": summary,
            "root_cause": root_cause, "impact": impact})

    def incident_check_escalation(self, incident_id: str) -> dict:
        return self._post(f"/incident/incidents/{incident_id}/escalation/check")

    def incident_create_escalation_policy(self, tenant: str = "default",
                                           name: str = "",
                                           description: str = "") -> dict:
        return self._post("/incident/escalation-policies", json={
            "tenant": tenant, "name": name, "description": description})

    def incident_get_anomalies(self, service: str = "", limit: int = 50) -> list:
        params: dict[str, Any] = {"limit": limit}
        if service:
            params["service"] = service
        return self._get("/incident/anomalies", params=params)

    def incident_get_slo(self, service: str, tenant: str = "default") -> dict:
        return self._get(f"/incident/slo/{service}", params={"tenant": tenant})

    def incident_get_metrics(self, service: str, tenant: str = "default") -> dict:
        return self._get(f"/incident/metrics/{service}", params={"tenant": tenant})

    def incident_health(self) -> dict:
        return self._get("/incident/health")

    def incident_check_recurrence(self, incident_id: str) -> dict:
        return self._get(f"/incident/recurrence/{incident_id}")


class AsyncIncidentMixin:
    """Async SDK methods for the Incident Response Platform."""

    async def incident_create_incident(self, tenant: str = "default", title: str = "",
                                        severity: str = "SEV2", service: str = "",
                                        incident_type: str = "technical",
                                        source: str = "sdk", description: str = "",
                                        environment: str = "", symptoms: str = "",
                                        impact: str = "") -> dict:
        return await self._post("/incident/incidents", json={
            "tenant": tenant, "title": title, "severity": severity, "service": service,
            "incident_type": incident_type, "source": source, "description": description,
            "environment": environment, "symptoms": symptoms, "impact": impact})

    async def incident_list_incidents(self, tenant: str = "default", limit: int = 50) -> list:
        return await self._get("/incident/incidents", params={"tenant": tenant, "limit": limit})

    async def incident_get_incident(self, incident_id: str) -> dict:
        return await self._get(f"/incident/incidents/{incident_id}")

    async def incident_health(self) -> dict:
        return await self._get("/incident/health")
