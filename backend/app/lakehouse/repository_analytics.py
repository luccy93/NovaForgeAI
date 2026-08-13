"""Repository Analytics Service - stars, forks, issues, PRs, contributors and growth."""
import statistics
from typing import Optional


class RepositoryAnalytics:
    """Public repository metrics and growth analysis."""

    def __init__(self, repo: dict = None):
        self.repo = repo or {}
        self.snapshots: list[dict] = []  # {"at": iso, "stars": n, "forks": n, "issues_open": n, ...}

    def snapshot(self, at: str, stars: int, forks: int, issues_open: int,
                 pull_requests: int, contributors: int) -> dict:
        record = {"at": at, "stars": stars, "forks": forks, "issues_open": issues_open,
                  "pull_requests": pull_requests, "contributors": contributors}
        self.snapshots.append(record)
        return record

    def latest(self) -> Optional[dict]:
        return self.snapshots[-1] if self.snapshots else None

    def stars_growth(self) -> dict:
        if len(self.snapshots) < 2:
            return {"growth": 0.0, "note": "need >= 2 snapshots"}
        first, last = self.snapshots[0], self.snapshots[-1]
        delta = last["stars"] - first["stars"]
        pct = (delta / max(1, first["stars"])) * 100.0
        return {"delta": delta, "percent_growth": round(pct, 2),
                "from_snapshot": first["at"], "to_snapshot": last["at"]}

    def spikes(self, threshold: int = 20) -> list[dict]:
        """Periods where stars increased by >= threshold between snapshots."""
        spikes = []
        for prev, cur in zip(self.snapshots, self.snapshots[1:]):
            delta = cur["stars"] - prev["stars"]
            if delta >= threshold:
                spikes.append({"from": prev["at"], "to": cur["at"], "stars_added": delta})
        return spikes

    def engagement_overview(self) -> dict:
        latest = self.latest() or {}
        return {
            "stars": latest.get("stars", 0),
            "forks": latest.get("forks", 0),
            "issues_open": latest.get("issues_open", 0),
            "pull_requests": latest.get("pull_requests", 0),
            "contributors": latest.get("contributors", 0),
            "issue_to_pr_ratio": round(
                latest.get("issues_open", 0) / max(1, latest.get("pull_requests", 0)), 2)
        }

    def repo_info(self) -> dict:
        return {"repo": self.repo.get("name"), "owner": self.repo.get("owner"),
                "language": self.repo.get("language"),
                "description": self.repo.get("description", "")}


def analyze_repo(repo: dict, snapshots: list[dict]) -> dict:
    engine = RepositoryAnalytics(repo)
    for s in snapshots:
        engine.snapshot(**s)
    return {"info": engine.repo_info(), "growth": engine.stars_growth(),
            "overview": engine.engagement_overview()}