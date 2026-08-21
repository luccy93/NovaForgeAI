"""Incident Response Platform -- Alert Ingestion Service (Volume 49).

Alert ingestion, fingerprinting, dedup, severity normalization,
maintenance-window suppression, and cross-tenant isolation.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


class AlertIngestionService:
    """In-memory alert ingestion with deduplication and fingerprinting."""

    def __init__(self):
        self._alerts: dict[str, dict[str, Any]] = {}
        self._fingerprints: dict[str, str] = {}
        self._maintenance_windows: list[dict[str, Any]] = []

    def ingest(self, tenant: str, alert_source: str, alert_id: str, rule_name: str,
               severity: str, service: str, environment: str, message: str,
               raw_payload: dict | None = None, labels: dict | None = None,
               timestamp: str = "") -> dict[str, Any]:
        labels = labels or {}
        fingerprint = self._compute_fingerprint(service, environment, rule_name, labels)

        if self._is_in_maintenance(service, environment):
            return {"status": "suppressed", "reason": "maintenance_window", "fingerprint": fingerprint}

        existing = self._find_active_by_fingerprint(tenant, fingerprint)
        if existing:
            existing["alert_count"] = existing.get("alert_count", 1) + 1
            existing["last_received_at"] = datetime.now(timezone.utc).isoformat()
            return {"status": "deduplicated", "incident_id": existing.get("incident_id", ""),
                    "fingerprint": fingerprint, "alert_id": existing["id"]}

        alert_id_str = str(uuid4())
        alert = {
            "id": alert_id_str,
            "tenant": tenant,
            "alert_source": alert_source,
            "external_alert_id": alert_id,
            "rule_name": rule_name,
            "severity": severity,
            "fingerprint": fingerprint,
            "service": service,
            "environment": environment,
            "message": message,
            "status": "firing",
            "raw_payload": raw_payload or {},
            "labels": labels,
            "incident_id": "",
            "alert_count": 1,
            "received_at": datetime.now(timezone.utc).isoformat(),
            "first_received_at": datetime.now(timezone.utc).isoformat(),
            "last_received_at": datetime.now(timezone.utc).isoformat(),
        }
        self._alerts[alert_id_str] = alert
        self._fingerprints[alert_id_str] = fingerprint
        return {"status": "ingested", "alert_id": alert_id_str, "fingerprint": fingerprint}

    def acknowledge(self, alert_id: str, ack_by: str = "user") -> dict[str, Any] | None:
        alert = self._alerts.get(alert_id)
        if not alert:
            return None
        alert["status"] = "acknowledged"
        alert["acknowledged_by"] = ack_by
        alert["acknowledged_at"] = datetime.now(timezone.utc).isoformat()
        return alert

    def resolve(self, alert_id: str) -> dict[str, Any] | None:
        alert = self._alerts.get(alert_id)
        if not alert:
            return None
        alert["status"] = "resolved"
        alert["resolved_at"] = datetime.now(timezone.utc).isoformat()
        return alert

    def resolve_by_fingerprint(self, fingerprint: str, tenant: str = "") -> int:
        count = 0
        for alert in self._alerts.values():
            if alert.get("fingerprint") == fingerprint and alert["status"] == "firing":
                if not tenant or alert.get("tenant") == tenant:
                    alert["status"] = "resolved"
                    alert["resolved_at"] = datetime.now(timezone.utc).isoformat()
                    count += 1
        return count

    def get_alert(self, alert_id: str) -> dict[str, Any] | None:
        return self._alerts.get(alert_id)

    def list_alerts(self, tenant: str = "", service: str = "", status: str = "",
                    environment: str = "", limit: int = 50) -> list[dict[str, Any]]:
        results = []
        for alert in self._alerts.values():
            if tenant and alert.get("tenant") != tenant:
                continue
            if service and alert.get("service") != service:
                continue
            if status and alert.get("status") != status:
                continue
            if environment and alert.get("environment") != environment:
                continue
            results.append(alert)
        results.sort(key=lambda a: a.get("received_at", ""), reverse=True)
        return results[:limit]

    def get_firing_count(self, tenant: str = "") -> int:
        return sum(1 for a in self._alerts.values()
                   if a["status"] == "firing" and (not tenant or a.get("tenant") == tenant))

    def add_maintenance_window(self, service: str, environment: str,
                               starts_at: str, ends_at: str) -> dict:
        window = {"service": service, "environment": environment,
                  "starts_at": starts_at, "ends_at": ends_at, "id": str(uuid4())}
        self._maintenance_windows.append(window)
        return window

    def remove_maintenance_window(self, window_id: str) -> bool:
        before = len(self._maintenance_windows)
        self._maintenance_windows = [w for w in self._maintenance_windows if w["id"] != window_id]
        return len(self._maintenance_windows) < before

    def _is_in_maintenance(self, service: str, environment: str) -> bool:
        now = datetime.now(timezone.utc)
        for w in self._maintenance_windows:
            if w["service"] == service and w["environment"] == environment:
                try:
                    starts = datetime.fromisoformat(w["starts_at"])
                    ends = datetime.fromisoformat(w["ends_at"])
                    if starts <= now <= ends:
                        return True
                except (ValueError, TypeError):
                    pass
        return False

    def _find_active_by_fingerprint(self, tenant: str, fingerprint: str) -> dict[str, Any] | None:
        for alert in self._alerts.values():
            if (alert.get("tenant") == tenant
                    and alert.get("fingerprint") == fingerprint
                    and alert["status"] == "firing"):
                return alert
        return None

    @staticmethod
    def _compute_fingerprint(service: str, environment: str, rule_name: str,
                              labels: dict) -> str:
        key_parts = [service, environment, rule_name]
        for k in sorted(labels.keys()):
            key_parts.append(f"{k}={labels[k]}")
        raw = "|".join(key_parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:32]
