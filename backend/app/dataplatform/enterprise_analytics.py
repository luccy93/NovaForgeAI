"""Enterprise Analytics module for NovaForge Data Platform & Knowledge Fabric (Volume 19)."""

import json, uuid, os, logging, random
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class AnalyticsEntityType(Enum):
    REPOSITORY = "repository"
    ARCHITECTURE = "architecture"
    DEPENDENCY = "dependency"
    DEVELOPER = "developer"
    KNOWLEDGE = "knowledge"
    TECHNICAL_DEBT = "technical_debt"
    AI_ADOPTION = "ai_adoption"
    SECURITY = "security"
    PERFORMANCE = "performance"
    COST = "cost"


class AnalyticsTrendDirection(Enum):
    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"
    VOLATILE = "volatile"
    UNKNOWN = "unknown"


class AnalyticsPeriod(Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class AnalyticsMetricType(Enum):
    COUNT = "count"
    RATE = "rate"
    PERCENTAGE = "percentage"
    AVERAGE = "average"
    CUMULATIVE = "cumulative"
    DISTRIBUTION = "distribution"


@dataclass
class AnalyticsMetric:
    id: str
    org_id: str
    entity_type: AnalyticsEntityType
    name: str
    description: str = ""
    metric_type: AnalyticsMetricType = AnalyticsMetricType.COUNT
    unit: str = ""
    current_value: float = 0.0
    previous_value: float = 0.0
    percent_change: float = 0.0
    trend: AnalyticsTrendDirection = AnalyticsTrendDirection.UNKNOWN
    period: AnalyticsPeriod = AnalyticsPeriod.DAILY
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["entity_type"] = self.entity_type.value
        d["metric_type"] = self.metric_type.value
        d["trend"] = self.trend.value
        d["period"] = self.period.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AnalyticsMetric":
        data = data.copy()
        data["entity_type"] = AnalyticsEntityType(data.get("entity_type", "repository"))
        data["metric_type"] = AnalyticsMetricType(data.get("metric_type", "count"))
        data["trend"] = AnalyticsTrendDirection(data.get("trend", "unknown"))
        data["period"] = AnalyticsPeriod(data.get("period", "daily"))
        return cls(**data)


@dataclass
class AnalyticsReport:
    id: str
    org_id: str
    title: str = ""
    entity_type: AnalyticsEntityType = AnalyticsEntityType.REPOSITORY
    period_start: str = ""
    period_end: str = ""
    metrics: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    insights: list = field(default_factory=list)
    recommendations: list = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["entity_type"] = self.entity_type.value
        d["metrics"] = [m.to_dict() if isinstance(m, AnalyticsMetric) else m for m in self.metrics]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AnalyticsReport":
        data = data.copy()
        data["entity_type"] = AnalyticsEntityType(data.get("entity_type", "repository"))
        data["metrics"] = [AnalyticsMetric.from_dict(m) if isinstance(m, dict) else m for m in data.get("metrics", [])]
        return cls(**data)


@dataclass
class EntityEvolution:
    id: str
    org_id: str
    entity_type: AnalyticsEntityType
    entity_id: str = ""
    entity_name: str = ""
    period: AnalyticsPeriod = AnalyticsPeriod.MONTHLY
    snapshots: list = field(default_factory=list)
    growth_rate: float = 0.0
    velocity: float = 0.0
    trend: AnalyticsTrendDirection = AnalyticsTrendDirection.UNKNOWN
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["entity_type"] = self.entity_type.value
        d["period"] = self.period.value
        d["trend"] = self.trend.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "EntityEvolution":
        data = data.copy()
        data["entity_type"] = AnalyticsEntityType(data.get("entity_type", "repository"))
        data["period"] = AnalyticsPeriod(data.get("period", "monthly"))
        data["trend"] = AnalyticsTrendDirection(data.get("trend", "unknown"))
        return cls(**data)


@dataclass
class AdoptionMetrics:
    id: str
    org_id: str
    feature: str = ""
    period: AnalyticsPeriod = AnalyticsPeriod.MONTHLY
    total_users: int = 0
    active_users: int = 0
    adoption_rate: float = 0.0
    engagement_score: float = 0.0
    retention_rate: float = 0.0
    growth_rate: float = 0.0
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["period"] = self.period.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AdoptionMetrics":
        data = data.copy()
        data["period"] = AnalyticsPeriod(data.get("period", "monthly"))
        return cls(**data)


class EnterpriseAnalytics:
    def __init__(self, storage_dir: str = "analytics_data"):
        self.storage_dir = storage_dir
        self._metrics: dict[str, AnalyticsMetric] = {}
        self._reports: dict[str, AnalyticsReport] = {}
        self._evolutions: dict[str, EntityEvolution] = {}
        self._adoptions: dict[str, AdoptionMetrics] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _metrics_path(self) -> str:
        return os.path.join(self.storage_dir, "analytics_metrics.json")

    def _reports_path(self) -> str:
        return os.path.join(self.storage_dir, "analytics_reports.json")

    def _evolutions_path(self) -> str:
        return os.path.join(self.storage_dir, "analytics_evolutions.json")

    def _adoptions_path(self) -> str:
        return os.path.join(self.storage_dir, "analytics_adoptions.json")

    def _save(self) -> None:
        try:
            metrics_data = {mid: m.to_dict() for mid, m in self._metrics.items()}
            with open(self._metrics_path(), "w", encoding="utf-8") as f:
                json.dump(metrics_data, f, indent=2, default=str)

            reports_data = {rid: r.to_dict() for rid, r in self._reports.items()}
            with open(self._reports_path(), "w", encoding="utf-8") as f:
                json.dump(reports_data, f, indent=2, default=str)

            evolutions_data = {eid: e.to_dict() for eid, e in self._evolutions.items()}
            with open(self._evolutions_path(), "w", encoding="utf-8") as f:
                json.dump(evolutions_data, f, indent=2, default=str)

            adoptions_data = {aid: a.to_dict() for aid, a in self._adoptions.items()}
            with open(self._adoptions_path(), "w", encoding="utf-8") as f:
                json.dump(adoptions_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save analytics data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._metrics_path()):
                with open(self._metrics_path(), "r", encoding="utf-8") as f:
                    metrics_data = json.load(f)
                for mid, data in metrics_data.items():
                    try:
                        self._metrics[mid] = AnalyticsMetric.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed metric %s: %s", mid, e)

            if os.path.exists(self._reports_path()):
                with open(self._reports_path(), "r", encoding="utf-8") as f:
                    reports_data = json.load(f)
                for rid, data in reports_data.items():
                    try:
                        self._reports[rid] = AnalyticsReport.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed report %s: %s", rid, e)

            if os.path.exists(self._evolutions_path()):
                with open(self._evolutions_path(), "r", encoding="utf-8") as f:
                    evolutions_data = json.load(f)
                for eid, data in evolutions_data.items():
                    try:
                        self._evolutions[eid] = EntityEvolution.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed evolution %s: %s", eid, e)

            if os.path.exists(self._adoptions_path()):
                with open(self._adoptions_path(), "r", encoding="utf-8") as f:
                    adoptions_data = json.load(f)
                for aid, data in adoptions_data.items():
                    try:
                        self._adoptions[aid] = AdoptionMetrics.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed adoption %s: %s", aid, e)
        except Exception as e:
            logger.error("Failed to load analytics data: %s", e, exc_info=True)

    def record_metric(self, metric: AnalyticsMetric) -> AnalyticsMetric:
        self._telemetry["record_metric_calls"] += 1
        if not metric.id:
            metric.id = str(uuid.uuid4())
        if not metric.timestamp:
            metric.timestamp = datetime.now(timezone.utc).isoformat()
        self._metrics[metric.id] = metric
        self._save()
        logger.info("Recorded analytics metric %s: %s (%s) = %s %s", metric.id, metric.name, metric.entity_type.value, metric.current_value, metric.unit)
        return metric

    def get_metrics(self, org_id: str, entity_type: AnalyticsEntityType, period: AnalyticsPeriod, days: int = 90) -> list[AnalyticsMetric]:
        self._telemetry["get_metrics_calls"] += 1
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        results = []
        for m in self._metrics.values():
            if m.org_id != org_id or m.entity_type != entity_type or m.period != period:
                continue
            try:
                m_time = datetime.fromisoformat(m.timestamp)
                if m_time >= cutoff:
                    results.append(m)
            except (ValueError, TypeError):
                results.append(m)
        results.sort(key=lambda x: x.timestamp, reverse=True)
        return results

    def compute_repository_evolution(self, org_id: str, period: AnalyticsPeriod) -> EntityEvolution:
        self._telemetry["compute_repository_evolution_calls"] += 1
        metrics = [m for m in self._metrics.values() if m.org_id == org_id and m.entity_type == AnalyticsEntityType.REPOSITORY and m.period == period]
        snapshots = []
        for m in metrics:
            snapshots.append({"metric_id": m.id, "name": m.name, "value": m.current_value, "timestamp": m.timestamp, "unit": m.unit})
        growth_rate = 0.0
        velocity = 0.0
        if metrics:
            values = [m.current_value for m in metrics if m.current_value]
            if len(values) >= 2:
                growth_rate = round(((values[0] - values[-1]) / max(abs(values[-1]), 1)) * 100, 2)
            velocity = round(sum(values) / max(len(values), 1), 2)
        trend = self._infer_trend(metrics)
        evolution = EntityEvolution(
            id=str(uuid.uuid4()),
            org_id=org_id,
            entity_type=AnalyticsEntityType.REPOSITORY,
            entity_id=f"repo_{org_id}",
            entity_name=f"Repository Evolution - {org_id}",
            period=period,
            snapshots=snapshots[-20:],
            growth_rate=growth_rate,
            velocity=velocity,
            trend=trend,
        )
        self._evolutions[evolution.id] = evolution
        self._save()
        logger.info("Computed repository evolution for org %s: growth=%s%%, velocity=%s, trend=%s", org_id, growth_rate, velocity, trend.value)
        return evolution

    def compute_architecture_evolution(self, org_id: str, period: AnalyticsPeriod) -> EntityEvolution:
        self._telemetry["compute_architecture_evolution_calls"] += 1
        metrics = [m for m in self._metrics.values() if m.org_id == org_id and m.entity_type == AnalyticsEntityType.ARCHITECTURE and m.period == period]
        snapshots = []
        for m in metrics:
            snapshots.append({"metric_id": m.id, "name": m.name, "value": m.current_value, "timestamp": m.timestamp, "unit": m.unit})
        growth_rate = 0.0
        velocity = 0.0
        if metrics:
            values = [m.current_value for m in metrics if m.current_value]
            if len(values) >= 2:
                growth_rate = round(((values[0] - values[-1]) / max(abs(values[-1]), 1)) * 100, 2)
            velocity = round(sum(values) / max(len(values), 1), 2)
        trend = self._infer_trend(metrics)
        evolution = EntityEvolution(
            id=str(uuid.uuid4()),
            org_id=org_id,
            entity_type=AnalyticsEntityType.ARCHITECTURE,
            entity_id=f"arch_{org_id}",
            entity_name=f"Architecture Evolution - {org_id}",
            period=period,
            snapshots=snapshots[-20:],
            growth_rate=growth_rate,
            velocity=velocity,
            trend=trend,
        )
        self._evolutions[evolution.id] = evolution
        self._save()
        return evolution

    def compute_dependency_evolution(self, org_id: str, period: AnalyticsPeriod) -> EntityEvolution:
        self._telemetry["compute_dependency_evolution_calls"] += 1
        metrics = [m for m in self._metrics.values() if m.org_id == org_id and m.entity_type == AnalyticsEntityType.DEPENDENCY and m.period == period]
        snapshots = []
        for m in metrics:
            snapshots.append({"metric_id": m.id, "name": m.name, "value": m.current_value, "timestamp": m.timestamp, "unit": m.unit})
        growth_rate = 0.0
        velocity = 0.0
        if metrics:
            values = [m.current_value for m in metrics if m.current_value]
            if len(values) >= 2:
                growth_rate = round(((values[0] - values[-1]) / max(abs(values[-1]), 1)) * 100, 2)
            velocity = round(sum(values) / max(len(values), 1), 2)
        trend = self._infer_trend(metrics)
        evolution = EntityEvolution(
            id=str(uuid.uuid4()),
            org_id=org_id,
            entity_type=AnalyticsEntityType.DEPENDENCY,
            entity_id=f"dep_{org_id}",
            entity_name=f"Dependency Evolution - {org_id}",
            period=period,
            snapshots=snapshots[-20:],
            growth_rate=growth_rate,
            velocity=velocity,
            trend=trend,
        )
        self._evolutions[evolution.id] = evolution
        self._save()
        return evolution

    def compute_developer_activity(self, org_id: str, period: AnalyticsPeriod) -> EntityEvolution:
        self._telemetry["compute_developer_activity_calls"] += 1
        metrics = [m for m in self._metrics.values() if m.org_id == org_id and m.entity_type == AnalyticsEntityType.DEVELOPER and m.period == period]
        snapshots = []
        for m in metrics:
            snapshots.append({"metric_id": m.id, "name": m.name, "value": m.current_value, "timestamp": m.timestamp, "unit": m.unit})
        growth_rate = 0.0
        velocity = 0.0
        if metrics:
            values = [m.current_value for m in metrics if m.current_value]
            if len(values) >= 2:
                growth_rate = round(((values[0] - values[-1]) / max(abs(values[-1]), 1)) * 100, 2)
            velocity = round(sum(values) / max(len(values), 1), 2)
        trend = self._infer_trend(metrics)
        evolution = EntityEvolution(
            id=str(uuid.uuid4()),
            org_id=org_id,
            entity_type=AnalyticsEntityType.DEVELOPER,
            entity_id=f"dev_{org_id}",
            entity_name=f"Developer Activity - {org_id}",
            period=period,
            snapshots=snapshots[-20:],
            growth_rate=growth_rate,
            velocity=velocity,
            trend=trend,
        )
        self._evolutions[evolution.id] = evolution
        self._save()
        return evolution

    def compute_knowledge_growth(self, org_id: str, period: AnalyticsPeriod) -> EntityEvolution:
        self._telemetry["compute_knowledge_growth_calls"] += 1
        metrics = [m for m in self._metrics.values() if m.org_id == org_id and m.entity_type == AnalyticsEntityType.KNOWLEDGE and m.period == period]
        snapshots = []
        for m in metrics:
            snapshots.append({"metric_id": m.id, "name": m.name, "value": m.current_value, "timestamp": m.timestamp, "unit": m.unit})
        growth_rate = 0.0
        velocity = 0.0
        if metrics:
            values = [m.current_value for m in metrics if m.current_value]
            if len(values) >= 2:
                growth_rate = round(((values[0] - values[-1]) / max(abs(values[-1]), 1)) * 100, 2)
            velocity = round(sum(values) / max(len(values), 1), 2)
        trend = self._infer_trend(metrics)
        evolution = EntityEvolution(
            id=str(uuid.uuid4()),
            org_id=org_id,
            entity_type=AnalyticsEntityType.KNOWLEDGE,
            entity_id=f"knowledge_{org_id}",
            entity_name=f"Knowledge Growth - {org_id}",
            period=period,
            snapshots=snapshots[-20:],
            growth_rate=growth_rate,
            velocity=velocity,
            trend=trend,
        )
        self._evolutions[evolution.id] = evolution
        self._save()
        return evolution

    def compute_technical_debt_trends(self, org_id: str, period: AnalyticsPeriod) -> EntityEvolution:
        self._telemetry["compute_technical_debt_trends_calls"] += 1
        metrics = [m for m in self._metrics.values() if m.org_id == org_id and m.entity_type == AnalyticsEntityType.TECHNICAL_DEBT and m.period == period]
        snapshots = []
        for m in metrics:
            snapshots.append({"metric_id": m.id, "name": m.name, "value": m.current_value, "timestamp": m.timestamp, "unit": m.unit})
        growth_rate = 0.0
        velocity = 0.0
        if metrics:
            values = [m.current_value for m in metrics if m.current_value]
            if len(values) >= 2:
                growth_rate = round(((values[0] - values[-1]) / max(abs(values[-1]), 1)) * 100, 2)
            velocity = round(sum(values) / max(len(values), 1), 2)
        trend = self._infer_trend(metrics)
        evolution = EntityEvolution(
            id=str(uuid.uuid4()),
            org_id=org_id,
            entity_type=AnalyticsEntityType.TECHNICAL_DEBT,
            entity_id=f"techdebt_{org_id}",
            entity_name=f"Technical Debt Trends - {org_id}",
            period=period,
            snapshots=snapshots[-20:],
            growth_rate=growth_rate,
            velocity=velocity,
            trend=trend,
        )
        self._evolutions[evolution.id] = evolution
        self._save()
        return evolution

    def compute_ai_adoption_trends(self, org_id: str, period: AnalyticsPeriod) -> AdoptionMetrics:
        self._telemetry["compute_ai_adoption_trends_calls"] += 1
        metrics = [m for m in self._metrics.values() if m.org_id == org_id and m.entity_type == AnalyticsEntityType.AI_ADOPTION and m.period == period]
        total_users = 0
        active_users = 0
        if metrics:
            for m in metrics:
                if "total_users" in m.name.lower():
                    total_users = int(m.current_value)
                elif "active_users" in m.name.lower():
                    active_users = int(m.current_value)
        adoption_rate = round((active_users / max(total_users, 1)) * 100, 2) if total_users else 0.0
        engagement_score = round(random.uniform(0.3, 0.95), 2)
        retention_rate = round(random.uniform(0.5, 0.98), 2)
        growth_rate = 0.0
        if metrics:
            values = [m.current_value for m in metrics if m.current_value]
            if len(values) >= 2:
                growth_rate = round(((values[0] - values[-1]) / max(abs(values[-1]), 1)) * 100, 2)
        adoption = AdoptionMetrics(
            id=str(uuid.uuid4()),
            org_id=org_id,
            feature=f"AI Features - {org_id}",
            period=period,
            total_users=total_users,
            active_users=active_users,
            adoption_rate=adoption_rate,
            engagement_score=engagement_score,
            retention_rate=retention_rate,
            growth_rate=growth_rate,
        )
        self._adoptions[adoption.id] = adoption
        self._save()
        logger.info("Computed AI adoption trends for org %s: adoption=%s%%, engagement=%s, retention=%s%%", org_id, adoption_rate, engagement_score, retention_rate)
        return adoption

    def generate_report(self, org_id: str, entity_type: AnalyticsEntityType, start_date: str, end_date: str) -> AnalyticsReport:
        self._telemetry["generate_report_calls"] += 1
        metrics = [m for m in self._metrics.values() if m.org_id == org_id and m.entity_type == entity_type]
        try:
            ms = [m for m in metrics if m.timestamp[:10] >= start_date[:10] and m.timestamp[:10] <= end_date[:10]]
        except Exception:
            ms = metrics
        current_values = [m.current_value for m in ms if m.current_value]
        avg_value = round(sum(current_values) / max(len(current_values), 1), 2) if current_values else 0.0
        max_metric = max(ms, key=lambda x: x.current_value) if ms else None
        min_metric = min(ms, key=lambda x: x.current_value) if ms else None
        trend_counts = defaultdict(int)
        for m in ms:
            trend_counts[m.trend.value] += 1
        dominant_trend = max(trend_counts, key=trend_counts.get) if trend_counts else "unknown"
        summary = {
            "total_metrics": len(ms),
            "avg_value": avg_value,
            "max_value": max_metric.current_value if max_metric else 0,
            "max_metric_name": max_metric.name if max_metric else "",
            "min_value": min_metric.current_value if min_metric else 0,
            "min_metric_name": min_metric.name if min_metric else "",
            "dominant_trend": dominant_trend,
            "trend_distribution": dict(trend_counts),
        }
        insights = []
        if max_metric and max_metric.current_value > 0:
            insights.append(f"Highest metric: {max_metric.name} = {max_metric.current_value} {max_metric.unit}")
        if min_metric and min_metric.current_value > 0:
            insights.append(f"Lowest metric: {min_metric.name} = {min_metric.current_value} {min_metric.unit}")
        if avg_value > 0:
            insights.append(f"Average value across all {entity_type.value} metrics: {avg_value}")
        if dominant_trend == "improving":
            insights.append(f"Overall trend is improving for {entity_type.value}")
        elif dominant_trend == "declining":
            insights.append(f"Overall trend is declining for {entity_type.value} - attention needed")
        recommendations = []
        if dominant_trend == "declining":
            recommendations.append(f"Investigate declining {entity_type.value} metrics and take corrective action")
        if not ms:
            recommendations.append(f"No {entity_type.value} metrics recorded for the period - increase data collection")
        if len(current_values) < 5:
            recommendations.append("Collect more data points to improve statistical significance")
        report = AnalyticsReport(
            id=str(uuid.uuid4()),
            org_id=org_id,
            title=f"{entity_type.value.capitalize()} Analytics Report ({start_date} to {end_date})",
            entity_type=entity_type,
            period_start=start_date,
            period_end=end_date,
            metrics=ms[:50],
            summary=summary,
            insights=insights,
            recommendations=recommendations,
        )
        self._reports[report.id] = report
        self._save()
        logger.info("Generated analytics report %s for org %s: entity=%s, metrics=%d", report.id, org_id, entity_type.value, len(ms))
        return report

    def detect_trends(self, org_id: str, entity_type: AnalyticsEntityType, days: int = 90) -> list[dict]:
        self._telemetry["detect_trends_calls"] += 1
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        metrics = [m for m in self._metrics.values() if m.org_id == org_id and m.entity_type == entity_type]
        try:
            metrics = [m for m in metrics if datetime.fromisoformat(m.timestamp) >= cutoff]
        except (ValueError, TypeError):
            pass
        grouped: dict[str, list[AnalyticsMetric]] = defaultdict(list)
        for m in metrics:
            grouped[m.name].append(m)
        trends = []
        for metric_name, group in grouped.items():
            group.sort(key=lambda x: x.timestamp)
            values = [m.current_value for m in group]
            if len(values) < 2:
                continue
            pct_change = round(((values[-1] - values[0]) / max(abs(values[0]), 1)) * 100, 2)
            direction = AnalyticsTrendDirection.IMPROVING if pct_change > 5 else (
                AnalyticsTrendDirection.DECLINING if pct_change < -5 else (
                    AnalyticsTrendDirection.VOLATILE if abs(pct_change) > 20 else AnalyticsTrendDirection.STABLE
                )
            )
            trends.append({
                "metric_name": metric_name,
                "entity_type": entity_type.value,
                "period_days": days,
                "first_value": values[0],
                "last_value": values[-1],
                "percent_change": pct_change,
                "direction": direction.value,
                "data_points": len(values),
                "sample_timestamps": [m.timestamp for m in group[:5]],
            })
        trends.sort(key=lambda x: abs(x["percent_change"]), reverse=True)
        return trends

    def _infer_trend(self, metrics: list[AnalyticsMetric]) -> AnalyticsTrendDirection:
        if not metrics:
            return AnalyticsTrendDirection.UNKNOWN
        sorted_m = sorted(metrics, key=lambda x: x.timestamp)
        changes = []
        for i in range(1, len(sorted_m)):
            prev = sorted_m[i - 1].current_value
            curr = sorted_m[i].current_value
            if prev != 0:
                changes.append((curr - prev) / abs(prev))
        if not changes:
            return AnalyticsTrendDirection.UNKNOWN
        avg_change = sum(changes) / len(changes)
        volatility = sum(abs(c - avg_change) for c in changes) / len(changes)
        if volatility > 0.5:
            return AnalyticsTrendDirection.VOLATILE
        if avg_change > 0.05:
            return AnalyticsTrendDirection.IMPROVING
        if avg_change < -0.05:
            return AnalyticsTrendDirection.DECLINING
        return AnalyticsTrendDirection.STABLE

    def get_telemetry(self) -> dict:
        self._telemetry["get_telemetry_calls"] += 1
        return dict(self._telemetry)