"""Incident Response Platform -- Anomaly Detector (Volume 49).

Configurable anomaly detection for latency, errors, traffic, resource
usage, and availability. Deterministic telemetry is the source of truth.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.incident.config import AnomalyConfig


class AnomalyDetector:
    """Configurable anomaly detection."""

    def __init__(self, config: AnomalyConfig | None = None):
        self._config = config or AnomalyConfig()
        self._data_points: dict[str, list[dict[str, Any]]] = {}
        self._anomalies: dict[str, list[dict[str, Any]]] = {}

    def record_metric(self, service: str, metric_name: str, value: float,
                      timestamp: str = "", labels: dict | None = None) -> dict:
        key = f"{service}:{metric_name}"
        point = {"service": service, "metric_name": metric_name, "value": value,
                 "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
                 "labels": labels or {}}
        if key not in self._data_points:
            self._data_points[key] = []
        self._data_points[key].append(point)
        if len(self._data_points[key]) > 1000:
            self._data_points[key] = self._data_points[key][-1000:]
        return point

    def detect_anomalies(self, service: str) -> list[dict[str, Any]]:
        anomalies = []
        anomalies.extend(self._check_latency(service))
        anomalies.extend(self._check_error_rate(service))
        anomalies.extend(self._check_resource_usage(service))
        if anomalies:
            if service not in self._anomalies:
                self._anomalies[service] = []
            self._anomalies[service].extend(anomalies)
        return anomalies

    def _check_latency(self, service: str) -> list[dict]:
        key = f"{service}:latency_ms"
        points = self._data_points.get(key, [])
        if len(points) < 3:
            return []
        recent = points[-5:]
        avg_latency = sum(p["value"] for p in recent) / len(recent)
        if avg_latency > self._config.latency_threshold_ms:
            return [{"type": "latency_anomaly", "service": service,
                     "metric": "latency_ms", "value": avg_latency,
                     "threshold": self._config.latency_threshold_ms,
                     "severity": "high" if avg_latency > self._config.latency_threshold_ms * 2 else "medium",
                     "detected_at": datetime.now(timezone.utc).isoformat()}]
        return []

    def _check_error_rate(self, service: str) -> list[dict]:
        key = f"{service}:error_rate"
        points = self._data_points.get(key, [])
        if len(points) < 3:
            return []
        recent = points[-5:]
        avg_rate = sum(p["value"] for p in recent) / len(recent)
        if avg_rate > self._config.error_rate_threshold:
            return [{"type": "error_rate_anomaly", "service": service,
                     "metric": "error_rate", "value": avg_rate,
                     "threshold": self._config.error_rate_threshold,
                     "severity": "critical" if avg_rate > 0.1 else "high",
                     "detected_at": datetime.now(timezone.utc).isoformat()}]
        return []

    def _check_resource_usage(self, service: str) -> list[dict]:
        anomalies = []
        for metric in ("cpu_usage", "memory_usage"):
            key = f"{service}:{metric}"
            points = self._data_points.get(key, [])
            if len(points) < 3:
                continue
            recent = points[-5:]
            avg = sum(p["value"] for p in recent) / len(recent)
            if avg > self._config.resource_usage_threshold:
                anomalies.append({"type": "resource_anomaly", "service": service,
                                  "metric": metric, "value": avg,
                                  "threshold": self._config.resource_usage_threshold,
                                  "severity": "high",
                                  "detected_at": datetime.now(timezone.utc).isoformat()})
        return anomalies

    def get_anomalies(self, service: str = "", limit: int = 50) -> list[dict]:
        if service:
            return self._anomalies.get(service, [])[:limit]
        all_anomalies = []
        for anomalies in self._anomalies.values():
            all_anomalies.extend(anomalies)
        all_anomalies.sort(key=lambda a: a.get("detected_at", ""), reverse=True)
        return all_anomalies[:limit]

    def get_metric_history(self, service: str, metric_name: str,
                           limit: int = 100) -> list[dict]:
        key = f"{service}:{metric_name}"
        return self._data_points.get(key, [])[-limit:]

    def compute_baseline(self, service: str, metric_name: str) -> dict[str, Any]:
        key = f"{service}:{metric_name}"
        points = self._data_points.get(key, [])
        if not points:
            return {"mean": 0, "std": 0, "min": 0, "max": 0, "count": 0}
        values = [p["value"] for p in points]
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        return {"mean": mean, "std": variance ** 0.5,
                "min": min(values), "max": max(values), "count": len(values)}
