"""Status page service — public service status, customer-safe incident info (Volume 54)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

SERVICE_DEFINITIONS = [
    {"id": "api", "name": "API", "group": "Core"},
    {"id": "ai_engine", "name": "AI Engine", "group": "Core"},
    {"id": "knowledge_base", "name": "Knowledge Base", "group": "Core"},
    {"id": "notifications", "name": "Notifications", "group": "Platform"},
    {"id": "marketplace", "name": "Marketplace", "group": "Platform"},
    {"id": "billing", "name": "Billing", "group": "Platform"},
    {"id": "ci_cd", "name": "CI/CD Pipeline", "group": "DevOps"},
    {"id": "security", "name": "Security Scanning", "group": "DevOps"},
]


class StatusPageService:
    def __init__(self):
        self._service_statuses: dict[str, dict] = {}
        self._maintenance_windows: list[dict] = []
        self._incidents: list[dict] = []
        for svc in SERVICE_DEFINITIONS:
            self._service_statuses[svc["id"]] = {
                **svc, "status": "operational",
                "message": None, "updated_at": datetime.now(timezone.utc).isoformat(),
            }

    def get_service_status(self, service_id: str) -> Optional[dict]:
        return self._service_statuses.get(service_id)

    def update_service_status(self, service_id: str, status: str,
                              message: Optional[str] = None) -> Optional[dict]:
        svc = self._service_statuses.get(service_id)
        if not svc:
            return None
        svc["status"] = status
        svc["message"] = message
        svc["updated_at"] = datetime.now(timezone.utc).isoformat()
        return svc

    def get_all_statuses(self) -> list[dict]:
        return list(self._service_statuses.values())

    def get_overall_status(self) -> str:
        statuses = [s["status"] for s in self._service_statuses.values()]
        if any(s == "major_outage" for s in statuses):
            return "major_outage"
        if any(s == "partial_outage" for s in statuses):
            return "partial_outage"
        if any(s == "degraded" for s in statuses):
            return "degraded"
        return "operational"

    def get_public_status(self) -> dict:
        return {
            "overall_status": self.get_overall_status(),
            "services": [
                {"name": s["name"], "status": s["status"], "message": s["message"],
                 "group": s["group"]}
                for s in self._service_statuses.values()
            ],
            "active_incidents": [self._sanitize_incident(i) for i in self._incidents
                                  if not i.get("resolved_at")],
            "maintenance": [m for m in self._maintenance_windows
                            if m.get("end_time", "") > datetime.now(timezone.utc).isoformat()],
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    def create_incident(self, title: str, service: str, severity: str,
                        impact: str = "investigating") -> dict:
        incident = {
            "id": f"inc-{len(self._incidents) + 1}",
            "title": title, "service": service, "severity": severity,
            "impact": impact, "status": "investigating",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "resolved_at": None, "updates": [],
        }
        self._incidents.append(incident)
        return incident

    def update_incident(self, incident_id: str, status: str,
                        message: Optional[str] = None) -> Optional[dict]:
        for inc in self._incidents:
            if inc["id"] == incident_id:
                inc["status"] = status
                inc["updates"].append({
                    "status": status, "message": message,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                if status == "resolved":
                    inc["resolved_at"] = datetime.now(timezone.utc).isoformat()
                return inc
        return None

    def create_maintenance(self, title: str, service_ids: list[str],
                           start_time: str, end_time: str,
                           description: str = "") -> dict:
        maintenance = {
            "id": f"mnt-{len(self._maintenance_windows) + 1}",
            "title": title, "service_ids": service_ids,
            "start_time": start_time, "end_time": end_time,
            "description": description,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._maintenance_windows.append(maintenance)
        return maintenance

    def _sanitize_incident(self, incident: dict) -> dict:
        return {
            "id": incident["id"],
            "title": incident["title"],
            "status": incident["status"],
            "impact": incident["impact"],
            "created_at": incident["created_at"],
            "resolved_at": incident.get("resolved_at"),
        }

    def get_incident_history(self, limit: int = 20) -> list[dict]:
        return [self._sanitize_incident(i) for i in self._incidents[-limit:]]


status_page_service = StatusPageService()
