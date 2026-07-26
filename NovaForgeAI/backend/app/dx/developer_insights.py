"""Developer Insights & Productivity Engine — measure coding time, review time, AI assistance, search time, deployment time, testing time, documentation time, developer efficiency."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class ProductivityMetric(Enum):
    CODING_TIME = "coding_time"
    REVIEW_TIME = "review_time"
    AI_ASSISTANCE = "ai_assistance"
    SEARCH_TIME = "search_time"
    DEPLOYMENT_TIME = "deployment_time"
    TESTING_TIME = "testing_time"
    DOCUMENTATION_TIME = "documentation_time"
    DEVELOPER_EFFICIENCY = "developer_efficiency"


@dataclass
class ProductivityRecord:
    id: str
    user_id: str
    org_id: str
    metric: ProductivityMetric
    value: float
    unit: str = "minutes"
    date: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["metric"] = self.metric.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ProductivityRecord":
        data = data.copy()
        data["metric"] = ProductivityMetric(data.get("metric", "coding_time"))
        return cls(**data)


@dataclass
class DeveloperInsight:
    id: str
    user_id: str
    org_id: str
    title: str
    description: str = ""
    metric: str = ""
    value: float = 0.0
    trend: str = "stable"
    recommendation: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "DeveloperInsight": return cls(**data)


class DeveloperInsights:
    def __init__(self, storage_dir: str = "dx_data/insights"):
        self.storage_dir = storage_dir
        self._records: dict[str, ProductivityRecord] = {}
        self._insights: dict[str, DeveloperInsight] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _rec_path(self) -> str: return os.path.join(self.storage_dir, "records.json")
    def _ins_path(self) -> str: return os.path.join(self.storage_dir, "insights.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._rec_path(), self._records, ProductivityRecord),
            (self._ins_path(), self._insights, DeveloperInsight),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Failed to load insights data: %s", e)

    def _save(self) -> None:
        try:
            with open(self._rec_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._records.items()}, f, indent=2, default=str)
            with open(self._ins_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._insights.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save insights data: %s", e)

    def record_metric(self, user_id: str, org_id: str, metric: ProductivityMetric, value: float, unit: str = "minutes") -> ProductivityRecord:
        rec = ProductivityRecord(id=str(uuid.uuid4()), user_id=user_id, org_id=org_id, metric=metric, value=value, unit=unit, date=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        self._records[rec.id] = rec
        self._save()
        return rec

    def get_user_metrics(self, user_id: str, metric: Optional[ProductivityMetric] = None, days: int = 30) -> dict:
        records = [r for r in self._records.values() if r.user_id == user_id]
        if metric: records = [r for r in records if r.metric == metric]
        summary = {}
        for m in ProductivityMetric:
            vals = [r.value for r in records if r.metric == m]
            if vals: summary[m.value] = {"total": round(sum(vals), 2), "avg": round(sum(vals) / len(vals), 2), "count": len(vals)}
        return summary

    def generate_insight(self, user_id: str, org_id: str, title: str, description: str = "", metric: str = "", value: float = 0.0, recommendation: str = "") -> DeveloperInsight:
        ins = DeveloperInsight(id=str(uuid.uuid4()), user_id=user_id, org_id=org_id, title=title, description=description, metric=metric, value=value, recommendation=recommendation)
        self._insights[ins.id] = ins
        self._save()
        return ins

    def get_insights(self, user_id: str) -> list[DeveloperInsight]:
        results = [i for i in self._insights.values() if i.user_id == user_id]
        return sorted(results, key=lambda i: i.created_at, reverse=True)

    def get_org_productivity(self, org_id: str) -> dict:
        records = [r for r in self._records.values() if r.org_id == org_id]
        summary = {}
        for m in ProductivityMetric:
            vals = [r.value for r in records if r.metric == m]
            if vals: summary[m.value] = {"total": round(sum(vals), 2), "avg": round(sum(vals) / len(vals), 2), "developers": len(set(r.user_id for r in records if r.metric == m))}
        return summary

    def get_telemetry(self) -> dict: return dict(self._telemetry)
