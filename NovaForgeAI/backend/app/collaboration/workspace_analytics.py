"""Workspace Analytics — analyze team productivity, repository activity, knowledge growth, engineering velocity, AI adoption, review efficiency, documentation quality, security trends."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class AnalyticsMetric(Enum):
    TEAM_PRODUCTIVITY = "team_productivity"
    REPOSITORY_ACTIVITY = "repository_activity"
    KNOWLEDGE_GROWTH = "knowledge_growth"
    ENGINEERING_VELOCITY = "engineering_velocity"
    AI_ADOPTION = "ai_adoption"
    REVIEW_EFFICIENCY = "review_efficiency"
    DOCUMENTATION_QUALITY = "documentation_quality"
    SECURITY_TRENDS = "security_trends"


@dataclass
class AnalyticsReport:
    id: str
    org_id: str
    workspace_id: str
    metric: AnalyticsMetric
    period: str
    value: float = 0.0
    previous_value: float = 0.0
    change_pct: float = 0.0
    data: dict = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["metric"] = self.metric.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AnalyticsReport":
        data = data.copy()
        data["metric"] = AnalyticsMetric(data.get("metric", "team_productivity"))
        return cls(**data)


class WorkspaceAnalytics:
    def __init__(self, storage_dir: str = "collab_data/analytics"):
        self.storage_dir = storage_dir
        self._reports: dict[str, AnalyticsReport] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "reports.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._reports[k] = AnalyticsReport.from_dict(v)
                    except Exception as e: logger.warning("Skipping report %s: %s", k, e)
            except Exception as e: logger.error("Failed to load analytics: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._reports.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save analytics: %s", e)

    def record_metric(self, org_id: str, workspace_id: str, metric: AnalyticsMetric, value: float, previous_value: float = 0.0, period: str = "daily", data: dict = None) -> AnalyticsReport:
        change = round(((value - previous_value) / max(previous_value, 0.01)) * 100, 2) if previous_value else 0.0
        report = AnalyticsReport(id=str(uuid.uuid4()), org_id=org_id, workspace_id=workspace_id, metric=metric, period=period, value=value, previous_value=previous_value, change_pct=change, data=data or {})
        self._reports[report.id] = report
        self._save()
        return report

    def get_workspace_report(self, workspace_id: str, metric: Optional[AnalyticsMetric] = None) -> list[AnalyticsReport]:
        results = [r for r in self._reports.values() if r.workspace_id == workspace_id]
        if metric: results = [r for r in results if r.metric == metric]
        return sorted(results, key=lambda r: r.generated_at, reverse=True)

    def get_trend(self, workspace_id: str, metric: AnalyticsMetric, limit: int = 30) -> list[dict]:
        results = sorted(
            [r for r in self._reports.values() if r.workspace_id == workspace_id and r.metric == metric],
            key=lambda r: r.generated_at, reverse=True
        )[:limit]
        return [{"date": r.generated_at, "value": r.value, "change": r.change_pct} for r in results]

    def get_summary(self, org_id: str, workspace_id: str = "") -> dict:
        reports = [r for r in self._reports.values() if r.org_id == org_id]
        if workspace_id: reports = [r for r in reports if r.workspace_id == workspace_id]
        summary = {}
        for m in AnalyticsMetric:
            metric_reports = [r for r in reports if r.metric == m]
            if metric_reports:
                summary[m.value] = {
                    "current": metric_reports[0].value,
                    "change": metric_reports[0].change_pct,
                    "records": len(metric_reports),
                }
        return summary

    def get_telemetry(self) -> dict: return dict(self._telemetry)
