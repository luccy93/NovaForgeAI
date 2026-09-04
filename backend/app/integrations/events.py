"""Integration event emitters — Volume 70 Commit 1.

Best-effort EventBus emission; integration state never depends on it.
"""

from __future__ import annotations

from app.integrations.common import emit_event


async def integration_created(tenant: str, payload: dict) -> None:
    await emit_event("integration_created", payload, tenant)


async def integration_updated(tenant: str, payload: dict) -> None:
    await emit_event("integration_updated", payload, tenant)


async def integration_disabled(tenant: str, payload: dict) -> None:
    await emit_event("integration_disabled", payload, tenant)


async def integration_revoked(tenant: str, payload: dict) -> None:
    await emit_event("integration_revoked", payload, tenant)


async def health_changed(tenant: str, payload: dict) -> None:
    await emit_event("integration_health_changed", payload, tenant)


async def delivery_succeeded(tenant: str, payload: dict) -> None:
    await emit_event("webhook_delivery_succeeded", payload, tenant)


async def delivery_failed(tenant: str, payload: dict) -> None:
    await emit_event("webhook_delivery_failed", payload, tenant)
