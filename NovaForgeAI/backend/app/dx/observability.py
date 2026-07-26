"""DX Observability — track developer actions, search performance, command usage, workspace performance, API explorer usage, terminal usage."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class DXObservabilityMetric(Enum):
    DEVELOPER_ACTIONS = "developer_actions"
    SEARCH_PERFORMANCE = "search_performance"
    COMMAND_USAGE = "command_usage"
    WORKSPACE_PERFORMANCE = "workspace_performance"
    API_EXPLORER_USAGE = "api_explorer_usage"
    TERMINAL_USAGE = "terminal_usage"
    AI_ASSISTANCE = "ai_assistance"
    DOCS_ACCESS = "docs_access"


@dataclass
class DXObservabilitySnapshot:
    id: str
    org_id: str
    metric: DXObservabilityMetric
    value: float
    tags: dict = field(default_factory=dict)
    recorded_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["metric"] = self.metric.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "DXObservabilitySnapshot":
        data = data.copy()
        data["metric"] = DXObservabilityMetric(data.get("metric", "developer_actions"))
        return cls(**data)


class DXObservability:
    def __init__(self, storage_dir: str = "dx_data/observability"):
        self.storage_dir = storage_dir
        self._snapshots: dict[str, DXObservabilitySnapshot] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "snapshots.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._snapshots[k] = DXObservabilitySnapshot.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Failed to load DX observability: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._snapshots.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save DX observability: %s", e)

    def record_metric(self, org_id: str, metric: DXObservabilityMetric, value: float, tags: dict = None) -> DXObservabilitySnapshot:
        snap = DXObservabilitySnapshot(id=str(uuid.uuid4()), org_id=org_id, metric=metric, value=value, tags=tags or {})
        self._snapshots[snap.id] = snap
        self._save()
        return snap

    def get_history(self, metric: DXObservabilityMetric, org_id: str = "", limit: int = 100) -> list[DXObservabilitySnapshot]:
        results = [s for s in self._snapshots.values() if s.metric == metric]
        if org_id: results = [s for s in results if s.org_id == org_id]
        return sorted(results, key=lambda s: s.recorded_at, reverse=True)[:limit]

    def get_dashboard(self, org_id: str) -> dict:
        dashboard = {}
        for m in DXObservabilityMetric:
            history = self.get_history(m, org_id, limit=1)
            if history: dashboard[m.value] = history[0].value
        return dashboard

    def get_telemetry(self) -> dict: return dict(self._telemetry)
