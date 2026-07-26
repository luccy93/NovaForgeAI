"""Workspace Intelligence — AI-powered insights on workspace usage, collaboration patterns, productivity optimization, and smart recommendations."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


class InsightType(Enum):
    PRODUCTIVITY = "productivity"
    COLLABORATION = "collaboration"
    KNOWLEDGE = "knowledge"
    EFFICIENCY = "efficiency"
    BOTTLENECK = "bottleneck"
    RECOMMENDATION = "recommendation"
    TREND = "trend"
    ANOMALY = "anomaly"


@dataclass
class WorkspaceInsight:
    id: str
    workspace_id: str
    org_id: str
    insight_type: InsightType
    title: str
    description: str = ""
    score: float = 0.0
    impact: str = "medium"
    data: dict = field(default_factory=dict)
    recommendations: list = field(default_factory=list)
    is_actioned: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["insight_type"] = self.insight_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "WorkspaceInsight":
        data = data.copy()
        data["insight_type"] = InsightType(data.get("insight_type", "productivity"))
        return cls(**data)


class WorkspaceIntelligence:
    def __init__(self, storage_dir: str = "collab_data/intelligence"):
        self.storage_dir = storage_dir
        self._insights: dict[str, WorkspaceInsight] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "insights.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._insights[k] = WorkspaceInsight.from_dict(v)
                    except Exception as e: logger.warning("Skipping insight %s: %s", k, e)
            except Exception as e: logger.error("Failed to load workspace intelligence: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._insights.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save workspace intelligence: %s", e)

    def generate_insight(self, workspace_id: str, org_id: str, insight_type: InsightType, title: str, description: str = "", score: float = 0.0, impact: str = "medium", data: dict = None, recommendations: list = None) -> WorkspaceInsight:
        insight = WorkspaceInsight(id=str(uuid.uuid4()), workspace_id=workspace_id, org_id=org_id, insight_type=insight_type, title=title, description=description, score=score, impact=impact, data=data or {}, recommendations=recommendations or [])
        self._insights[insight.id] = insight
        self._save()
        return insight

    def list_insights(self, workspace_id: str = "", insight_type: Optional[InsightType] = None, limit: int = 50) -> list[WorkspaceInsight]:
        results = list(self._insights.values())
        if workspace_id: results = [i for i in results if i.workspace_id == workspace_id]
        if insight_type: results = [i for i in results if i.insight_type == insight_type]
        return sorted(results, key=lambda i: i.score, reverse=True)[:limit]

    def get_recommendations(self, workspace_id: str) -> list[WorkspaceInsight]:
        return [i for i in self._insights.values() if i.workspace_id == workspace_id and i.insight_type == InsightType.RECOMMENDATION and not i.is_actioned]

    def mark_actioned(self, insight_id: str) -> bool:
        insight = self._insights.get(insight_id)
        if not insight: return False
        insight.is_actioned = True
        self._save()
        return True

    def get_telemetry(self) -> dict: return dict(self._telemetry)
