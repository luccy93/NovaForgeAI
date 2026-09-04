"""Governed integrations API — Volume 70 Commit 1.

Tenant-scoped registry, connections, versioned contracts, bounded API
execution, webhooks, deliveries, subscriptions and health. Authorization
reuses organization:read / settings:admin through the existing policy
authorizer with the superuser convention; explicit deny overrides are
honored. Credential material is never returned.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db as _get_db_session
from app.integrations.common import ADMIN_PERMISSION, READ_PERMISSION

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["Integrations"])


async def _get_db():
    from app.core.database import async_session
    async with async_session() as session:
        yield session


async def _resolve_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(_get_db_session),
):
    try:
        from app.api.auth import _get_current_user
        return await _get_current_user(authorization, db)
    except HTTPException:
        raise
    except Exception:
        class _Anon:
            id = ""
            organization_id = ""
            role = "anonymous"
        return _Anon()


def _tenant(user) -> str:
    oid = getattr(user, "organization_id", None) or getattr(user, "id", None)
    if not oid:
        raise HTTPException(status_code=403, detail="No tenant context")
    return str(oid)


def _iam_check(user, tenant: str, perm: str) -> None:
    if getattr(user, "is_superuser", False):
        return
    try:
        from app.iam.policy_authorizer import policy_authorizer
        result = policy_authorizer.authorize(
            str(getattr(user, "id", "")), tenant, perm,
            context={"role": getattr(user, "role", "user")},
        )
        if isinstance(result, dict) and not result.get("allowed", True):
            raise HTTPException(status_code=403, detail="forbidden")
    except HTTPException:
        raise
    except Exception:
        pass


def _err(exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    from app.integrations.common import ValidationError as _ValidationError
    if isinstance(exc, _ValidationError):
        return HTTPException(status_code=422, detail=f"{type(exc).__name__}: {exc}")
    msg = f"{type(exc).__name__}: {exc}"
    lowered = str(exc).lower()
    if "not found" in lowered:
        return HTTPException(status_code=404, detail=msg)
    if "already exists" in lowered or "duplicate" in lowered:
        return HTTPException(status_code=409, detail=msg)
    if ("required" in lowered or "too large" in lowered or "must be" in lowered
            or "unsupported" in lowered or "unknown" in lowered or "not allowed" in lowered
            or "blocked" in lowered or "invalid" in lowered or "duplicate" in lowered):
        return HTTPException(status_code=422, detail=msg)
    return HTTPException(status_code=500, detail=msg)


def _user_id(user) -> str:
    return str(getattr(user, "id", "") or "")


# ─── Schemas ─────────────────────────────────────────────────────────────────


class IntegrationIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    type: str = Field(..., max_length=32)
    provider: str = ""
    version: str = "1.0.0"
    workspace: str = ""
    environment: str = ""
    region: str = ""
    capabilities: Optional[list] = None
    config: Optional[dict] = None
    owner: str = ""


class IntegrationUpdateIn(BaseModel):
    version: Optional[str] = None
    workspace: Optional[str] = None
    environment: Optional[str] = None
    region: Optional[str] = None
    capabilities: Optional[list] = None
    config: Optional[dict] = None
    owner: Optional[str] = None
    health: Optional[str] = None


class StatusIn(BaseModel):
    status: str


class VersionIn(BaseModel):
    version: str = Field(..., min_length=1, max_length=32)
    contract: Optional[dict] = None
    compatibility: str = "compatible"
    deprecated: bool = False
    migration_notes: str = ""


class ConnectionIn(BaseModel):
    integration_id: str
    workspace: str = ""
    environment: str = ""
    endpoint_ref: str = ""
    scopes: Optional[list] = None


class CredentialIn(BaseModel):
    kind: str
    material: str = Field(..., min_length=1)
    connection_id: Optional[str] = None
    scopes: Optional[list] = None
    expires_at: Optional[str] = None
    auth_config: Optional[dict] = None


class ExecuteIn(BaseModel):
    operation: str = ""
    method: str = "GET"
    path: str = ""
    params: Optional[dict] = None
    idempotency_key: str = ""
    timeout: float = 15.0


class WebhookIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    url: str = Field(..., min_length=1, max_length=1024)
    integration_id: Optional[str] = None
    events: Optional[list] = None
    signing_secret: str = ""


class DeliveryIn(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=128)
    payload: Optional[dict] = None
    delivery_id: str = ""


class SubscriptionIn(BaseModel):
    connection_id: str
    event_filter: Optional[dict] = None
    target_url: str = Field(..., min_length=1, max_length=1024)


# ─── Integrations ────────────────────────────────────────────────────────────


@router.get("")
async def list_integrations(
    status: Optional[str] = None, provider: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.integrations.registry import list_integrations as _list
        return await _list(db, tenant, status=status or "", provider=provider or "", limit=limit)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("", status_code=201)
async def create_integration(
    payload: IntegrationIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.integrations.registry import register_integration as _create
        result = await _create(db, tenant, payload.name, payload.type, **{
            k: v for k, v in payload.model_dump().items() if k not in ("name", "type")
        }, actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/{integration_id}")
async def get_integration(
    integration_id: str,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.integrations.registry import get_integration as _get
        return await _get(db, tenant, integration_id)
    except Exception as exc:
        raise _err(exc) from exc


@router.patch("/{integration_id}")
async def update_integration(
    integration_id: str, payload: IntegrationUpdateIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.integrations.registry import update_integration as _update
        result = await _update(db, tenant, integration_id,
                               {k: v for k, v in payload.model_dump().items() if v is not None},
                               actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/{integration_id}/status")
async def set_status(
    integration_id: str, payload: StatusIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.integrations.registry import set_integration_status as _set
        result = await _set(db, tenant, integration_id, payload.status, actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


# ─── Versions ────────────────────────────────────────────────────────────────


@router.get("/{integration_id}/versions")
async def get_versions(
    integration_id: str,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.integrations.registry import list_versions as _list
        return await _list(db, tenant, integration_id)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/{integration_id}/versions", status_code=201)
async def create_version(
    integration_id: str, payload: VersionIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.integrations.registry import create_version as _create
        result = await _create(db, tenant, integration_id, payload.version, **{
            k: v for k, v in payload.model_dump().items() if k != "version"
        }, actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


# ─── Connections & credentials ───────────────────────────────────────────────


@router.get("/connections/all")
async def get_connections(
    integration_id: Optional[str] = None, status: Optional[str] = None,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.integrations.connections import list_connections as _list
        return await _list(db, tenant, integration_id=integration_id, status=status or "")
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/connections", status_code=201)
async def create_connection(
    payload: ConnectionIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.integrations.connections import create_connection as _create
        result = await _create(db, tenant, payload.integration_id, **{
            k: v for k, v in payload.model_dump().items() if k != "integration_id"
        }, actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/connections/{connection_id}")
async def get_connection(
    connection_id: str,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.integrations.connections import get_connection as _get
        return await _get(db, tenant, connection_id)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/connections/{connection_id}/status")
async def set_connection_status(
    connection_id: str, payload: StatusIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.integrations.connections import set_connection_status as _set
        result = await _set(db, tenant, connection_id, payload.status, actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/credentials", status_code=201)
async def create_credential(
    payload: CredentialIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.integrations.connections import store_credential as _store
        result = await _store(db, tenant, payload.kind, payload.material, **{
            k: v for k, v in payload.model_dump().items() if k not in ("kind", "material")
        }, actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/credentials/{credential_id}/rotate")
async def rotate_credential(
    credential_id: str, payload: dict,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.integrations.connections import rotate_credential as _rotate
        result = await _rotate(db, tenant, credential_id, payload.get("material", ""),
                               actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


# ─── Execution ───────────────────────────────────────────────────────────────


@router.post("/connections/{connection_id}/execute")
async def execute_operation(
    connection_id: str, payload: ExecuteIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.integrations.workers import execute_operation as _execute
        result = await _execute(db, tenant, connection_id, payload.operation, **{
            k: v for k, v in payload.model_dump().items() if k != "operation"
        }, actor=_user_id(current_user))
        await db.commit()
        scrubbed = dict(result)
        return scrubbed
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/connections/{connection_id}/health")
async def connection_health(
    connection_id: str,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.integrations.connections import get_connection as _get
        from app.integrations.workers import run_health_check as _check
        conn = await _get(db, tenant, connection_id)
        result = await _check(db, tenant, conn["integration_id"],
                              connection_id=connection_id, actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


# ─── Webhooks ────────────────────────────────────────────────────────────────


@router.get("/webhooks/all")
async def get_webhooks(
    status: Optional[str] = None,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.integrations.webhooks import list_webhooks as _list
        return await _list(db, tenant, status=status or "")
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/webhooks", status_code=201)
async def create_webhook(
    payload: WebhookIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.integrations.webhooks import register_webhook as _create
        result = await _create(db, tenant, payload.name, payload.url, **{
            k: v for k, v in payload.model_dump().items() if k not in ("name", "url")
        }, actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/webhooks/{webhook_id}")
async def get_webhook(
    webhook_id: str,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.integrations.webhooks import get_webhook as _get
        return await _get(db, tenant, webhook_id)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/webhooks/{webhook_id}/status")
async def set_webhook_status(
    webhook_id: str, payload: StatusIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.integrations.webhooks import set_webhook_status as _set
        result = await _set(db, tenant, webhook_id, payload.status, actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/webhooks/{webhook_id}/deliver", status_code=201)
async def enqueue_delivery(
    webhook_id: str, payload: DeliveryIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.integrations.webhooks import enqueue_delivery as _enqueue
        result = await _enqueue(db, tenant, webhook_id, payload.event_type,
                                payload.payload or {}, delivery_id=payload.delivery_id)
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/webhooks/{webhook_id}/deliveries")
async def get_deliveries(
    webhook_id: str, limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.integrations.webhooks import delivery_history as _history
        return await _history(db, tenant, webhook_id, limit=limit)
    except Exception as exc:
        raise _err(exc) from exc


# ─── Subscriptions ───────────────────────────────────────────────────────────


@router.post("/subscriptions", status_code=201)
async def create_subscription(
    payload: SubscriptionIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.integrations.network_policy import validate_url
        from app.integrations.connections import get_connection as _get_conn
        from app.integrations.governed_models import IntegrationApiSubscription
        import uuid as _uuid
        await _get_conn(db, tenant, payload.connection_id)
        validate_url(payload.target_url)
        row = IntegrationApiSubscription(
            tenant=tenant, connection_id=payload.connection_id,
            event_filter=payload.event_filter or {}, target_url=payload.target_url,
            credential_id=None, status="ACTIVE", metadata_={},
        )
        row.id = _uuid.uuid4()
        db.add(row)
        await db.flush()
        await db.commit()
        return {"id": str(row.id), "tenant": tenant, "status": row.status,
                "target_url": row.target_url}
    except Exception as exc:
        raise _err(exc) from exc
