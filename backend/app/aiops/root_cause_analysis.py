"""Root Cause Analysis — primary cause, contributing causes, timeline, affected services, impact, confidence."""
import json, uuid, os, logging, time
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class RootCause:
    id: str; org_id: str; incident_id: str; primary_cause: str = ""
    contributing_causes: list = field(default_factory=list)
    timeline: list = field(default_factory=list); affected_services: list = field(default_factory=list)
    affected_users: int = 0; business_impact: str = ""; recovery_priority: int = 3
    confidence_score: float = 0.0; created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "RootCause": return cls(**data)

class RootCauseAnalysis:
    def __init__(self, storage_dir: str = "aiops_data/rca"):
        self.storage_dir = storage_dir; self._analyses: dict[str, RootCause] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "analyses.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._analyses[k] = RootCause.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._analyses.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def analyze(self, org_id: str, incident_id: str, primary_cause: str, confidence: float = 0.0, contributing: list = None, services: list = None) -> RootCause:
        r = RootCause(id=str(uuid.uuid4()), org_id=org_id, incident_id=incident_id, primary_cause=primary_cause, confidence_score=confidence, contributing_causes=contributing or [], affected_services=services or [])
        self._analyses[r.id] = r; self._save(); return r

    def get_by_incident(self, incident_id: str) -> Optional[RootCause]:
        for r in self._analyses.values():
            if r.incident_id == incident_id: return r
        return None
