"""NovaForge Analytics Platform -- Anomaly Detection Service (Volume 50).

In-memory, Z-score based anomaly detection over metric observations.
A baseline (mean/std) is maintained per tenant and metric; an observed
value is flagged as an anomaly when its absolute deviation from the
baseline exceeds ``sensitivity`` standard deviations (default 2.0).
At least 10 baseline samples are required before anything is flagged.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timezone
from uuid import uuid4

DEFAULT_SENSITIVITY = 2.0
MIN_BASELINE_SAMPLES = 10
MAX_OBSERVATIONS_PER_METRIC = 5000
MAX_STORED_ANOMALIES = 2000

SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"
SEVERITY_CRITICAL = "critical"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(value: str) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


class AnomalyService:
    """Detects metric anomalies against rolling in-memory baselines."""

    def __init__(self, sensitivity: float = DEFAULT_SENSITIVITY,
                 min_samples: int = MIN_BASELINE_SAMPLES):
        self._sensitivity = max(0.5, float(sensitivity))
        self._min_samples = max(2, int(min_samples))
        self._observations: dict[tuple[str, str], list[dict]] = {}
        self._anomalies: list[dict] = []

    # ── Recording ──────────────────────────────────────────────────────

    def record_observation(self, metric_name: str, value: float,
                           dimensions: dict | None = None,
                           tenant: str = "default",
                           timestamp: str = "") -> dict:
        observation = {
            "observation_id": uuid4().hex,
            "tenant": tenant,
            "metric_name": metric_name,
            "value": float(value),
            "dimensions": dict(dimensions or {}),
            "timestamp": timestamp or _utc_now(),
        }
        series = self._observations.setdefault((tenant, metric_name), [])
        series.append(observation)
        if len(series) > MAX_OBSERVATIONS_PER_METRIC:
            del series[:len(series) - MAX_OBSERVATIONS_PER_METRIC]
        return observation

    # ── Detection ──────────────────────────────────────────────────────

    def detect(self, tenant: str = "default", metric_name: str = "") -> list[dict]:
        found: list[dict] = []
        for key in sorted(self._observations):
            obs_tenant, obs_metric = key
            if obs_tenant != tenant:
                continue
            if metric_name and obs_metric != metric_name:
                continue
            series = self._observations[key]
            if len(series) < self._min_samples + 1:
                continue
            baseline = [point["value"] for point in series[:-1]]
            latest = series[-1]
            anomaly = self._evaluate(obs_tenant, obs_metric, latest["value"],
                                     baseline, dimensions=latest["dimensions"],
                                     timestamp=latest["timestamp"])
            if anomaly:
                found.append(anomaly)
                self._remember(anomaly)
        return found

    def detect_single(self, metric_name: str, current_value: float,
                      tenant: str = "default") -> dict | None:
        series = self._observations.get((tenant, metric_name), [])
        if len(series) < self._min_samples:
            return None
        baseline = [point["value"] for point in series]
        return self._evaluate(tenant, metric_name, float(current_value),
                              baseline, dimensions={}, timestamp=_utc_now())

    def _evaluate(self, tenant: str, metric_name: str, value: float,
                  baseline: list[float], dimensions: dict,
                  timestamp: str) -> dict | None:
        if len(baseline) < self._min_samples:
            return None
        mean = statistics.fmean(baseline)
        std = statistics.stdev(baseline)
        delta = value - mean
        if std > 0:
            deviation = delta / std
        else:
            deviation = 0.0 if delta == 0 else 999.0
        if abs(deviation) <= self._sensitivity:
            return None
        z_abs = abs(deviation)
        if z_abs >= 4.0:
            severity = SEVERITY_CRITICAL
        elif z_abs >= 3.0:
            severity = SEVERITY_HIGH
        else:
            severity = SEVERITY_MEDIUM
        raw_confidence = 1.0 - 1.0 / (z_abs * z_abs) if z_abs > 1.0 else 0.5
        confidence = round(min(0.99, max(0.5, raw_confidence)), 4)
        threshold = self._sensitivity * std
        return {
            "anomaly_id": uuid4().hex,
            "tenant": tenant,
            "metric_name": metric_name,
            "observed_value": round(value, 6),
            "baseline_mean": round(mean, 6),
            "baseline_std": round(std, 6),
            "deviation": round(deviation, 4),
            "confidence": confidence,
            "severity": severity,
            "detected_at": timestamp or _utc_now(),
            "evidence": {
                "sample_count": len(baseline),
                "sensitivity": self._sensitivity,
                "upper_bound": round(mean + threshold, 6),
                "lower_bound": round(mean - threshold, 6),
                "direction": "above_baseline" if delta > 0 else "below_baseline",
                "dimensions": dict(dimensions or {}),
            },
        }

    def _remember(self, anomaly: dict) -> None:
        self._anomalies.append(anomaly)
        if len(self._anomalies) > MAX_STORED_ANOMALIES:
            del self._anomalies[:len(self._anomalies) - MAX_STORED_ANOMALIES]

    # ── Baselines ──────────────────────────────────────────────────────

    def get_baseline(self, metric_name: str, tenant: str = "default") -> dict:
        values = [point["value"]
                  for point in self._observations.get((tenant, metric_name), [])]
        if not values:
            return {"metric_name": metric_name, "tenant": tenant, "mean": 0.0,
                    "std": 0.0, "min": 0.0, "max": 0.0, "count": 0,
                    "sufficient": False}
        return {
            "metric_name": metric_name,
            "tenant": tenant,
            "mean": round(statistics.fmean(values), 6),
            "std": round(statistics.stdev(values), 6) if len(values) > 1 else 0.0,
            "min": round(min(values), 6),
            "max": round(max(values), 6),
            "count": len(values),
            "sufficient": len(values) >= self._min_samples,
        }

    # ── Retrieval ──────────────────────────────────────────────────────

    def get_anomalies(self, tenant: str = "", metric_name: str = "",
                      limit: int = 50) -> list[dict]:
        selected = [
            anomaly for anomaly in reversed(self._anomalies)
            if (not tenant or anomaly["tenant"] == tenant)
            and (not metric_name or anomaly["metric_name"] == metric_name)
        ]
        return selected[:max(0, limit)]

    def get_anomaly_summary(self, tenant: str = "", start_time: str = "",
                            end_time: str = "") -> dict:
        start = _parse_ts(start_time)
        end = _parse_ts(end_time)
        selected: list[dict] = []
        for anomaly in self._anomalies:
            if tenant and anomaly["tenant"] != tenant:
                continue
            detected = _parse_ts(anomaly["detected_at"])
            if start and (detected is None or detected < start):
                continue
            if end and (detected is None or detected > end):
                continue
            selected.append(anomaly)
        by_severity = {SEVERITY_MEDIUM: 0, SEVERITY_HIGH: 0, SEVERITY_CRITICAL: 0}
        metrics: set[str] = set()
        for anomaly in selected:
            by_severity[anomaly["severity"]] = by_severity.get(anomaly["severity"], 0) + 1
            metrics.add(anomaly["metric_name"])
        return {
            "total_anomalies": len(selected),
            "by_severity": by_severity,
            "metrics_affected": sorted(metrics),
            "start_time": start_time,
            "end_time": end_time,
        }
