"""Data Observability - pipeline health, latency, freshness and volume drift metrics."""
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class PipelineHealth:
    name: str
    status: str = "healthy"  # healthy | degraded | failed
    last_run_at: str = ""
    run_count: int = 0
    failures: int = 0
    latency_ms: float = 0.0
    last_records: int = 0
    reason: str = ""


class DataObservability:
    """Tracks pipeline health, freshness and volume drift without fabricated metrics."""

    def __init__(self):
        self.health: dict[str, PipelineHealth] = {}
        self.latency_series: dict[str, list[float]] = {}
        self.checks: list[dict] = []

    def register(self, name: str) -> PipelineHealth:
        health = self.health.setdefault(name, PipelineHealth(name))
        self.latency_series.setdefault(name, [])
        return health

    def finish(self, name: str, latency_ms: float, records: int = 0,
               success: bool = True, reason: str = "") -> PipelineHealth:
        health = self.health.setdefault(name, PipelineHealth(name))
        self.latency_series.setdefault(name, []).append(latency_ms)
        health.run_count += 1
        health.last_run_at = datetime.now(timezone.utc).isoformat()
        health.latency_ms = latency_ms
        health.last_records = records
        if success:
            health.status = "healthy"
            health.reason = ""
        else:
            health.failures += 1
            health.status = "degraded" if health.failures < 3 else "failed"
            health.reason = reason or "pipeline failure"
        return health

    def freshness(self, dataset: str, last_loaded_at: str, max_age_hours: float = 24.0) -> dict:
        try:
            parsed = datetime.fromisoformat(last_loaded_at)
            age_hours = (datetime.now(timezone.utc) - parsed).total_seconds() / 3600.0
        except (ValueError, TypeError, AttributeError):
            age_hours = None
        fresh = age_hours is not None and age_hours <= max_age_hours
        self.checks.append({"dataset": dataset, "fresh": fresh,
                            "at": datetime.now(timezone.utc).isoformat()})
        return {"dataset": dataset,
                "age_hours": round(age_hours, 2) if age_hours is not None else None,
                "max_age_hours": max_age_hours, "fresh": fresh}

    def volume_drift(self, dataset: str, recent_counts: list[int], window: int = 7) -> dict:
        if len(recent_counts) < window + 2:
            return {"dataset": dataset, "drift_detected": False, "z": 0.0,
                    "note": "insufficient history"}
        baseline = recent_counts[:-1]
        latest = float(recent_counts[-1])
        base = baseline[-window:]
        mean = statistics.mean(base)
        std = statistics.pstdev(base) or 1.0
        z = (latest - mean) / std
        return {"dataset": dataset, "latest": int(latest),
                "baseline_mean": round(mean, 2), "z": round(z, 3),
                "drift_detected": abs(z) > 2.5}

    def compliance_ready_report(self) -> dict:
        return {"pipeline_count": len(self.health),
                "pipelines": [
                    {"name": h.name, "status": h.status, "runs": h.run_count,
                     "failures": h.failures, "avg_latency_ms":
                         round(statistics.mean(self.latency_series.get(h.name, []) or [0.0]), 1),
                     "last_run_at": h.last_run_at, "last_records": h.last_records,
                     "reason": h.reason}
                    for h in self.health.values()],
                "freshness_checks": len(self.checks)}