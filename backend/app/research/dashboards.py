"""Research Dashboards — model leaderboard, prompt leaderboard, agent leaderboard, embedding leaderboard, RAG leaderboard, performance dashboard, innovation dashboard, experiment dashboard."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


class DashboardType(Enum):
    MODEL_LEADERBOARD = "model_leaderboard"
    PROMPT_LEADERBOARD = "prompt_leaderboard"
    AGENT_LEADERBOARD = "agent_leaderboard"
    EMBEDDING_LEADERBOARD = "embedding_leaderboard"
    RAG_LEADERBOARD = "rag_leaderboard"
    PERFORMANCE = "performance"
    INNOVATION = "innovation"
    EXPERIMENT = "experiment"


@dataclass
class DashboardWidget:
    id: str
    title: str
    widget_type: str
    config: dict = field(default_factory=dict)
    data: Any = None
    order: int = 0
    refresh_interval: int = 300

    def to_dict(self) -> dict: return asdict(self)


@dataclass
class Dashboard:
    id: str
    org_id: str
    name: str
    dashboard_type: DashboardType
    description: str = ""
    widgets: list = field(default_factory=list)
    layout: str = "grid"
    filters: dict = field(default_factory=dict)
    sharing: str = "private"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["dashboard_type"] = self.dashboard_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Dashboard":
        data = data.copy()
        data["dashboard_type"] = DashboardType(data.get("dashboard_type", "performance"))
        return cls(**data)


class ResearchDashboards:
    def __init__(self, storage_dir: str = "research_data/dashboards"):
        self.storage_dir = storage_dir
        self._dashboards: dict[str, Dashboard] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "dashboards.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._dashboards[k] = Dashboard.from_dict(v)
                    except Exception as e: logger.warning("Skipping dashboard %s: %s", k, e)
            except Exception as e: logger.error("Failed to load dashboards: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._dashboards.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save dashboards: %s", e)

    def create_dashboard(self, name: str, org_id: str, dashboard_type: DashboardType = DashboardType.PERFORMANCE, description: str = "") -> Dashboard:
        db = Dashboard(id=str(uuid.uuid4()), org_id=org_id, name=name, dashboard_type=dashboard_type, description=description)
        self._dashboards[db.id] = db
        self._save()
        return db

    def get_dashboard(self, db_id: str) -> Optional[Dashboard]: return self._dashboards.get(db_id)

    def update_dashboard(self, db_id: str, updates: dict) -> Optional[Dashboard]:
        db = self._dashboards.get(db_id)
        if not db: return None
        for k, v in updates.items():
            if hasattr(db, k) and k not in ("id", "created_at"):
                if k == "dashboard_type": setattr(db, k, DashboardType(v) if isinstance(v, str) else v)
                else: setattr(db, k, v)
        db.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return db

    def add_widget(self, db_id: str, title: str, widget_type: str, config: dict = None) -> Optional[DashboardWidget]:
        db = self._dashboards.get(db_id)
        if not db: return None
        widget = DashboardWidget(id=str(uuid.uuid4()), title=title, widget_type=widget_type, config=config or {}, order=len(db.widgets))
        db.widgets.append(widget)
        db.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return widget

    def update_widget(self, db_id: str, widget_id: str, updates: dict) -> Optional[Dashboard]:
        db = self._dashboards.get(db_id)
        if not db: return None
        for w in db.widgets:
            if w.id == widget_id:
                for k, v in updates.items():
                    if hasattr(w, k): setattr(w, k, v)
                break
        db.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return db

    def render_leaderboard(self, leaderboard_type: str, data: list[dict]) -> dict:
        return {"type": leaderboard_type, "entries": data, "generated_at": datetime.now(timezone.utc).isoformat(), "total": len(data)}

    def list_dashboards(self, org_id: str = "", dashboard_type: Optional[DashboardType] = None) -> list[Dashboard]:
        results = list(self._dashboards.values())
        if org_id: results = [d for d in results if d.org_id == org_id]
        if dashboard_type: results = [d for d in results if d.dashboard_type == dashboard_type]
        return results

    def delete_dashboard(self, db_id: str) -> bool:
        if db_id not in self._dashboards: return False
        del self._dashboards[db_id]
        self._save()
        return True

    def get_telemetry(self) -> dict: return dict(self._telemetry)
