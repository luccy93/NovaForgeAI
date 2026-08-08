"""Real-Time Collaboration — live presence, repo updates, AI chat, agent progress, code review, search, architecture updates, notifications, activity feed via streaming events."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


class RealtimeEventType(Enum):
    PRESENCE = "presence"
    REPOSITORY_UPDATE = "repository_update"
    AI_CHAT = "ai_chat"
    AGENT_PROGRESS = "agent_progress"
    CODE_REVIEW = "code_review"
    SEARCH = "search"
    ARCHITECTURE_UPDATE = "architecture_update"
    NOTIFICATION = "notification"
    ACTIVITY_FEED = "activity_feed"
    WORKSPACE_UPDATE = "workspace_update"


class RealtimeChannel(Enum):
    WORKSPACE = "workspace"
    REPOSITORY = "repository"
    TEAM = "team"
    ORGANIZATION = "organization"
    USER = "user"
    GLOBAL = "global"


@dataclass
class RealtimeEvent:
    id: str
    event_type: RealtimeEventType
    channel: RealtimeChannel
    channel_id: str
    user_id: str
    data: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["event_type"] = self.event_type.value
        d["channel"] = self.channel.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RealtimeEvent":
        data = data.copy()
        data["event_type"] = RealtimeEventType(data.get("event_type", "presence"))
        data["channel"] = RealtimeChannel(data.get("channel", "workspace"))
        return cls(**data)


@dataclass
class ChannelSubscription:
    id: str
    user_id: str
    channel: RealtimeChannel
    channel_id: str
    is_active: bool = True
    subscribed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["channel"] = self.channel.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ChannelSubscription":
        data = data.copy()
        data["channel"] = RealtimeChannel(data.get("channel", "workspace"))
        return cls(**data)


class RealtimeService:
    def __init__(self, storage_dir: str = "collab_data/realtime"):
        self.storage_dir = storage_dir
        self._events: list[RealtimeEvent] = []
        self._subscriptions: dict[str, ChannelSubscription] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _events_path(self) -> str: return os.path.join(self.storage_dir, "events.json")
    def _subs_path(self) -> str: return os.path.join(self.storage_dir, "subscriptions.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._events_path(), None, None),
            (self._subs_path(), self._subscriptions, ChannelSubscription),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if cls:
                        for k, v in data.items():
                            try: store[k] = cls.from_dict(v)
                            except Exception as e: logger.warning("Skipping %s: %s", k, e)
                    else:
                        self._events = [RealtimeEvent.from_dict(e) for e in data]
                except Exception as e: logger.error("Failed to load realtime data: %s", e)

    def _save(self) -> None:
        try:
            with open(self._events_path(), "w", encoding="utf-8") as f:
                json.dump([e.to_dict() for e in self._events[-5000:]], f, indent=2, default=str)
            with open(self._subs_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._subscriptions.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save realtime data: %s", e)

    def publish(self, event_type: RealtimeEventType, channel: RealtimeChannel, channel_id: str, user_id: str, data: dict = None) -> RealtimeEvent:
        event = RealtimeEvent(id=str(uuid.uuid4()), event_type=event_type, channel=channel, channel_id=channel_id, user_id=user_id, data=data or {})
        self._events.append(event)
        self._telemetry["events_published"] = self._telemetry.get("events_published", 0) + 1
        self._save()
        return event

    def subscribe(self, user_id: str, channel: RealtimeChannel, channel_id: str) -> ChannelSubscription:
        sub = ChannelSubscription(id=str(uuid.uuid4()), user_id=user_id, channel=channel, channel_id=channel_id)
        self._subscriptions[sub.id] = sub
        self._save()
        return sub

    def unsubscribe(self, sub_id: str) -> bool:
        if sub_id not in self._subscriptions: return False
        self._subscriptions[sub_id].is_active = False
        self._save()
        return True

    def get_channel_events(self, channel: RealtimeChannel, channel_id: str, since: str = "", limit: int = 100) -> list[RealtimeEvent]:
        results = [e for e in self._events if e.channel == channel and e.channel_id == channel_id]
        if since: results = [e for e in results if e.timestamp > since]
        return results[-limit:]

    def get_subscribers(self, channel: RealtimeChannel, channel_id: str) -> list[ChannelSubscription]:
        return [s for s in self._subscriptions.values() if s.channel == channel and s.channel_id == channel_id and s.is_active]

    def get_user_events(self, user_id: str, limit: int = 100) -> list[RealtimeEvent]:
        return [e for e in self._events if e.user_id == user_id][-limit:]

    def get_telemetry(self) -> dict: return dict(self._telemetry)
