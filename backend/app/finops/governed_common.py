"""Governed FinOps shared helpers — Volume 69 Commit 1.

Tenant scoping, deterministic hashing, bounded ranges, and best-effort
event emission. Financial writes themselves are never best-effort; only
the side-channel event emission is.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

READ_PERMISSION = "billing:read"
ADMIN_PERMISSION = "billing:admin"

MAX_QUERY_DAYS = 90
MAX_RESULTS = 1000
DEFAULT_RESULTS = 100

COST_BASIS_ACTUAL = "actual"
COST_BASIS_ESTIMATED = "estimated"
COST_BASIS_UNPRICED = "unpriced"

GRANULARITIES = ("hour", "day", "week", "month")

BUDGET_STATUSES = ("ACTIVE", "WARNING", "EXCEEDED", "SUSPENDED", "CLOSED")
ENFORCEMENTS = ("alert", "require_approval", "block")


class FinOpsError(Exception):
    pass


class NotFoundError(FinOpsError):
    pass


class ValidationError(FinOpsError):
    pass


class AuthError(FinOpsError):
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


def clamp_range(start: Optional[datetime], end: Optional[datetime], *, max_days: int = MAX_QUERY_DAYS) -> tuple[datetime, datetime]:
    now = _utcnow()
    end = _ensure_aware(end) if end else now
    start = _ensure_aware(start) if start else end
    if start > end:
        raise ValidationError("start must be <= end")
    if (end - start).days > max_days:
        raise ValidationError(f"date range too large (max {max_days} days)")
    return start, end


def dimensions_hash(dimensions: dict) -> str:
    payload = json.dumps({k: (v or "") for k, v in sorted(dimensions.items())}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def idempotency_key(*parts: str) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()


def sanitize_metadata(metadata: Optional[dict]) -> dict:
    """Strip secret-bearing keys before persistence."""
    if not metadata:
        return {}
    dangerous = {"password", "secret", "token", "api_key", "private_key", "auth_token", "credentials", "authorization"}
    clean: dict[str, Any] = {}
    for key, value in metadata.items():
        if str(key).lower() in dangerous:
            clean[key] = "[REDACTED]"
        else:
            clean[key] = value
    return clean


async def emit_finops_event(event_name: str, data: dict, tenant: str) -> None:
    try:
        from app.core.events import Event, EventType, event_bus

        event_type = getattr(EventType, event_name, None)
        if event_type is None:
            return
        await event_bus.publish_nowait(Event(event_type, data, source="finops", organization_id=tenant))
    except Exception:
        pass
