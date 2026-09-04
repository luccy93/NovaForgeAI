"""Connections and credential references — Volume 70 Commit 1.

Connections bind an integration to an environment with a credential
reference. Credential material is encrypted with the existing
EncryptionService (fail-closed when no master key is configured) and is
NEVER returned by any serializer, log, or event. Rotation creates a new
credential row and revokes the old one.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.common import (
    HEALTH_STATES,
    STATUSES,
    NotFoundError,
    ValidationError,
    _as_uuid,
    _ensure_aware,
    parse_time,
    sanitize_metadata,
)
from app.integrations.governed_models import (
    Integration,
    IntegrationAuditLog,
    IntegrationConnection,
    IntegrationCredential,
)
from app.integrations.network_policy import validate_url

CREDENTIAL_KINDS = ("api_key", "bearer", "basic", "oauth", "webhook_secret")


def _serialize_connection(row: IntegrationConnection) -> dict:
    return {
        "id": str(row.id),
        "tenant": row.tenant,
        "integration_id": str(row.integration_id),
        "workspace": row.workspace or "",
        "environment": row.environment or "",
        "endpoint_ref": row.endpoint_ref or "",
        "credential_id": str(row.credential_id) if row.credential_id else None,
        "scopes": row.scopes or [],
        "status": row.status,
        "health": row.health,
        "last_success_at": row.last_success_at.isoformat() if row.last_success_at else None,
        "last_failure_at": row.last_failure_at.isoformat() if row.last_failure_at else None,
        "consecutive_failures": row.consecutive_failures,
    }


def _serialize_credential(row: IntegrationCredential) -> dict:
    """Credential metadata only — material is never exposed."""
    return {
        "id": str(row.id),
        "tenant": row.tenant,
        "connection_id": str(row.connection_id) if row.connection_id else None,
        "kind": row.kind,
        "secret_ref": row.secret_ref,
        "material_hint": row.material_hint or "",
        "scopes": row.scopes or [],
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "status": row.status,
    }


async def _audit(db: AsyncSession, tenant: str, actor: str, action: str,
                 resource_type: str, resource_id: str, details: dict) -> None:
    db.add(IntegrationAuditLog(
        tenant=tenant, actor=actor or "", action=action,
        resource_type=resource_type, resource_id=resource_id,
        details=sanitize_metadata(details), status="SUCCESS",
    ))
    await db.flush()


def _require_crypto() -> None:
    from app.core.config import settings
    master = getattr(settings, "encryption_master_key", None)
    if not master or len(str(master)) < 32:
        raise ValidationError("credential storage unavailable: encryption not configured")


async def create_connection(
    db: AsyncSession, tenant: str, integration_id, *,
    workspace: str = "", environment: str = "", endpoint_ref: str = "",
    scopes: Optional[list] = None, actor: str = "",
) -> dict:
    if not tenant:
        raise ValidationError("tenant required")
    stmt = select(Integration).where(Integration.id == _as_uuid(integration_id), Integration.tenant == tenant)
    integration = (await db.execute(stmt)).scalar_one_or_none()
    if integration is None:
        raise NotFoundError("integration not found")
    if integration.status in ("DISABLED", "REVOKED", "QUARANTINED"):
        raise ValidationError(f"integration is {integration.status}")
    if endpoint_ref:
        validate_url(endpoint_ref)
    row = IntegrationConnection(
        id=uuid.uuid4(), tenant=tenant, integration_id=integration.id,
        workspace=workspace or "", environment=environment or "",
        endpoint_ref=endpoint_ref or "", credential_id=None,
        scopes=[str(s) for s in (scopes or [])],
        status="ACTIVE", health="UNKNOWN", consecutive_failures=0, metadata_={},
    )
    db.add(row)
    await db.flush()
    await _audit(db, tenant, actor, "connection.create", "connection", str(row.id),
                 {"integration_id": str(integration.id)})
    return _serialize_connection(row)


async def get_connection(db: AsyncSession, tenant: str, connection_id) -> dict:
    stmt = select(IntegrationConnection).where(
        IntegrationConnection.id == _as_uuid(connection_id),
        IntegrationConnection.tenant == tenant,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise NotFoundError("connection not found")
    return _serialize_connection(row)


async def list_connections(db: AsyncSession, tenant: str, *, integration_id=None, status: str = "", limit: int = 100) -> dict:
    stmt = select(IntegrationConnection).where(IntegrationConnection.tenant == tenant)
    if integration_id:
        stmt = stmt.where(IntegrationConnection.integration_id == _as_uuid(integration_id))
    if status:
        stmt = stmt.where(IntegrationConnection.status == status)
    limit = min(max(int(limit or 100), 1), 1000)
    rows = (await db.execute(stmt.order_by(desc(IntegrationConnection.created_at)).limit(limit))).scalars().all()
    return {"items": [_serialize_connection(r) for r in rows], "total": len(rows)}


async def set_connection_status(db: AsyncSession, tenant: str, connection_id, status: str, *, actor: str = "") -> dict:
    if status not in STATUSES:
        raise ValidationError(f"invalid status: {status!r}")
    stmt = select(IntegrationConnection).where(
        IntegrationConnection.id == _as_uuid(connection_id),
        IntegrationConnection.tenant == tenant,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise NotFoundError("connection not found")
    row.status = status
    await db.flush()
    await _audit(db, tenant, actor, f"connection.{status.lower()}", "connection", str(row.id), {"status": status})
    return _serialize_connection(row)


async def store_credential(
    db: AsyncSession, tenant: str, kind: str, material: str, *,
    connection_id=None, scopes: Optional[list] = None, expires_at=None,
    auth_config: Optional[dict] = None, actor: str = "",
) -> dict:
    """Encrypt and store credential material. Returns metadata only.

    auth_config is non-secret injection metadata, e.g.
    {"header": "X-Api-Key"}, {"scheme": "Bearer"} or
    {"query_param": "api_key"}.
    """
    from app.core.security import EncryptionService

    if kind not in CREDENTIAL_KINDS:
        raise ValidationError(f"unsupported credential kind: {kind!r}")
    if not material:
        raise ValidationError("credential material required")
    _require_crypto()
    service = EncryptionService()
    ciphertext = service.encrypt_field(material)
    hint = service.mask(material)
    auth = {k: str(v)[:128] for k, v in (auth_config or {}).items()
            if k in ("header", "scheme", "query_param")}
    row = IntegrationCredential(
        id=uuid.uuid4(), tenant=tenant,
        connection_id=_as_uuid(connection_id) if connection_id else None,
        kind=kind, secret_ref=f"enc:v1:{uuid.uuid4().hex}",
        encrypted_material=ciphertext, material_hint=hint,
        scopes=[str(s) for s in (scopes or [])],
        expires_at=_ensure_aware(parse_time(expires_at)) if expires_at else None,
        status="ACTIVE", metadata_={"auth": auth} if auth else {},
    )
    db.add(row)
    await db.flush()
    if connection_id:
        conn_stmt = select(IntegrationConnection).where(
            IntegrationConnection.id == _as_uuid(connection_id),
            IntegrationConnection.tenant == tenant,
        )
        conn = (await db.execute(conn_stmt)).scalar_one_or_none()
        if conn is None:
            raise NotFoundError("connection not found")
        conn.credential_id = row.id
        await db.flush()
    await _audit(db, tenant, actor, "credential.create", "credential", str(row.id), {"kind": kind})
    return _serialize_credential(row)


async def resolve_credential_material(db: AsyncSession, tenant: str, credential_id, *, purpose: str, actor: str = "") -> str:
    """Decrypt material for server-side use only. Never returned over APIs."""
    from app.core.security import EncryptionService

    stmt = select(IntegrationCredential).where(
        IntegrationCredential.id == _as_uuid(credential_id),
        IntegrationCredential.tenant == tenant,
        IntegrationCredential.status == "ACTIVE",
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None or not row.encrypted_material:
        raise NotFoundError("credential not available")
    _require_crypto()
    await _audit(db, tenant, actor, "credential.resolve", "credential", str(row.id), {"purpose": purpose})
    return EncryptionService().decrypt_field(row.encrypted_material) or ""


async def rotate_credential(db: AsyncSession, tenant: str, credential_id, new_material: str, *, actor: str = "") -> dict:
    stmt = select(IntegrationCredential).where(
        IntegrationCredential.id == _as_uuid(credential_id),
        IntegrationCredential.tenant == tenant,
    )
    old = (await db.execute(stmt)).scalar_one_or_none()
    if old is None:
        raise NotFoundError("credential not found")
    created = await store_credential(
        db, tenant, old.kind, new_material, connection_id=old.connection_id,
        scopes=old.scopes, actor=actor,
    )
    old.status = "REVOKED"
    await db.flush()
    await _audit(db, tenant, actor, "credential.rotate", "credential", created["id"], {"rotated_from": str(old.id)})
    return created


async def record_connection_result(db: AsyncSession, tenant: str, connection_id, *, success: bool) -> None:
    from datetime import timezone
    stmt = select(IntegrationConnection).where(
        IntegrationConnection.id == _as_uuid(connection_id),
        IntegrationConnection.tenant == tenant,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        return
    now = datetime.now(timezone.utc)
    if success:
        row.last_success_at = now
        row.consecutive_failures = 0
        row.health = "HEALTHY"
    else:
        row.last_failure_at = now
        row.consecutive_failures = (row.consecutive_failures or 0) + 1
        row.health = "DEGRADED" if row.consecutive_failures < 5 else "UNHEALTHY"
    await db.flush()
