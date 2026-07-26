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


class ROICategory(Enum):
    DEVELOPER_TIME_SAVED = "developer_time_saved"
    AI_PRODUCTIVITY = "ai_productivity"
    REVIEW_TIME_SAVED = "review_time_saved"
    TESTING_TIME_SAVED = "testing_time_saved"
    DOCUMENTATION_TIME_SAVED = "documentation_time_saved"
    DEPLOYMENT_TIME_SAVED = "deployment_time_saved"
    BUG_REDUCTION = "bug_reduction"
    SECURITY_IMPROVEMENT = "security_improvement"
    ENGINEERING_VELOCITY = "engineering_velocity"
    ONBOARDING_TIME = "onboarding_time"
    CODE_QUALITY = "code_quality"
    INFRASTRUCTURE_OPTIMIZATION = "infrastructure_optimization"


class ROIStatus(Enum):
    TRACKING = "tracking"
    ON_TARGET = "on_target"
    BELOW_TARGET = "below_target"
    EXCEEDING = "exceeding"
    NOT_MEASURED = "not_measured"


class BenefitType(Enum):
    TIME_SAVINGS = "time_savings"
    COST_REDUCTION = "cost_reduction"
    REVENUE_INCREASE = "revenue_increase"
    QUALITY_IMPROVEMENT = "quality_improvement"
    RISK_REDUCTION = "risk_reduction"
    VELOCITY_INCREASE = "velocity_increase"


@dataclass
class ROIMetric:
    id: str
    org_id: str
    workspace_id: str
    category: ROICategory
    name: str
    description: str
    unit: str
    target_value: float = 0.0
    current_value: float = 0.0
    baseline_value: float = 0.0
    measurement_interval: str = "monthly"
    status: ROIStatus = ROIStatus.TRACKING
    last_measured: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["category"] = self.category.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ROIMetric":
        data = data.copy()
        data["category"] = ROICategory(data.get("category", "developer_time_saved"))
        data["status"] = ROIStatus(data.get("status", "tracking"))
        return cls(**data)


@dataclass
class TimeSavingsMetric:
    id: str
    org_id: str
    category: ROICategory
    task_name: str
    manual_hours: float = 0.0
    automated_hours: float = 0.0
    hours_saved: float = 0.0
    hourly_rate: float = 0.0
    total_savings: float = 0.0
    developers_affected: int = 0
    frequency_per_week: float = 1.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        if self.hours_saved == 0 and self.manual_hours > 0:
            self.hours_saved = self.manual_hours - self.automated_hours
        if self.total_savings == 0 and self.hours_saved > 0:
            self.total_savings = round(self.hours_saved * self.hourly_rate * self.frequency_per_week * 4.33, 2)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["category"] = self.category.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "TimeSavingsMetric":
        data = data.copy()
        data["category"] = ROICategory(data.get("category", "developer_time_saved"))
        return cls(**data)


@dataclass
class QualityMetric:
    id: str
    org_id: str
    category: ROICategory
    metric_name: str
    before_value: float = 0.0
    after_value: float = 0.0
    improvement_percent: float = 0.0
    impact_area: str = ""
    measurement_method: str = ""
    measured_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        if self.improvement_percent == 0 and self.before_value > 0:
            self.improvement_percent = round(
                ((self.after_value - self.before_value) / self.before_value) * 100, 2
            )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["category"] = self.category.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "QualityMetric":
        data = data.copy()
        data["category"] = ROICategory(data.get("category", "code_quality"))
        return cls(**data)


