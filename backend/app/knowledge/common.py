"""Shared helpers for the Universal Knowledge & Search Platform — Volume 68."""

import hashlib
import uuid
from typing import Optional

SEARCH_PERMISSION = "knowledge:read"
WRITE_PERMISSION = "knowledge:write"
ADMIN_PERMISSION = "knowledge:admin"

MAX_CHUNK_SIZE = 1500
MAX_CHUNK_OVERLAP = 200
DEFAULT_VECTOR_DIM = 384
MAX_QUERY_LENGTH = 2000
MAX_RESULTS = 100
DEFAULT_RESULTS = 20
MAX_INGESTION_BATCH = 50
FRESHNESS_STALE_HOURS = 168
MAX_GRAPH_DEPTH = 4
MAX_GRAPH_RESULTS = 50


class NotFoundError(Exception):
    pass


class PermissionDeniedError(Exception):
    pass


class StaleContentError(Exception):
    pass


class DuplicateIngestionError(Exception):
    pass


class SecurityViolationError(Exception):
    pass


def _to_tenant(user) -> str:
    oid = getattr(user, "organization_id", None) or getattr(user, "id", None)
    return str(oid) if oid else ""


def _to_user_id(user) -> str:
    return str(getattr(user, "id", "") or "")


def _as_uuid(value) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, round(len(text) / 4))


def compute_content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


async def emit_event(event_name: str, data: dict, tenant: str, source: str = "knowledge"):
    try:
        from app.core.events import Event, EventType, event_bus

        et = getattr(EventType, event_name, None)
        if et is not None:
            await event_bus.publish_nowait(
                Event(et, data, source=source, organization_id=tenant)
            )
    except Exception:
        pass


def record_usage_best_effort(tenant: str, action: str, quantity: int = 1):
    try:
        from app.billing.meter_service import meter_service

        meter_service.record_usage(
            organization_id=tenant, metric=f"knowledge.{action}",
            value=quantity, unit="count",
        )
    except Exception:
        pass


def ingest_metric_best_effort(metric_name: str, value: float, tags: Optional[dict] = None):
    try:
        from app.observability.platform import ObservabilityPlatform
        op = ObservabilityPlatform()
        try:
            import asyncio
            loop = asyncio.get_running_loop()
            loop.create_task(
                op.ingest_metric(None, tenant=(tags or {}).get("tenant", "default"), metric=metric_name, type="gauge", value=value, tags=tags or {})
            )
        except RuntimeError:
            pass
    except Exception:
        pass
