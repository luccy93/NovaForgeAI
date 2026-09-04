"""Reusable connector framework — Volume 70 Commit 2.

Fixed lifecycle (DISCOVER, REGISTER, AUTHORIZE, CONNECT, HEALTH_CHECK,
SYNC, EXECUTE, DISABLE, REVOKE) over governed primitives. Built-in
connector definitions declare base URLs, auth kinds, capabilities and
health endpoints; connector actions are fixed code paths over data
parameters — connectors can never execute caller-supplied code.
Enterprise provider ABCs in app.enterprise.providers remain the
interface reference; live calls always go through outbound.py.
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
    _utcnow,
    idempotency_key,
    sanitize_metadata,
)
from app.integrations.governed_models import IntegrationAuditLog, IntegrationConnection
from app.integrations.governed_models_c2 import IntegrationConnectorSync

BUILTIN_CONNECTORS = {
    "github": {
        "provider": "github", "base_url": "https://api.github.com",
        "auth_kind": "bearer", "capabilities": ["execute", "sync", "health"],
        "health_endpoint": "https://api.github.com/rate_limit",
        "allowlist": ["api.github.com"],
        "sync_paths": ["/user/repos?per_page=100"],
    },
    "gitlab": {
        "provider": "gitlab", "base_url": "https://gitlab.com/api/v4",
        "auth_kind": "bearer", "capabilities": ["execute", "sync", "health"],
        "health_endpoint": "https://gitlab.com/api/v4/version",
        "allowlist": ["gitlab.com"],
        "sync_paths": ["/projects?per_page=100"],
    },
    "slack": {
        "provider": "slack", "base_url": "https://slack.com/api",
        "auth_kind": "bearer", "capabilities": ["execute", "health"],
        "health_endpoint": "https://slack.com/api/api.test",
        "allowlist": ["slack.com"],
        "sync_paths": [],
    },
    "jira": {
        "provider": "jira", "base_url": "",
        "auth_kind": "basic", "capabilities": ["execute", "sync", "health"],
        "health_endpoint": "",
        "allowlist": [],
        "sync_paths": [],
    },
    "generic_rest": {
        "provider": "generic", "base_url": "",
        "auth_kind": "api_key", "capabilities": ["execute", "health"],
        "health_endpoint": "",
        "allowlist": [],
        "sync_paths": [],
    },
}

SYNC_MAX_PAGES = 10


def discover_connectors() -> list[dict]:
    return [{"key": key, "provider": spec["provider"], "capabilities": spec["capabilities"],
             "auth_kind": spec["auth_kind"]} for key, spec in BUILTIN_CONNECTORS.items()]


async def _audit(db: AsyncSession, tenant: str, actor: str, action: str, resource_id: str, details: dict) -> None:
    db.add(IntegrationAuditLog(
        tenant=tenant, actor=actor or "", action=action,
        resource_type="connector", resource_id=resource_id,
        details=sanitize_metadata(details), status="SUCCESS",
    ))
    await db.flush()


async def register_connector(
    db: AsyncSession, tenant: str, connector_key: str, name: str, *,
    base_url: str = "", workspace: str = "", environment: str = "",
    owner: str = "", actor: str = "",
) -> dict:
    from app.integrations.registry import register_integration

    spec = BUILTIN_CONNECTORS.get(connector_key)
    if spec is None:
        raise ValidationError(f"unknown connector: {connector_key!r}")
    resolved_base = base_url or spec["base_url"]
    if connector_key == "jira" and not resolved_base:
        raise ValidationError("jira requires an explicit base_url")
    if connector_key == "generic_rest" and not resolved_base:
        raise ValidationError("generic_rest requires an explicit base_url")
    integration = await register_integration(
        db, tenant, name, "connector", provider=spec["provider"],
        workspace=workspace, environment=environment,
        capabilities=list(spec["capabilities"]),
        config={"connector_key": connector_key, "base_url": resolved_base,
                "auth_kind": spec["auth_kind"], "allowlist": spec["allowlist"],
                "sync_paths": list(spec["sync_paths"])},
        owner=owner, actor=actor)
    await _audit(db, tenant, actor, "connector.register", integration["id"],
                 {"connector_key": connector_key})
    return {**integration, "connector_key": connector_key}


async def connect_connector(
    db: AsyncSession, tenant: str, integration_id, material: str, *,
    workspace: str = "", environment: str = "", endpoint_ref: str = "",
    auth_config: Optional[dict] = None, allowed_methods: Optional[list] = None,
    actor: str = "",
) -> dict:
    """AUTHORIZE + CONNECT: store credential, create connection, link them."""
    from app.integrations.connections import create_connection, store_credential
    from app.integrations.registry import get_integration

    integration = await get_integration(db, tenant, integration_id)
    config = integration.get("config") or {}
    base = endpoint_ref or config.get("base_url") or ""
    if not base:
        raise ValidationError("no endpoint available for this connector")
    connection = await create_connection(
        db, tenant, integration_id, workspace=workspace, environment=environment,
        endpoint_ref=base, actor=actor)
    kind_map = {"bearer": "bearer", "api_key": "api_key", "basic": "basic"}
    auth_kind = (config.get("auth_kind") or "api_key")
    cred = await store_credential(
        db, tenant, kind_map.get(auth_kind, "api_key"), material,
        connection_id=connection["id"], auth_config=auth_config or {}, actor=actor)
    if allowed_methods:
        from app.integrations.governed_models import IntegrationConnection as _Conn
        stmt = select(_Conn).where(_Conn.id == _as_uuid(connection["id"]), _Conn.tenant == tenant)
        row = (await db.execute(stmt)).scalar_one_or_none()
        if row is not None:
            row.metadata_ = {"allowed_methods": [str(m).upper() for m in allowed_methods]}
            await db.flush()
    await _audit(db, tenant, actor, "connector.connect", connection["id"],
                 {"integration_id": str(integration["id"])})
    return {**connection, "credential": cred}


async def connector_health(db: AsyncSession, tenant: str, connection_id, *, actor: str = "") -> dict:
    from app.integrations.governed_models import IntegrationConnection as _Conn
    from app.integrations.outbound import execute as outbound

    stmt = select(_Conn).where(_Conn.id == _as_uuid(connection_id), _Conn.tenant == tenant)
    connection = (await db.execute(stmt)).scalar_one_or_none()
    if connection is None:
        raise NotFoundError("connection not found")
    from app.integrations.registry import get_integration
    integration = await get_integration(db, tenant, connection.integration_id)
    config = integration.get("config") or {}
    target = config.get("health_endpoint") or connection.endpoint_ref or ""
    if not target:
        return {"connection_id": str(connection.id), "status": "UNKNOWN",
                "detail": "no health endpoint configured"}
    allowlist = config.get("allowlist") or None
    try:
        result = await outbound(
            tenant=tenant, method="HEAD", url=target, timeout=10.0, max_attempts=1,
            allowlist=allowlist,
            rate_limit_key=f"integrations:{tenant}:connector-health",
            rate_limit_max=60, actor=actor)
        code = result["status_code"]
        status = "HEALTHY" if code < 400 else ("DEGRADED" if code < 500 else "UNHEALTHY")
    except Exception as exc:
        status, code = "UNHEALTHY", None
        result = {"latency_ms": 0}
        _detail = f"{type(exc).__name__}"
    from app.integrations.connections import record_connection_result
    await record_connection_result(db, tenant, connection.id, success=(status == "HEALTHY"))
    await _audit(db, tenant, actor, "connector.health", str(connection.id), {"status": status})
    out: dict = {"connection_id": str(connection.id), "status": status,
                 "latency_ms": result.get("latency_ms", 0)}
    if code is not None:
        out["status_code"] = code
    else:
        out["detail"] = _detail
    return out


async def connector_sync(
    db: AsyncSession, tenant: str, connection_id, *, sync_key: str = "",
    paths: Optional[list] = None, actor: str = "",
) -> dict:
    """Bounded sync: fixed paths, capped pages, idempotent by sync key."""
    from app.integrations.governed_models import IntegrationConnection as _Conn
    from app.integrations.outbound import execute as outbound
    from app.integrations.workers import _credential_auth_config
    from app.integrations.connections import resolve_credential_material

    stmt = select(_Conn).where(_Conn.id == _as_uuid(connection_id), _Conn.tenant == tenant)
    connection = (await db.execute(stmt)).scalar_one_or_none()
    if connection is None:
        raise NotFoundError("connection not found")
    if connection.status != "ACTIVE":
        raise ValidationError(f"connection is {connection.status}")
    from app.integrations.registry import get_integration
    integration = await get_integration(db, tenant, connection.integration_id)
    config = integration.get("config") or {}
    if "sync" not in (integration.get("capabilities") or []):
        raise ValidationError("connector does not implement sync")

    key = sync_key or idempotency_key(tenant, str(connection.id), "sync",
                                      _utcnow().strftime("%Y-%m-%d-%H"))
    dup = (await db.execute(select(IntegrationConnectorSync).where(
        IntegrationConnectorSync.tenant == tenant,
        IntegrationConnectorSync.sync_key == key))).scalar_one_or_none()
    if dup is not None:
        return {"sync_key": key, "status": dup.status, "pages": dup.pages,
                "records": dup.records, "deduplicated": True}

    managed_auth = None
    if connection.credential_id:
        material = await resolve_credential_material(
            db, tenant, connection.credential_id, purpose="connector_sync", actor=actor)
        auth_cfg = await _credential_auth_config(db, tenant, connection.credential_id)
        if auth_cfg.get("header"):
            managed_auth = {"header": str(auth_cfg["header"]), "value": material}
        elif material:
            managed_auth = {"header": "Authorization",
                            "value": f"{auth_cfg.get('scheme', 'Bearer')} {material}"}

    sync_row = IntegrationConnectorSync(
        tenant=tenant, connection_id=connection.id, sync_key=key,
        status="STARTED", metadata_={},
    )
    db.add(sync_row)
    await db.flush()

    base = (connection.endpoint_ref or "").rstrip("/")
    targets = paths or config.get("sync_paths") or []
    allowlist = config.get("allowlist") or None
    pages, records, error = 0, 0, ""
    try:
        from app.integrations.common import emit_event
        await emit_event("connector_sync_started", {"connection_id": str(connection.id),
                                                    "sync_key": key}, tenant)
    except Exception:
        pass
    try:
        for rel in targets[:SYNC_MAX_PAGES]:
            target = f"{base}/{rel.lstrip('/')}" if base else rel
            result = await outbound(
                tenant=tenant, method="GET", url=target, timeout=15.0, max_attempts=2,
                allowlist=allowlist, managed_auth=managed_auth,
                rate_limit_key=f"integrations:{tenant}:sync:{connection.id}",
                rate_limit_max=60, actor=actor)
            pages += 1
            if result["status_code"] >= 400:
                error = f"http_{result['status_code']}"
                break
            try:
                import json as _json
                data = _json.loads((result["body"] or b"[]").decode())
                records += len(data) if isinstance(data, list) else 1
            except Exception:
                records += 1
        sync_row.status = "COMPLETED" if not error else "FAILED"
        sync_row.pages, sync_row.records, sync_row.error = pages, records, error[:500]
    except Exception as exc:
        sync_row.status = "FAILED"
        sync_row.pages, sync_row.records = pages, records
        sync_row.error = f"{type(exc).__name__}"[:500]
        error = sync_row.error
    await db.flush()
    try:
        from app.integrations.common import emit_event
        await emit_event("connector_sync_completed" if not error else "connector_sync_failed",
                         {"connection_id": str(connection.id), "sync_key": key,
                          "pages": pages, "records": records}, tenant)
    except Exception:
        pass
    await _audit(db, tenant, actor, "connector.sync", str(connection.id),
                 {"sync_key": key, "status": sync_row.status})
    return {"sync_key": key, "status": sync_row.status, "pages": pages,
            "records": records, "error": error}


def _utcnow():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


async def list_syncs(db: AsyncSession, tenant: str, connection_id, *, limit: int = 50) -> dict:
    from sqlalchemy import desc as _desc
    stmt = select(IntegrationConnectorSync).where(
        IntegrationConnectorSync.tenant == tenant,
        IntegrationConnectorSync.connection_id == _as_uuid(connection_id),
    )
    limit = min(max(int(limit or 50), 1), 1000)
    rows = (await db.execute(stmt.order_by(_desc(IntegrationConnectorSync.created_at)).limit(limit))).scalars().all()
    return {"items": [{"sync_key": r.sync_key, "status": r.status, "pages": r.pages,
                       "records": r.records, "error": r.error or ""} for r in rows],
            "total": len(rows)}
