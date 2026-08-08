"""Collaborative Chat — shared conversations, team/org/repo conversations, user/agent mentions, shared prompt library, conversation history, AI summaries."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class ChatScope(Enum):
    SHARED = "shared"
    TEAM = "team"
    ORGANIZATION = "organization"
    REPOSITORY = "repository"
    DIRECT = "direct"


@dataclass
class ChatMessage:
    id: str
    conversation_id: str
    user_id: str
    content: str
    role: str = "user"
    mentions: list = field(default_factory=list)
    agent_mentions: list = field(default_factory=list)
    attachments: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "ChatMessage": return cls(**data)


@dataclass
class Conversation:
    id: str
    org_id: str
    title: str
    scope: ChatScope
    channel_id: str = ""
    participants: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    is_archived: bool = False
    message_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_summary: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["scope"] = self.scope.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Conversation":
        data = data.copy()
        data["scope"] = ChatScope(data.get("scope", "team"))
        return cls(**data)


class CollaborativeChat:
    def __init__(self, storage_dir: str = "collab_data/chat"):
        self.storage_dir = storage_dir
        self._conversations: dict[str, Conversation] = {}
        self._messages: dict[str, ChatMessage] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _conv_path(self) -> str: return os.path.join(self.storage_dir, "conversations.json")
    def _msg_path(self) -> str: return os.path.join(self.storage_dir, "messages.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._conv_path(), self._conversations, Conversation),
            (self._msg_path(), self._messages, ChatMessage),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Failed to load chat data: %s", e)

    def _save(self) -> None:
        try:
            with open(self._conv_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._conversations.items()}, f, indent=2, default=str)
            with open(self._msg_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._messages.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save chat data: %s", e)

    def create_conversation(self, title: str, org_id: str, scope: ChatScope, channel_id: str = "", participants: list = None) -> Conversation:
        conv = Conversation(id=str(uuid.uuid4()), org_id=org_id, title=title, scope=scope, channel_id=channel_id, participants=participants or [])
        self._conversations[conv.id] = conv
        self._save()
        return conv

    def send_message(self, conversation_id: str, user_id: str, content: str, role: str = "user", mentions: list = None, agent_mentions: list = None) -> Optional[ChatMessage]:
        conv = self._conversations.get(conversation_id)
        if not conv: return None
        msg = ChatMessage(id=str(uuid.uuid4()), conversation_id=conversation_id, user_id=user_id, content=content, role=role, mentions=mentions or [], agent_mentions=agent_mentions or [])
        self._messages[msg.id] = msg
        conv.message_count += 1
        conv.updated_at = datetime.now(timezone.utc).isoformat()
        if user_id not in conv.participants: conv.participants.append(user_id)
        self._save()
        return msg

    def get_conversation(self, conv_id: str) -> Optional[Conversation]: return self._conversations.get(conv_id)

    def get_messages(self, conversation_id: str, limit: int = 100) -> list[ChatMessage]:
        msgs = [m for m in self._messages.values() if m.conversation_id == conversation_id]
        return sorted(msgs, key=lambda m: m.created_at)[-limit:]

    def list_conversations(self, org_id: str = "", user_id: str = "", scope: Optional[ChatScope] = None) -> list[Conversation]:
        results = list(self._conversations.values())
        if org_id: results = [c for c in results if c.org_id == org_id]
        if user_id: results = [c for c in results if user_id in c.participants]
        if scope: results = [c for c in results if c.scope == scope]
        return sorted(results, key=lambda c: c.updated_at, reverse=True)

    def generate_summary(self, conversation_id: str) -> Optional[str]:
        conv = self._conversations.get(conversation_id)
        if not conv: return None
        msgs = self.get_messages(conversation_id, limit=50)
        summary = f"Conversation '{conv.title}' with {len(msgs)} messages by {len(set(m.user_id for m in msgs))} participants."
        conv.last_summary = summary
        self._save()
        return summary

    def archive_conversation(self, conv_id: str) -> bool:
        conv = self._conversations.get(conv_id)
        if not conv: return False
        conv.is_archived = True
        self._save()
        return True

    def get_telemetry(self) -> dict: return dict(self._telemetry)
