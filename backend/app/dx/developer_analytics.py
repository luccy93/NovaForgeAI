"""Developer Analytics — track session length, commands used, AI usage, repo activity, search patterns, docs usage, review activity, deployment activity."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class DXAnalyticsMetric(Enum):
    SESSION_LENGTH = "session_length"
    COMMANDS_USED = "commands_used"
    AI_USAGE = "ai_usage"
    REPO_ACTIVITY = "repo_activity"
    SEARCH_PATTERNS = "search_patterns"
    DOCS_USAGE = "docs_usage"
    REVIEW_ACTIVITY = "review_activity"
    DEPLOYMENT_ACTIVITY = "deployment_activity"


@dataclass
class DXAnalyticsRecord:
    id: str
    user_id: str
    org_id: str
    metric: DXAnalyticsMetric
    value: float
    tags: dict = field(default_factory=dict)
    recorded_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["metric"] = self.metric.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "DXAnalyticsRecord":
        data = data.copy()
        data["metric"] = DXAnalyticsMetric(data.get("metric", "session_length"))
        return cls(**data)


class DeveloperAnalytics:
    def __init__(self, storage_dir: str = "dx_data/analytics"):
        self.storage_dir = storage_dir
        self._records: dict[str, DXAnalyticsRecord] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "records.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._records[k] = DXAnalyticsRecord.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Failed to load DX analytics: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._records.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save DX analytics: %s", e)

    def record_metric(self, user_id: str, org_id: str, metric: DXAnalyticsMetric, value: float, tags: dict = None) -> DXAnalyticsRecord:
        rec = DXAnalyticsRecord(id=str(uuid.uuid4()), user_id=user_id, org_id=org_id, metric=metric, value=value, tags=tags or {})
        self._records[rec.id] = rec
        self._save()
        return rec

    def get_user_analytics(self, user_id: str, metric: Optional[DXAnalyticsMetric] = None, limit: int = 100) -> dict:
        records = [r for r in self._records.values() if r.user_id == user_id]
        if metric: records = [r for r in records if r.metric == metric]
        summary = {}
        for m in DXAnalyticsMetric:
            vals = [r.value for r in records if r.metric == m]
            if vals: summary[m.value] = {"total": round(sum(vals), 2), "avg": round(sum(vals) / len(vals), 2), "count": len(vals)}
        return summary

    def get_org_analytics(self, org_id: str) -> dict:
        records = [r for r in self._records.values() if r.org_id == org_id]
        summary = {}
        for m in DXAnalyticsMetric:
            vals = [r.value for r in records if r.metric == m]
            if vals: summary[m.value] = {"total": round(sum(vals), 2), "avg": round(sum(vals) / len(vals), 2), "users": len(set(r.user_id for r in records if r.metric == m))}
        return summary

    def get_telemetry(self) -> dict: return dict(self._telemetry)
