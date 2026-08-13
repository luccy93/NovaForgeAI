"""Stream Processing - windowed real-time metrics over ingested events."""
import time, statistics
from dataclasses import dataclass, field
from collections import defaultdict
from datetime import datetime, timezone


@dataclass
class MetricWindow:
    """Tumbling window accumulating counts and sums."""
    start_ts: float
    end_ts: float
    counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    tokens: int = 0
    cost: float = 0.0
    errors: int = 0
    users: set[str] = field(default_factory=set)
    repositories: set[str] = field(default_factory=set)
    deployments: int = 0
    incidents: int = 0
    requests: int = 0


class StreamProcessor:
    """Real-time processing engine computing standard operational metrics."""

    def __init__(self, window_seconds: float = 60.0):
        self.window_seconds = window_seconds
        self.queue: list[dict] = []
        self.windows: list[MetricWindow] = []
        self.current: dict = defaultdict(int)
        self.current_users: set[str] = set()
        self.current_repos: set[str] = set()
        self.current_cost: float = 0.0
        self.current_tokens: int = 0
        self.current_errors: int = 0
        self.current_deployments: int = 0
        self.current_incidents: int = 0
        self.current_requests: int = 0
        self.last_window: dict = {}
        self._started = None

    def push(self, event: dict) -> None:
        """Feeds an accepted, stored event into the streaming window."""
        self.queue.append(event)
        if self._started is None:
            self._started = datetime.now(timezone.utc).timestamp()
            self.last_window_start = self._started
        now = datetime.now(timezone.utc).timestamp()
        if now - self.last_window_start >= self.window_seconds:
            self._close_window(self.last_window_start, now)
            self.last_window_start = now
            self.current.clear()
            self.current_users.clear()
            self.current_repos.clear()
            self.current_cost = 0.0
            self.current_tokens = 0
            self.current_errors = 0
            self.current_deployments = 0
            self.current_incidents = 0
            self.current_requests = 0
        self._accumulate(event)

    def _accumulate(self, event: dict) -> None:
        cat = (event.get("category") or "")
        p = event.get("payload") or {}
        self.current["total"] += 1
        self.current[cat] += 1
        self.current_requests += 1
        self.current["requests"] += 1
        if event.get("user_id"):
            self.current_users.add(event["user_id"])
        if event.get("repository_id"):
            self.current_repos.add(event["repository_id"])
        if p.get("tokens"):
            self.current_tokens += int(p.get("tokens", 0))
        if p.get("cost"):
            self.current_cost += float(p.get("cost", 0.0))
        if cat != "billing" and p.get("error"):
            self.current_errors += 1
            self.current["errors"] += 1
        if cat == "incident":
            self.current_incidents += 1
        if cat == "deployment" and "failed" not in event.get("event_type", ""):
            self.current_deployments += 1

    def _close_window(self, start: float, end: float) -> None:
        w = MetricWindow(start_ts=start, end_ts=end)
        w.counts = dict(self.current)
        w.tokens = self.current_tokens
        w.cost = self.current_cost
        w.errors = self.current_errors
        w.users = set(self.current_users)
        w.repositories = set(self.current_repos)
        w.deployments = self.current_deployments
        w.incidents = self.current_incidents
        w.requests = self.current_requests
        self.windows.append(w)

    def metrics(self) -> dict:
        """Real-time operational metrics computed over the active/rolling window."""
        duration = self.window_seconds
        return {
            "requests_per_second": round(self.current_requests / duration, 3),
            "tokens_per_second": round(self.current_tokens / duration, 3),
            "active_users": len(self.current_users),
            "active_repositories": len(self.current_repos),
            "deployment_rate": round(self.current_deployments / duration, 3),
            "error_rate": round(self.current_errors / max(1, self.current_requests), 4),
            "incident_rate": round(self.current_incidents / duration, 3),
            "ai_cost_rate": round(self.current_cost / duration, 6),
            "total_events_observed": self.current_requests,
            "observed_categories": dict(self.current),
            "window_seconds": duration,
            "open_windows": len(self.windows),
        }

    def rate_history(self, metric: str = "requests_per_second", limit: int = 100) -> list[float]:
        """Historical rate series for a metric over closed windows."""
        key = {
            "requests_per_second": lambda w: w.requests / max(1.0, w.end_ts - w.start_ts),
            "tokens_per_second": lambda w: w.tokens / max(1.0, w.end_ts - w.start_ts),
            "errors_per_second": lambda w: w.errors / max(1.0, w.end_ts - w.start_ts),
            "deployments_per_second": lambda w: w.deployments / max(1.0, w.end_ts - w.start_ts),
            "incidents_per_second": lambda w: w.incidents / max(1.0, w.end_ts - w.start_ts),
        }.get(metric)
        if key is None:
            return []
        values = [key(w) for w in self.windows[-limit:]]
        return [round(v, 6) for v in values]

    def health(self) -> dict:
        return {"observed_events": self.current_requests, "closed_windows": len(self.windows),
                "window_seconds": self.window_seconds}