"""Billing event handler — emits billing events via the event bus and handles incoming events."""
import logging
from typing import Optional
from app.core.events import Event, EventType, event_bus

logger = logging.getLogger(__name__)


async def emit_billing_event(
    event_type: EventType,
    data: dict,
    organization_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Event:
    event = Event(
        event_type=event_type,
        data=data,
        source="billing",
        organization_id=organization_id,
        user_id=user_id,
    )
    try:
        await event_bus.publish_nowait(event)
    except Exception as exc:
        logger.warning("Failed to emit billing event %s: %s", event_type.value, exc)
    return event


async def emit_subscription_created(subscription: dict) -> Event:
    return await emit_billing_event(
        EventType.billing_subscription_changed,
        {"action": "created", "subscription": subscription},
        organization_id=subscription.get("organization_id"),
    )


async def emit_subscription_changed(subscription: dict, action: str) -> Event:
    return await emit_billing_event(
        EventType.billing_subscription_changed,
        {"action": action, "subscription": subscription},
        organization_id=subscription.get("organization_id"),
    )


async def emit_payment_succeeded(payment: dict) -> Event:
    return await emit_billing_event(
        EventType.billing_subscription_changed,
        {"action": "payment_succeeded", "payment": payment},
        organization_id=payment.get("organization_id"),
    )


async def emit_payment_failed(payment: dict, reason: str = "") -> Event:
    return await emit_billing_event(
        EventType.billing_payment_failed,
        {"payment": payment, "reason": reason},
        organization_id=payment.get("organization_id"),
    )


async def emit_invoice_created(invoice: dict) -> Event:
    return await emit_billing_event(
        EventType.billing_subscription_changed,
        {"action": "invoice_created", "invoice": invoice},
        organization_id=invoice.get("organization_id"),
    )


async def emit_usage_threshold_exceeded(
    organization_id: str,
    metric_name: str,
    current_usage: float,
    limit: float,
) -> Event:
    return await emit_billing_event(
        EventType.billing_subscription_changed,
        {
            "action": "usage_threshold_exceeded",
            "metric_name": metric_name,
            "current_usage": current_usage,
            "limit": limit,
        },
        organization_id=organization_id,
    )


async def emit_budget_alert(
    organization_id: str,
    budget_id: str,
    status: str,
    spent_cents: int,
    limit_cents: int,
) -> Event:
    event_type = (
        EventType.billing_payment_failed
        if status == "hard_limit"
        else EventType.billing_subscription_changed
    )
    return await emit_billing_event(
        event_type,
        {
            "action": "budget_alert",
            "budget_id": budget_id,
            "status": status,
            "spent_cents": spent_cents,
            "limit_cents": limit_cents,
        },
        organization_id=organization_id,
    )


def get_billing_event_handlers() -> dict:
    return {
        "subscription_created": emit_subscription_created,
        "subscription_changed": emit_subscription_changed,
        "payment_succeeded": emit_payment_succeeded,
        "payment_failed": emit_payment_failed,
        "invoice_created": emit_invoice_created,
    }
