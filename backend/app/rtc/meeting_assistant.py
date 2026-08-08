"""Meeting Assistant — record, summarize, action items, tasks, follow-ups, archive."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class Meeting:
    id: str; org_id: str; title: str; description: str = ""
    organizer_id: str = ""; participants: list = field(default_factory=list)
    notes: str = ""; summary: str = ""; action_items: list = field(default_factory=list)
    decisions: list = field(default_factory=list); duration_minutes: int = 0
    recorded: bool = False; status: str = "scheduled"  # scheduled, ongoing, completed, cancelled
    started_at: str = ""; ended_at: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "Meeting": return cls(**data)

class MeetingAssistant:
    def __init__(self, storage_dir: str = "rtc_data/meetings"):
        self.storage_dir = storage_dir; self._meetings: dict[str, Meeting] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "meetings.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r", encoding="utf-8") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._meetings[k] = Meeting.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._meetings.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def schedule(self, org_id: str, title: str, organizer_id: str = "", description: str = "") -> Meeting:
        m = Meeting(id=str(uuid.uuid4()), org_id=org_id, title=title, organizer_id=organizer_id, description=description)
        self._meetings[m.id] = m; self._save(); return m

    def start(self, meeting_id: str) -> Optional[Meeting]:
        m = self._meetings.get(meeting_id)
        if not m: return None
        m.status = "ongoing"; m.started_at = datetime.now(timezone.utc).isoformat(); self._save(); return m

    def end(self, meeting_id: str) -> Optional[Meeting]:
        m = self._meetings.get(meeting_id)
        if not m: return None
        m.status = "completed"; m.ended_at = datetime.now(timezone.utc).isoformat()
        if m.started_at: m.duration_minutes = int((datetime.fromisoformat(m.ended_at) - datetime.fromisoformat(m.started_at)).total_seconds() / 60)
        self._save(); return m

    def add_notes(self, meeting_id: str, notes: str) -> Optional[Meeting]:
        m = self._meetings.get(meeting_id)
        if not m: return None
        m.notes = notes; self._save(); return m

    def generate_summary(self, meeting_id: str) -> Optional[Meeting]:
        m = self._meetings.get(meeting_id)
        if not m: return None
        m.summary = f"AI Summary: {m.title} - {len(m.participants)} participants, {len(m.action_items)} action items"
        self._save(); return m

    def add_action_item(self, meeting_id: str, item: str) -> Optional[Meeting]:
        m = self._meetings.get(meeting_id)
        if not m: return None
        m.action_items.append(item); self._save(); return m
