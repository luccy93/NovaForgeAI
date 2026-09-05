"""Central governance plane shared helpers — Volume 71 Commit 1."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

READ_PERMISSION = "organization:read"
ADMIN_PERMISSION = "settings:admin"

MAX_RESULTS = 1000
MAX_RULES = 50
MAX_CONDITION_DEPTH = 3
MAX_POLICY_BYTES = 65536

POLICY_STATUSES = ("DRAFT", "VALIDATING", "ACTIVE", "SUPERSEDED", "RETIRED")
VERSION_STATUSES = ("DRAFT", "VALIDATING", "ACTIVE", "SUPERSEDED", "RETIRED")
DECISIONS = ("ALLOW", "DENY", "REQUIRE_APPROVAL")
EFFECTS = ("allow", "deny", "require_approval")
SCOPE_TYPES = ("organization", "tenant", "workspace", "resource")
EXCEPTION_STATUSES = ("PENDING", "APPROVED", "DENIED", "EXPIRED", "REVOKED")

CONDITION_OPS = ("equals", "not_equals", "in", "not_in", "contains",
                 "greater_than", "less_than", "exists", "not_exists")
# Fixed allowlisted context schema — unknown fields are dropped, never read.
CONTEXT_FIELDS = ("organization", "tenant", "workspace", "project", "repository",
                  "workflow", "integration", "model", "provider", "dataset",
                  "resource", "environment", "region", "classification",
                  "operation", "action", "actor", "risk", "cost_cents")


class GovernanceError(Exception):
    pass


class NotFoundError(GovernanceError):
    pass


class ValidationError(GovernanceError):
    pass


class AuthError(GovernanceError):
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


def canonical_checksum(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def request_hash(tenant: str, scope_type: str, scope_value: str, operation: str, context: dict) -> str:
    return canonical_checksum([tenant, scope_type, scope_value, operation, context])


def sanitize_context(context: Optional[dict]) -> dict:
    """Keep only allowlisted scalar fields; drop secrets and nesting abuse."""
    if not context:
        return {}
    clean: dict[str, Any] = {}
    for key, value in context.items():
        if key not in CONTEXT_FIELDS:
            continue
        lowered = str(key).lower()
        if "secret" in lowered or "token" in lowered or "password" in lowered or "key" in lowered:
            continue
        if value is None or isinstance(value, (str, int, float, bool)):
            clean[key] = value
        elif isinstance(value, list) and all(isinstance(v, (str, int, float, bool)) for v in value[:20]):
            clean[key] = list(value[:20])
    return clean


def sanitize_metadata(metadata: Optional[dict]) -> dict:
    if not metadata:
        return {}
    dangerous = {"password", "secret", "token", "api_key", "private_key", "auth_token",
                 "credentials", "authorization", "client_secret", "refresh_token", "access_token"}
    clean: dict[str, Any] = {}
    for key, value in metadata.items():
        lowered = str(key).lower()
        if lowered in dangerous or "secret" in lowered or "token" in lowered:
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
        await event_bus.publish_nowait(Event(event_type, data, source="governance", organization_id=tenant))
    except Exception:
        pass
