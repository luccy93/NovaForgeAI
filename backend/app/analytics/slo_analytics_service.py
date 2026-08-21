"""Unified Analytics Platform -- SLO Analytics (Volume 50)."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import uuid4


class SLOAnalyticsService:
    """SLO analytics with error budget tracking."""

    def __init__(self):
        self._measurements: list[dict[str, Any]] = []
        self._slos: dict[str, dict[str, Any]] = {}

    def record_slo_measurement(self, tenant: str, service: str, metric_name: str,
                               actual_value: float, target: float,
                               window_start: str, window_end: str) -> dict:
        measurement = {
            "id": f"slo_{uuid4().hex[:12]}", "tenant": tenant, "service": service,
            "metric_name": metric_name, "actual_value": actual_value,
            "target": target, "compliant": actual_value >= target,
            "window_start": window_start, "window_end": window_end,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        self._measurements.append(measurement)
        key = f"{tenant}:{service}:{metric_name}"
        self._slos[key] = {"tenant": tenant, "service": service,
                           "metric_name": metric_name, "target": target,
                           "last_actual": actual_value, "last_compliant": measurement["compliant"],
                           "last_window_end": window_end}
        return measurement

    def get_slo_status(self, tenant: str, service: str = "") -> dict:
        services: dict[str, list[dict]] = {}
        for m in self._measurements:
            if m["tenant"] != tenant:
                continue
            if service and m["service"] != service:
                continue
            services.setdefault(m["service"], []).append(m)
        result = {}
        for svc, ms in services.items():
            total = len(ms)
            compliant = sum(1 for m in ms if m["compliant"])
            result[svc] = {"total_measurements": total, "compliant": compliant,
                           "compliance_rate": compliant / total if total else 0}
        return result

    def get_slo_trends(self, tenant: str, service: str = "",
                       granularity: str = "day", start_time: str = "",
                       end_time: str = "") -> list[dict]:
        results = []
        for m in self._measurements:
            if m["tenant"] != tenant:
                continue
            if service and m["service"] != service:
                continue
            if start_time and m["window_end"] < start_time:
                continue
            if end_time and m["window_end"] > end_time:
                continue
            results.append(m)
        return results

    def get_error_budget(self, tenant: str, service: str = "") -> dict:
        ms = [m for m in self._measurements if m["tenant"] == tenant
              and (not service or m["service"] == service)]
        if not ms:
            return {"service": service, "budget_remaining_pct": 1.0, "burn_rate": 0}
        total = len(ms)
        violations = sum(1 for m in ms if not m["compliant"])
        budget = 1.0 - (violations / total) if total else 1.0
        return {"service": service, "budget_remaining_pct": budget,
                "violations": violations, "total": total}

    def get_slo_breaches(self, tenant: str, service: str = "",
                         start_time: str = "", end_time: str = "") -> list[dict]:
        breaches = []
        for m in self._measurements:
            if m["tenant"] != tenant:
                continue
            if m["compliant"]:
                continue
            if service and m["service"] != service:
                continue
            if start_time and m["window_end"] < start_time:
                continue
            if end_time and m["window_end"] > end_time:
                continue
            breaches.append(m)
        return breaches

    def compute_burn_rate(self, tenant: str, service: str = "",
                          window_hours: int = 1) -> float:
        now = datetime.now(timezone.utc)
        cutoff = (now - timedelta(hours=window_hours)).isoformat()
        recent = [m for m in self._measurements
                  if m["tenant"] == tenant and m["window_end"] >= cutoff
                  and (not service or m["service"] == service)]
        if not recent:
            return 0.0
        violations = sum(1 for m in recent if not m["compliant"])
        return violations / len(recent) if recent else 0.0

    def get_slo_summary(self, tenant: str = "") -> dict:
        services: dict[str, dict] = {}
        for m in self._measurements:
            if tenant and m["tenant"] != tenant:
                continue
            svc = m["service"]
            if svc not in services:
                services[svc] = {"total": 0, "compliant": 0}
            services[svc]["total"] += 1
            if m["compliant"]:
                services[svc]["compliant"] += 1
        return {svc: {**v, "compliance_rate": v["compliant"] / v["total"] if v["total"] else 0}
                for svc, v in services.items()}


slo_analytics_service = SLOAnalyticsService()
