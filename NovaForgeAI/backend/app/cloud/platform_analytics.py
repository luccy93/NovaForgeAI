"""
Platform Analytics — Organization, Engineering, Developer, AI, Repository, Security, Infrastructure Analytics.
"""
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any
import json
import uuid
import hashlib
import time
import os
from collections import defaultdict

logger = logging.getLogger(__name__)


class AnalyticsType(Enum):
    ORGANIZATION = "organization"
    ENGINEERING = "engineering"
    DEVELOPER = "developer"
    AI = "ai"
    REPOSITORY = "repository"
    SECURITY = "security"
    INFRASTRUCTURE = "infrastructure"
    PERFORMANCE = "performance"
    COST = "cost"


class ReportFormat(Enum):
    JSON = "json"
    CSV = "csv"
    PDF = "pdf"
    HTML = "html"
    MARKDOWN = "markdown"


class TimeGranularity(Enum):
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


@dataclass
class AnalyticsEvent:
    id: str
    event_type: str
    source: str
    org_id: str
    workspace_id: Optional[str] = None
    project_id: Optional[str] = None
    repository_id: Optional[str] = None
    user_id: Optional[str] = None
    data: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    severity: str = "info"
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "source": self.source,
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "repository_id": self.repository_id,
            "user_id": self.user_id,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "severity": self.severity,
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AnalyticsEvent":
        return cls(
            id=data["id"],
            event_type=data["event_type"],
            source=data["source"],
            org_id=data["org_id"],
            workspace_id=data.get("workspace_id"),
            project_id=data.get("project_id"),
            repository_id=data.get("repository_id"),
            user_id=data.get("user_id"),
            data=data.get("data", {}),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            severity=data.get("severity", "info"),
            duration_ms=data.get("duration_ms", 0.0),
        )


@dataclass
class AnalyticsMetric:
    id: str
    metric_name: str
    value: float
    unit: str
    tags: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = ""
    granularity: TimeGranularity = TimeGranularity.DAILY

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "metric_name": self.metric_name,
            "value": self.value,
            "unit": self.unit,
            "tags": self.tags,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "granularity": self.granularity.value,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AnalyticsMetric":
        return cls(
            id=data["id"],
            metric_name=data["metric_name"],
            value=data["value"],
            unit=data["unit"],
            tags=data.get("tags", {}),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            source=data.get("source", ""),
            granularity=TimeGranularity(data.get("granularity", "daily")),
        )


@dataclass
class AnalyticsReport:
    id: str
    analytics_type: AnalyticsType
    title: str
    description: str = ""
    metrics: dict = field(default_factory=dict)
    insights: list = field(default_factory=list)
    recommendations: list = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    format: ReportFormat = ReportFormat.JSON

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "analytics_type": self.analytics_type.value,
            "title": self.title,
            "description": self.description,
            "metrics": self.metrics,
            "insights": self.insights,
            "recommendations": self.recommendations,
            "generated_at": self.generated_at.isoformat(),
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "format": self.format.value,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AnalyticsReport":
        return cls(
            id=data["id"],
            analytics_type=AnalyticsType(data["analytics_type"]),
            title=data["title"],
            description=data.get("description", ""),
            metrics=data.get("metrics", {}),
            insights=data.get("insights", []),
            recommendations=data.get("recommendations", []),
            generated_at=datetime.fromisoformat(data["generated_at"]),
            period_start=datetime.fromisoformat(data["period_start"]) if data.get("period_start") else None,
            period_end=datetime.fromisoformat(data["period_end"]) if data.get("period_end") else None,
            format=ReportFormat(data.get("format", "json")),
        )


@dataclass
class DeveloperMetrics:
    user_id: str
    commits: int = 0
    prs_created: int = 0
    prs_merged: int = 0
    reviews_done: int = 0
    issues_resolved: int = 0
    code_churn: int = 0
    active_days: int = 0
    contribution_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "commits": self.commits,
            "prs_created": self.prs_created,
            "prs_merged": self.prs_merged,
            "reviews_done": self.reviews_done,
            "issues_resolved": self.issues_resolved,
            "code_churn": self.code_churn,
            "active_days": self.active_days,
            "contribution_score": self.contribution_score,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DeveloperMetrics":
        return cls(
            user_id=data["user_id"],
            commits=data.get("commits", 0),
            prs_created=data.get("prs_created", 0),
            prs_merged=data.get("prs_merged", 0),
            reviews_done=data.get("reviews_done", 0),
            issues_resolved=data.get("issues_resolved", 0),
            code_churn=data.get("code_churn", 0),
            active_days=data.get("active_days", 0),
            contribution_score=data.get("contribution_score", 0.0),
        )


@dataclass
class Insight:
    id: str
    insight_type: str
    title: str
    description: str = ""
    confidence: float = 0.0
    evidence: dict = field(default_factory=dict)
    impact: str = "medium"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "insight_type": self.insight_type,
            "title": self.title,
            "description": self.description,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "impact": self.impact,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Insight":
        return cls(
            id=data["id"],
            insight_type=data["insight_type"],
            title=data["title"],
            description=data.get("description", ""),
            confidence=data.get("confidence", 0.0),
            evidence=data.get("evidence", {}),
            impact=data.get("impact", "medium"),
            created_at=datetime.fromisoformat(data["created_at"]),
            metadata=data.get("metadata", {}),
        )


