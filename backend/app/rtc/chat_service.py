"""Chat Service — enterprise channels, threads, DMs, typing, history, search."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class Channel:
    id: str; org_id: str; name: str; channel_type: str = "team"  # repo, project, team, org, security, arch, devops, release, ai
    topic: str = ""; members: list = field(default_factory=list); is_private: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

@dataclass
class Message:
    id: str; channel_id: str; sender_id: str; content: str
    message_type: str = "text"; thread_id: str = ""
    mentions: list = field(default_factory=list); attachments: list = field(default_factory=list)
    edited: bool = False; edited_at: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "Message": return cls(**data)

class ChatService:
    def __init__(self, storage_dir: str = "rtc_data/chat"):
        self.storage_dir = storage_dir; self._channels: dict[str, Channel] = {}
        self._messages: dict[str, Message] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _ch_path(self) -> str: return os.path.join(self.storage_dir, "channels.json")
    def _msg_path(self) -> str: return os.path.join(self.storage_dir, "messages.json")

    def _load(self) -> None:
        for path, store, store_cls in [(self._ch_path(), self._channels, Channel), (self._msg_path(), self._messages, Message)]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f: data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = store_cls(**v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._ch_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() if hasattr(v, 'to_dict') else asdict(v) for k, v in self._channels.items()}, f, indent=2, default=str)
            with open(self._msg_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._messages.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create_channel(self, org_id: str, name: str, channel_type: str = "team") -> Channel:
        c = Channel(id=str(uuid.uuid4()), org_id=org_id, name=name, channel_type=channel_type)
        self._channels[c.id] = c; self._save(); return c

    def send_message(self, channel_id: str, sender_id: str, content: str, message_type: str = "text", mentions: list = None) -> Optional[Message]:
        if channel_id not in self._channels: return None
        m = Message(id=str(uuid.uuid4()), channel_id=channel_id, sender_id=sender_id, content=content, message_type=message_type, mentions=mentions or [])
        self._messages[m.id] = m; self._save(); return m

    def get_messages(self, channel_id: str, limit: int = 50) -> list[Message]:
        return sorted([m for m in self._messages.values() if m.channel_id == channel_id], key=lambda m: m.created_at, reverse=True)[:limit]

    def get_channels(self, org_id: str) -> list[Channel]:
        return [c for c in self._channels.values() if c.org_id == org_id]

    def get_telemetry(self) -> dict: return {"channels": len(self._channels), "messages": len(self._messages)}
