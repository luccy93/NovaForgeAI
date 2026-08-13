"""Batch Processing - scheduled daily/weekly/monthly aggregations and rollups."""
import time, logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class BatchJob:
    """A scheduled batch job definition."""
    name: str
    period: str  # daily | weekly | monthly
    run: Callable[[], dict]
    last_run: str = ""
    last_status: str = "pending"
    runs: int = 0
    failures: int = 0
    last_duration: float = 0.0


class BatchScheduler:
    """Schedules and executes batch aggregation pipelines."""

    def __init__(self, timezone_offset_hours: int = 0):
        self.jobs: dict[str, BatchJob] = {}
        self.results: dict[str, dict] = {}

    def register(self, name: str, period: str, fn: Callable[[], dict]) -> None:
        self.jobs[name] = BatchJob(name=name, period=period, run=fn)

    def run_job(self, name: str) -> dict:
        job = self.jobs.get(name)
        if not job:
            raise KeyError(f"no batch job: {name}")
        started = time.time()
        try:
            result = job.run()
            job.last_status = "ok"
            job.last_duration = time.time() - started
            job.last_run = datetime.now(timezone.utc).isoformat()
            job.runs += 1
            self.results[name] = {"status": "ok", "duration": job.last_duration, "result": result}
            return self.results[name]
        except Exception as exc:
            job.last_status = "failed"
            job.failures += 1
            job.last_duration = time.time() - started
            job.last_run = datetime.now(timezone.utc).isoformat()
            self.results[name] = {"status": "failed", "error": str(exc)}
            logger.error("Batch job %s failed: %s", name, exc)
            return self.results[name]

    def run_all(self, period: Optional[str] = None) -> dict:
        summary = {}
        for name, job in self.jobs.items():
            if period and job.period != period:
                continue
            summary[name] = self.run_job(name)
        return summary

    def run_due(self, now: Optional[datetime] = None) -> dict:
        """Runs jobs whose schedule window has elapsed (simple last-run gating)."""
        now = now or datetime.now(timezone.utc)
        summary = {}
        for name, job in self.jobs.items():
            if not job.last_run:
                summary[name] = self.run_job(name)
                continue
            last = datetime.fromisoformat(job.last_run)
            elapsed = now - last
            threshold = {"daily": timedelta(hours=24), "weekly": timedelta(days=7),
                         "monthly": timedelta(days=30)}.get(job.period, timedelta(hours=24))
            if elapsed >= threshold:
                summary[name] = self.run_job(name)
        return summary

    def status(self) -> dict:
        return {name: {"period": j.period, "status": j.last_status, "runs": j.runs,
                       "failures": j.failures, "last_run": j.last_run,
                       "last_duration": j.last_duration}
                for name, j in self.jobs.items()}


class AggregationEngine:
    """Rollups over event streams by period, driven by metric aggregator functions."""

    def __init__(self, timezone_offset_hours: int = 0):
        self.timezone_offset = timezone_offset_hours
        self.aggregates: dict[str, dict] = {}
        self.run_count = 0

    def period_key(self, ts: str, period: str) -> str:
        dt = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
        if period == "daily":
            return dt.strftime("%Y-%m-%d")
        if period == "weekly":
            iso = dt.isocalendar()
            return f"{iso[0]}-W{iso[1]:02d}"
        if period == "monthly":
            return dt.strftime("%Y-%m")
        return dt.strftime("%Y-%m-%d")

    def aggregate(self, events: list[dict], period: str, metric_fns: dict[str, Callable[[list[dict]], float]]) -> dict[str, dict]:
        """Groups events by period and applies each metric function."""
        buckets: dict[str, list[dict]] = {}
        for ev in events:
            key = self.period_key(ev.get("timestamp", ""), period)
            buckets.setdefault(key, []).append(ev)
        result = {}
        for key, group in sorted(buckets.items()):
            row = {"period": key, "events": len(group), "orgs": len({e.get("organization_id") for e in group})}
            for name, fn in metric_fns.items():
                row[name] = round(fn(group), 6)
            result[key] = row
        self.aggregates[period] = result
        self.run_count += 1
        return result

    def get(self, period: str) -> dict:
        return self.aggregates.get(period, {})