class OrganizationAnalytics:
    def __init__(self, storage_dir: str):
        if not hasattr(self, "telemetry"):
            self.telemetry = defaultdict(int)
        self._org_storage_dir = os.path.join(storage_dir, "organization_analytics")
        os.makedirs(self._org_storage_dir, exist_ok=True)
        self._org_events_file = os.path.join(self._org_storage_dir, "events.json")
        self._org_metrics_file = os.path.join(self._org_storage_dir, "metrics.json")
        self._org_events = []
        self._org_metrics = {}
        self._load_org_data()

    def _load_org_data(self):
        try:
            if os.path.exists(self._org_events_file):
                with open(self._org_events_file, "r") as f:
                    data = json.load(f)
                self._org_events = [AnalyticsEvent.from_dict(e) for e in data]
            if os.path.exists(self._org_metrics_file):
                with open(self._org_metrics_file, "r") as f:
                    self._org_metrics = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load organization data: {e}")

    def _save_org_data(self):
        try:
            with open(self._org_events_file, "w") as f:
                json.dump([e.to_dict() for e in self._org_events], f, indent=2)
            with open(self._org_metrics_file, "w") as f:
                json.dump(self._org_metrics, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save organization data: {e}")

    def track_event(self, event_type: str, source: str, org_id: str, **kwargs) -> AnalyticsEvent:
        self.telemetry["track_event"] += 1
        try:
            event = AnalyticsEvent(
                id=str(uuid.uuid4()),
                event_type=event_type,
                source=source,
                org_id=org_id,
                workspace_id=kwargs.get("workspace_id"),
                project_id=kwargs.get("project_id"),
                repository_id=kwargs.get("repository_id"),
                user_id=kwargs.get("user_id"),
                data=kwargs.get("data", {}),
                severity=kwargs.get("severity", "info"),
                duration_ms=kwargs.get("duration_ms", 0.0),
            )
            self._org_events.append(event)
            self._save_org_data()
            logger.debug(f"Tracked org event {event.id} type={event_type}")
            return event
        except Exception as e:
            logger.error(f"Failed to track org event: {e}")
            raise

    def get_org_metrics(self, org_id: str = None) -> dict:
        self.telemetry["get_org_metrics"] += 1
        try:
            relevant = [e for e in self._org_events if org_id is None or e.org_id == org_id]
            return {
                "total_events": len(relevant),
                "unique_sources": len(set(e.source for e in relevant)),
                "event_types": dict(self._count_events_by_key(relevant, "event_type")),
                "severity_distribution": dict(self._count_events_by_key(relevant, "severity")),
                "avg_duration_ms": sum(e.duration_ms for e in relevant) / max(len(relevant), 1),
                "last_event": relevant[-1].to_dict() if relevant else None,
            }
        except Exception as e:
            logger.error(f"Failed to get org metrics: {e}")
            raise

    def get_growth_metrics(self, org_id: str = None) -> dict:
        self.telemetry["get_growth_metrics"] += 1
        try:
            relevant = [e for e in self._org_events if org_id is None or e.org_id == org_id]
            now = datetime.now(timezone.utc)
            periods = {"1d": 86400, "7d": 604800, "30d": 2592000}
            growth = {}
            for label, seconds in periods.items():
                period_events = [e for e in relevant if (now - e.timestamp).total_seconds() <= seconds]
                growth[label] = len(period_events)
            return {"event_growth": growth, "total_growth": len(relevant)}
        except Exception as e:
            logger.error(f"Failed to get growth metrics: {e}")
            raise

    def get_adoption_metrics(self, org_id: str = None) -> dict:
        self.telemetry["get_adoption_metrics"] += 1
        try:
            relevant = [e for e in self._org_events if org_id is None or e.org_id == org_id]
            sources = set(e.source for e in relevant)
            return {
                "active_sources": len(sources),
                "sources": list(sources),
                "event_volume": len(relevant),
                "adoption_rate": len(sources) / max(len(relevant), 1) * 100 if relevant else 0,
            }
        except Exception as e:
            logger.error(f"Failed to get adoption metrics: {e}")
            raise

    def get_retention_metrics(self, org_id: str = None) -> dict:
        self.telemetry["get_retention_metrics"] += 1
        try:
            relevant = [e for e in self._org_events if org_id is None or e.org_id == org_id]
            now = datetime.now(timezone.utc)
            active_users = set(e.user_id for e in relevant if e.user_id)
            recent = set(e.user_id for e in relevant if e.user_id and (now - e.timestamp).total_seconds() <= 604800)
            retention = len(recent) / max(len(active_users), 1) * 100 if active_users else 0
            return {"active_users": len(active_users), "retained_users": len(recent), "retention_rate": retention}
        except Exception as e:
            logger.error(f"Failed to get retention metrics: {e}")
            raise

    def get_org_health_score(self, org_id: str = None) -> float:
        self.telemetry["get_org_health_score"] += 1
        try:
            relevant = [e for e in self._org_events if org_id is None or e.org_id == org_id]
            if not relevant:
                return 0.0
            recent = [e for e in relevant if (datetime.now(timezone.utc) - e.timestamp).total_seconds() <= 86400]
            activity_score = min(len(recent) / 10, 1.0)
            severity_score = sum(1 for e in relevant if e.severity in ("error", "critical")) / max(len(relevant), 1)
            return round(max(0, (activity_score * 0.6 + (1 - severity_score) * 0.4)) * 100, 2)
        except Exception as e:
            logger.error(f"Failed to get org health score: {e}")
            raise

    def _count_events_by_key(self, events, key):
        counter = defaultdict(int)
        for e in events:
            counter[getattr(e, key, "unknown")] += 1
        return counter


class EngineeringAnalytics:
    def __init__(self, storage_dir: str):
        if not hasattr(self, "telemetry"):
            self.telemetry = defaultdict(int)
        self._eng_storage_dir = os.path.join(storage_dir, "engineering_analytics")
        os.makedirs(self._eng_storage_dir, exist_ok=True)
        self._eng_metrics_file = os.path.join(self._eng_storage_dir, "metrics.json")
        self._eng_metrics = []
        self._load_eng_data()

    def _load_eng_data(self):
        try:
            if os.path.exists(self._eng_metrics_file):
                with open(self._eng_metrics_file, "r") as f:
                    self._eng_metrics = [AnalyticsMetric.from_dict(m) for m in json.load(f)]
        except Exception as e:
            logger.error(f"Failed to load engineering data: {e}")

    def _save_eng_data(self):
        try:
            with open(self._eng_metrics_file, "w") as f:
                json.dump([m.to_dict() for m in self._eng_metrics], f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save engineering data: {e}")

    def track_engineering_metric(self, metric_name: str, value: float, unit: str = "", **kwargs) -> AnalyticsMetric:
        self.telemetry["track_engineering_metric"] += 1
        try:
            metric = AnalyticsMetric(
                id=str(uuid.uuid4()),
                metric_name=metric_name,
                value=value,
                unit=unit,
                tags=kwargs.get("tags", {}),
                source=kwargs.get("source", "engineering"),
                granularity=kwargs.get("granularity", TimeGranularity.DAILY),
            )
            self._eng_metrics.append(metric)
            self._save_eng_data()
            logger.debug(f"Tracked engineering metric {metric_name}={value}")
            return metric
        except Exception as e:
            logger.error(f"Failed to track engineering metric: {e}")
            raise

    def get_engineering_metrics(self) -> dict:
        self.telemetry["get_engineering_metrics"] += 1
        try:
            return {
                "total_metrics": len(self._eng_metrics),
                "metric_names": list(set(m.metric_name for m in self._eng_metrics)),
                "recent": [m.to_dict() for m in self._eng_metrics[-20:]],
            }
        except Exception as e:
            logger.error(f"Failed to get engineering metrics: {e}")
            raise

    def get_dora_metrics(self) -> dict:
        self.telemetry["get_dora_metrics"] += 1
        try:
            deploys = [m for m in self._eng_metrics if "deploy" in m.metric_name.lower()]
            failures = [m for m in self._eng_metrics if "failure" in m.metric_name.lower()]
            lead_times = [m for m in self._eng_metrics if "lead_time" in m.metric_name.lower()]
            mttr = [m for m in self._eng_metrics if "mttr" in m.metric_name.lower()]
            return {
                "deployment_frequency": sum(m.value for m in deploys) / max(len(deploys), 1),
                "change_failure_rate": sum(m.value for m in failures) / max(len(failures), 1) * 100 if failures else 0,
                "lead_time_for_changes": sum(m.value for m in lead_times) / max(len(lead_times), 1) if lead_times else 0,
                "mttr_seconds": sum(m.value for m in mttr) / max(len(mttr), 1) if mttr else 0,
            }
        except Exception as e:
            logger.error(f"Failed to get DORA metrics: {e}")
            raise

    def get_velocity_metrics(self) -> dict:
        self.telemetry["get_velocity_metrics"] += 1
        try:
            velocity_metrics = [m for m in self._eng_metrics if "velocity" in m.metric_name.lower()]
            throughput = [m for m in self._eng_metrics if "throughput" in m.metric_name.lower()]
            return {
                "velocity_score": sum(m.value for m in velocity_metrics) / max(len(velocity_metrics), 1) if velocity_metrics else 0,
                "throughput": sum(m.value for m in throughput) / max(len(throughput), 1) if throughput else 0,
                "sprint_completion_rate": self._org_metrics.get("sprint_completion_rate", 0),
            }
        except Exception as e:
            logger.error(f"Failed to get velocity metrics: {e}")
            raise

    def get_quality_metrics(self) -> dict:
        self.telemetry["get_quality_metrics"] += 1
        try:
            coverage = [m for m in self._eng_metrics if "coverage" in m.metric_name.lower()]
            defects = [m for m in self._eng_metrics if "defect" in m.metric_name.lower()]
            return {
                "code_coverage": sum(m.value for m in coverage) / max(len(coverage), 1) if coverage else 0,
                "defect_rate": sum(m.value for m in defects) / max(len(defects), 1) if defects else 0,
                "flaky_tests": sum(m.value for m in self._eng_metrics if "flaky" in m.metric_name.lower()),
            }
        except Exception as e:
            logger.error(f"Failed to get quality metrics: {e}")
            raise

    def get_bottlenecks(self) -> list:
        self.telemetry["get_bottlenecks"] += 1
        try:
            bottlenecks = []
            wait_times = [m for m in self._eng_metrics if "wait" in m.metric_name.lower()]
            queue_sizes = [m for m in self._eng_metrics if "queue" in m.metric_name.lower()]
            if wait_times and sum(m.value for m in wait_times) / len(wait_times) > 300:
                bottlenecks.append("High wait time detected in engineering pipeline")
            if queue_sizes and sum(m.value for m in queue_sizes) / len(queue_sizes) > 10:
                bottlenecks.append("Queue size exceeds threshold")
            return bottlenecks
        except Exception as e:
            logger.error(f"Failed to get bottlenecks: {e}")
            raise


class DeveloperAnalytics:
    def __init__(self, storage_dir: str):
        if not hasattr(self, "telemetry"):
            self.telemetry = defaultdict(int)
        self._dev_storage_dir = os.path.join(storage_dir, "developer_analytics")
        os.makedirs(self._dev_storage_dir, exist_ok=True)
        self._dev_activities_file = os.path.join(self._dev_storage_dir, "activities.json")
        self._dev_metrics_file = os.path.join(self._dev_storage_dir, "developer_metrics.json")
        self._dev_activities = []
        self._dev_metrics = {}
        self._load_dev_data()

    def _load_dev_data(self):
        try:
            if os.path.exists(self._dev_activities_file):
                with open(self._dev_activities_file, "r") as f:
                    self._dev_activities = json.load(f)
            if os.path.exists(self._dev_metrics_file):
                with open(self._dev_metrics_file, "r") as f:
                    raw = json.load(f)
                    self._dev_metrics = {uid: DeveloperMetrics.from_dict(d) for uid, d in raw.items()}
        except Exception as e:
            logger.error(f"Failed to load developer data: {e}")

    def _save_dev_data(self):
        try:
            with open(self._dev_activities_file, "w") as f:
                json.dump(self._dev_activities, f, indent=2)
            with open(self._dev_metrics_file, "w") as f:
                json.dump({uid: m.to_dict() for uid, m in self._dev_metrics.items()}, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save developer data: {e}")

    def track_developer_activity(self, user_id: str, activity_type: str, **kwargs) -> dict:
        self.telemetry["track_developer_activity"] += 1
        try:
            entry = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "activity_type": activity_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": kwargs,
            }
            self._dev_activities.append(entry)
            if user_id not in self._dev_metrics:
                self._dev_metrics[user_id] = DeveloperMetrics(user_id=user_id)
            m = self._dev_metrics[user_id]
            if activity_type == "commit":
                m.commits += 1
            elif activity_type == "pr_create":
                m.prs_created += 1
            elif activity_type == "pr_merge":
                m.prs_merged += 1
            elif activity_type == "review":
                m.reviews_done += 1
            elif activity_type == "issue_resolve":
                m.issues_resolved += 1
            m.contribution_score = self._calc_contribution_score(m)
            self._save_dev_data()
            logger.debug(f"Tracked dev activity {activity_type} for {user_id}")
            return entry
        except Exception as e:
            logger.error(f"Failed to track developer activity: {e}")
            raise

    def get_developer_metrics(self, user_id: str) -> Optional[DeveloperMetrics]:
        self.telemetry["get_developer_metrics"] += 1
        return self._dev_metrics.get(user_id)

    def compare_developers(self, user_ids: list[str]) -> dict:
        self.telemetry["compare_developers"] += 1
        try:
            return {uid: self._dev_metrics[uid].to_dict() for uid in user_ids if uid in self._dev_metrics}
        except Exception as e:
            logger.error(f"Failed to compare developers: {e}")
            raise

    def get_top_performers(self, n: int = 5) -> list:
        self.telemetry["get_top_performers"] += 1
        try:
            sorted_devs = sorted(self._dev_metrics.values(), key=lambda d: d.contribution_score, reverse=True)
            return [d.to_dict() for d in sorted_devs[:n]]
        except Exception as e:
            logger.error(f"Failed to get top performers: {e}")
            raise

    def get_developer_trends(self, user_id: str = None) -> dict:
        self.telemetry["get_developer_trends"] += 1
        try:
            activities = self._dev_activities
            if user_id:
                activities = [a for a in activities if a["user_id"] == user_id]
            now = datetime.now(timezone.utc)
            daily = defaultdict(int)
            for a in activities:
                day = datetime.fromisoformat(a["timestamp"]).strftime("%Y-%m-%d")
                daily[day] += 1
            return {"daily_activity": dict(daily), "total_activities": len(activities), "user_id": user_id}
        except Exception as e:
            logger.error(f"Failed to get developer trends: {e}")
            raise

    def get_team_metrics(self, user_ids: list[str] = None) -> dict:
        self.telemetry["get_team_metrics"] += 1
        try:
            relevant = self._dev_metrics
            if user_ids:
                relevant = {uid: m for uid, m in self._dev_metrics.items() if uid in user_ids}
            if not relevant:
                return {}
            return {
                "team_size": len(relevant),
                "total_commits": sum(m.commits for m in relevant.values()),
                "total_prs": sum(m.prs_created for m in relevant.values()),
                "total_reviews": sum(m.reviews_done for m in relevant.values()),
                "total_issues_resolved": sum(m.issues_resolved for m in relevant.values()),
                "avg_contribution_score": sum(m.contribution_score for m in relevant.values()) / len(relevant),
            }
        except Exception as e:
            logger.error(f"Failed to get team metrics: {e}")
            raise

    def _calc_contribution_score(self, m: DeveloperMetrics) -> float:
        score = (m.commits * 1 + m.prs_created * 3 + m.prs_merged * 5 + m.reviews_done * 2 + m.issues_resolved * 4)
        return round(score / max(m.active_days, 1), 2)


class AIAnalytics:
    def __init__(self, storage_dir: str):
        if not hasattr(self, "telemetry"):
            self.telemetry = defaultdict(int)
        self._ai_storage_dir = os.path.join(storage_dir, "ai_analytics")
        os.makedirs(self._ai_storage_dir, exist_ok=True)
        self._ai_usage_file = os.path.join(self._ai_storage_dir, "usage.json")
        self._ai_metrics_file = os.path.join(self._ai_storage_dir, "metrics.json")
        self._ai_usage = []
        self._ai_metrics = []
        self._load_ai_data()

    def _load_ai_data(self):
        try:
            if os.path.exists(self._ai_usage_file):
                with open(self._ai_usage_file, "r") as f:
                    self._ai_usage = json.load(f)
            if os.path.exists(self._ai_metrics_file):
                with open(self._ai_metrics_file, "r") as f:
                    self._ai_metrics = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load AI data: {e}")

    def _save_ai_data(self):
        try:
            with open(self._ai_usage_file, "w") as f:
                json.dump(self._ai_usage, f, indent=2)
            with open(self._ai_metrics_file, "w") as f:
                json.dump(self._ai_metrics, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save AI data: {e}")

    def track_ai_usage(self, model: str, tokens_in: int, tokens_out: int, **kwargs) -> dict:
        self.telemetry["track_ai_usage"] += 1
        try:
            entry = {
                "id": str(uuid.uuid4()),
                "model": model,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "total_tokens": tokens_in + tokens_out,
                "cost_estimate": kwargs.get("cost_estimate", 0.0),
                "user_id": kwargs.get("user_id"),
                "feature": kwargs.get("feature", "unknown"),
                "latency_ms": kwargs.get("latency_ms", 0),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "success": kwargs.get("success", True),
            }
            self._ai_usage.append(entry)
            self._save_ai_data()
            logger.debug(f"Tracked AI usage model={model} tokens={entry['total_tokens']}")
            return entry
        except Exception as e:
            logger.error(f"Failed to track AI usage: {e}")
            raise

    def get_ai_metrics(self) -> dict:
        self.telemetry["get_ai_metrics"] += 1
        try:
            total_tokens = sum(u["total_tokens"] for u in self._ai_usage)
            total_cost = sum(u.get("cost_estimate", 0) for u in self._ai_usage)
            models = set(u["model"] for u in self._ai_usage)
            return {
                "total_requests": len(self._ai_usage),
                "total_tokens": total_tokens,
                "total_cost": total_cost,
                "unique_models": list(models),
                "avg_latency_ms": sum(u.get("latency_ms", 0) for u in self._ai_usage) / max(len(self._ai_usage), 1),
            }
        except Exception as e:
            logger.error(f"Failed to get AI metrics: {e}")
            raise

    def get_model_performance(self) -> dict:
        self.telemetry["get_model_performance"] += 1
        try:
            by_model = defaultdict(list)
            for u in self._ai_usage:
                by_model[u["model"]].append(u)
            perf = {}
            for model, usage in by_model.items():
                total = len(usage)
                successes = sum(1 for u in usage if u.get("success", True))
                perf[model] = {
                    "requests": total,
                    "success_rate": successes / max(total, 1) * 100,
                    "avg_latency_ms": sum(u.get("latency_ms", 0) for u in usage) / max(total, 1),
                    "total_tokens": sum(u["total_tokens"] for u in usage),
                }
            return perf
        except Exception as e:
            logger.error(f"Failed to get model performance: {e}")
            raise

    def get_token_usage_trends(self) -> dict:
        self.telemetry["get_token_usage_trends"] += 1
        try:
            by_day = defaultdict(lambda: {"tokens_in": 0, "tokens_out": 0})
            for u in self._ai_usage:
                day = datetime.fromisoformat(u["timestamp"]).strftime("%Y-%m-%d")
                by_day[day]["tokens_in"] += u["tokens_in"]
                by_day[day]["tokens_out"] += u["tokens_out"]
            return dict(by_day)
        except Exception as e:
            logger.error(f"Failed to get token usage trends: {e}")
            raise

    def get_ai_adoption_rate(self) -> dict:
        self.telemetry["get_ai_adoption_rate"] += 1
        try:
            users = set(u.get("user_id") for u in self._ai_usage if u.get("user_id"))
            features = set(u.get("feature") for u in self._ai_usage if u.get("feature"))
            models = set(u["model"] for u in self._ai_usage)
            return {
                "unique_users": len(users),
                "features_adopted": len(features),
                "models_used": len(models),
                "total_usage": len(self._ai_usage),
                "adoption_score": min(len(users) * 10 + len(features) * 5, 100),
            }
        except Exception as e:
            logger.error(f"Failed to get AI adoption rate: {e}")
            raise

    def get_ai_roi(self) -> dict:
        self.telemetry["get_ai_roi"] += 1
        try:
            total_cost = sum(u.get("cost_estimate", 0) for u in self._ai_usage)
            total_tokens = sum(u["total_tokens"] for u in self._ai_usage)
            estimated_time_saved = total_tokens / 1000 * 0.5
            estimated_labor_cost = estimated_time_saved * 50
            roi = ((estimated_labor_cost - total_cost) / max(total_cost, 1)) * 100
            return {
                "total_cost": total_cost,
                "total_tokens": total_tokens,
                "estimated_time_saved_hours": estimated_time_saved,
                "estimated_labor_savings": estimated_labor_cost,
                "roi_percent": round(roi, 2),
            }
        except Exception as e:
            logger.error(f"Failed to get AI ROI: {e}")
            raise


class RepositoryAnalytics:
    def __init__(self, storage_dir: str):
        if not hasattr(self, "telemetry"):
            self.telemetry = defaultdict(int)
        self._repo_storage_dir = os.path.join(storage_dir, "repository_analytics")
        os.makedirs(self._repo_storage_dir, exist_ok=True)
        self._repo_activities_file = os.path.join(self._repo_storage_dir, "activities.json")
        self._repo_metrics_file = os.path.join(self._repo_storage_dir, "repo_metrics.json")
        self._repo_activities = []
        self._repo_metrics = {}
        self._load_repo_data()

    def _load_repo_data(self):
        try:
            if os.path.exists(self._repo_activities_file):
                with open(self._repo_activities_file, "r") as f:
                    self._repo_activities = json.load(f)
            if os.path.exists(self._repo_metrics_file):
                with open(self._repo_metrics_file, "r") as f:
                    self._repo_metrics = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load repository data: {e}")

    def _save_repo_data(self):
        try:
            with open(self._repo_activities_file, "w") as f:
                json.dump(self._repo_activities, f, indent=2)
            with open(self._repo_metrics_file, "w") as f:
                json.dump(self._repo_metrics, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save repository data: {e}")

    def track_repo_activity(self, repository_id: str, activity_type: str, **kwargs) -> dict:
        self.telemetry["track_repo_activity"] += 1
        try:
            entry = {
                "id": str(uuid.uuid4()),
                "repository_id": repository_id,
                "activity_type": activity_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "user_id": kwargs.get("user_id"),
                "branch": kwargs.get("branch", "main"),
                "details": kwargs.get("details", {}),
            }
            self._repo_activities.append(entry)
            if repository_id not in self._repo_metrics:
                self._repo_metrics[repository_id] = {"commits": 0, "prs": 0, "issues": 0, "reviews": 0}
            self._repo_metrics[repository_id]["commits"] += 1 if activity_type == "commit" else 0
            self._repo_metrics[repository_id]["prs"] += 1 if activity_type == "pr" else 0
            self._repo_metrics[repository_id]["issues"] += 1 if activity_type == "issue" else 0
            self._repo_metrics[repository_id]["reviews"] += 1 if activity_type == "review" else 0
            self._save_repo_data()
            logger.debug(f"Tracked repo activity {activity_type} for {repository_id}")
            return entry
        except Exception as e:
            logger.error(f"Failed to track repo activity: {e}")
            raise

    def get_repo_metrics(self, repository_id: str) -> dict:
        self.telemetry["get_repo_metrics"] += 1
        try:
            metrics = self._repo_metrics.get(repository_id, {})
            activities = [a for a in self._repo_activities if a["repository_id"] == repository_id]
            return {**metrics, "total_activities": len(activities), "repository_id": repository_id}
        except Exception as e:
            logger.error(f"Failed to get repo metrics: {e}")
            raise

    def compare_repos(self, repository_ids: list[str]) -> dict:
        self.telemetry["compare_repos"] += 1
        try:
            return {rid: self._repo_metrics.get(rid, {}) for rid in repository_ids}
        except Exception as e:
            logger.error(f"Failed to compare repos: {e}")
            raise

    def get_repo_health_trend(self, repository_id: str = None) -> dict:
        self.telemetry["get_repo_health_trend"] += 1
        try:
            activities = self._repo_activities
            if repository_id:
                activities = [a for a in activities if a["repository_id"] == repository_id]
            by_month = defaultdict(int)
            for a in activities:
                month = datetime.fromisoformat(a["timestamp"]).strftime("%Y-%m")
                by_month[month] += 1
            return {"monthly_activity": dict(by_month), "total": len(activities)}
        except Exception as e:
            logger.error(f"Failed to get repo health trend: {e}")
            raise

    def get_activity_hotspots(self) -> list:
        self.telemetry["get_activity_hotspots"] += 1
        try:
            repo_counts = defaultdict(int)
            for a in self._repo_activities:
                repo_counts[a["repository_id"]] += 1
            sorted_repos = sorted(repo_counts.items(), key=lambda x: x[1], reverse=True)
            return [{"repository_id": rid, "activity_count": cnt} for rid, cnt in sorted_repos[:10]]
        except Exception as e:
            logger.error(f"Failed to get activity hotspots: {e}")
            raise


class SecurityAnalytics:
    def __init__(self, storage_dir: str):
        if not hasattr(self, "telemetry"):
            self.telemetry = defaultdict(int)
        self._sec_storage_dir = os.path.join(storage_dir, "security_analytics")
        os.makedirs(self._sec_storage_dir, exist_ok=True)
        self._sec_events_file = os.path.join(self._sec_storage_dir, "events.json")
        self._sec_compliance_file = os.path.join(self._sec_storage_dir, "compliance.json")
        self._sec_events = []
        self._sec_compliance = []
        self._load_sec_data()

    def _load_sec_data(self):
        try:
            if os.path.exists(self._sec_events_file):
                with open(self._sec_events_file, "r") as f:
                    self._sec_events = json.load(f)
            if os.path.exists(self._sec_compliance_file):
                with open(self._sec_compliance_file, "r") as f:
                    self._sec_compliance = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load security data: {e}")

    def _save_sec_data(self):
        try:
            with open(self._sec_events_file, "w") as f:
                json.dump(self._sec_events, f, indent=2)
            with open(self._sec_compliance_file, "w") as f:
                json.dump(self._sec_compliance, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save security data: {e}")

    def track_security_event(self, event_type: str, severity: str, source: str, **kwargs) -> dict:
        self.telemetry["track_security_event"] += 1
        try:
            event = {
                "id": str(uuid.uuid4()),
                "event_type": event_type,
                "severity": severity,
                "source": source,
                "description": kwargs.get("description", ""),
                "indicator": kwargs.get("indicator", ""),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "org_id": kwargs.get("org_id"),
                "resolved": kwargs.get("resolved", False),
            }
            self._sec_events.append(event)
            self._save_sec_data()
            logger.debug(f"Tracked security event {event_type} severity={severity}")
            return event
        except Exception as e:
            logger.error(f"Failed to track security event: {e}")
            raise

    def get_security_metrics(self) -> dict:
        self.telemetry["get_security_metrics"] += 1
        try:
            critical = sum(1 for e in self._sec_events if e.get("severity") == "critical")
            high = sum(1 for e in self._sec_events if e.get("severity") == "high")
            resolved = sum(1 for e in self._sec_events if e.get("resolved"))
            return {
                "total_events": len(self._sec_events),
                "critical": critical,
                "high": high,
                "open": len(self._sec_events) - resolved,
                "resolution_rate": resolved / max(len(self._sec_events), 1) * 100,
            }
        except Exception as e:
            logger.error(f"Failed to get security metrics: {e}")
            raise

    def get_vulnerability_trends(self) -> dict:
        self.telemetry["get_vulnerability_trends"] += 1
        try:
            by_month = defaultdict(int)
            for e in self._sec_events:
                month = datetime.fromisoformat(e["timestamp"]).strftime("%Y-%m")
                by_month[month] += 1
            return {"monthly_trend": dict(by_month), "total_vulnerabilities": len(self._sec_events)}
        except Exception as e:
            logger.error(f"Failed to get vulnerability trends: {e}")
            raise

    def get_compliance_score_trend(self) -> dict:
        self.telemetry["get_compliance_score_trend"] += 1
        try:
            by_month = defaultdict(list)
            for c in self._sec_compliance:
                month = datetime.fromisoformat(c["checked_at"]).strftime("%Y-%m")
                by_month[month].append(c.get("score", 0))
            return {month: sum(scores) / len(scores) for month, scores in by_month.items()}
        except Exception as e:
            logger.error(f"Failed to get compliance score trend: {e}")
            raise

    def get_threat_landscape(self) -> dict:
        self.telemetry["get_threat_landscape"] += 1
        try:
            types = defaultdict(int)
            for e in self._sec_events:
                types[e.get("event_type", "unknown")] += 1
            return {
                "threat_types": dict(types),
                "total_threats": len(self._sec_events),
                "most_common": max(types, key=types.get) if types else None,
            }
        except Exception as e:
            logger.error(f"Failed to get threat landscape: {e}")
            raise


class InfrastructureAnalytics:
    def __init__(self, storage_dir: str):
        if not hasattr(self, "telemetry"):
            self.telemetry = defaultdict(int)
        self._infra_storage_dir = os.path.join(storage_dir, "infrastructure_analytics")
        os.makedirs(self._infra_storage_dir, exist_ok=True)
        self._infra_metrics_file = os.path.join(self._infra_storage_dir, "metrics.json")
        self._infra_cost_file = os.path.join(self._infra_storage_dir, "costs.json")
        self._infra_metrics = []
        self._infra_costs = []
        self._load_infra_data()

    def _load_infra_data(self):
        try:
            if os.path.exists(self._infra_metrics_file):
                with open(self._infra_metrics_file, "r") as f:
                    self._infra_metrics = json.load(f)
            if os.path.exists(self._infra_cost_file):
                with open(self._infra_cost_file, "r") as f:
                    self._infra_costs = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load infrastructure data: {e}")

    def _save_infra_data(self):
        try:
            with open(self._infra_metrics_file, "w") as f:
                json.dump(self._infra_metrics, f, indent=2)
            with open(self._infra_cost_file, "w") as f:
                json.dump(self._infra_costs, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save infrastructure data: {e}")

    def track_infra_metric(self, metric_name: str, value: float, unit: str, **kwargs) -> dict:
        self.telemetry["track_infra_metric"] += 1
        try:
            entry = {
                "id": str(uuid.uuid4()),
                "metric_name": metric_name,
                "value": value,
                "unit": unit,
                "resource": kwargs.get("resource", "unknown"),
                "region": kwargs.get("region", "global"),
                "tags": kwargs.get("tags", {}),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self._infra_metrics.append(entry)
            self._save_infra_data()
            logger.debug(f"Tracked infra metric {metric_name}={value}{unit}")
            return entry
        except Exception as e:
            logger.error(f"Failed to track infra metric: {e}")
            raise

    def get_infra_metrics(self) -> dict:
        self.telemetry["get_infra_metrics"] += 1
        try:
            names = set(m["metric_name"] for m in self._infra_metrics)
            resources = set(m.get("resource", "unknown") for m in self._infra_metrics)
            return {
                "total_metrics": len(self._infra_metrics),
                "metric_names": list(names),
                "resources_monitored": list(resources),
            }
        except Exception as e:
            logger.error(f"Failed to get infra metrics: {e}")
            raise

    def get_resource_utilization(self) -> dict:
        self.telemetry["get_resource_utilization"] += 1
        try:
            by_resource = defaultdict(list)
            for m in self._infra_metrics:
                by_resource[m.get("resource", "unknown")].append(m)
            utilization = {}
            for resource, metrics in by_resource.items():
                cpu = [m for m in metrics if "cpu" in m["metric_name"].lower()]
                memory = [m for m in metrics if "memory" in m["metric_name"].lower() or "mem" in m["metric_name"].lower()]
                utilization[resource] = {
                    "avg_cpu": sum(m["value"] for m in cpu) / max(len(cpu), 1) if cpu else 0,
                    "avg_memory": sum(m["value"] for m in memory) / max(len(memory), 1) if memory else 0,
                    "total_metrics": len(metrics),
                }
            return utilization
        except Exception as e:
            logger.error(f"Failed to get resource utilization: {e}")
            raise

    def get_cost_trends(self) -> dict:
        self.telemetry["get_cost_trends"] += 1
        try:
            by_month = defaultdict(float)
            for c in self._infra_costs:
                month = datetime.fromisoformat(c.get("timestamp", c.get("date", ""))).strftime("%Y-%m")
                by_month[month] += c.get("amount", c.get("cost", 0))
            return {"monthly_cost": dict(by_month), "total_cost": sum(by_month.values())}
        except Exception as e:
            logger.error(f"Failed to get cost trends: {e}")
            raise

    def get_capacity_planning(self) -> dict:
        self.telemetry["get_capacity_planning"] += 1
        try:
            cpu_metrics = [m for m in self._infra_metrics if "cpu" in m["metric_name"].lower()]
            mem_metrics = [m for m in self._infra_metrics if "memory" in m["metric_name"].lower()]
            avg_cpu = sum(m["value"] for m in cpu_metrics) / max(len(cpu_metrics), 1) if cpu_metrics else 0
            avg_mem = sum(m["value"] for m in mem_metrics) / max(len(mem_metrics), 1) if mem_metrics else 0
            return {
                "avg_cpu_utilization": avg_cpu,
                "avg_memory_utilization": avg_mem,
                "cpu_headroom": 100 - avg_cpu,
                "memory_headroom": 100 - avg_mem,
                "scale_recommendation": "scale_up" if avg_cpu > 80 or avg_mem > 80 else "scale_down" if avg_cpu < 20 and avg_mem < 20 else "stable",
            }
        except Exception as e:
            logger.error(f"Failed to get capacity planning: {e}")
            raise


class InsightEngine:
    def __init__(self, storage_dir: str):
        if not hasattr(self, "telemetry"):
            self.telemetry = defaultdict(int)
        self._insight_storage_dir = os.path.join(storage_dir, "insight_engine")
        os.makedirs(self._insight_storage_dir, exist_ok=True)
        self._insight_file = os.path.join(self._insight_storage_dir, "insights.json")
        self._insights = []
        self._load_insights()

    def _load_insights(self):
        try:
            if os.path.exists(self._insight_file):
                with open(self._insight_file, "r") as f:
                    data = json.load(f)
                self._insights = [Insight.from_dict(i) for i in data]
        except Exception as e:
            logger.error(f"Failed to load insights: {e}")

    def _save_insights(self):
        try:
            with open(self._insight_file, "w") as f:
                json.dump([i.to_dict() for i in self._insights], f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save insights: {e}")

    def generate_insight(self, insight_type: str, title: str, **kwargs) -> Insight:
        self.telemetry["generate_insight"] += 1
        try:
            insight = Insight(
                id=str(uuid.uuid4()),
                insight_type=insight_type,
                title=title,
                description=kwargs.get("description", ""),
                confidence=kwargs.get("confidence", 0.0),
                evidence=kwargs.get("evidence", {}),
                impact=kwargs.get("impact", "medium"),
                metadata=kwargs.get("metadata", {}),
            )
            self._insights.append(insight)
            self._save_insights()
            logger.debug(f"Generated insight {insight.id} type={insight_type}")
            return insight
        except Exception as e:
            logger.error(f"Failed to generate insight: {e}")
            raise

    def list_insights(self, limit: int = 50) -> list:
        self.telemetry["list_insights"] += 1
        try:
            return [i.to_dict() for i in self._insights[-limit:]]
        except Exception as e:
            logger.error(f"Failed to list insights: {e}")
            raise

    def get_insight_by_type(self, insight_type: str) -> list:
        self.telemetry["get_insight_by_type"] += 1
        try:
            return [i.to_dict() for i in self._insights if i.insight_type == insight_type]
        except Exception as e:
            logger.error(f"Failed to get insights by type: {e}")
            raise

    def get_trending_insights(self, min_confidence: float = 0.7) -> list:
        self.telemetry["get_trending_insights"] += 1
        try:
            recent = [i for i in self._insights if i.confidence >= min_confidence]
            sorted_insights = sorted(recent, key=lambda i: i.confidence, reverse=True)
            return [i.to_dict() for i in sorted_insights[:10]]
        except Exception as e:
            logger.error(f"Failed to get trending insights: {e}")
            raise

    def auto_discover_insights(self) -> list:
        self.telemetry["auto_discover_insights"] += 1
        try:
            discovered = []
            existing_types = set(i.insight_type for i in self._insights)
            patterns = ["performance_degradation", "usage_spike", "anomaly_detection", "cost_optimization", "security_risk"]
            for pattern in patterns:
                if pattern not in existing_types:
                    insight = self.generate_insight(
                        insight_type=pattern,
                        title=f"Auto-discovered: {pattern.replace('_', ' ').title()}",
                        description=f"System identified {pattern} pattern for analysis",
                        confidence=0.5,
                        impact="medium",
                    )
                    discovered.append(insight.to_dict())
            return discovered
        except Exception as e:
            logger.error(f"Failed to auto-discover insights: {e}")
            raise


class PlatformAnalytics(
    OrganizationAnalytics, EngineeringAnalytics, DeveloperAnalytics,
    AIAnalytics, RepositoryAnalytics, SecurityAnalytics,
    InfrastructureAnalytics, InsightEngine
):
    def __init__(self, storage_dir: str):
        self.telemetry = defaultdict(int)
        OrganizationAnalytics.__init__(self, storage_dir)
        EngineeringAnalytics.__init__(self, storage_dir)
        DeveloperAnalytics.__init__(self, storage_dir)
        AIAnalytics.__init__(self, storage_dir)
        RepositoryAnalytics.__init__(self, storage_dir)
        SecurityAnalytics.__init__(self, storage_dir)
        InfrastructureAnalytics.__init__(self, storage_dir)
        InsightEngine.__init__(self, storage_dir)
        self._platform_storage_dir = os.path.join(storage_dir, "platform_analytics")
        os.makedirs(self._platform_storage_dir, exist_ok=True)
        self._reports_file = os.path.join(self._platform_storage_dir, "reports.json")
        self._reports = []
        self._load_platform_data()
        self.telemetry["platform_analytics_init"] += 1
        logger.info(f"PlatformAnalytics initialized at {storage_dir}")

    def _load_platform_data(self):
        try:
            if os.path.exists(self._reports_file):
                with open(self._reports_file, "r") as f:
                    data = json.load(f)
                self._reports = [AnalyticsReport.from_dict(r) for r in data]
        except Exception as e:
            logger.error(f"Failed to load platform data: {e}")

    def _save_platform_data(self):
        try:
            with open(self._reports_file, "w") as f:
                json.dump([r.to_dict() for r in self._reports], f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save platform data: {e}")

    def generate_report(self, analytics_type: AnalyticsType, title: str, **kwargs) -> AnalyticsReport:
        self.telemetry["generate_report"] += 1
        try:
            metrics = {}
            if analytics_type == AnalyticsType.ORGANIZATION:
                metrics = self.get_org_metrics(kwargs.get("org_id"))
            elif analytics_type == AnalyticsType.ENGINEERING:
                metrics = self.get_engineering_metrics()
            elif analytics_type == AnalyticsType.DEVELOPER:
                uid = kwargs.get("user_id")
                if uid:
                    m = self.get_developer_metrics(uid)
                    metrics = m.to_dict() if m else {}
                else:
                    metrics = self.get_team_metrics(kwargs.get("user_ids"))
            elif analytics_type == AnalyticsType.AI:
                metrics = self.get_ai_metrics()
            elif analytics_type == AnalyticsType.REPOSITORY:
                rid = kwargs.get("repository_id")
                metrics = self.get_repo_metrics(rid) if rid else {"repos": list(self._repo_metrics.keys())}
            elif analytics_type == AnalyticsType.SECURITY:
                metrics = self.get_security_metrics()
            elif analytics_type == AnalyticsType.INFRASTRUCTURE:
                metrics = self.get_infra_metrics()

            report = AnalyticsReport(
                id=str(uuid.uuid4()),
                analytics_type=analytics_type,
                title=title,
                description=kwargs.get("description", ""),
                metrics=metrics,
                insights=[i.to_dict() for i in self._insights[-5:]],
                recommendations=kwargs.get("recommendations", []),
                period_start=kwargs.get("period_start"),
                period_end=kwargs.get("period_end"),
                format=kwargs.get("format", ReportFormat.JSON),
            )
            self._reports.append(report)
            self._save_platform_data()
            logger.info(f"Generated {analytics_type.value} report: {report.id}")
            return report
        except Exception as e:
            logger.error(f"Failed to generate report: {e}")
            raise

    def get_dashboard_data(self) -> dict:
        self.telemetry["get_dashboard_data"] += 1
        try:
            return {
                "organizational": self.get_org_metrics(),
                "engineering": self.get_engineering_metrics(),
                "dora": self.get_dora_metrics(),
                "top_developers": self.get_top_performers(5),
                "ai": self.get_ai_metrics(),
                "repository_hotspots": self.get_activity_hotspots(),
                "security": self.get_security_metrics(),
                "infrastructure": self.get_resource_utilization(),
                "recent_insights": self.list_insights(5),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.error(f"Failed to get dashboard data: {e}")
            raise
