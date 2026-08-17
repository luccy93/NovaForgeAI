"""Webhook event bridge — connects EventBus to webhook delivery.

Subscribes to all EventBus events and triggers webhook deliveries
for webhooks registered to receive those event types.
"""
import asyncio
import logging
from typing import Optional

from app.core.events import Event, EventBus, event_bus, EventType
from app.core.webhooks import webhook_service, WebhookDeliveryStatus

logger = logging.getLogger("novaforge.webhook_bridge")


class WebhookEventBridge:
    """Bridges EventBus events to webhook deliveries.

    For each event published on the EventBus, finds all active webhooks
    subscribed to that event type and triggers async delivery.
    """

    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._webhook_store: dict[str, dict] = {}

    def set_webhook_store(self, store: dict[str, dict]) -> None:
        """Set reference to the webhook store (shared with webhooks API)."""
        self._webhook_store = store

    def get_webhook_store(self) -> dict[str, dict]:
        """Get webhook store reference."""
        return self._webhook_store

    async def start(self) -> None:
        """Start the bridge by subscribing to all event types."""
        if self._running:
            return
        self._running = True
        event_bus.subscribe_all(self._on_event)
        logger.info("Webhook event bridge started")

    async def stop(self) -> None:
        """Stop the bridge."""
        self._running = False
        if self._on_event in event_bus._global_subscribers:
            event_bus._global_subscribers.remove(self._on_event)
        logger.info("Webhook event bridge stopped")

    async def _on_event(self, event: Event) -> None:
        """Handle an event from the EventBus by delivering to matching webhooks."""
        if not self._running:
            return

        event_type = event.event_type.value
        delivered = 0
        failed = 0

        for webhook_id, webhook in self._webhook_store.items():
            if not webhook.get("active", True):
                continue

            subscribed_events = webhook.get("events", [])
            if event_type not in subscribed_events and "*" not in subscribed_events:
                continue

            try:
                url = webhook.get("url")
                if not url:
                    continue

                result = await webhook_service.deliver(
                    webhook_id=webhook_id,
                    url=url,
                    event_type=event_type,
                    payload=event.to_dict(),
                    secret=webhook.get("secret"),
                )

                if result.get("status") == WebhookDeliveryStatus.DELIVERED:
                    delivered += 1
                else:
                    failed += 1
                    logger.warning(
                        "Webhook delivery failed for %s event %s: %s",
                        webhook_id, event_type, result.get("error"),
                    )
            except Exception as e:
                failed += 1
                logger.error("Webhook bridge error for %s: %s", webhook_id, e)

        if delivered > 0 or failed > 0:
            logger.info(
                "Webhook bridge: event=%s delivered=%d failed=%d",
                event_type, delivered, failed,
            )

    async def deliver_test_event(self, webhook_id: str, event_type: str = "test.ping") -> dict:
        """Send a test ping event to a specific webhook."""
        webhook = self._webhook_store.get(webhook_id)
        if not webhook:
            return {"error": "Webhook not found"}

        test_event = Event(
            event_type=EventType(event_type) if event_type in [e.value for e in EventType] else EventType.webhook_delivered,
            data={"test": True, "message": "Ping from NovaForge webhook bridge"},
            source="webhook_bridge",
        )

        result = await webhook_service.deliver(
            webhook_id=webhook_id,
            url=webhook["url"],
            event_type=event_type,
            payload=test_event.to_dict(),
            secret=webhook.get("secret"),
        )
        return result

    def get_stats(self) -> dict:
        """Get bridge statistics."""
        active_webhooks = sum(1 for wh in self._webhook_store.values() if wh.get("active", True))
        return {
            "running": self._running,
            "total_webhooks": len(self._webhook_store),
            "active_webhooks": active_webhooks,
            "event_types_watched": len(EventType),
        }


webhook_bridge = WebhookEventBridge()
