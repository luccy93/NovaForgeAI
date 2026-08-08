"""Reporting — release reports, dashboards, analytics, exports, trends."""
import json, uuid, os, logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class Report:
    id: str; org_id: str; title: str; report_type: str  # release_summary, deployment_report, quality_report, compliance_report
    data: dict = field(default_factory=dict); filters: dict = field(default_factory=dict)
    format: str = "markdown"; generated_by: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "Report": return cls(**data)

@dataclass
class Dashboard:
    id: str; org_id: str; name: str; description: str = ""
    widgets: list = field(default_factory=list); layout: dict = field(default_factory=dict)
    is_default: bool = False; refresh_interval: int = 60
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "Dashboard": return cls(**data)

class Reporting:
    def __init__(self, storage_dir: str = "release_data/reporting"):
        self.storage_dir = storage_dir; self._reports: dict[str, Report] = {}
        self._dashboards: dict[str, Dashboard] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _rep_path(self) -> str: return os.path.join(self.storage_dir, "reports.json")
    def _dash_path(self) -> str: return os.path.join(self.storage_dir, "dashboards.json")

    def _load(self) -> None:
        for path, store, cls in [(self._rep_path(), self._reports, Report), (self._dash_path(), self._dashboards, Dashboard)]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f: data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._rep_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._reports.items()}, f, indent=2, default=str)
            with open(self._dash_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._dashboards.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def generate_report(self, org_id: str, title: str, report_type: str, data: dict = None, format: str = "markdown") -> Report:
        r = Report(id=str(uuid.uuid4()), org_id=org_id, title=title, report_type=report_type, data=data or {}, format=format)
        self._reports[r.id] = r; self._save(); return r

    def create_dashboard(self, org_id: str, name: str, description: str = "") -> Dashboard:
        d = Dashboard(id=str(uuid.uuid4()), org_id=org_id, name=name, description=description)
        self._dashboards[d.id] = d; self._save(); return d

    def list_reports(self, org_id: str, report_type: str = "") -> list[Report]:
        results = [r for r in self._reports.values() if r.org_id == org_id]
        if report_type: results = [r for r in results if r.report_type == report_type]
        return sorted(results, key=lambda r: r.created_at, reverse=True)
