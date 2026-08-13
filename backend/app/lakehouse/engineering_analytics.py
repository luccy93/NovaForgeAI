"""Engineering Analytics Service - CI health, cycle time, velocity and code metrics."""
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class EngineeringMetric:
    organization_id: str
    metric: str          # deploy_frequency | cycle_time | lead_time | failure_rate | velocity
    value: float = 0.0
    at: str = ""


@dataclass
class CommitInfo:
    organization_id: str
    commit_id: str
    author: str
    inserted: int = 0
    deleted: int = 0
    files_changed: int = 0
    at: str = ""


class EngineeringAnalytics:
    """DORA-style engineering metrics: cycle time, velocity, CI health, churn."""

    def __init__(self):
        self.metrics: list[EngineeringMetric] = []
        self.commits: list[CommitInfo] = []
        self.ci_runs: list[dict] = []

    def record_metric(self, metric: EngineeringMetric) -> None:
        if not metric.at:
            metric.at = datetime.now(timezone.utc).isoformat()
        self.metrics.append(metric)

    def record_commit(self, commit: CommitInfo) -> None:
        if not commit.at:
            commit.at = datetime.now(timezone.utc).isoformat()
        self.commits.append(commit)

    def record_ci(self, organization_id: str, success: bool, duration_s: float = 0.0) -> None:
        self.ci_runs.append({"organization_id": organization_id, "success": success,
                             "duration_s": duration_s,
                             "at": datetime.now(timezone.utc).isoformat()})

    def metrics_summary(self, organization_id: Optional[str] = None) -> dict:
        rows = [m for m in self.metrics
                if not organization_id or m.organization_id == organization_id]
        out = {}
        for m in rows:
            series = out.setdefault(m.metric, [])
            series.append(m.value)
        return {name: {"latest": round(series[-1], 2),
                       "mean": round(statistics.mean(series), 2),
                       "observations": len(series)}
                for name, series in out.items()}

    def delivery_health(self, organization_id: Optional[str] = None) -> dict:
        rows = self.metrics_summary(organization_id)
        ci = [r for r in self.ci_runs
              if not organization_id or r["organization_id"] == organization_id]
        return {"metrics": rows,
                "ci_runs": len(ci),
                "ci_success_rate": round(sum(1 for r in ci if r["success"]) / max(1, len(ci)), 4)}

    def code_churn(self, organization_id: Optional[str] = None) -> dict:
        commits = self._commits(organization_id)
        if not commits:
            return {"commits": 0}
        return {
            "commits": len(commits),
            "files_changed_total": sum(c.files_changed for c in commits),
            "insertions": sum(c.inserted for c in commits),
            "deletions": sum(c.deleted for c in commits),
            "net_lines": sum(c.inserted - c.deleted for c in commits),
            "avg_changes_per_commit": round(
                sum(c.inserted + c.deleted for c in commits) / len(commits), 2),
        }

    def _commits(self, organization_id: Optional[str] = None) -> list[CommitInfo]:
        return [c for c in self.commits
                if not organization_id or c.organization_id == organization_id]