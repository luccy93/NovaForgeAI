"""Message Bus — event-driven messaging system for integration events, repository, deployment, security, pipeline, agent, billing, analytics, plugin, workflow events."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


class MessagePriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class MessageStatus(Enum):
    PUBLISHED = "published"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class Message:
    id: str
    topic: str
    source: str
    event_type: str
    payload: Any = None
    priority: MessagePriority = MessagePriority.MEDIUM
    status: MessageStatus = MessageStatus.PUBLISHED
    correlation_id: str = ""
    headers: dict = field(default_factory=dict)
    retry_count: int = 0
    max_retries: int = 3
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    delivered_at: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["priority"] = self.priority.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        data = data.copy()
        data["priority"] = MessagePriority(data.get("priority", "medium"))
        data["status"] = MessageStatus(data.get("status", "published"))
        return cls(**data)


@dataclass
class Subscription:
    id: str
    topic: str
    endpoint: str
    handler_type: str = "webhook"
    is_active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "Subscription": return cls(**data)


MESSAGE_TOPICS = [
    "repository", "deployment", "issue", "security", "pipeline",
    "agent", "billing", "analytics", "plugin", "workflow",
    "identity", "monitoring", "notification", "audit", "integration",
]


class MessageBus:
    def __init__(self, storage_dir: str = "integration_data/bus"):
        self.storage_dir = storage_dir
        self._messages: dict[str, Message] = {}
        self._subscriptions: dict[str, Subscription] = {}
        self._handlers: dict[str, list] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _msg_path(self) -> str: return os.path.join(self.storage_dir, "messages.json")
    def _sub_path(self) -> str: return os.path.join(self.storage_dir, "subscriptions.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._msg_path(), self._messages, Message),
            (self._sub_path(), self._subscriptions, Subscription),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Failed to load bus data: %s", e)

    def _save(self) -> None:
        try:
            with open(self._msg_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._messages.items()}, f, indent=2, default=str)
            with open(self._sub_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._subscriptions.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save bus data: %s", e)

    def publish(self, topic: str, source: str, event_type: str, payload: Any = None, priority: MessagePriority = MessagePriority.MEDIUM, correlation_id: str = "") -> Message:
        msg = Message(id=str(uuid.uuid4()), topic=topic, source=source, event_type=event_type, payload=payload, priority=priority, correlation_id=correlation_id or str(uuid.uuid4()))
        self._messages[msg.id] = msg
        self._telemetry["messages_published"] = self._telemetry.get("messages_published", 0) + 1
        self._save()
        self._dispatch(msg)
        return msg

    def subscribe(self, topic: str, endpoint: str, handler_type: str = "webhook") -> Subscription:
        sub = Subscription(id=str(uuid.uuid4()), topic=topic, endpoint=endpoint, handler_type=handler_type)
        self._subscriptions[sub.id] = sub
        self._save()
        return sub

    def unsubscribe(self, sub_id: str) -> bool:
        if sub_id not in self._subscriptions: return False
        self._subscriptions[sub_id].is_active = False
        self._save()
        return True

    def register_handler(self, topic: str, handler) -> None:
        if topic not in self._handlers: self._handlers[topic] = []
        self._handlers[topic].append(handler)

    def _dispatch(self, msg: Message) -> None:
        for sub in self._subscriptions.values():
            if sub.topic == msg.topic and sub.is_active:
                try: msg.status = MessageStatus.DELIVERED
                except Exception as e: logger.error("Delivery failed: %s", e)
        handlers = self._handlers.get(msg.topic, [])
        for h in handlers:
            try: h(msg)
            except Exception as e: logger.error("Handler error: %s", e)

    def get_messages(self, topic: str = "", limit: int = 100) -> list[Message]:
        results = list(self._messages.values())
        if topic: results = [m for m in results if m.topic == topic]
        return sorted(results, key=lambda m: m.created_at, reverse=True)[:limit]

    def get_topics(self) -> list[str]: return MESSAGE_TOPICS

    def get_telemetry(self) -> dict:
        tel = dict(self._telemetry)
        tel["total_messages"] = len(self._messages)
        tel["total_subscriptions"] = len(self._subscriptions)
        return tel
