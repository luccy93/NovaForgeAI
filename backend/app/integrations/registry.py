"""Governed integration registry — Volume 70 Commit 1.

Registration, versioning, status lifecycle and capability enforcement.
Capabilities are explicit per integration type; undeclared capabilities
are rejected so an integration can never claim what it does not
implement. Version rows are immutable history.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.common import (
    HEALTH_STATES,
    STATUSES,
    TYPES,
    NotFoundError,
    ValidationError,
    _as_uuid,
    sanitize_metadata,
)
from app.integrations.governed_models import Integration, IntegrationAuditLog, IntegrationVersion

CAPABILITIES_BY_TYPE = {
    "webhook": ("receive", "deliver", "sign", "verify"),
    "api": ("execute", "sync", "health"),
    "oauth": ("authorize", "refresh", "revoke"),
    "connector": ("execute", "sync", "health", "discover"),
}

COMPATIBILITIES = ("compatible", "deprecated", "breaking")


def _serialize(row: Integration) -> dict:
    return {
        "id": str(row.id),
        "tenant": row.tenant,
        "name": row.name,
        "type": row.type,
        "provider": row.provider or "",
        "version": row.version,
        "workspace": row.workspace or "",
        "environment": row.environment or "",
        "region": row.region or "",
        "capabilities": row.capabilities or [],
        "status": row.status,
        "health": row.health,
        "config": row.config or {},
        "owner": row.owner or "",
    }


def _check_capabilities(integration_type: str, capabilities: list) -> list[str]:
    allowed = CAPABILITIES_BY_TYPE.get(integration_type, ())
    caps = [str(c) for c in (capabilities or [])]
    unknown = [c for c in caps if c not in allowed]
    if unknown:
        raise ValidationError(f"capabilities not implemented for type '{integration_type}': {unknown}")
    return caps


async def _audit(db: AsyncSession, tenant: str, actor: str, action: str, resource_id: str, details: dict) -> None:
    db.add(IntegrationAuditLog(
        tenant=tenant, actor=actor or "", action=action,
        resource_type="integration", resource_id=resource_id,
        details=sanitize_metadata(details), status="SUCCESS",
    ))
    await db.flush()


async def register_integration(
    db: AsyncSession, tenant: str, name: str, integration_type: str, *,
    provider: str = "", version: str = "1.0.0", workspace: str = "",
    environment: str = "", region: str = "", capabilities: Optional[list] = None,
    config: Optional[dict] = None, owner: str = "", actor: str = "",
) -> dict:
    if not tenant:
        raise ValidationError("tenant required")
    name = (name or "").strip()
    if not name:
        raise ValidationError("name required")
    if integration_type not in TYPES:
        raise ValidationError(f"unsupported type: {integration_type!r}")
    caps = _check_capabilities(integration_type, capabilities or [])
    row = Integration(
        id=uuid.uuid4(), tenant=tenant, name=name, type=integration_type,
        provider=provider or "", version=version or "1.0.0",
        workspace=workspace or "", environment=environment or "", region=region or "",
        capabilities=caps, status="ACTIVE", health="UNKNOWN",
        config=sanitize_metadata(config), owner=owner or "",
        metadata_={},
    )
    try:
        async with db.begin_nested():
            db.add(row)
            await db.flush()
    except IntegrityError:
        raise ValidationError("integration already exists")
    db.add(IntegrationVersion(
        tenant=tenant, integration_id=row.id, version=row.version,
        contract={"capabilities": caps}, compatibility="compatible",
        deprecated=False, migration_notes="", metadata_={},
    ))
    await db.flush()
    await _audit(db, tenant, actor, "integration.create", str(row.id), {"name": name, "type": integration_type})
    try:
        from app.integrations.common import emit_event
        await emit_event("integration_created", {"id": str(row.id), "name": name}, tenant)
    except Exception:
        pass
    return _serialize(row)


async def get_integration(db: AsyncSession, tenant: str, integration_id) -> dict:
    stmt = select(Integration).where(Integration.id == _as_uuid(integration_id), Integration.tenant == tenant)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise NotFoundError("integration not found")
    return _serialize(row)


async def list_integrations(db: AsyncSession, tenant: str, *, status: str = "", provider: str = "", limit: int = 100) -> dict:
    stmt = select(Integration).where(Integration.tenant == tenant)
    if status:
        stmt = stmt.where(Integration.status == status)
    if provider:
        stmt = stmt.where(Integration.provider == provider)
    limit = min(max(int(limit or 100), 1), 1000)
    rows = (await db.execute(stmt.order_by(desc(Integration.created_at)).limit(limit))).scalars().all()
    return {"items": [_serialize(r) for r in rows], "total": len(rows)}


async def update_integration(db: AsyncSession, tenant: str, integration_id, updates: dict, *, actor: str = "") -> dict:
    stmt = select(Integration).where(Integration.id == _as_uuid(integration_id), Integration.tenant == tenant)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise NotFoundError("integration not found")
    allowed = ("version", "workspace", "environment", "region", "config", "owner", "health")
    applied: dict = {}
    for key in allowed:
        if key in updates and updates[key] is not None:
            setattr(row, key, updates[key] if key != "config" else sanitize_metadata(updates[key]))
            applied[key] = updates[key]
    if "capabilities" in updates and updates["capabilities"] is not None:
        row.capabilities = _check_capabilities(row.type, updates["capabilities"])
        applied["capabilities"] = updates["capabilities"]
    await db.flush()
    await _audit(db, tenant, actor, "integration.update", str(row.id), applied)
    try:
        from app.integrations.common import emit_event
        await emit_event("integration_updated", {"id": str(row.id)}, tenant)
    except Exception:
        pass
    return _serialize(row)


async def set_integration_status(db: AsyncSession, tenant: str, integration_id, status: str, *, actor: str = "") -> dict:
    if status not in STATUSES:
        raise ValidationError(f"invalid status: {status!r}")
    stmt = select(Integration).where(Integration.id == _as_uuid(integration_id), Integration.tenant == tenant)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise NotFoundError("integration not found")
    row.status = status
    await db.flush()
    await _audit(db, tenant, actor, f"integration.{status.lower()}", str(row.id), {"status": status})
    try:
        from app.integrations.common import emit_event
        if status == "DISABLED":
            await emit_event("integration_disabled", {"id": str(row.id)}, tenant)
        elif status == "REVOKED":
            await emit_event("integration_revoked", {"id": str(row.id)}, tenant)
        else:
            await emit_event("integration_updated", {"id": str(row.id), "status": status}, tenant)
    except Exception:
        pass
    return _serialize(row)


async def create_version(
    db: AsyncSession, tenant: str, integration_id, version: str, *,
    contract: Optional[dict] = None, compatibility: str = "compatible",
    deprecated: bool = False, migration_notes: str = "", actor: str = "",
) -> dict:
    stmt = select(Integration).where(Integration.id == _as_uuid(integration_id), Integration.tenant == tenant)
    integration = (await db.execute(stmt)).scalar_one_or_none()
    if integration is None:
        raise NotFoundError("integration not found")
    if compatibility not in COMPATIBILITIES:
        raise ValidationError(f"invalid compatibility: {compatibility!r}")
    row = IntegrationVersion(
        tenant=tenant, integration_id=integration.id, version=version,
        contract=sanitize_metadata(contract), compatibility=compatibility,
        deprecated=bool(deprecated), migration_notes=migration_notes or "", metadata_={},
    )
    try:
        async with db.begin_nested():
            db.add(row)
            await db.flush()
    except IntegrityError:
        raise ValidationError("version already exists")
    await _audit(db, tenant, actor, "integration.version_create", str(row.id),
                 {"integration_id": str(integration.id), "version": version})
    return {
        "id": str(row.id), "integration_id": str(row.integration_id), "version": row.version,
        "contract": row.contract or {}, "compatibility": row.compatibility,
        "deprecated": row.deprecated, "migration_notes": row.migration_notes,
    }


async def list_versions(db: AsyncSession, tenant: str, integration_id, *, limit: int = 100) -> dict:
    stmt = select(IntegrationVersion).where(
        IntegrationVersion.tenant == tenant,
        IntegrationVersion.integration_id == _as_uuid(integration_id),
    )
    limit = min(max(int(limit or 100), 1), 1000)
    rows = (await db.execute(stmt.order_by(desc(IntegrationVersion.created_at)).limit(limit))).scalars().all()
    return {"items": [{
        "id": str(r.id), "integration_id": str(r.integration_id), "version": r.version,
        "contract": r.contract or {}, "compatibility": r.compatibility,
        "deprecated": r.deprecated, "migration_notes": r.migration_notes,
    } for r in rows], "total": len(rows)}
