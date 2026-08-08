"""Collaboration Bus — event bus, pub/sub, message queue, routing, delivery."""
import json, uuid, os, logging, asyncio
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Any, Callable

logger = logging.getLogger(__name__)

@dataclass
class BusMessage:
    id: str; topic: str; sender_id: str; payload: dict
    priority: int = 0; ttl_seconds: int = 300
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "BusMessage": return cls(**data)

class CollaborationBus:
    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = {}
        self._history: list[BusMessage] = []
        self._telemetry: dict = {"published": 0, "delivered": 0, "topics": 0}

    def subscribe(self, topic: str, handler: Callable) -> None:
        if topic not in self._subscribers: self._subscribers[topic] = []; self._telemetry["topics"] += 1
        self._subscribers[topic].append(handler)

    def unsubscribe(self, topic: str, handler: Callable) -> bool:
        if topic in self._subscribers and handler in self._subscribers[topic]:
            self._subscribers[topic].remove(handler); return True
        return False

    async def publish(self, topic: str, sender_id: str, payload: dict, priority: int = 0) -> int:
        msg = BusMessage(id=str(uuid.uuid4()), topic=topic, sender_id=sender_id, payload=payload, priority=priority)
        self._history.append(msg)
        self._telemetry["published"] += 1
        count = 0
        for handler in self._subscribers.get(topic, []):
            try:
                if asyncio.iscoroutinefunction(handler): await handler(msg)
                else: handler(msg)
                count += 1
            except Exception as e: logger.error("Handler error on %s: %s", topic, e)
        self._telemetry["delivered"] += count
        return count

    def get_history(self, topic: str = "", limit: int = 100) -> list[BusMessage]:
        results = self._history if not topic else [m for m in self._history if m.topic == topic]
        return sorted(results, key=lambda m: m.created_at, reverse=True)[:limit]

    def get_telemetry(self) -> dict: return dict(self._telemetry)
