"""Incident Management — timeline, services, root cause, recovery plan, postmortem, lessons learned."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class Incident:
    id: str; org_id: str; title: str; severity: str = "medium"; status: str = "open"
    services_affected: list = field(default_factory=list); root_cause: str = ""
    recovery_plan: str = ""; postmortem: str = ""; lessons: list = field(default_factory=list)
    tasks: list = field(default_factory=list); owner_id: str = ""
    detected_at: str = ""; resolved_at: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "Incident": return cls(**data)

class IncidentManagement:
    def __init__(self, storage_dir: str = "aiops_data/incidents"):
        self.storage_dir = storage_dir; self._incidents: dict[str, Incident] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "incidents.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._incidents[k] = Incident.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._incidents.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create(self, org_id: str, title: str, severity: str = "medium") -> Incident:
        i = Incident(id=str(uuid.uuid4()), org_id=org_id, title=title, severity=severity, detected_at=datetime.now(timezone.utc).isoformat())
        self._incidents[i.id] = i; self._save(); return i

    def resolve(self, incident_id: str, root_cause: str = "", postmortem: str = "") -> Optional[Incident]:
        i = self._incidents.get(incident_id)
        if not i: return None
        i.status = "resolved"; i.root_cause = root_cause; i.postmortem = postmortem; i.resolved_at = datetime.now(timezone.utc).isoformat()
        self._save(); return i

    def add_lesson(self, incident_id: str, lesson: str) -> Optional[Incident]:
        i = self._incidents.get(incident_id)
        if not i: return None
        i.lessons.append(lesson); self._save(); return i

    def get_active(self, org_id: str) -> list[Incident]:
        return [i for i in self._incidents.values() if i.org_id == org_id and i.status == "open"]
