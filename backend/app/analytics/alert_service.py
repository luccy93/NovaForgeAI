"""Unified Analytics Platform -- Alert Service (Volume 50)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


class AnalyticsAlertService:
    """Analytics alert service."""

    def __init__(self):
        self._alerts: dict[str, dict[str, Any]] = {}
        self._history: list[dict[str, Any]] = []

    def create_alert(self, tenant: str, name: str, alert_type: str,
                     metric_name: str = "", condition: dict | None = None,
                     severity: str = "medium", cooldown_seconds: int = 3600) -> dict:
        alert_id = f"alert_{uuid4().hex[:12]}"
        alert = {"id": alert_id, "tenant": tenant, "name": name,
                 "alert_type": alert_type, "metric_name": metric_name,
                 "condition": condition or {}, "severity": severity,
                 "cooldown_seconds": cooldown_seconds, "status": "active",
                 "created_at": datetime.now(timezone.utc).isoformat(),
                 "last_triggered": None}
        self._alerts[alert_id] = alert
        return alert

    def get_alert(self, alert_id: str) -> dict | None:
        return self._alerts.get(alert_id)

    def list_alerts(self, tenant: str = "", alert_type: str = "",
                    status: str = "", limit: int = 50) -> list[dict]:
        results = []
        for a in self._alerts.values():
            if tenant and a.get("tenant") != tenant:
                continue
            if alert_type and a.get("alert_type") != alert_type:
                continue
            if status and a.get("status") != status:
                continue
            results.append(a)
        return results[:limit]

    def update_alert(self, alert_id: str, **kwargs) -> dict | None:
        alert = self._alerts.get(alert_id)
        if not alert:
            return None
        for k, v in kwargs.items():
            if k in ("name", "condition", "severity", "cooldown_seconds", "status"):
                alert[k] = v
        return alert

    def delete_alert(self, alert_id: str) -> bool:
        if alert_id in self._alerts:
            del self._alerts[alert_id]
            return True
        return False

    def evaluate_alerts(self, tenant: str, metrics: dict | None = None) -> list[dict]:
        triggered = []
        metrics = metrics or {}
        now = datetime.now(timezone.utc).isoformat()
        for a in self._alerts.values():
            if a["tenant"] != tenant or a["status"] != "active":
                continue
            if a["last_triggered"]:
                try:
                    last = datetime.fromisoformat(a["last_triggered"])
                    cooldown_end = last.replace(second=last.second + a["cooldown_seconds"])
                    if now < cooldown_end.isoformat():
                        continue
                except (ValueError, TypeError):
                    pass
            metric_val = metrics.get(a.get("metric_name", ""))
            if metric_val is not None:
                triggered.append(self.trigger_alert(a["id"], float(metric_val)))
        return triggered

    def trigger_alert(self, alert_id: str, current_value: float = 0,
                      message: str = "") -> dict:
        alert = self._alerts.get(alert_id)
        if not alert:
            return {"error": "alert not found"}
        entry = {"alert_id": alert_id, "tenant": alert["tenant"],
                 "alert_name": alert["name"], "alert_type": alert["alert_type"],
                 "severity": alert["severity"], "current_value": current_value,
                 "message": message or f"Alert triggered: {alert['name']}",
                 "triggered_at": datetime.now(timezone.utc).isoformat()}
        self._history.append(entry)
        alert["last_triggered"] = entry["triggered_at"]
        return entry

    def get_alert_history(self, tenant: str = "", alert_id: str = "",
                          limit: int = 50) -> list[dict]:
        results = []
        for h in reversed(self._history):
            if tenant and h.get("tenant") != tenant:
                continue
            if alert_id and h.get("alert_id") != alert_id:
                continue
            results.append(h)
            if len(results) >= limit:
                break
        return results

    def get_alert_summary(self, tenant: str = "") -> dict:
        total = 0
        active = 0
        triggered_today = 0
        today_str = datetime.now(timezone.utc).date().isoformat()
        for a in self._alerts.values():
            if tenant and a.get("tenant") != tenant:
                continue
            total += 1
            if a["status"] == "active":
                active += 1
        for h in self._history:
            if tenant and h.get("tenant") != tenant:
                continue
            if h.get("triggered_at", "").startswith(today_str):
                triggered_today += 1
        return {"total_alerts": total, "active": active,
                "triggered_today": triggered_today}


analytics_alert_service = AnalyticsAlertService()
