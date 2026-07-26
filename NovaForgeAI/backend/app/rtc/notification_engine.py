"""Notification Engine — real-time alerts, email, Slack, Teams, webhook, mobile push, digest."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

class NotificationChannel:
    IN_APP = "in_app"; EMAIL = "email"; SLACK = "slack"; TEAMS = "teams"
    DISCORD = "discord"; WEBHOOK = "webhook"; MOBILE = "mobile"; DESKTOP = "desktop"

@dataclass
class Notification:
    id: str; org_id: str; user_id: str; title: str; message: str = ""
    channel: str = NotificationChannel.IN_APP; priority: str = "normal"
    read: bool = False; action_url: str = ""; metadata: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    read_at: str = ""

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "Notification": return cls(**data)

@dataclass
class NotificationDigest:
    id: str; org_id: str; user_id: str; period: str  # daily, weekly
    notifications: list = field(default_factory=list); summary: str = ""
    sent_at: str = ""; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "NotificationDigest": return cls(**data)

class NotificationEngine:
    def __init__(self, storage_dir: str = "rtc_data/notifications"):
        self.storage_dir = storage_dir; self._notifications: dict[str, Notification] = {}
        self._digests: dict[str, NotificationDigest] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _not_path(self) -> str: return os.path.join(self.storage_dir, "notifications.json")
    def _dig_path(self) -> str: return os.path.join(self.storage_dir, "digests.json")

    def _load(self) -> None:
        for path, store, cls in [(self._not_path(), self._notifications, Notification), (self._dig_path(), self._digests, NotificationDigest)]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f: data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._not_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._notifications.items()}, f, indent=2, default=str)
            with open(self._dig_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._digests.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def send(self, org_id: str, user_id: str, title: str, message: str = "", channel: str = NotificationChannel.IN_APP, priority: str = "normal") -> Notification:
        n = Notification(id=str(uuid.uuid4()), org_id=org_id, user_id=user_id, title=title, message=message, channel=channel, priority=priority)
        self._notifications[n.id] = n; self._save(); return n

    def mark_read(self, not_id: str) -> Optional[Notification]:
        n = self._notifications.get(not_id)
        if not n: return None
        n.read = True; n.read_at = datetime.now(timezone.utc).isoformat(); self._save(); return n

    def get_unread(self, user_id: str) -> list[Notification]:
        return sorted([n for n in self._notifications.values() if n.user_id == user_id and not n.read], key=lambda n: n.created_at, reverse=True)

    def create_digest(self, org_id: str, user_id: str, period: str) -> NotificationDigest:
        unread = self.get_unread(user_id)
        d = NotificationDigest(id=str(uuid.uuid4()), org_id=org_id, user_id=user_id, period=period, notifications=[n.to_dict() for n in unread[:20]], summary=f"You have {len(unread)} unread notifications")
        self._digests[d.id] = d; self._save(); return d
