"""Governed integrations shared helpers — Volume 70 Commit 1."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

READ_PERMISSION = "organization:read"
ADMIN_PERMISSION = "settings:admin"

MAX_QUERY_DAYS = 90
MAX_RESULTS = 1000

STATUSES = ("ACTIVE", "DISABLED", "DEGRADED", "QUARANTINED", "REVOKED")
TYPES = ("webhook", "api", "oauth", "connector")
HEALTH_STATES = ("UNKNOWN", "HEALTHY", "DEGRADED", "UNHEALTHY")


class IntegrationError(Exception):
    pass


class NotFoundError(IntegrationError):
    pass


class ValidationError(IntegrationError):
    pass


class AuthError(IntegrationError):
    pass


class NetworkPolicyError(ValidationError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_tenant(user) -> str:
    oid = getattr(user, "organization_id", None) or getattr(user, "id", None)
    return str(oid) if oid else ""


def _to_user_id(user) -> str:
    return str(getattr(user, "id", "") or "")


def _as_uuid(value) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_time(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return _ensure_aware(value)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return _ensure_aware(parsed)


def idempotency_key(*parts: str) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()


def sanitize_metadata(metadata: Optional[dict]) -> dict:
    if not metadata:
        return {}
    dangerous = {"password", "secret", "token", "api_key", "private_key", "auth_token",
                 "credentials", "authorization", "client_secret", "refresh_token", "access_token"}
    clean: dict[str, Any] = {}
    for key, value in metadata.items():
        if str(key).lower() in dangerous or "secret" in str(key).lower() or "token" in str(key).lower():
            clean[key] = "[REDACTED]"
        else:
            clean[key] = value
    return clean


async def emit_event(event_name: str, data: dict, tenant: str) -> None:
    try:
        from app.core.events import Event, EventType, event_bus

        event_type = getattr(EventType, event_name, None)
        if event_type is None:
            return
        await event_bus.publish_nowait(Event(event_type, data, source="integrations", organization_id=tenant))
    except Exception:
        pass
