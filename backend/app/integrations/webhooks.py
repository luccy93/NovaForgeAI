"""Secure webhook registration and delivery — Volume 70 Commit 1.

Signing secrets live in the credential store (encrypted); serializers
expose references only. Delivery goes through the governed outbound
client (SSRF-enforced). Retries use bounded exponential backoff with a
dead-letter state; delivery rows are idempotent on
(tenant, delivery_id). Inbound verification reuses the HMAC helpers
with bounded replay protection.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.common import (
    STATUSES,
    NotFoundError,
    ValidationError,
    _as_uuid,
    _ensure_aware,
    _utcnow,
    idempotency_key,
    sanitize_metadata,
)
from app.integrations.governed_models import (
    IntegrationAuditLog,
    IntegrationCredential,
    IntegrationWebhook,
    IntegrationWebhookDelivery,
)
from app.integrations.network_policy import validate_url

MAX_ATTEMPTS = 5
BASE_BACKOFF_SECONDS = 30
MAX_BACKOFF_SECONDS = 3600

# Bounded in-memory replay protection (best-effort; Redis-backed callers
# may add their own). Entries expire after 24h.
_seen_deliveries: dict[str, float] = {}
REPLAY_TTL = 86400


def _serialize_webhook(row: IntegrationWebhook) -> dict:
    return {
        "id": str(row.id),
        "tenant": row.tenant,
        "name": row.name,
        "integration_id": str(row.integration_id) if row.integration_id else None,
        "url": row.url,
        "events": row.events or [],
        "credential_id": str(row.credential_id) if row.credential_id else None,
        "status": row.status,
    }


def _serialize_delivery(row: IntegrationWebhookDelivery) -> dict:
    return {
        "id": str(row.id),
        "tenant": row.tenant,
        "webhook_id": str(row.webhook_id),
        "delivery_id": row.delivery_id,
        "event_type": row.event_type or "",
        "status": row.status,
        "attempts": row.attempts,
        "next_retry_at": row.next_retry_at.isoformat() if row.next_retry_at else None,
        "response_code": row.response_code,
        "response_bytes": row.response_bytes,
        "error": row.error or "",
    }


async def _audit(db: AsyncSession, tenant: str, actor: str, action: str,
                 resource_type: str, resource_id: str, details: dict) -> None:
    db.add(IntegrationAuditLog(
        tenant=tenant, actor=actor or "", action=action,
        resource_type=resource_type, resource_id=resource_id,
        details=sanitize_metadata(details), status="SUCCESS",
    ))
    await db.flush()


async def register_webhook(
    db: AsyncSession, tenant: str, name: str, url: str, *,
    integration_id=None, events: Optional[list] = None,
    signing_secret: str = "", actor: str = "",
) -> dict:
    if not tenant:
        raise ValidationError("tenant required")
    name = (name or "").strip()
    if not name:
        raise ValidationError("name required")
    validate_url(url)
    row = IntegrationWebhook(
        id=uuid.uuid4(), tenant=tenant, name=name,
        integration_id=_as_uuid(integration_id) if integration_id else None,
        url=url, events=[str(e) for e in (events or [])],
        credential_id=None, status="ACTIVE", metadata_={},
    )
    try:
        async with db.begin_nested():
            db.add(row)
            await db.flush()
    except IntegrityError:
        raise ValidationError("webhook already exists")
    if signing_secret:
        from app.integrations.connections import store_credential
        cred = await store_credential(db, tenant, "webhook_secret", signing_secret, actor=actor)
        row.credential_id = uuid.UUID(cred["id"])
        await db.flush()
    await _audit(db, tenant, actor, "webhook.create", "webhook", str(row.id), {"name": name, "url": url})
    return _serialize_webhook(row)


async def get_webhook(db: AsyncSession, tenant: str, webhook_id) -> dict:
    stmt = select(IntegrationWebhook).where(
        IntegrationWebhook.id == _as_uuid(webhook_id),
        IntegrationWebhook.tenant == tenant,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise NotFoundError("webhook not found")
    return _serialize_webhook(row)


async def list_webhooks(db: AsyncSession, tenant: str, *, status: str = "", limit: int = 100) -> dict:
    stmt = select(IntegrationWebhook).where(IntegrationWebhook.tenant == tenant)
    if status:
        stmt = stmt.where(IntegrationWebhook.status == status)
    limit = min(max(int(limit or 100), 1), 1000)
    rows = (await db.execute(stmt.order_by(desc(IntegrationWebhook.created_at)).limit(limit))).scalars().all()
    return {"items": [_serialize_webhook(r) for r in rows], "total": len(rows)}


async def set_webhook_status(db: AsyncSession, tenant: str, webhook_id, status: str, *, actor: str = "") -> dict:
    if status not in STATUSES:
        raise ValidationError(f"invalid status: {status!r}")
    stmt = select(IntegrationWebhook).where(
        IntegrationWebhook.id == _as_uuid(webhook_id),
        IntegrationWebhook.tenant == tenant,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise NotFoundError("webhook not found")
    row.status = status
    await db.flush()
    await _audit(db, tenant, actor, f"webhook.{status.lower()}", "webhook", str(row.id), {"status": status})
    return _serialize_webhook(row)


async def enqueue_delivery(
    db: AsyncSession, tenant: str, webhook_id, event_type: str, payload: dict, *,
    delivery_id: str = "",
) -> dict:
    stmt = select(IntegrationWebhook).where(
        IntegrationWebhook.id == _as_uuid(webhook_id),
        IntegrationWebhook.tenant == tenant,
    )
    webhook = (await db.execute(stmt)).scalar_one_or_none()
    if webhook is None:
        raise NotFoundError("webhook not found")
    if webhook.status != "ACTIVE":
        raise ValidationError(f"webhook is {webhook.status}")
    if webhook.events and event_type not in webhook.events:
        raise ValidationError(f"event '{event_type}' not subscribed")
    key = delivery_id or idempotency_key(tenant, str(webhook.id), event_type, str(sorted((payload or {}).keys())))
    # Sanitize: never persist secrets inside delivery metadata.
    row = IntegrationWebhookDelivery(
        id=uuid.uuid4(), tenant=tenant, webhook_id=webhook.id, delivery_id=key,
        event_type=event_type, status="PENDING", attempts=0,
        next_retry_at=_utcnow(), response_bytes=0,
        metadata_={"payload_keys": sorted((payload or {}).keys())},
    )
    try:
        async with db.begin_nested():
            db.add(row)
            await db.flush()
    except IntegrityError:
        dup = (await db.execute(select(IntegrationWebhookDelivery).where(
            IntegrationWebhookDelivery.tenant == tenant,
            IntegrationWebhookDelivery.delivery_id == key,
        ))).scalar_one_or_none()
        if dup is None:
            raise
        return {**_serialize_delivery(dup), "deduplicated": True}
    try:
        from app.integrations.common import emit_event
        await emit_event("webhook_delivery_queued", {"webhook_id": str(webhook.id), "delivery_id": key}, tenant)
    except Exception:
        pass
    return _serialize_delivery(row)


def _backoff(attempt: int) -> datetime:
    delay = min(BASE_BACKOFF_SECONDS * (2 ** max(attempt - 1, 0)), MAX_BACKOFF_SECONDS)
    return _utcnow() + timedelta(seconds=delay)


async def deliver_attempt(db: AsyncSession, tenant: str, delivery_id: str, payload: dict) -> dict:
    """Execute one delivery attempt. Returns the updated delivery dict."""
    from app.core.webhooks import WebhookService
    from app.integrations.outbound import execute as outbound

    id_conditions = [IntegrationWebhookDelivery.delivery_id == delivery_id]
    try:
        id_conditions.append(IntegrationWebhookDelivery.id == uuid.UUID(str(delivery_id)))
    except (ValueError, AttributeError, TypeError):
        pass
    stmt = select(IntegrationWebhookDelivery).where(
        IntegrationWebhookDelivery.tenant == tenant,
        (id_conditions[0] if len(id_conditions) == 1 else (id_conditions[0] | id_conditions[1])),
    )
    delivery = (await db.execute(stmt)).scalar_one_or_none()
    if delivery is None:
        raise NotFoundError("delivery not found")
    if delivery.status in ("DELIVERED", "DEAD_LETTER"):
        return {**_serialize_delivery(delivery), "deduplicated": True}

    wh_stmt = select(IntegrationWebhook).where(
        IntegrationWebhook.id == delivery.webhook_id,
        IntegrationWebhook.tenant == tenant,
    )
    webhook = (await db.execute(wh_stmt)).scalar_one_or_none()
    if webhook is None or webhook.status != "ACTIVE":
        delivery.status = "DEAD_LETTER"
        delivery.error = "webhook unavailable"
        await db.flush()
        return _serialize_delivery(delivery)

    secret = ""
    if webhook.credential_id:
        try:
            from app.integrations.connections import resolve_credential_material
            secret = await resolve_credential_material(
                db, tenant, webhook.credential_id, purpose="webhook_sign", actor="worker")
        except Exception:
            secret = ""
    import json as _json
    body = _json.dumps({"event": delivery.event_type, "id": delivery.delivery_id,
                        "payload": payload}, sort_keys=True).encode()
    headers = {"Content-Type": "application/json", "X-Webhook-ID": str(webhook.id),
               "X-Webhook-Event": delivery.event_type, "X-Delivery-ID": delivery.delivery_id}
    if secret:
        headers["X-Webhook-Signature"] = WebhookService.sign_payload(
            {"event": delivery.event_type, "id": delivery.delivery_id, "payload": payload}, secret)

    delivery.attempts = (delivery.attempts or 0) + 1
    try:
        result = await outbound(tenant=tenant, method="POST", url=webhook.url,
                                headers=headers, body=body, timeout=15.0,
                                rate_limit_key=f"integrations:{tenant}:webhook:{webhook.id}",
                                rate_limit_max=120, max_attempts=1, actor="worker")
        delivery.response_code = result["status_code"]
        delivery.response_bytes = result["bytes"]
        if 200 <= result["status_code"] < 300:
            delivery.status = "DELIVERED"
            delivery.error = ""
            try:
                from app.integrations.common import emit_event
                await emit_event("webhook_delivery_succeeded",
                                 {"webhook_id": str(webhook.id), "delivery_id": delivery.delivery_id}, tenant)
            except Exception:
                pass
        elif delivery.attempts >= MAX_ATTEMPTS:
            delivery.status = "DEAD_LETTER"
            delivery.error = f"http_{result['status_code']}"
            try:
                from app.integrations.common import emit_event
                await emit_event("webhook_delivery_failed",
                                 {"webhook_id": str(webhook.id), "delivery_id": delivery.delivery_id,
                                  "reason": "max_attempts"}, tenant)
            except Exception:
                pass
        else:
            delivery.status = "RETRYING"
            delivery.next_retry_at = _backoff(delivery.attempts)
            delivery.error = f"http_{result['status_code']}"
    except Exception as exc:
        delivery.response_bytes = 0
        if delivery.attempts >= MAX_ATTEMPTS:
            delivery.status = "DEAD_LETTER"
            delivery.error = f"{type(exc).__name__}"
            try:
                from app.integrations.common import emit_event
                await emit_event("webhook_delivery_failed",
                                 {"webhook_id": str(webhook.id), "delivery_id": delivery.delivery_id,
                                  "reason": "max_attempts"}, tenant)
            except Exception:
                pass
        else:
            delivery.status = "RETRYING"
            delivery.next_retry_at = _backoff(delivery.attempts)
            delivery.error = f"{type(exc).__name__}"
    await db.flush()
    return _serialize_delivery(delivery)


async def delivery_history(db: AsyncSession, tenant: str, webhook_id, *, limit: int = 100) -> dict:
    stmt = select(IntegrationWebhookDelivery).where(
        IntegrationWebhookDelivery.tenant == tenant,
        IntegrationWebhookDelivery.webhook_id == _as_uuid(webhook_id),
    )
    limit = min(max(int(limit or 100), 1), 1000)
    rows = (await db.execute(stmt.order_by(desc(IntegrationWebhookDelivery.created_at)).limit(limit))).scalars().all()
    return {"items": [_serialize_delivery(r) for r in rows], "total": len(rows)}


def verify_inbound(payload: dict, signature: str, secret: str, *, delivery_id: str = "") -> bool:
    """Verify an inbound webhook signature with bounded replay protection."""
    from app.core.webhooks import WebhookService

    if delivery_id:
        now = time.time()
        seen = _seen_deliveries.get(delivery_id)
        for key in [k for k, ts in _seen_deliveries.items() if ts < now - REPLAY_TTL]:
            _seen_deliveries.pop(key, None)
        if seen and seen > now - REPLAY_TTL:
            return False
        _seen_deliveries[delivery_id] = now
    if not secret or not signature:
        return False
    try:
        return bool(WebhookService.verify_signature(payload, signature, secret))
    except Exception:
        return False
