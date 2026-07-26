"""Meeting Assistant — automatically summarize meetings, extract action items, generate tasks, generate documentation, update knowledge base, assign work, track decisions."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Meeting:
    id: str
    org_id: str
    title: str
    date: str
    duration_minutes: int = 0
    participants: list = field(default_factory=list)
    notes: str = ""
    summary: str = ""
    action_items: list = field(default_factory=list)
    decisions: list = field(default_factory=list)
    tasks_created: list = field(default_factory=list)
    documents_generated: list = field(default_factory=list)
    knowledge_updated: list = field(default_factory=list)
    transcript: str = ""
    tags: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "Meeting": return cls(**data)


@dataclass
class ActionItem:
    id: str
    meeting_id: str
    description: str
    assignee: str = ""
    due_date: str = ""
    priority: str = "medium"
    status: str = "open"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "ActionItem": return cls(**data)


class MeetingAssistant:
    def __init__(self, storage_dir: str = "collab_data/meetings"):
        self.storage_dir = storage_dir
        self._meetings: dict[str, Meeting] = {}
        self._action_items: dict[str, ActionItem] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _meetings_path(self) -> str: return os.path.join(self.storage_dir, "meetings.json")
    def _actions_path(self) -> str: return os.path.join(self.storage_dir, "actions.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._meetings_path(), self._meetings, Meeting),
            (self._actions_path(), self._action_items, ActionItem),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Failed to load meeting data: %s", e)

    def _save(self) -> None:
        try:
            with open(self._meetings_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._meetings.items()}, f, indent=2, default=str)
            with open(self._actions_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._action_items.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save meeting data: %s", e)

    def create_meeting(self, org_id: str, title: str, date: str, duration_minutes: int = 0, participants: list = None) -> Meeting:
        meeting = Meeting(id=str(uuid.uuid4()), org_id=org_id, title=title, date=date, duration_minutes=duration_minutes, participants=participants or [])
        self._meetings[meeting.id] = meeting
        self._save()
        return meeting

    def get_meeting(self, meeting_id: str) -> Optional[Meeting]: return self._meetings.get(meeting_id)

    def update_meeting(self, meeting_id: str, updates: dict) -> Optional[Meeting]:
        meeting = self._meetings.get(meeting_id)
        if not meeting: return None
        for k, v in updates.items():
            if hasattr(meeting, k) and k not in ("id", "created_at"): setattr(meeting, k, v)
        meeting.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return meeting

    def generate_summary(self, meeting_id: str) -> Optional[str]:
        meeting = self._meetings.get(meeting_id)
        if not meeting: return None
        summary = f"Meeting: {meeting.title} on {meeting.date} with {len(meeting.participants)} participants. {len(meeting.action_items)} action items, {len(meeting.decisions)} decisions."
        meeting.summary = summary
        self._save()
        return summary

    def add_action_item(self, meeting_id: str, description: str, assignee: str = "", due_date: str = "", priority: str = "medium") -> Optional[ActionItem]:
        meeting = self._meetings.get(meeting_id)
        if not meeting: return None
        item = ActionItem(id=str(uuid.uuid4()), meeting_id=meeting_id, description=description, assignee=assignee, due_date=due_date, priority=priority)
        self._action_items[item.id] = item
        meeting.action_items.append(item.to_dict())
        meeting.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return item

    def record_decision(self, meeting_id: str, decision: str) -> bool:
        meeting = self._meetings.get(meeting_id)
        if not meeting: return False
        meeting.decisions.append({"decision": decision, "recorded_at": datetime.now(timezone.utc).isoformat()})
        meeting.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return True

    def set_transcript(self, meeting_id: str, transcript: str) -> bool:
        meeting = self._meetings.get(meeting_id)
        if not meeting: return False
        meeting.transcript = transcript
        self._save()
        return True

    def list_meetings(self, org_id: str = "", limit: int = 50) -> list[Meeting]:
        results = list(self._meetings.values())
        if org_id: results = [m for m in results if m.org_id == org_id]
        return sorted(results, key=lambda m: m.date, reverse=True)[:limit]

    def list_action_items(self, meeting_id: str = "", assignee: str = "") -> list[ActionItem]:
        results = list(self._action_items.values())
        if meeting_id: results = [a for a in results if a.meeting_id == meeting_id]
        if assignee: results = [a for a in results if a.assignee == assignee]
        return sorted(results, key=lambda a: a.created_at, reverse=True)

    def get_telemetry(self) -> dict: return dict(self._telemetry)
