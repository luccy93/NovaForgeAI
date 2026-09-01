"""Shared helpers for the AI Developer Experience layer — Volume 67."""

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.repository import Repository

MAX_PATCH_FILES = 10
MAX_FIX_ITERATIONS = 3
DEFAULT_TOKEN_BUDGET = 4000
DEFAULT_MAX_FILES = 5
DEFAULT_MAX_SYMBOLS = 20
DEFAULT_TEST_FRAMEWORK = "pytest"
DEFAULT_AGENT_THROTTLE = 5
DEFAULT_AGENT_BUDGET_TOKENS = 120000
MAX_BENCHMARK_PATCHES = 10

READ_PERMISSION = "repository:read"
WRITE_PERMISSION = "repository:write"


class NotFoundError(Exception):
    pass


class PermissionError_(Exception):
    pass


class StalePatchError(Exception):
    pass


class PatchAlreadyAppliedError(Exception):
    pass


def _to_tenant(user) -> str:
    oid = getattr(user, "organization_id", None) or getattr(user, "id", None)
    return str(oid) if oid else ""


def _to_user_id(user) -> str:
    return str(getattr(user, "id", "") or "")


def _as_uuid(value) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


async def resolve_repository(
    db: AsyncSession, tenant: str, repository_id, *, allow_org_mismatch: bool = False
) -> Repository:
    rid = _as_uuid(repository_id)
    repo = await db.get(Repository, rid)
    if repo is None:
        raise NotFoundError("repository not found")
    if tenant and not allow_org_mismatch:
        if repo.organization_id is None:
            raise NotFoundError("repository not found for tenant")
        try:
            tenant_uuid = uuid.UUID(tenant)
        except Exception:
            tenant_uuid = None
        if tenant_uuid is None or repo.organization_id != tenant_uuid:
            raise NotFoundError("repository not found for tenant")
    return repo


async def emit_event(event_name: str, data: dict, tenant: str, source: str = "ai_dev"):
    try:
        from app.core.events import Event, EventType, event_bus

        et = getattr(EventType, event_name, None)
        if et is not None:
            await event_bus.publish_nowait(
                Event(et, data, source=source, organization_id=tenant)
            )
    except Exception:
        pass


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, round(len(text) / 4))


def record_usage_best_effort(tenant: str, action: str, quantity: int = 1):
    try:
        from app.billing.meter_service import record_usage

        record_usage(organization_id=tenant, metric_name="code_ai", quantity=quantity)
    except Exception:
        pass


def ingest_metric_best_effort(metric_name: str, value: float, tags: Optional[dict] = None):
    try:
        from app.observability.platform import ingest_metric

        ingest_metric(metric_name, value, tags=tags or {})
    except Exception:
        pass


async def get_symbols_for_path(
    db: AsyncSession, repository_id, path: str, limit: int = 50
) -> list:
    from app.code_intelligence.models import CodeSymbol

    rows = (
        (
            await db.execute(
                select(CodeSymbol)
                .where(
                    CodeSymbol.repository_id == _as_uuid(repository_id),
                    CodeSymbol.file_path == path,
                )
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)