"""Inbound webhook pipeline — Volume 70 Commit 2.

receive → verify → deduplicate → authorize → normalize → EventBus →
async processing record. Inbound payloads are untrusted: only
allowlisted fields are normalized, privileged operations never execute
directly — they produce a Zero Trust JIT approval request instead.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.common import (
    NotFoundError,
    ValidationError,
    _as_uuid,
    sanitize_metadata,
)
from app.integrations.governed_models import IntegrationAuditLog, IntegrationWebhook
from app.integrations.governed_models_c2 import IntegrationInboundWebhook
from app.integrations.webhooks import verify_inbound

PRIVILEGED_OPERATIONS = (
    "connection.create",
    "credential.rotate",
    "credential.create",
    "execute.destructive",
    "integration.revoke",
)

NORMALIZED_FIELDS = ("event", "id", "timestamp", "repository", "action",
                     "sender", "ref", "status", "conclusion")


def _serialize(row: IntegrationInboundWebhook) -> dict:
    return {
        "id": str(row.id),
        "tenant": row.tenant,
        "webhook_id": str(row.webhook_id),
        "delivery_id": row.delivery_id,
        "event_type": row.event_type or "",
        "status": row.status,
        "approval_id": row.approval_id or "",
    }


def _normalize(payload: dict) -> dict:
    normalized: dict = {}
    for field in NORMALIZED_FIELDS:
        value = (payload or {}).get(field)
        if isinstance(value, (str, int, float, bool)) or value is None:
            normalized[field] = value
        elif isinstance(value, dict):
            normalized[field] = {k: v for k, v in list(value.items())[:10]
                                 if isinstance(v, (str, int, float, bool)) or v is None}
    return normalized


async def receive_inbound(
    db: AsyncSession, webhook_id, headers: dict, raw_body: bytes, *,
    event_type: str = "", delivery_id: str = "", actor: str = "",
) -> dict:
    """Verify, deduplicate and normalize an inbound webhook call."""
    import json as _json

    stmt = select(IntegrationWebhook).where(IntegrationWebhook.id == _as_uuid(webhook_id))
    webhook = (await db.execute(stmt)).scalar_one_or_none()
    if webhook is None or webhook.status != "ACTIVE":
        raise NotFoundError("webhook not found")
    tenant = webhook.tenant

    try:
        payload = _json.loads((raw_body or b"{}").decode())
        if not isinstance(payload, dict):
            payload = {"value": str(payload)[:1024]}
    except Exception:
        raise ValidationError("invalid payload")

    secret = ""
    if webhook.credential_id:
        try:
            from app.integrations.connections import resolve_credential_material
            secret = await resolve_credential_material(
                db, tenant, webhook.credential_id, purpose="webhook_verify", actor="worker")
        except Exception:
            secret = ""
    signature = (headers or {}).get("X-Webhook-Signature") or (headers or {}).get("x-hub-signature-256") or ""
    if signature.startswith("sha256="):
        signature = signature[len("sha256="):]
    if not verify_inbound(payload, signature, secret, delivery_id=delivery_id or ""):
        try:
            from app.integrations.common import emit_event
            await emit_event("webhook_replay_rejected",
                             {"webhook_id": str(webhook.id)}, tenant)
        except Exception:
            pass
        raise ValidationError("signature verification failed")

    key = delivery_id or f"in-{uuid.uuid4().hex}"
    dup = (await db.execute(select(IntegrationInboundWebhook).where(
        IntegrationInboundWebhook.tenant == tenant,
        IntegrationInboundWebhook.delivery_id == key))).scalar_one_or_none()
    if dup is not None:
        return {**_serialize(dup), "deduplicated": True}

    requested_op = str(payload.get("requested_operation") or "")
    approval_id = ""
    status = "RECEIVED"
    if requested_op in PRIVILEGED_OPERATIONS:
        try:
            from app.zero_trust.jit import request_access
            rec = await request_access(
                db, tenant, actor or "webhook", f"integrations:{requested_op}",
                requested_op, f"Inbound webhook requested {requested_op}",
                duration_seconds=3600, scope={"webhook_id": str(webhook.id)},
                privilege_level="HIGH", requested_by=actor or "webhook")
            approval_id = str(rec.id)
            status = "PENDING_APPROVAL"
        except Exception as exc:
            raise ValidationError(f"approval unavailable: {type(exc).__name__}")

    row = IntegrationInboundWebhook(
        webhook_id=webhook.id, tenant=tenant, delivery_id=key,
        event_type=event_type or str(payload.get("event") or ""),
        status=status, approval_id=approval_id,
        metadata_={"normalized": _normalize(payload)},
    )
    # Tenant is authoritative from the webhook record — never from payload.
    row.tenant = tenant
    db.add(row)
    await db.flush()
    db.add(IntegrationAuditLog(
        tenant=tenant, actor=actor or "webhook", action="webhook.received",
        resource_type="webhook", resource_id=str(webhook.id),
        details={"delivery_id": key, "status": status}, status="SUCCESS",
    ))
    await db.flush()
    try:
        from app.integrations.common import emit_event
        await emit_event("webhook_received",
                         {"webhook_id": str(webhook.id), "delivery_id": key,
                          "status": status, "approval_id": approval_id}, tenant)
    except Exception:
        pass
    return _serialize(row)


async def list_inbound(db: AsyncSession, tenant: str, webhook_id, *, limit: int = 100) -> dict:
    stmt = select(IntegrationInboundWebhook).where(
        IntegrationInboundWebhook.tenant == tenant,
        IntegrationInboundWebhook.webhook_id == _as_uuid(webhook_id),
    )
    limit = min(max(int(limit or 100), 1), 1000)
    rows = (await db.execute(stmt.order_by(desc(IntegrationInboundWebhook.created_at)).limit(limit))).scalars().all()
    return {"items": [_serialize(r) for r in rows], "total": len(rows)}
