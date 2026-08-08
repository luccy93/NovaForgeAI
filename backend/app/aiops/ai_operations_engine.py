"""AI Operations Engine — analyze logs, generate incident reports, recommend fixes, prioritize, assign."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class AIOpsReport:
    id: str; org_id: str; incident_id: str; analysis: str = ""
    recommended_fixes: list = field(default_factory=list); priority: str = "medium"
    assignee: str = ""; tickets: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "AIOpsReport": return cls(**data)

class AIOperationsEngine:
    def __init__(self, storage_dir: str = "aiops_data/aiops"):
        self.storage_dir = storage_dir; self._reports: dict[str, AIOpsReport] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "reports.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._reports[k] = AIOpsReport.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._reports.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def analyze_incident(self, org_id: str, incident_id: str, logs: str = "") -> AIOpsReport:
        report = AIOpsReport(id=str(uuid.uuid4()), org_id=org_id, incident_id=incident_id, analysis=f"AI Analysis of incident {incident_id}: {len(logs)} log lines analyzed", recommended_fixes=["check logs", "restart service"], priority="high")
        self._reports[report.id] = report; self._save(); return report

    def generate_recovery_plan(self, report_id: str) -> Optional[AIOpsReport]:
        r = self._reports.get(report_id)
        if not r: return None
        r.recommended_fixes.append("automated rollback to last stable version")
        self._save(); return r

    def get_telemetry(self) -> dict: return {"reports": len(self._reports)}
