import json
import uuid
import hashlib
import time
import math
import os
import logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class UsageMetric(Enum):
    DAILY_ACTIVE_USERS = "daily_active_users"
    MONTHLY_ACTIVE_USERS = "monthly_active_users"
    REPOSITORIES_INDEXED = "repositories_indexed"
    AI_REQUESTS = "ai_requests"
    PROMPT_COUNT = "prompt_count"
    AGENT_EXECUTIONS = "agent_executions"
    SEARCH_REQUESTS = "search_requests"
    DEPLOYMENTS = "deployments"
    SECURITY_SCANS = "security_scans"
    DOCS_GENERATED = "docs_generated"
    TESTS_GENERATED = "tests_generated"
    API_CALLS = "api_calls"
    STORAGE_USED_BYTES = "storage_used_bytes"
    TOKENS_CONSUMED = "tokens_consumed"
    GPU_SECONDS = "gpu_seconds"
    CPU_SECONDS = "cpu_seconds"
    BANDWIDTH_BYTES = "bandwidth_bytes"


class AnalyticsPeriod(Enum):
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class TrendDirection(Enum):
    UP = "up"
    DOWN = "down"
    STABLE = "stable"
    VOLATILE = "volatile"
    UNKNOWN = "unknown"


class SegmentBy(Enum):
    NONE = "none"
    ORG = "org"
    WORKSPACE = "workspace"
    USER = "user"
    TEAM = "team"
    REPOSITORY = "repository"
    MODEL = "model"
    PROVIDER = "provider"
    REGION = "region"


@dataclass
class UsageDataPoint:
    id: str
    org_id: str
    workspace_id: str
    metric: UsageMetric
    value: float
    unit: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = ""
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["metric"] = self.metric.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "UsageDataPoint":
        data = data.copy()
        data["metric"] = UsageMetric(data.get("metric", "daily_active_users"))
        return cls(**data)


@dataclass
class AnalyticsSnapshot:
    id: str
    org_id: str
    timestamp: str
    period: AnalyticsPeriod
    metrics: dict[str, float] = field(default_factory=dict)
    changes: dict[str, float] = field(default_factory=dict)
    top_orgs: list[dict] = field(default_factory=list)
    top_workspaces: list[dict] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["period"] = self.period.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AnalyticsSnapshot":
        data = data.copy()
        data["period"] = AnalyticsPeriod(data.get("period", "daily"))
        return cls(**data)


@dataclass
class TrendAnalysis:
    id: str
    org_id: str
    metric: UsageMetric
    period: AnalyticsPeriod
    direction: TrendDirection = TrendDirection.UNKNOWN
    current_value: float = 0.0
    previous_value: float = 0.0
    percent_change: float = 0.0
    avg_value: float = 0.0
    min_value: float = 0.0
    max_value: float = 0.0
    volatility: float = 0.0
    forecast_next: float = 0.0
    data_points: list[dict] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["metric"] = self.metric.value
        d["period"] = self.period.value
        d["direction"] = self.direction.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "TrendAnalysis":
        data = data.copy()
        data["metric"] = UsageMetric(data.get("metric", "daily_active_users"))
        data["period"] = AnalyticsPeriod(data.get("period", "daily"))
        data["direction"] = TrendDirection(data.get("direction", "unknown"))
        return cls(**data)


@dataclass
class UsageReport:
    id: str
    org_id: str
    start_date: str
    end_date: str
    total_metrics: dict = field(default_factory=dict)
    trends: list[dict] = field(default_factory=list)
    top_users_by_metric: dict = field(default_factory=dict)
    adoption_rate: dict = field(default_factory=dict)
    growth_rate: float = 0.0
    peak_usage_times: list[dict] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "UsageReport":
        return cls(**data)


@dataclass
class UserActivitySummary:
    id: str
    user_id: str
    org_id: str
    workspace_id: str
    total_requests: int = 0
    unique_actions: int = 0
    active_days: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    last_active: str = ""
    first_active: str = ""
    avg_daily_usage: float = 0.0
    engagement_score: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "UserActivitySummary":
        return cls(**data)


