"""Governed integrations intelligence API — Volume 70 Commit 2.

OAuth lifecycle, connectors, inbound webhooks, policies, health
summaries, FinOps/Knowledge/Workflow/AI bridges. Reuses the C1 auth
helpers; everything is tenant-scoped and bounded.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.api import (
    ADMIN_PERMISSION,
    READ_PERMISSION,
    _err,
    _get_db,
    _iam_check,
    _resolve_user,
    _tenant,
    _user_id,
)

router = APIRouter(prefix="/integrations", tags=["Integrations"])


class OAuthStartIn(BaseModel):
    integration_id: str
    provider: str = ""
    client_id: str = Field(..., min_length=1, max_length=256)
    scopes: Optional[list] = None
    redirect_uri: str = Field(..., min_length=1, max_length=1024)
    authorization_endpoint: str = Field(..., min_length=1, max_length=1024)


class OAuthCallbackIn(BaseModel):
    state: str = Field(..., min_length=1)
    code: str = Field(..., min_length=1)
    token_endpoint: str = Field(..., min_length=1, max_length=1024)


class OAuthRefreshIn(BaseModel):
    token_endpoint: str = Field(..., min_length=1, max_length=1024)


class ConnectorRegisterIn(BaseModel):
    connector_key: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    base_url: str = ""
    workspace: str = ""
    environment: str = ""
    owner: str = ""


class ConnectorConnectIn(BaseModel):
    integration_id: str
    material: str = Field(..., min_length=1)
    workspace: str = ""
    environment: str = ""
    endpoint_ref: str = ""
    auth_config: Optional[dict] = None
    allowed_methods: Optional[list] = None


class ConnectorSyncIn(BaseModel):
    sync_key: str = ""
    paths: Optional[list] = None


class InboundIn(BaseModel):
    headers: Optional[dict] = None
    body: Optional[dict] = None
    event_type: str = ""
    delivery_id: str = ""


class PolicyIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    workspace: str = ""
    project: str = ""
    provider: str = ""
    operation: str = ""
    action: str = "alert"
    allowed_classifications: Optional[list] = None
    allowed_regions: Optional[list] = None
    allowed_fields: Optional[list] = None
    max_estimated_cents: Optional[int] = None
    owner: str = ""


class PolicyUpdateIn(BaseModel):
    workspace: Optional[str] = None
    project: Optional[str] = None
    provider: Optional[str] = None
    operation: Optional[str] = None
    action: Optional[str] = None
    allowed_classifications: Optional[list] = None
    allowed_regions: Optional[list] = None
    allowed_fields: Optional[list] = None
    max_estimated_cents: Optional[int] = None
    enabled: Optional[bool] = None
    owner: Optional[str] = None


class TransferEvaluateIn(BaseModel):
    workspace: str = ""
    project: str = ""
    provider: str = ""
    operation: str = ""
    classification: str = ""
    region: str = ""
    fields: Optional[list] = None
    estimated_cents: int = 0


class AIActionIn(BaseModel):
    operation: str = ""
    target_url: str = ""
    method: str = "GET"
    model: str = ""
    provider: str = ""


# ─── OAuth ───────────────────────────────────────────────────────────────────


@router.post("/oauth/start", status_code=201)
async def oauth_start(
    payload: OAuthStartIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.integrations.oauth import start_oauth as _start
        result = await _start(db, tenant, payload.integration_id, **{
            k: v for k, v in payload.model_dump().items() if k != "integration_id"
        }, actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/oauth/callback")
async def oauth_callback(
    payload: OAuthCallbackIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.integrations.oauth import oauth_callback as _callback
        result = await _callback(db, tenant, payload.state, payload.code,
                                 token_endpoint=payload.token_endpoint,
                                 actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/oauth")
async def oauth_list(
    status: Optional[str] = None,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.integrations.oauth import list_oauth as _list
        return await _list(db, tenant, status=status or "")
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/oauth/{oauth_id}")
async def oauth_get(
    oauth_id: str,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.integrations.oauth import get_oauth as _get
        return await _get(db, tenant, oauth_id)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/oauth/{oauth_id}/refresh")
async def oauth_refresh(
    oauth_id: str, payload: OAuthRefreshIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.integrations.oauth import refresh_oauth as _refresh
        result = await _refresh(db, tenant, oauth_id,
                                token_endpoint=payload.token_endpoint,
                                actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/oauth/{oauth_id}/revoke")
async def oauth_revoke(
    oauth_id: str,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.integrations.oauth import revoke_oauth as _revoke
        result = await _revoke(db, tenant, oauth_id, actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


# ─── Connectors ──────────────────────────────────────────────────────────────


@router.get("/connectors/available")
async def connectors_available(
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.integrations.connectors import discover_connectors as _discover
        return {"items": _discover()}
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/connectors/register", status_code=201)
async def connectors_register(
    payload: ConnectorRegisterIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.integrations.connectors import register_connector as _register
        result = await _register(db, tenant, payload.connector_key, payload.name, **{
            k: v for k, v in payload.model_dump().items()
            if k not in ("connector_key", "name")
        }, actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/connectors/connect", status_code=201)
async def connectors_connect(
    payload: ConnectorConnectIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.integrations.connectors import connect_connector as _connect
        result = await _connect(db, tenant, payload.integration_id, payload.material, **{
            k: v for k, v in payload.model_dump().items()
            if k not in ("integration_id", "material")
        }, actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/connections/{connection_id}/connector-health")
async def connectors_health(
    connection_id: str,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.integrations.connectors import connector_health as _health
        result = await _health(db, tenant, connection_id, actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/connections/{connection_id}/sync")
async def connectors_sync(
    connection_id: str, payload: ConnectorSyncIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.integrations.connectors import connector_sync as _sync
        result = await _sync(db, tenant, connection_id, sync_key=payload.sync_key,
                             paths=payload.paths, actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/connections/{connection_id}/syncs")
async def connectors_syncs(
    connection_id: str,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.integrations.connectors import list_syncs as _list
        return await _list(db, tenant, connection_id)
    except Exception as exc:
        raise _err(exc) from exc


# ─── Inbound webhooks ────────────────────────────────────────────────────────


@router.post("/webhooks/{webhook_id}/inbound", status_code=201)
async def inbound_receive(
    webhook_id: str, payload: InboundIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        import json as _json
        from app.integrations.inbound import receive_inbound as _receive
        raw = _json.dumps(payload.body or {}).encode()
        result = await _receive(db, webhook_id, payload.headers or {}, raw,
                                event_type=payload.event_type,
                                delivery_id=payload.delivery_id,
                                actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/webhooks/{webhook_id}/inbound")
async def inbound_list(
    webhook_id: str,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.integrations.inbound import list_inbound as _list
        return await _list(db, tenant, webhook_id)
    except Exception as exc:
        raise _err(exc) from exc


# ─── Policies ────────────────────────────────────────────────────────────────


@router.get("/policies")
async def policies_list(
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.integrations.policies import list_policies as _list
        return await _list(db, tenant)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/policies", status_code=201)
async def policies_create(
    payload: PolicyIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.integrations.policies import create_policy as _create
        result = await _create(db, tenant, payload.name, **{
            k: v for k, v in payload.model_dump().items() if k != "name"
        }, actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.patch("/policies/{policy_id}")
async def policies_update(
    policy_id: str, payload: PolicyUpdateIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.integrations.policies import update_policy as _update
        result = await _update(db, tenant, policy_id,
                               {k: v for k, v in payload.model_dump().items() if v is not None},
                               actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/policies/evaluate-transfer")
async def policies_evaluate(
    payload: TransferEvaluateIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.integrations.policies import evaluate_transfer as _evaluate
        return await _evaluate(db, tenant, **payload.model_dump(), actor=_user_id(current_user))
    except Exception as exc:
        raise _err(exc) from exc


# ─── Health summary ──────────────────────────────────────────────────────────


@router.get("/integrations/{integration_id}/health-summary")
async def health_summary(
    integration_id: str, days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.integrations.health import health_summary as _summary
        return await _summary(db, tenant, integration_id, days=days)
    except Exception as exc:
        raise _err(exc) from exc


# ─── Bridges ─────────────────────────────────────────────────────────────────


@router.post("/connections/{connection_id}/finops-usage", status_code=201)
async def bridge_finops_usage(
    connection_id: str, payload: dict,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.integrations.bridges import record_integration_usage as _record
        result = await _record(db, tenant, connection_id, payload.get("operation", ""), **{
            k: v for k, v in payload.items() if k != "operation"
        }, actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/integrations/{integration_id}/knowledge-source", status_code=201)
async def bridge_knowledge_source(
    integration_id: str, payload: dict,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.integrations.bridges import link_knowledge_source as _link
        result = await _link(db, tenant, integration_id,
                             source_type=payload.get("source_type", "external"),
                             name=payload.get("name", ""), actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/connections/{connection_id}/workflow-invoke")
async def bridge_workflow_invoke(
    connection_id: str, payload: dict,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.integrations.bridges import invoke_from_workflow as _invoke
        result = await _invoke(db, tenant, connection_id, payload.get("operation", ""), **{
            k: v for k, v in payload.items() if k != "operation"
        }, actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/ai/request-action")
async def bridge_ai_action(
    payload: AIActionIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.integrations.bridges import ai_request_action as _request
        result = await _request(db, tenant, _user_id(current_user), **payload.model_dump())
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc
