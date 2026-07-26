"""Activity Stream — repository updates, commits, PRs, deployments, agent activity."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class ActivityEvent:
    id: str; org_id: str; event_type: str  # commit, pr, deploy, agent, search, prompt, knowledge, arch_change
    title: str; description: str = ""; actor_id: str = ""; resource_type: str = ""; resource_id: str = ""
    metadata: dict = field(default_factory=dict); tags: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "ActivityEvent": return cls(**data)

class ActivityStream:
    def __init__(self, storage_dir: str = "rtc_data/activity"):
        self.storage_dir = storage_dir; self._events: dict[str, ActivityEvent] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "events.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r", encoding="utf-8") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._events[k] = ActivityEvent.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._events.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def track(self, org_id: str, event_type: str, title: str, actor_id: str = "", resource_type: str = "", resource_id: str = "", description: str = "", metadata: dict = None) -> ActivityEvent:
        e = ActivityEvent(id=str(uuid.uuid4()), org_id=org_id, event_type=event_type, title=title, actor_id=actor_id, resource_type=resource_type, resource_id=resource_id, description=description, metadata=metadata or {})
        self._events[e.id] = e; self._save(); return e

    def get_feed(self, org_id: str, limit: int = 50, event_type: str = "") -> list[ActivityEvent]:
        results = [e for e in self._events.values() if e.org_id == org_id]
        if event_type: results = [e for e in results if e.event_type == event_type]
        return sorted(results, key=lambda e: e.created_at, reverse=True)[:limit]