class UsageAnalytics:
    def __init__(self, storage_dir: str = "usage_analytics_data"):
        self.storage_dir = storage_dir
        self._data_points: dict[str, UsageDataPoint] = {}
        self._snapshots: dict[str, AnalyticsSnapshot] = {}
        self._trends: dict[str, TrendAnalysis] = {}
        self._reports: dict[str, UsageReport] = {}
        self._user_summaries: dict[str, UserActivitySummary] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _data_points_path(self) -> str:
        return os.path.join(self.storage_dir, "data_points.json")

    def _snapshots_path(self) -> str:
        return os.path.join(self.storage_dir, "snapshots.json")

    def _trends_path(self) -> str:
        return os.path.join(self.storage_dir, "trends.json")

    def _reports_path(self) -> str:
        return os.path.join(self.storage_dir, "reports.json")

    def _user_summaries_path(self) -> str:
        return os.path.join(self.storage_dir, "user_summaries.json")

    def _save(self) -> None:
        try:
            dp_data = {pid: p.to_dict() for pid, p in self._data_points.items()}
            with open(self._data_points_path(), "w", encoding="utf-8") as f:
                json.dump(dp_data, f, indent=2, default=str)

            snap_data = {sid: s.to_dict() for sid, s in self._snapshots.items()}
            with open(self._snapshots_path(), "w", encoding="utf-8") as f:
                json.dump(snap_data, f, indent=2, default=str)

            trend_data = {tid: t.to_dict() for tid, t in self._trends.items()}
            with open(self._trends_path(), "w", encoding="utf-8") as f:
                json.dump(trend_data, f, indent=2, default=str)

            report_data = {rid: r.to_dict() for rid, r in self._reports.items()}
            with open(self._reports_path(), "w", encoding="utf-8") as f:
                json.dump(report_data, f, indent=2, default=str)

            us_data = {uid: u.to_dict() for uid, u in self._user_summaries.items()}
            with open(self._user_summaries_path(), "w", encoding="utf-8") as f:
                json.dump(us_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save usage analytics data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._data_points_path()):
                with open(self._data_points_path(), "r", encoding="utf-8") as f:
                    dp_data = json.load(f)
                for pid, data in dp_data.items():
                    try:
                        self._data_points[pid] = UsageDataPoint.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed data point %s: %s", pid, e)

            if os.path.exists(self._snapshots_path()):
                with open(self._snapshots_path(), "r", encoding="utf-8") as f:
                    snap_data = json.load(f)
                for sid, data in snap_data.items():
                    try:
                        self._snapshots[sid] = AnalyticsSnapshot.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed snapshot %s: %s", sid, e)

            if os.path.exists(self._trends_path()):
                with open(self._trends_path(), "r", encoding="utf-8") as f:
                    trend_data = json.load(f)
                for tid, data in trend_data.items():
                    try:
                        self._trends[tid] = TrendAnalysis.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed trend %s: %s", tid, e)

            if os.path.exists(self._reports_path()):
                with open(self._reports_path(), "r", encoding="utf-8") as f:
                    report_data = json.load(f)
                for rid, data in report_data.items():
                    try:
                        self._reports[rid] = UsageReport.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed report %s: %s", rid, e)

            if os.path.exists(self._user_summaries_path()):
                with open(self._user_summaries_path(), "r", encoding="utf-8") as f:
                    us_data = json.load(f)
                for uid, data in us_data.items():
                    try:
                        self._user_summaries[uid] = UserActivitySummary.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed user summary %s: %s", uid, e)
        except Exception as e:
            logger.error("Failed to load usage analytics data: %s", e, exc_info=True)

    def record_data_point(self, point: UsageDataPoint) -> UsageDataPoint:
        self._telemetry["record_data_point_calls"] += 1
        if not point.id:
            point.id = str(uuid.uuid4())
        if not point.timestamp:
            point.timestamp = datetime.now(timezone.utc).isoformat()
        self._data_points[point.id] = point
        self._save()
        logger.info("Recorded usage data point %s: %s=%.4f for org %s", point.id, point.metric.value, point.value, point.org_id)
        return point

    def get_data_points(self, org_id: str, metric: UsageMetric, start_date: str, end_date: str) -> list[UsageDataPoint]:
        self._telemetry["get_data_points_calls"] += 1
        results = []
        for point in self._data_points.values():
            if point.org_id == org_id and point.metric == metric and start_date <= point.timestamp[:10] <= end_date:
                results.append(point)
        results.sort(key=lambda p: p.timestamp)
        return results

    def compute_aggregate(self, org_id: str, metric: UsageMetric, period: AnalyticsPeriod) -> dict:
        self._telemetry["compute_aggregate_calls"] += 1
        now = datetime.now(timezone.utc)
        period_days_map = {
            AnalyticsPeriod.HOURLY: 1 / 24,
            AnalyticsPeriod.DAILY: 1,
            AnalyticsPeriod.WEEKLY: 7,
            AnalyticsPeriod.MONTHLY: 30,
            AnalyticsPeriod.QUARTERLY: 91,
            AnalyticsPeriod.YEARLY: 365,
        }
        period_days = period_days_map.get(period, 1)
        cutoff = now - timedelta(days=period_days)

        values = []
        for point in self._data_points.values():
            if point.org_id == org_id and point.metric == metric:
                try:
                    if datetime.fromisoformat(point.timestamp) >= cutoff:
                        values.append(point.value)
                except Exception:
                    continue

        if not values:
            return {
                "org_id": org_id,
                "metric": metric.value,
                "period": period.value,
                "sum": 0.0,
                "avg": 0.0,
                "min": 0.0,
                "max": 0.0,
                "count": 0,
            }

        return {
            "org_id": org_id,
            "metric": metric.value,
            "period": period.value,
            "sum": round(sum(values), 4),
            "avg": round(sum(values) / len(values), 4),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
            "count": len(values),
        }

    def get_current_snapshot(self, org_id: str) -> AnalyticsSnapshot:
        self._telemetry["get_current_snapshot_calls"] += 1
        now = datetime.now(timezone.utc)
        period = AnalyticsPeriod.DAILY
        cutoff = now - timedelta(days=1)

        def _parse_dt(s: str) -> datetime:
            try:
                dt = datetime.fromisoformat(s)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception:
                return now

        org_points = [p for p in self._data_points.values() if p.org_id == org_id]
        period_points = [p for p in org_points if _parse_dt(p.timestamp) >= cutoff]

        metrics: dict[str, float] = defaultdict(float)
        changes: dict[str, float] = {}
        for p in period_points:
            metrics[p.metric.value] += p.value

        # Compare with previous period for changes
        prev_cutoff = cutoff - timedelta(days=1)
        prev_period = [p for p in org_points if prev_cutoff <= _parse_dt(p.timestamp) < cutoff]
        prev_metrics: dict[str, float] = defaultdict(float)
        for p in prev_period:
            prev_metrics[p.metric.value] += p.value

        for metric_key in set(list(metrics.keys()) + list(prev_metrics.keys())):
            cur = metrics.get(metric_key, 0.0)
            prv = prev_metrics.get(metric_key, 0.0)
            if prv > 0:
                changes[metric_key] = round((cur - prv) / prv * 100, 2)
            else:
                changes[metric_key] = round(cur * 100, 2) if cur > 0 else 0.0

        # Aggregate by org and workspace across entire data
        org_totals: dict[str, float] = defaultdict(float)
        ws_totals: dict[str, float] = defaultdict(float)
        for p in org_points:
            org_totals[p.org_id] += p.value
            ws_totals[p.workspace_id] += p.value

        sorted_orgs = sorted(org_totals.items(), key=lambda x: x[1], reverse=True)[:10]
        sorted_ws = sorted(ws_totals.items(), key=lambda x: x[1], reverse=True)[:10]

        top_orgs = [{"org_id": oid, "total": round(val, 4)} for oid, val in sorted_orgs]
        top_workspaces = [{"workspace_id": wid, "total": round(val, 4)} for wid, val in sorted_ws]

        snapshot = AnalyticsSnapshot(
            id=str(uuid.uuid4()),
            org_id=org_id,
            timestamp=now.isoformat(),
            period=period,
            metrics={k: round(v, 4) for k, v in metrics.items()},
            changes=changes,
            top_orgs=top_orgs,
            top_workspaces=top_workspaces,
        )
        self._snapshots[snapshot.id] = snapshot
        self._save()
        return snapshot

    def analyze_trend(self, org_id: str, metric: UsageMetric, period: AnalyticsPeriod, days: int = 90) -> TrendAnalysis:
        self._telemetry["analyze_trend_calls"] += 1
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=days)

        points = []
        for p in self._data_points.values():
            if p.org_id == org_id and p.metric == metric:
                try:
                    dt = datetime.fromisoformat(p.timestamp)
                    if dt >= cutoff:
                        points.append(p)
                except Exception:
                    continue

        if not points:
            return TrendAnalysis(
                id=str(uuid.uuid4()),
                org_id=org_id,
                metric=metric,
                period=period,
                direction=TrendDirection.UNKNOWN,
            )

        # Sort by timestamp and compute interval aggregates
        points.sort(key=lambda p: p.timestamp)

        # Group by period bucket
        bucket_format = "%Y-%m-%d"
        if period == AnalyticsPeriod.HOURLY:
            bucket_format = "%Y-%m-%dT%H"
        elif period == AnalyticsPeriod.WEEKLY:
            bucket_format = "%Y-W%W"
        elif period == AnalyticsPeriod.MONTHLY:
            bucket_format = "%Y-%m"
        elif period == AnalyticsPeriod.QUARTERLY:
            bucket_format = "%Y-Q%q"
        elif period == AnalyticsPeriod.YEARLY:
            bucket_format = "%Y"

        bucketed: dict[str, float] = defaultdict(float)
        bucket_times: dict[str, str] = {}
        for p in points:
            dt = datetime.fromisoformat(p.timestamp)
            key = dt.strftime(bucket_format)
            bucketed[key] += p.value
            if key not in bucket_times:
                bucket_times[key] = p.timestamp

        sorted_buckets = sorted(bucketed.items())
        values = [v for _, v in sorted_buckets]

        if not values:
            return TrendAnalysis(
                id=str(uuid.uuid4()),
                org_id=org_id,
                metric=metric,
                period=period,
                direction=TrendDirection.UNKNOWN,
            )

        current_value = values[-1]
        avg_value = sum(values) / len(values)
        min_value = min(values)
        max_value = max(values)

        # Determine direction by comparing first half vs second half
        mid = len(values) // 2
        first_half = sum(values[:mid]) / max(mid, 1)
        second_half = sum(values[mid:]) / max(len(values[mid:]), 1)

        direction = TrendDirection.STABLE
        percent_change = 0.0
        if first_half > 0:
            percent_change = round((second_half - first_half) / first_half * 100, 2)
            if percent_change > 10:
                direction = TrendDirection.UP
            elif percent_change < -10:
                direction = TrendDirection.DOWN

        # Volatility: coefficient of variation
        if avg_value > 0:
            variance = sum((v - avg_value) ** 2 for v in values) / len(values)
            std_dev = math.sqrt(variance)
            volatility = round(std_dev / avg_value, 4)
            if volatility > 0.5:
                direction = TrendDirection.VOLATILE
        else:
            volatility = 0.0

        # Simple linear forecast: extend last slope
        previous_value = values[-2] if len(values) >= 2 else 0.0
        if len(values) >= 2:
            x_vals = list(range(len(values)))
            n = len(x_vals)
            sum_x = sum(x_vals)
            sum_y = sum(values)
            sum_xy = sum(x * y for x, y in zip(x_vals, values))
            sum_xx = sum(x * x for x in x_vals)
            denom = n * sum_xx - sum_x * sum_x
            if denom != 0:
                slope = (n * sum_xy - sum_x * sum_y) / denom
            else:
                slope = 0.0
            forecast_next = round(values[-1] + slope, 4)
        else:
            forecast_next = current_value

        data_points = [{"bucket": b, "value": round(v, 4)} for b, v in sorted_buckets]

        trend = TrendAnalysis(
            id=str(uuid.uuid4()),
            org_id=org_id,
            metric=metric,
            period=period,
            direction=direction,
            current_value=round(current_value, 4),
            previous_value=round(previous_value, 4),
            percent_change=percent_change,
            avg_value=round(avg_value, 4),
            min_value=round(min_value, 4),
            max_value=round(max_value, 4),
            volatility=volatility,
            forecast_next=round(forecast_next, 4),
            data_points=data_points,
        )
        self._trends[trend.id] = trend
        self._save()
        return trend

    def get_daily_active_users(self, org_id: str, days: int = 30) -> list[dict]:
        self._telemetry["get_daily_active_users_calls"] += 1
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=days)

        daily_users: dict[str, set[str]] = defaultdict(set)
        for p in self._data_points.values():
            if p.org_id == org_id and p.metric == UsageMetric.DAILY_ACTIVE_USERS:
                try:
                    dt = datetime.fromisoformat(p.timestamp)
                    if dt >= start:
                        day_key = dt.strftime("%Y-%m-%d")
                        # Use source as surrogate user identifier
                        daily_users[day_key].update(p.tags)
                except Exception:
                    continue

        # Also infer from data points with workspace_id as user presence
        for p in self._data_points.values():
            if p.org_id == org_id:
                try:
                    dt = datetime.fromisoformat(p.timestamp)
                    if dt >= start:
                        day_key = dt.strftime("%Y-%m-%d")
                        daily_users[day_key].add(p.workspace_id)
                except Exception:
                    continue

        results = []
        for i in range(days):
            day = (now - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
            count = len(daily_users.get(day, set()))
            results.append({"date": day, "active_users": count})
        return results

    def get_monthly_active_users(self, org_id: str, months: int = 6) -> list[dict]:
        self._telemetry["get_monthly_active_users_calls"] += 1
        now = datetime.now(timezone.utc)
        monthly_users: dict[str, set[str]] = defaultdict(set)

        for p in self._data_points.values():
            if p.org_id == org_id and p.metric == UsageMetric.MONTHLY_ACTIVE_USERS:
                try:
                    dt = datetime.fromisoformat(p.timestamp)
                    month_key = dt.strftime("%Y-%m")
                    monthly_users[month_key].update(p.tags)
                except Exception:
                    continue

        # Infer from all data points
        for p in self._data_points.values():
            if p.org_id == org_id:
                try:
                    dt = datetime.fromisoformat(p.timestamp)
                    month_key = dt.strftime("%Y-%m")
                    monthly_users[month_key].add(p.workspace_id)
                except Exception:
                    continue

        results = []
        for i in range(months - 1, -1, -1):
            month_dt = datetime(now.year, now.month, 1) - timedelta(days=30 * i)
            month_key = month_dt.strftime("%Y-%m")
            count = len(monthly_users.get(month_key, set()))
            results.append({"month": month_key, "active_users": count})
        return results

    def get_adoption_rate(self, org_id: str) -> dict:
        self._telemetry["get_adoption_rate_calls"] += 1
        all_metrics = list(UsageMetric)
        total_org_points = [p for p in self._data_points.values() if p.org_id == org_id]

        # Find which orgs exist
        org_ids = set(p.org_id for p in self._data_points.values())

        adoption: dict[str, float] = {}
        for metric in all_metrics:
            metric_orgs = set(p.org_id for p in self._data_points.values() if p.metric == metric)
            if org_ids:
                adoption[metric.value] = round(len(metric_orgs) / len(org_ids) * 100, 2)
            else:
                adoption[metric.value] = 0.0

        # Also compute for the requested org specifically
        org_metric_counts: dict[str, int] = defaultdict(int)
        for p in total_org_points:
            org_metric_counts[p.metric.value] += 1

        total_possible = len(all_metrics)
        features_used = len(org_metric_counts)
        org_adoption_rate = round(features_used / total_possible * 100, 2) if total_possible > 0 else 0.0

        return {
            "overall_adoption_rate": org_adoption_rate,
            "by_metric": adoption,
            "features_used": features_used,
            "total_features": total_possible,
            "org_id": org_id,
        }

    def get_growth_rate(self, org_id: str, metric: UsageMetric, period_days: int = 30) -> float:
        self._telemetry["get_growth_rate_calls"] += 1
        now = datetime.now(timezone.utc)
        current_start = now - timedelta(days=period_days)
        prev_start = current_start - timedelta(days=period_days)

        current_total = 0.0
        prev_total = 0.0

        for p in self._data_points.values():
            if p.org_id == org_id and p.metric == metric:
                try:
                    dt = datetime.fromisoformat(p.timestamp)
                    if prev_start <= dt < current_start:
                        prev_total += p.value
                    elif dt >= current_start:
                        current_total += p.value
                except Exception:
                    continue

        if prev_total > 0:
            return round((current_total - prev_total) / prev_total * 100, 2)
        return round(current_total * 100, 2) if current_total > 0 else 0.0

    def get_peak_usage_times(self, org_id: str, metric: UsageMetric, days: int = 30) -> list[dict]:
        self._telemetry["get_peak_usage_times_calls"] += 1
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=days)

        hourly_totals: dict[int, float] = defaultdict(float)
        hourly_counts: dict[int, int] = defaultdict(int)

        for p in self._data_points.values():
            if p.org_id == org_id and p.metric == metric:
                try:
                    dt = datetime.fromisoformat(p.timestamp)
                    if dt >= cutoff:
                        hour = dt.hour
                        hourly_totals[hour] += p.value
                        hourly_counts[hour] += 1
                except Exception:
                    continue

        if not hourly_totals:
            return []

        results = []
        for hour in sorted(hourly_totals.keys()):
            avg = hourly_totals[hour] / hourly_counts[hour] if hourly_counts[hour] > 0 else 0.0
            results.append({
                "hour": hour,
                "total": round(hourly_totals[hour], 4),
                "count": hourly_counts[hour],
                "average": round(avg, 4),
            })

        results.sort(key=lambda r: r["total"], reverse=True)
        return results

    def get_user_activity_summary(self, user_id: str) -> UserActivitySummary:
        self._telemetry["get_user_activity_summary_calls"] += 1

        # Check cache first
        if user_id in self._user_summaries:
            return self._user_summaries[user_id]

        user_points = [p for p in self._data_points.values() if user_id in p.tags]
        if not user_points:
            user_points = [p for p in self._data_points.values() if p.source == user_id]

        if not user_points:
            summary = UserActivitySummary(
                id=str(uuid.uuid4()),
                user_id=user_id,
                org_id="",
                workspace_id="",
            )
            self._user_summaries[summary.id] = summary
            self._save()
            return summary

        org_id = user_points[0].org_id
        workspace_id = user_points[0].workspace_id
        total_requests = len(user_points)
        total_tokens = 0
        total_cost = 0.0
        active_dates: set[str] = set()
        unique_actions: set[str] = set()
        timestamps: list[str] = []

        for p in user_points:
            unique_actions.add(p.metric.value)
            active_dates.add(p.timestamp[:10])
            timestamps.append(p.timestamp)
            if p.metric == UsageMetric.TOKENS_CONSUMED:
                total_tokens += int(p.value)
            if p.metric == UsageMetric.AI_REQUESTS:
                total_cost += p.value * 0.0001

        timestamps.sort()
        first_active = timestamps[0] if timestamps else ""
        last_active = timestamps[-1] if timestamps else ""
        active_days_count = len(active_dates)

        days_span = 0
        if first_active and last_active:
            try:
                days_span = max(1, (datetime.fromisoformat(last_active) - datetime.fromisoformat(first_active)).days)
            except Exception:
                days_span = 1

        avg_daily_usage = round(total_requests / max(days_span, 1), 2)

        # Engagement score: weighted combination of metrics
        frequency_score = min(total_requests / max(days_span, 1) * 10, 50)
        breadth_score = min(len(unique_actions) * 10, 30)
        recency_score = 0
        if last_active:
            try:
                days_since = (datetime.now(timezone.utc) - datetime.fromisoformat(last_active)).days
                recency_score = max(0, 20 - days_since)
            except Exception:
                recency_score = 10
        engagement_score = round(frequency_score + breadth_score + recency_score, 2)

        summary = UserActivitySummary(
            id=str(uuid.uuid4()),
            user_id=user_id,
            org_id=org_id,
            workspace_id=workspace_id,
            total_requests=total_requests,
            unique_actions=len(unique_actions),
            active_days=active_days_count,
            total_tokens=total_tokens,
            total_cost=round(total_cost, 4),
            last_active=last_active,
            first_active=first_active,
            avg_daily_usage=avg_daily_usage,
            engagement_score=engagement_score,
        )
        self._user_summaries[summary.id] = summary
        self._save()
        return summary

    def generate_usage_report(self, org_id: str, start_date: str, end_date: str) -> UsageReport:
        self._telemetry["generate_usage_report_calls"] += 1
        filtered = [p for p in self._data_points.values() if p.org_id == org_id and start_date <= p.timestamp[:10] <= end_date]

        total_metrics: dict[str, float] = defaultdict(float)
        daily_totals: dict[str, float] = defaultdict(float)
        user_metric_totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        hour_totals: dict[int, float] = defaultdict(float)

        for p in filtered:
            total_metrics[p.metric.value] += p.value
            daily_totals[p.timestamp[:10]] += p.value
            for tag in p.tags:
                user_metric_totals[tag][p.metric.value] += p.value
            try:
                dt = datetime.fromisoformat(p.timestamp)
                hour_totals[dt.hour] += p.value
            except Exception:
                pass

        trends = [{"date": day, "total": round(val, 4)} for day, val in sorted(daily_totals.items())]

        top_users_by_metric: dict[str, list[dict]] = {}
        for metric_key in set(m.value for m in UsageMetric):
            user_scores = []
            for uid, mdict in user_metric_totals.items():
                if metric_key in mdict:
                    user_scores.append({"user_id": uid, "total": round(mdict[metric_key], 4)})
            user_scores.sort(key=lambda x: x["total"], reverse=True)
            if user_scores:
                top_users_by_metric[metric_key] = user_scores[:10]

        adoption = self.get_adoption_rate(org_id)
        growth = self.get_growth_rate(org_id, UsageMetric.AI_REQUESTS, 30)

        sorted_hours = sorted(hour_totals.items(), key=lambda x: x[1], reverse=True)
        peak_usage_times = [{"hour": h, "total": round(v, 4)} for h, v in sorted_hours[:5]]

        recommendations = []
        if total_metrics.get("tokens_consumed", 0) > 1_000_000:
            recommendations.append("Token consumption is high. Consider implementing prompt optimization strategies.")
        if total_metrics.get("gpu_seconds", 0) > 3600:
            recommendations.append("High GPU usage detected. Evaluate if batch processing or spot instances can reduce costs.")
        if total_metrics.get("storage_used_bytes", 0) > 10_737_418_240:
            recommendations.append("Storage usage exceeds 10GB. Implement data lifecycle policies and archive stale data.")
        if total_metrics.get("api_calls", 0) > 100_000:
            recommendations.append("API call volume is high. Consider implementing caching to reduce redundant requests.")
        if adoption.get("overall_adoption_rate", 100) < 50:
            recommendations.append("Feature adoption rate is below 50%. Consider user onboarding initiatives to increase engagement.")

        report = UsageReport(
            id=str(uuid.uuid4()),
            org_id=org_id,
            start_date=start_date,
            end_date=end_date,
            total_metrics={k: round(v, 4) for k, v in total_metrics.items()},
            trends=trends,
            top_users_by_metric=top_users_by_metric,
            adoption_rate=adoption,
            growth_rate=growth,
            peak_usage_times=peak_usage_times,
            recommendations=recommendations,
        )
        self._reports[report.id] = report
        self._save()
        return report

    def get_top_users_by_metric(self, org_id: str, metric: UsageMetric, limit: int = 10) -> list[dict]:
        self._telemetry["get_top_users_by_metric_calls"] += 1
        user_totals: dict[str, float] = defaultdict(float)

        for p in self._data_points.values():
            if p.org_id == org_id and p.metric == metric:
                # Use tags as user identifiers
                for tag in p.tags:
                    user_totals[tag] += p.value
                if not p.tags and p.source:
                    user_totals[p.source] += p.value

        sorted_users = sorted(user_totals.items(), key=lambda x: x[1], reverse=True)[:limit]
        return [{"user_id": uid, "total": round(val, 4)} for uid, val in sorted_users]

    def compare_periods(self, org_id: str, metric: UsageMetric,
                        period_a_start: str, period_a_end: str,
                        period_b_start: str, period_b_end: str) -> dict:
        self._telemetry["compare_periods_calls"] += 1

        def aggregate_period(start: str, end: str) -> dict:
            points = []
            for p in self._data_points.values():
                if p.org_id == org_id and p.metric == metric and start <= p.timestamp[:10] <= end:
                    points.append(p)
            values = [p.value for p in points]
            if not values:
                return {"sum": 0, "avg": 0, "min": 0, "max": 0, "count": 0}
            return {
                "sum": round(sum(values), 4),
                "avg": round(sum(values) / len(values), 4),
                "min": round(min(values), 4),
                "max": round(max(values), 4),
                "count": len(values),
            }

        period_a = aggregate_period(period_a_start, period_a_end)
        period_b = aggregate_period(period_b_start, period_b_end)

        change = 0.0
        if period_a["sum"] > 0:
            change = round((period_b["sum"] - period_a["sum"]) / period_a["sum"] * 100, 2)

        return {
            "org_id": org_id,
            "metric": metric.value,
            "period_a": {"start": period_a_start, "end": period_a_end, **period_a},
            "period_b": {"start": period_b_start, "end": period_b_end, **period_b},
            "change_percent": change,
            "direction": TrendDirection.UP.value if change > 0 else TrendDirection.DOWN.value if change < 0 else TrendDirection.STABLE.value,
        }

    def get_telemetry(self) -> dict:
        self._telemetry["get_telemetry_calls"] += 1
        return dict(self._telemetry)
