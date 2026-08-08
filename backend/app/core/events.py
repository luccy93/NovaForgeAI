"""Event bus — pub/sub, async events, persistence, replay, ordering."""

import json
import uuid
import asyncio
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional

from app.core.config import settings
from app.core.redis import get_redis


class EventType(str, Enum):
    repository_created = "repository.created"
    repository_updated = "repository.updated"
    repository_deleted = "repository.deleted"
    repository_imported = "repository.imported"
    organization_created = "organization.created"
    organization_updated = "organization.updated"
    organization_deleted = "organization.deleted"
    user_created = "user.created"
    user_updated = "user.updated"
    user_deleted = "user.deleted"
    agent_run_completed = "agent.run.completed"
    agent_run_failed = "agent.run.failed"
    pipeline_completed = "pipeline.completed"
    deployment_started = "deployment.started"
    deployment_completed = "deployment.completed"
    deployment_failed = "deployment.failed"
    security_alert = "security.alert"
    security_scan_completed = "security.scan.completed"
    billing_subscription_changed = "billing.subscription.changed"
    billing_payment_failed = "billing.payment.failed"
    notification_sent = "notification.sent"
    webhook_delivered = "webhook.delivered"
    webhook_failed = "webhook.failed"
    plugin_installed = "plugin.installed"
    plugin_uninstalled = "plugin.uninstalled"
    plugin_updated = "plugin.updated"


class Event:
    def __init__(
        self,
        event_type: EventType,
        data: dict,
        source: str = "system",
        organization_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        self.id = str(uuid.uuid4())
        self.event_type = event_type
        self.data = data
        self.source = source
        self.organization_id = organization_id
        self.user_id = user_id
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.version = "1.0"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.event_type.value,
            "data": self.data,
            "source": self.source,
            "organization_id": self.organization_id,
            "user_id": self.user_id,
            "timestamp": self.timestamp,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        e = cls.__new__(cls)
        e.id = d.get("id", str(uuid.uuid4()))
        e.event_type = EventType(d["type"])
        e.data = d.get("data", {})
        e.source = d.get("source", "system")
        e.organization_id = d.get("organization_id")
        e.user_id = d.get("user_id")
        e.timestamp = d.get("timestamp", datetime.now(timezone.utc).isoformat())
        e.version = d.get("version", "1.0")
        return e


EventHandler = Callable[[Event], Any]


class EventBus:
    """Async event bus with Redis persistence, in-memory subscribers, and replay."""

    def __init__(self):
        self._subscribers: dict[EventType, list[EventHandler]] = {}
        self._global_subscribers: list[EventHandler] = []
        self._running = False
        self._queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None

    def subscribe(self, event_type: EventType, handler: EventHandler):
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    def subscribe_all(self, handler: EventHandler):
        self._global_subscribers.append(handler)

    def unsubscribe(self, event_type: EventType, handler: EventHandler):
        if event_type in self._subscribers:
            self._subscribers[event_type] = [h for h in self._subscribers[event_type] if h is not handler]

    async def publish(self, event: Event) -> None:
        await self._persist(event)
        await self._queue.put(event)

    async def publish_nowait(self, event: Event) -> None:
        await self._persist(event)
        for handler in self._subscribers.get(event.event_type, []):
            await self._safe_call(handler, event)
        for handler in self._global_subscribers:
            await self._safe_call(handler, event)

    async def _persist(self, event: Event) -> None:
        try:
            redis = await get_redis()
            key = f"events:{event.event_type.value}:{event.id}"
            await redis.setex(key, 86400 * 7, json.dumps(event.to_dict()))
            await redis.lpush(f"events:recent:{event.event_type.value}", json.dumps(event.to_dict()))
            await redis.ltrim(f"events:recent:{event.event_type.value}", 0, 999)
        except Exception:
            pass

    async def _safe_call(self, handler: EventHandler, event: Event) -> None:
        try:
            result = handler(event)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            pass

    async def start(self):
        self._running = True
        self._worker_task = asyncio.create_task(self._process_queue())

    async def stop(self):
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def _process_queue(self):
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                for handler in self._subscribers.get(event.event_type, []):
                    await self._safe_call(handler, event)
                for handler in self._global_subscribers:
                    await self._safe_call(handler, event)
            except asyncio.TimeoutError:
                continue
            except Exception:
                continue

    async def replay(self, event_type: Optional[EventType] = None, limit: int = 100) -> list[Event]:
        events = []
        try:
            redis = await get_redis()
            if event_type:
                raw = await redis.lrange(f"events:recent:{event_type.value}", 0, limit - 1)
            else:
                raw = []
                for et in EventType:
                    batch = await redis.lrange(f"events:recent:{et.value}", 0, limit // len(EventType))
                    raw.extend(batch)
            for item in raw:
                try:
                    events.append(Event.from_dict(json.loads(item)))
                except Exception:
                    continue
        except Exception:
            pass
        return events

    async def get_recent(self, event_type: Optional[str] = None, limit: int = 50) -> list[dict]:
        events = await self.replay(
            EventType(event_type) if event_type else None,
            limit,
        )
        return [e.to_dict() for e in events]


event_bus = EventBus()
