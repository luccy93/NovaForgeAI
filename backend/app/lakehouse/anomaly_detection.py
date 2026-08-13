"""Anomaly Detection - statistical methods (zscore, IQR, EWMA) without arbitrary thresholds."""
import time, statistics
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class Anomaly:
    metric: str
    method: str
    value: float
    expected: float
    deviation: float
    severity: str  # low | medium | high
    shifted_baseline: bool


class AnomalyDetector:
    """Runs multiple statistical detectors and emits scored anomalies."""

    def __init__(self, methods: tuple = ("zscore", "iqr", "ewma"),
                 sensitivity: float = 2.5, alpha: float = 0.3):
        self.methods = methods
        self.sensitivity = sensitivity
        self.alpha = alpha

    def detect(self, metric: str, series: list[float]) -> list[Anomaly]:
        if len(series) < 6:
            return []
        baseline = list(series[:-1])
        latest = series[-1]
        result: list[Anomaly] = []
        mean = statistics.mean(baseline)
        std = statistics.pstdev(baseline) or 1.0

        if "zscore" in self.methods:
            z = (latest - mean) / std if std else 0.0
            if abs(z) >= self.sensitivity:
                result.append(Anomaly(metric, "zscore", latest, mean, round(abs(z), 3),
                                      self._zscore_severity(abs(z)),
                                      abs(z) > self.sensitivity * 1.5))

        if "iqr" in self.methods:
            lo, hi = self._iqr(baseline)
            if latest < lo or latest > hi:
                deviation = (lo - latest) if latest < lo else (latest - hi)
                result.append(Anomaly(metric, "iqr", latest, mean, round(abs(deviation), 3),
                                      "medium", False))

        if "ewma" in self.methods:
            smoothed = self._ewma(baseline)
            resid = [abs(b - s) for b, s in zip(baseline, smoothed)]
            resid_std = statistics.pstdev(resid) or 1.0
            dz = abs(latest - smoothed[-1]) / resid_std
            if dz >= self.sensitivity:
                result.append(Anomaly(metric, "ewma", latest, smoothed[-1],
                                      round(dz, 3), self._high(dz), False))
        return result

    @classmethod
    def _zscore_severity(cls, z: float) -> str:
        return "high" if z >= 4.0 else ("medium" if z >= 3.0 else "low")

    @staticmethod
    def _high(z: float) -> str:
        return "high" if z >= 4.0 else ("medium" if z >= 3.0 else "low")

    @staticmethod
    def _iqr(values: list[float]) -> tuple[float, float]:
        sorted_v = sorted(values)
        n = len(sorted_v)
        q1 = sorted_v[n // 4]
        q3 = sorted_v[3 * n // 4]
        iqr = q3 - q1
        return (q1 - 1.5 * iqr, q3 + 1.5 * iqr)

    def _ewma(self, values: list[float]) -> list[float]:
        if not values:
            return []
        out = [values[0]]
        for v in values[1:]:
            out.append(self.alpha * v + (1 - self.alpha) * out[-1])
        return out


class AnomalyEngine:
    """Applies the detector to many metric series and keeps a history."""

    def __init__(self, detector: AnomalyDetector = None):
        self.detector = detector or AnomalyDetector()
        self.history: list[dict] = []

    def run(self, series_map: dict[str, list[float]]) -> dict:
        results = {}
        total = 0
        for metric, series in series_map.items():
            detected = self.detector.detect(metric, series)
            results[metric] = [
                {"method": a.method, "value": a.value, "expected": a.expected,
                 "deviation": a.deviation, "severity": a.severity,
                 "shifted_baseline": a.shifted_baseline} for a in detected]
            total += len(detected)
        report = {"at": time.time(),
                  "observed_at": datetime.now(timezone.utc).isoformat(),
                  "results": results,
                  "anomaly_count": total}
        self.history.append(report)
        return report

    def latest(self) -> dict:
        return self.history[-1] if self.history else {"results": {}, "anomaly_count": 0}