@dataclass
class ROICalculation:
    id: str
    org_id: str
    period_start: str
    period_end: str
    total_investment: float = 0.0
    total_benefits: float = 0.0
    net_roi: float = 0.0
    roi_percent: float = 0.0
    payback_period_days: int = 0
    categories: dict[ROICategory, float] = field(default_factory=dict)
    benefit_by_type: dict[BenefitType, float] = field(default_factory=dict)
    assumptions: list = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["categories"] = {k.value if isinstance(k, ROICategory) else k: v for k, v in self.categories.items()}
        d["benefit_by_type"] = {k.value if isinstance(k, BenefitType) else k: v for k, v in self.benefit_by_type.items()}
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ROICalculation":
        data = data.copy()
        if "categories" in data:
            data["categories"] = {
                ROICategory(k) if isinstance(k, str) else k: v for k, v in data["categories"].items()
            }
        if "benefit_by_type" in data:
            data["benefit_by_type"] = {
                BenefitType(k) if isinstance(k, str) else k: v for k, v in data["benefit_by_type"].items()
            }
        return cls(**data)


@dataclass
class ProductivityReport:
    id: str
    org_id: str
    period_start: str
    period_end: str
    total_hours_saved: float = 0.0
    total_cost_saved: float = 0.0
    velocity_improvement: float = 0.0
    quality_improvement: float = 0.0
    developer_satisfaction: float = 0.0
    top_improvements: list = field(default_factory=list)
    recommendations: list = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ProductivityReport":
        return cls(**data)


