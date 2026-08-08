"""Engineering Analytics — DORA metrics, lead/cycle time, deployment frequency, change failure rate, MTTR, productivity."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional
import re


@dataclass
class DORAMetrics:
    deployment_frequency: str = "unknown"  # daily, weekly, monthly, yearly
    lead_time: float = 0.0  # hours
    change_failure_rate: float = 0.0  # percentage
    mean_time_to_recovery: float = 0.0  # hours
    elite_score: float = 0.0  # 0-100


@dataclass
class ProductivityMetrics:
    commits_per_week: float = 0.0
    lines_changed_per_week: float = 0.0
    files_changed_per_week: float = 0.0
    reviews_per_week: float = 0.0
    avg_review_time_hours: float = 0.0
    avg_merge_time_hours: float = 0.0


@dataclass
class AIProductivity:
    total_ai_interactions: int = 0
    ai_acceptance_rate: float = 0.0
    avg_token_usage: float = 0.0
    search_accuracy: float = 0.0
    suggestions_accepted: int = 0


@dataclass
class AnalyticsReport:
    repo_id: str
    repo_name: str
    timestamp: str
    dora: DORAMetrics = field(default_factory=DORAMetrics)
    productivity: ProductivityMetrics = field(default_factory=ProductivityMetrics)
    ai_productivity: AIProductivity = field(default_factory=AIProductivity)
    repo_growth: dict[str, Any] = field(default_factory=dict)
    developer_productivity: dict[str, Any] = field(default_factory=dict)
    trends: dict[str, list[float]] = field(default_factory=dict)
    insights: list[str] = field(default_factory=list)
    overall_engineering_score: float = 0.0


class EngineeringAnalytics:
    """Tracks and analyzes engineering metrics — DORA, productivity, AI effectiveness, repository growth."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)

    def analyze(self) -> AnalyticsReport:
        report = AnalyticsReport(
            repo_id=str(hash(str(self.repo_path))),
            repo_name=self.repo_path.name,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        self._calculate_dora_metrics(report)
        self._calculate_productivity(report)
        self._calculate_ai_productivity(report)
        self._calculate_repo_growth(report)
        self._generate_insights(report)
        report.overall_engineering_score = self._calculate_overall_score(report)

        return report

    def _calculate_dora_metrics(self, report: AnalyticsReport):
        try:
            git_dir = self.repo_path / ".git"
            if not git_dir.exists():
                report.dora = DORAMetrics(
                    deployment_frequency="unknown",
                    lead_time=0,
                    change_failure_rate=0,
                    mean_time_to_recovery=0,
                    elite_score=30,
                )
                return

            import subprocess

            result = subprocess.run(
                ["git", "log", "--oneline", "--since=30.days"],
                cwd=self.repo_path, capture_output=True, text=True, timeout=5
            )
            commits_30d = len(result.stdout.splitlines())
            weekly_commits = commits_30d / 4.29

            if weekly_commits > 20:
                report.dora.deployment_frequency = "daily"
            elif weekly_commits > 5:
                report.dora.deployment_frequency = "weekly"
            elif weekly_commits > 1:
                report.dora.deployment_frequency = "monthly"
            else:
                report.dora.deployment_frequency = "yearly"

            result2 = subprocess.run(
                ["git", "log", "--oneline", "--since=90.days", "--format=%H"],
                cwd=self.repo_path, capture_output=True, text=True, timeout=5
            )
            commits_90d = result2.stdout.splitlines()

            total_commits = len(commits_90d)
            if total_commits > 0:
                result3 = subprocess.run(
                    ["git", "log", "--since=90.days", "--format=%at"],
                    cwd=self.repo_path, capture_output=True, text=True, timeout=5
                )
                timestamps = [int(t) for t in result3.stdout.splitlines() if t.strip()]
                if timestamps:
                    now = datetime.now().timestamp()
                    avg_age = sum(now - ts for ts in timestamps) / len(timestamps)
                    report.dora.lead_time = round(avg_age / 3600, 1)

                    recent = sum(1 for ts in timestamps if now - ts < 86400 * 7)
                    report.dora.change_failure_rate = round(
                        (1 - recent / max(len(timestamps), 1)) * 100, 1
                    )

            deploy_files = list(self.repo_path.glob("Dockerfile")) + list(self.repo_path.glob(".github/workflows/deploy*"))
            has_deploy = bool(deploy_files)
            if not has_deploy:
                report.dora.deployment_frequency = "unknown"

            elite_scores = {
                "daily": 90, "weekly": 70, "monthly": 40, "yearly": 20, "unknown": 10
            }
            base = elite_scores.get(report.dora.deployment_frequency, 10)
            lead_time_bonus = max(0, 20 - report.dora.lead_time / 10) if report.dora.lead_time else 0
            failure_penalty = report.dora.change_failure_rate * 0.5
            report.dora.elite_score = round(max(0, base + lead_time_bonus - failure_penalty), 1)

        except Exception:
            report.dora = DORAMetrics(
                deployment_frequency="unknown", lead_time=0,
                change_failure_rate=0, mean_time_to_recovery=0, elite_score=30,
            )

    def _calculate_productivity(self, report: AnalyticsReport):
        try:
            import subprocess
            git_dir = self.repo_path / ".git"
            if not git_dir.exists():
                return

            result = subprocess.run(
                ["git", "log", "--oneline", "--since=30.days", "--format=%H"],
                cwd=self.repo_path, capture_output=True, text=True, timeout=5
            )
            commit_hashes = result.stdout.splitlines()
            report.productivity.commits_per_week = round(len(commit_hashes) / 4.29, 1)

            total_lines = 0
            total_files = 0
            for ch in commit_hashes[-50:]:
                try:
                    diff = subprocess.run(
                        ["git", "diff", "--shortstat", f"{ch}^..{ch}"],
                        cwd=self.repo_path, capture_output=True, text=True, timeout=5
                    )
                    match = re.search(r'(\d+)\s+insertions?', diff.stdout)
                    if match:
                        total_lines += int(match.group(1))
                    match = re.search(r'(\d+)\s+files? changed', diff.stdout)
                    if match:
                        total_files += int(match.group(1))
                except Exception:
                    pass

            weeks = max(1, len(commit_hashes) / 30 * 4.29)
            report.productivity.lines_changed_per_week = round(total_lines / max(weeks, 1), 1)
            report.productivity.files_changed_per_week = round(total_files / max(weeks, 1), 1)

        except Exception:
            pass

    def _calculate_ai_productivity(self, report: AnalyticsReport):
        ai_trace_dir = self.repo_path / ".ai-traces"
        total_interactions = 0
        total_accepts = 0
        total_tokens = 0
        search_matches = 0
        search_total = 0

        if ai_trace_dir.exists():
            for trace_file in ai_trace_dir.glob("*.jsonl"):
                try:
                    for line in trace_file.read_text().splitlines():
                        if not line.strip():
                            continue
                        import json
                        entry = json.loads(line)
                        total_interactions += 1
                        if entry.get("accepted"):
                            total_accepts += 1
                        total_tokens += entry.get("tokens", 0)
                        if entry.get("type") == "search":
                            search_total += 1
                            if entry.get("relevant"):
                                search_matches += 1
                except Exception:
                    pass

        report.ai_productivity.total_ai_interactions = total_interactions
        report.ai_productivity.suggestions_accepted = total_accepts
        report.ai_productivity.ai_acceptance_rate = round(
            total_accepts / max(total_interactions, 1) * 100, 1
        )
        report.ai_productivity.avg_token_usage = round(
            total_tokens / max(total_interactions, 1), 1
        )
        report.ai_productivity.search_accuracy = round(
            search_matches / max(search_total, 1) * 100, 1
        )

    def _calculate_repo_growth(self, report: AnalyticsReport):
        py_files = list(self.repo_path.rglob("*.py"))
        js_files = list(self.repo_path.rglob("*.js")) + list(self.repo_path.rglob("*.ts")) + \
                   list(self.repo_path.rglob("*.jsx")) + list(self.repo_path.rglob("*.tsx"))
        md_files = list(self.repo_path.rglob("*.md"))

        total_source = 0
        for f in py_files + js_files:
            try:
                total_source += len(f.read_text(encoding="utf-8", errors="ignore").splitlines())
            except Exception:
                pass

        report.repo_growth = {
            "python_files": len(py_files),
            "javascript_files": len(js_files),
            "doc_files": len(md_files),
            "total_source_lines": total_source,
            "top_level_dirs": len([d for d in self.repo_path.iterdir() if d.is_dir() and not d.name.startswith(".")]),
            "config_files": len(list(self.repo_path.rglob("*.json"))) + len(list(self.repo_path.rglob("*.yaml"))) + len(list(self.repo_path.rglob("*.yml"))),
        }

    def _generate_insights(self, report: AnalyticsReport):
        insights = []

        d = report.dora
        if d.deployment_frequency in ("daily", "weekly"):
            insights.append(f"Elite DORA performance: deploying {d.deployment_frequency} with lead time {d.lead_time}h")
        elif d.deployment_frequency == "monthly":
            insights.append("Opportunity to improve deployment frequency to weekly or daily")
        else:
            insights.append("Set up CI/CD pipeline to enable regular deployments")

        if d.change_failure_rate > 20:
            insights.append(f"High change failure rate ({d.change_failure_rate}%) — improve testing and review processes")
        elif d.change_failure_rate < 10:
            insights.append(f"Low change failure rate ({d.change_failure_rate}%) — good testing practices")

        p = report.productivity
        if p.commits_per_week > 10:
            insights.append(f"High development velocity: {p.commits_per_week} commits/week")
        elif p.commits_per_week < 2:
            insights.append(f"Low commit frequency ({p.commits_per_week}/week) — consider shorter development cycles")

        ai = report.ai_productivity
        if ai.total_ai_interactions > 0:
            if ai.ai_acceptance_rate > 60:
                insights.append(f"High AI suggestion acceptance rate ({ai.ai_acceptance_rate}%) — AI is well-calibrated")
            elif ai.ai_acceptance_rate < 30:
                insights.append(f"Low AI acceptance rate ({ai.ai_acceptance_rate}%) — review suggestion quality")

        if not insights:
            insights.append("Collect more data for meaningful engineering analytics insights")

        report.insights = insights

    def _calculate_overall_score(self, report: AnalyticsReport) -> float:
        score = 50.0

        d = report.dora
        score += d.elite_score * 0.3

        p = report.productivity
        score += min(20, p.commits_per_week * 2)

        ai = report.ai_productivity
        score += ai.ai_acceptance_rate * 0.2

        if report.repo_growth:
            growth_score = min(10, report.repo_growth["total_source_lines"] / 1000)
            score += growth_score

        return round(min(100, score), 1)