class ROIEngine:
    def __init__(self, storage_dir: str = "roi_engine_data"):
        self.storage_dir = storage_dir
        self._roi_metrics: dict[str, ROIMetric] = {}
        self._time_savings: dict[str, TimeSavingsMetric] = {}
        self._quality_metrics: dict[str, QualityMetric] = {}
        self._roi_calculations: dict[str, ROICalculation] = {}
        self._productivity_reports: dict[str, ProductivityReport] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _roi_metrics_path(self) -> str:
        return os.path.join(self.storage_dir, "roi_metrics.json")

    def _time_savings_path(self) -> str:
        return os.path.join(self.storage_dir, "time_savings.json")

    def _quality_metrics_path(self) -> str:
        return os.path.join(self.storage_dir, "quality_metrics.json")

    def _roi_calculations_path(self) -> str:
        return os.path.join(self.storage_dir, "roi_calculations.json")

    def _productivity_reports_path(self) -> str:
        return os.path.join(self.storage_dir, "productivity_reports.json")

    def _save(self) -> None:
        try:
            metrics_data = {mid: m.to_dict() for mid, m in self._roi_metrics.items()}
            with open(self._roi_metrics_path(), "w", encoding="utf-8") as f:
                json.dump(metrics_data, f, indent=2, default=str)

            savings_data = {sid: s.to_dict() for sid, s in self._time_savings.items()}
            with open(self._time_savings_path(), "w", encoding="utf-8") as f:
                json.dump(savings_data, f, indent=2, default=str)

            quality_data = {qid: q.to_dict() for qid, q in self._quality_metrics.items()}
            with open(self._quality_metrics_path(), "w", encoding="utf-8") as f:
                json.dump(quality_data, f, indent=2, default=str)

            calc_data = {cid: c.to_dict() for cid, c in self._roi_calculations.items()}
            with open(self._roi_calculations_path(), "w", encoding="utf-8") as f:
                json.dump(calc_data, f, indent=2, default=str)

            report_data = {rid: r.to_dict() for rid, r in self._productivity_reports.items()}
            with open(self._productivity_reports_path(), "w", encoding="utf-8") as f:
                json.dump(report_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save ROI engine data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._roi_metrics_path()):
                with open(self._roi_metrics_path(), "r", encoding="utf-8") as f:
                    metrics_data = json.load(f)
                for mid, data in metrics_data.items():
                    try:
                        self._roi_metrics[mid] = ROIMetric.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed ROI metric %s: %s", mid, e)

            if os.path.exists(self._time_savings_path()):
                with open(self._time_savings_path(), "r", encoding="utf-8") as f:
                    savings_data = json.load(f)
                for sid, data in savings_data.items():
                    try:
                        self._time_savings[sid] = TimeSavingsMetric.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed time savings %s: %s", sid, e)

            if os.path.exists(self._quality_metrics_path()):
                with open(self._quality_metrics_path(), "r", encoding="utf-8") as f:
                    quality_data = json.load(f)
                for qid, data in quality_data.items():
                    try:
                        self._quality_metrics[qid] = QualityMetric.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed quality metric %s: %s", qid, e)

            if os.path.exists(self._roi_calculations_path()):
                with open(self._roi_calculations_path(), "r", encoding="utf-8") as f:
                    calc_data = json.load(f)
                for cid, data in calc_data.items():
                    try:
                        self._roi_calculations[cid] = ROICalculation.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed ROI calculation %s: %s", cid, e)

            if os.path.exists(self._productivity_reports_path()):
                with open(self._productivity_reports_path(), "r", encoding="utf-8") as f:
                    report_data = json.load(f)
                for rid, data in report_data.items():
                    try:
                        self._productivity_reports[rid] = ProductivityReport.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed productivity report %s: %s", rid, e)
        except Exception as e:
            logger.error("Failed to load ROI engine data: %s", e, exc_info=True)

    def create_roi_metric(self, metric: ROIMetric) -> ROIMetric:
        self._telemetry["create_roi_metric_calls"] += 1
        if not metric.id:
            metric.id = str(uuid.uuid4())
        if not metric.created_at:
            now = datetime.now(timezone.utc).isoformat()
            metric.created_at = now
            metric.updated_at = now
        self._roi_metrics[metric.id] = metric
        self._save()
        logger.info("Created ROI metric %s: %s (%s)", metric.id, metric.name, metric.category.value)
        return metric

    def update_roi_metric(self, metric_id: str, updates: dict) -> Optional[ROIMetric]:
        self._telemetry["update_roi_metric_calls"] += 1
        metric = self._roi_metrics.get(metric_id)
        if not metric:
            logger.warning("Attempted to update unknown ROI metric: %s", metric_id)
            return None
        for key, value in updates.items():
            if hasattr(metric, key) and key not in ("id", "created_at"):
                if key == "category":
                    setattr(metric, key, ROICategory(value) if isinstance(value, str) else value)
                elif key == "status":
                    setattr(metric, key, ROIStatus(value) if isinstance(value, str) else value)
                else:
                    setattr(metric, key, value)
        metric.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Updated ROI metric: %s", metric_id)
        return metric

    def list_roi_metrics(self, org_id: str, category: Optional[ROICategory] = None) -> list[ROIMetric]:
        self._telemetry["list_roi_metrics_calls"] += 1
        results = []
        for m in self._roi_metrics.values():
            if m.org_id == org_id:
                if category is None or m.category == category:
                    results.append(m)
        results.sort(key=lambda m: m.created_at, reverse=True)
        return results

    def record_time_savings(self, savings: TimeSavingsMetric) -> TimeSavingsMetric:
        self._telemetry["record_time_savings_calls"] += 1
        if not savings.id:
            savings.id = str(uuid.uuid4())
        if not savings.created_at:
            savings.created_at = datetime.now(timezone.utc).isoformat()
        savings.hours_saved = savings.manual_hours - savings.automated_hours
        savings.total_savings = round(savings.hours_saved * savings.hourly_rate * savings.frequency_per_week * 4.33, 2)
        self._time_savings[savings.id] = savings
        self._save()
        logger.info("Recorded time savings %s: %.2f hrs saved (%.2f) for task %s",
                     savings.id, savings.hours_saved, savings.total_savings, savings.task_name)
        return savings

    def record_quality_metric(self, metric: QualityMetric) -> QualityMetric:
        self._telemetry["record_quality_metric_calls"] += 1
        if not metric.id:
            metric.id = str(uuid.uuid4())
        if not metric.measured_at:
            metric.measured_at = datetime.now(timezone.utc).isoformat()
        if metric.before_value > 0:
            metric.improvement_percent = round(
                ((metric.after_value - metric.before_value) / metric.before_value) * 100, 2
            )
        self._quality_metrics[metric.id] = metric
        self._save()
        logger.info("Recorded quality metric %s: %s improved by %.2f%%",
                     metric.id, metric.metric_name, metric.improvement_percent)
        return metric

    def calculate_developer_time_saved(self, org_id: str, start_date: str, end_date: str) -> dict:
        self._telemetry["calculate_developer_time_saved_calls"] += 1
        filtered = [
            s for s in self._time_savings.values()
            if s.org_id == org_id and start_date <= s.created_at[:10] <= end_date
        ]

        total_manual_hours = sum(s.manual_hours * s.frequency_per_week * 4.33 for s in filtered)
        total_automated_hours = sum(s.automated_hours * s.frequency_per_week * 4.33 for s in filtered)
        total_hours_saved = total_manual_hours - total_automated_hours
        total_cost_saved = sum(s.total_savings for s in filtered)
        avg_hourly_rate = sum(s.hourly_rate for s in filtered) / max(len(filtered), 1)

        by_category: dict[str, dict] = defaultdict(lambda: {"hours_saved": 0.0, "cost_saved": 0.0, "count": 0})
        for s in filtered:
            cat = s.category.value
            monthly_hours = s.hours_saved * s.frequency_per_week * 4.33
            by_category[cat]["hours_saved"] += monthly_hours
            by_category[cat]["cost_saved"] += s.total_savings
            by_category[cat]["count"] += 1

        return {
            "org_id": org_id,
            "period_start": start_date,
            "period_end": end_date,
            "total_manual_hours": round(total_manual_hours, 2),
            "total_automated_hours": round(total_automated_hours, 2),
            "total_hours_saved": round(total_hours_saved, 2),
            "total_cost_saved": round(total_cost_saved, 2),
            "avg_hourly_rate": round(avg_hourly_rate, 2),
            "developers_affected": sum(s.developers_affected for s in filtered),
            "by_category": dict(by_category),
            "entry_count": len(filtered),
            "productivity_gain_pct": round(
                (total_hours_saved / max(total_manual_hours, 1)) * 100, 2
            ) if total_manual_hours > 0 else 0.0,
        }

    def calculate_ai_productivity(self, org_id: str, start_date: str, end_date: str) -> dict:
        self._telemetry["calculate_ai_productivity_calls"] += 1
        filtered = [
            s for s in self._time_savings.values()
            if s.org_id == org_id and start_date <= s.created_at[:10] <= end_date
        ]

        total_hours_saved = sum(s.hours_saved * s.frequency_per_week * 4.33 for s in filtered)
        total_cost_saved = sum(s.total_savings for s in filtered)
        total_developers = sum(s.developers_affected for s in filtered)

        ai_categories = {
            ROICategory.DEVELOPER_TIME_SAVED,
            ROICategory.AI_PRODUCTIVITY,
            ROICategory.REVIEW_TIME_SAVED,
            ROICategory.TESTING_TIME_SAVED,
            ROICategory.DOCUMENTATION_TIME_SAVED,
        }
        ai_filtered = [s for s in filtered if s.category in ai_categories]
        ai_hours = sum(s.hours_saved * s.frequency_per_week * 4.33 for s in ai_filtered)
        ai_cost = sum(s.total_savings for s in ai_filtered)

        avg_hours_per_dev = total_hours_saved / max(total_developers, 1)
        efficiency_ratio = round(ai_hours / max(total_hours_saved, 1), 4) if total_hours_saved > 0 else 0

        return {
            "org_id": org_id,
            "period_start": start_date,
            "period_end": end_date,
            "total_hours_saved": round(total_hours_saved, 2),
            "total_cost_saved": round(total_cost_saved, 2),
            "ai_attributed_hours": round(ai_hours, 2),
            "ai_attributed_cost": round(ai_cost, 2),
            "ai_efficiency_ratio": efficiency_ratio,
            "developers_affected": total_developers,
            "avg_hours_saved_per_developer": round(avg_hours_per_dev, 2),
            "monthly_savings_per_developer": round(avg_hours_per_dev * 4.33, 2) if avg_hours_per_dev > 0 else 0,
            "productivity_multiplier": round(1 + efficiency_ratio, 2),
        }

    def calculate_code_quality_improvement(self, org_id: str, start_date: str, end_date: str) -> dict:
        self._telemetry["calculate_code_quality_improvement_calls"] += 1
        filtered = [
            q for q in self._quality_metrics.values()
            if q.org_id == org_id and start_date <= q.measured_at[:10] <= end_date
        ]

        quality_categories = {ROICategory.CODE_QUALITY, ROICategory.BUG_REDUCTION, ROICategory.SECURITY_IMPROVEMENT}
        quality_filtered = [q for q in filtered if q.category in quality_categories]

        if not quality_filtered:
            return {
                "org_id": org_id,
                "period_start": start_date,
                "period_end": end_date,
                "metrics_count": 0,
                "avg_improvement_pct": 0.0,
                "quality_score": 0.0,
                "improvements": [],
            }

        total_improvement = sum(q.improvement_percent for q in quality_filtered)
        avg_improvement = total_improvement / len(quality_filtered)
        weighted_score = sum(
            q.improvement_percent * (q.after_value / max(q.before_value, 1))
            for q in quality_filtered if q.before_value > 0
        ) / max(len(quality_filtered), 1)

        by_impact: dict[str, list] = defaultdict(list)
        for q in quality_filtered:
            by_impact[q.impact_area or "general"].append({
                "metric_id": q.id,
                "metric_name": q.metric_name,
                "before_value": q.before_value,
                "after_value": q.after_value,
                "improvement_percent": q.improvement_percent,
                "measurement_method": q.measurement_method,
                "measured_at": q.measured_at,
            })

        return {
            "org_id": org_id,
            "period_start": start_date,
            "period_end": end_date,
            "metrics_count": len(quality_filtered),
            "avg_improvement_pct": round(avg_improvement, 2),
            "quality_score": round(min(100, max(0, weighted_score)), 2),
            "improvements": [
                {"metric_name": q.metric_name, "improvement_pct": q.improvement_percent, "impact_area": q.impact_area}
                for q in sorted(quality_filtered, key=lambda x: x.improvement_percent, reverse=True)[:10]
            ],
            "by_impact_area": {k: v for k, v in by_impact.items()},
        }

    def calculate_infrastructure_optimization(self, org_id: str, start_date: str, end_date: str) -> dict:
        self._telemetry["calculate_infrastructure_optimization_calls"] += 1
        filtered = [
            s for s in self._time_savings.values()
            if s.org_id == org_id
            and s.category == ROICategory.INFRASTRUCTURE_OPTIMIZATION
            and start_date <= s.created_at[:10] <= end_date
        ]

        total_cost_saved = sum(s.total_savings for s in filtered)
        total_hours_saved = sum(s.hours_saved * s.frequency_per_week * 4.33 for s in filtered)

        savings_breakdown = []
        for s in filtered:
            savings_breakdown.append({
                "task_name": s.task_name,
                "hours_saved": round(s.hours_saved * s.frequency_per_week * 4.33, 2),
                "cost_saved": s.total_savings,
                "developers_affected": s.developers_affected,
                "hourly_rate": s.hourly_rate,
            })

        return {
            "org_id": org_id,
            "period_start": start_date,
            "period_end": end_date,
            "total_cost_saved": round(total_cost_saved, 2),
            "total_hours_saved": round(total_hours_saved, 2),
            "optimization_count": len(filtered),
            "savings_breakdown": savings_breakdown,
            "estimated_monthly_recurring_savings": round(
                total_cost_saved / max(1, (len(filtered) or 1)), 2
            ),
        }

    def calculate_total_roi(self, org_id: str, start_date: str, end_date: str, investment_amount: Optional[float] = None) -> ROICalculation:
        self._telemetry["calculate_total_roi_calls"] += 1

        time_savings_data = self.calculate_developer_time_saved(org_id, start_date, end_date)
        productivity_data = self.calculate_ai_productivity(org_id, start_date, end_date)
        quality_data = self.calculate_code_quality_improvement(org_id, start_date, end_date)
        infra_data = self.calculate_infrastructure_optimization(org_id, start_date, end_date)

        total_benefits = (
            time_savings_data["total_cost_saved"]
            + productivity_data["ai_attributed_cost"]
            + infra_data["total_cost_saved"]
        )
        quality_benefit = quality_data["avg_improvement_pct"] * 100
        total_benefits += quality_benefit

        if investment_amount is None:
            investment_amount = total_benefits * 0.3 if total_benefits > 0 else 10000.0

        net_roi = total_benefits - investment_amount
        roi_percent = round((net_roi / investment_amount) * 100, 2) if investment_amount > 0 else 0.0

        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
        period_days = max(1, (end - start).days)

        payback_days = 0
        if total_benefits > 0:
            daily_benefit = total_benefits / period_days
            payback_days = int(investment_amount / daily_benefit) if daily_benefit > 0 else 0

        categories: dict[ROICategory, float] = {}
        for s in self._time_savings.values():
            if s.org_id == org_id and start_date <= s.created_at[:10] <= end_date:
                cat = s.category
                categories[cat] = round(categories.get(cat, 0.0) + s.total_savings, 2)

        for q in self._quality_metrics.values():
            if q.org_id == org_id and start_date <= q.measured_at[:10] <= end_date:
                cat = q.category
                categories[cat] = round(categories.get(cat, 0.0) + q.improvement_percent * 10, 2)

        benefit_by_type: dict[BenefitType, float] = {
            BenefitType.TIME_SAVINGS: round(time_savings_data["total_cost_saved"], 2),
            BenefitType.COST_REDUCTION: round(infra_data["total_cost_saved"], 2),
            BenefitType.QUALITY_IMPROVEMENT: round(quality_benefit, 2),
            BenefitType.VELOCITY_INCREASE: round(productivity_data["productivity_multiplier"] * 100, 2),
            BenefitType.RISK_REDUCTION: round(quality_benefit * 0.5, 2),
            BenefitType.REVENUE_INCREASE: round(total_benefits * 0.1, 2),
        }

        assumptions = [
            "Hourly developer rate based on average of recorded time savings entries",
            f"Productivity gain of {productivity_data['productivity_multiplier']}x estimated from AI-attributed savings",
            f"Quality improvement of {quality_data['avg_improvement_pct']}% applied across {quality_data['metrics_count']} metrics",
            f"Benefit period of {period_days} days used for payback calculation",
            "Infrastructure savings assumed recurring monthly",
            "Revenue increase estimated at 10% of total measured benefits",
        ]

        calc = ROICalculation(
            id=str(uuid.uuid4()),
            org_id=org_id,
            period_start=start_date,
            period_end=end_date,
            total_investment=round(investment_amount, 2),
            total_benefits=round(total_benefits, 2),
            net_roi=round(net_roi, 2),
            roi_percent=roi_percent,
            payback_period_days=payback_days,
            categories=categories,
            benefit_by_type=benefit_by_type,
            assumptions=assumptions,
        )
        self._roi_calculations[calc.id] = calc
        self._save()
        logger.info("Calculated total ROI for org %s: %.2f%% (benefits=%.2f, investment=%.2f)",
                     org_id, roi_percent, total_benefits, investment_amount)
        return calc

    def estimate_engineering_velocity(self, org_id: str) -> dict:
        self._telemetry["estimate_engineering_velocity_calls"] += 1
        metrics = [m for m in self._roi_metrics.values() if m.org_id == org_id]
        savings = [s for s in self._time_savings.values() if s.org_id == org_id]

        pr_cycle_time = 0.0
        deploy_frequency = 0.0
        lead_time = 0.0
        time_to_merge = 0.0

        for m in metrics:
            if m.category == ROICategory.ENGINEERING_VELOCITY:
                if "pr_cycle" in m.name.lower():
                    pr_cycle_time = m.current_value if m.current_value > 0 else m.target_value
                elif "deploy" in m.name.lower():
                    deploy_frequency = m.current_value if m.current_value > 0 else m.target_value
                elif "lead_time" in m.name.lower():
                    lead_time = m.current_value if m.current_value > 0 else m.target_value
                elif "merge" in m.name.lower():
                    time_to_merge = m.current_value if m.current_value > 0 else m.target_value

        if pr_cycle_time == 0:
            pr_cycle_time = 4.5
        if deploy_frequency == 0:
            deploy_frequency = 12.0
        if lead_time == 0:
            lead_time = 2.0
        if time_to_merge == 0:
            time_to_merge = 1.5

        review_savings = sum(
            s.hours_saved * s.frequency_per_week for s in savings
            if s.category == ROICategory.REVIEW_TIME_SAVED
        )
        testing_savings = sum(
            s.hours_saved * s.frequency_per_week for s in savings
            if s.category == ROICategory.TESTING_TIME_SAVED
        )
        deployment_savings = sum(
            s.hours_saved * s.frequency_per_week for s in savings
            if s.category == ROICategory.DEPLOYMENT_TIME_SAVED
        )

        velocity_score = min(100, round(
            (1 / max(pr_cycle_time, 0.1) * 10)
            + (deploy_frequency / 5 * 15)
            + (1 / max(lead_time, 0.1) * 10)
            + (review_savings * 2)
            + (testing_savings * 1.5)
            + (deployment_savings * 3)
        ))

        return {
            "org_id": org_id,
            "pr_cycle_time_hours": round(pr_cycle_time, 1),
            "deploy_frequency_per_week": round(deploy_frequency, 1),
            "lead_time_hours": round(lead_time, 1),
            "time_to_merge_hours": round(time_to_merge, 1),
            "review_time_saved_hours_per_week": round(review_savings, 1),
            "testing_time_saved_hours_per_week": round(testing_savings, 1),
            "deployment_time_saved_hours_per_week": round(deployment_savings, 1),
            "velocity_score": velocity_score,
            "velocity_rating": "high" if velocity_score >= 70 else "medium" if velocity_score >= 40 else "low",
            "estimated_cycle_time_reduction_pct": round(
                (review_savings + testing_savings) / max(pr_cycle_time * deploy_frequency, 1) * 100, 1
            ) if pr_cycle_time > 0 and deploy_frequency > 0 else 0.0,
        }

    def generate_productivity_report(self, org_id: str, start_date: str, end_date: str) -> ProductivityReport:
        self._telemetry["generate_productivity_report_calls"] += 1

        time_data = self.calculate_developer_time_saved(org_id, start_date, end_date)
        product_data = self.calculate_ai_productivity(org_id, start_date, end_date)
        quality_data = self.calculate_code_quality_improvement(org_id, start_date, end_date)
        velocity_data = self.estimate_engineering_velocity(org_id)

        total_hours_saved = time_data["total_hours_saved"]
        total_cost_saved = time_data["total_cost_saved"] + product_data["ai_attributed_cost"]
        velocity_improvement = velocity_data["velocity_score"]
        quality_improvement = quality_data["avg_improvement_pct"]

        top_improvements = quality_data["improvements"][:5] + [
            {"metric_name": "Developer Time Saved", "improvement_pct": round(
                time_data["productivity_gain_pct"], 2
            )},
            {"metric_name": "Engineering Velocity", "improvement_pct": velocity_improvement},
        ]

        recommendations = []
        if total_hours_saved < 100:
            recommendations.append("Increase AI tool adoption across more engineering workflows to boost time savings")
        if quality_improvement < 20:
            recommendations.append("Implement AI-assisted code review to improve code quality metrics")
        if velocity_data["velocity_rating"] == "low":
            recommendations.append("Focus on reducing PR cycle time through automated testing and review pipelines")
        if velocity_data["deploy_frequency_per_week"] < 10:
            recommendations.append("Increase deployment frequency by automating CI/CD pipelines")
        if not recommendations:
            recommendations.append("Sustain current productivity gains by continuing AI-assisted development practices")
            recommendations.append("Explore expanding AI automation to additional engineering domains")

        report = ProductivityReport(
            id=str(uuid.uuid4()),
            org_id=org_id,
            period_start=start_date,
            period_end=end_date,
            total_hours_saved=round(total_hours_saved, 2),
            total_cost_saved=round(total_cost_saved, 2),
            velocity_improvement=round(velocity_improvement, 2),
            quality_improvement=round(quality_improvement, 2),
            developer_satisfaction=round(
                min(100, max(0, 60 + quality_improvement * 0.5 + velocity_improvement * 0.3)), 2
            ),
            top_improvements=top_improvements,
            recommendations=recommendations,
        )
        self._productivity_reports[report.id] = report
        self._save()
        logger.info("Generated productivity report %s for org %s", report.id, org_id)
        return report

    def get_roi_trend(self, org_id: str, months: int = 6) -> list[dict]:
        self._telemetry["get_roi_trend_calls"] += 1
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=months * 30)

        monthly_data: dict[str, dict] = {}
        current = start
        while current <= end:
            month_key = current.strftime("%Y-%m")
            monthly_data[month_key] = {
                "month": month_key,
                "total_benefits": 0.0,
                "total_hours_saved": 0.0,
                "quality_improvement": 0.0,
                "entry_count": 0,
            }
            current += timedelta(days=30)

        for savings in self._time_savings.values():
            if savings.org_id == org_id:
                dt = datetime.fromisoformat(savings.created_at)
                month_key = dt.strftime("%Y-%m")
                if month_key in monthly_data:
                    monthly_data[month_key]["total_benefits"] += savings.total_savings
                    monthly_data[month_key]["total_hours_saved"] += savings.hours_saved * savings.frequency_per_week * 4.33
                    monthly_data[month_key]["entry_count"] += 1

        for quality in self._quality_metrics.values():
            if quality.org_id == org_id:
                dt = datetime.fromisoformat(quality.measured_at)
                month_key = dt.strftime("%Y-%m")
                if month_key in monthly_data:
                    monthly_data[month_key]["quality_improvement"] += quality.improvement_percent

        for key in monthly_data:
            monthly_data[key]["total_benefits"] = round(monthly_data[key]["total_benefits"], 2)
            monthly_data[key]["total_hours_saved"] = round(monthly_data[key]["total_hours_saved"], 2)
            monthly_data[key]["quality_improvement"] = round(monthly_data[key]["quality_improvement"], 2)

        return sorted(monthly_data.values(), key=lambda x: x["month"])

    def get_roi_by_category(self, org_id: str) -> dict:
        self._telemetry["get_roi_by_category_calls"] += 1
        category_data: dict[str, dict] = {}

        for savings in self._time_savings.values():
            if savings.org_id == org_id:
                cat = savings.category.value
                if cat not in category_data:
                    category_data[cat] = {
                        "category": cat,
                        "total_savings": 0.0,
                        "total_hours": 0.0,
                        "entry_count": 0,
                    }
                category_data[cat]["total_savings"] += savings.total_savings
                category_data[cat]["total_hours"] += savings.hours_saved * savings.frequency_per_week * 4.33
                category_data[cat]["entry_count"] += 1

        for quality in self._quality_metrics.values():
            if quality.org_id == org_id:
                cat = quality.category.value
                if cat not in category_data:
                    category_data[cat] = {
                        "category": cat,
                        "total_savings": 0.0,
                        "total_hours": 0.0,
                        "entry_count": 0,
                    }
                category_data[cat]["total_savings"] += quality.improvement_percent * 10
                category_data[cat]["entry_count"] += 1

        for cat in category_data:
            category_data[cat]["total_savings"] = round(category_data[cat]["total_savings"], 2)
            category_data[cat]["total_hours"] = round(category_data[cat]["total_hours"], 2)

        total = sum(d["total_savings"] for d in category_data.values())
        for cat in category_data:
            category_data[cat]["percentage"] = round(
                category_data[cat]["total_savings"] / total * 100, 2
            ) if total > 0 else 0.0

        return dict(sorted(category_data.items(), key=lambda x: x[1]["total_savings"], reverse=True))

    def get_telemetry(self) -> dict:
        self._telemetry["get_telemetry_calls"] += 1
        return dict(self._telemetry)
