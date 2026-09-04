"""Generic OAuth/OIDC connections — Volume 70 Commit 2.

Authorization URL + PKCE, callback code exchange, encrypted token
storage, locked refresh, revocation. Reuses the existing
EncryptionService, governed outbound client, lease pattern and Zero
Trust-independent status machine. Tokens are never serialized,
logged, or emitted — only references and expiry metadata leave the
server boundary.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.common import (
    NotFoundError,
    ValidationError,
    _as_uuid,
    _ensure_aware,
    _utcnow,
    parse_time,
    sanitize_metadata,
)
from app.integrations.governed_models import IntegrationAuditLog
from app.integrations.governed_models_c2 import IntegrationOAuthConnection
from app.integrations.network_policy import validate_url

STATUSES = ("PENDING", "ACTIVE", "NEEDS_REAUTH", "REVOKED")

REFRESH_SKEW_SECONDS = 300


def _serialize(row: IntegrationOAuthConnection) -> dict:
    return {
        "id": str(row.id),
        "tenant": row.tenant,
        "integration_id": str(row.integration_id),
        "connection_id": str(row.connection_id) if row.connection_id else None,
        "provider": row.provider or "",
        "client_id": row.client_id or "",
        "scopes": row.scopes or [],
        "redirect_uri": row.redirect_uri or "",
        "token_ref": row.token_ref or "",
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "status": row.status,
    }


def _require_crypto() -> None:
    from app.core.config import settings
    master = getattr(settings, "encryption_master_key", None)
    if not master or len(str(master)) < 32:
        raise ValidationError("credential storage unavailable: encryption not configured")


async def _audit(db: AsyncSession, tenant: str, actor: str, action: str, resource_id: str, details: dict) -> None:
    db.add(IntegrationAuditLog(
        tenant=tenant, actor=actor or "", action=action,
        resource_type="oauth_connection", resource_id=resource_id,
        details=sanitize_metadata(details), status="SUCCESS",
    ))
    await db.flush()


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    import base64
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


async def start_oauth(
    db: AsyncSession, tenant: str, integration_id, *,
    provider: str = "", client_id: str = "", scopes: Optional[list] = None,
    redirect_uri: str = "", authorization_endpoint: str = "", actor: str = "",
) -> dict:
    """Create a PENDING OAuth connection and return the authorize URL."""
    from app.core.security import EncryptionService
    from app.integrations.governed_models import Integration

    if not tenant:
        raise ValidationError("tenant required")
    stmt = select(Integration).where(Integration.id == _as_uuid(integration_id),
                                    Integration.tenant == tenant)
    integration = (await db.execute(stmt)).scalar_one_or_none()
    if integration is None:
        raise NotFoundError("integration not found")
    if not authorization_endpoint or not client_id or not redirect_uri:
        raise ValidationError("authorization_endpoint, client_id and redirect_uri required")
    validate_url(authorization_endpoint)
    validate_url(redirect_uri)
    _require_crypto()

    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(24)
    row = IntegrationOAuthConnection(
        id=uuid.uuid4(), tenant=tenant, integration_id=integration.id,
        provider=provider or integration.provider or "",
        client_id=client_id, scopes=[str(s) for s in (scopes or [])],
        redirect_uri=redirect_uri, state=state,
        encrypted_verifier=EncryptionService().encrypt_field(verifier),
        status="PENDING", token_ref=f"oauth:v1:{uuid.uuid4().hex}", metadata_={},
    )
    db.add(row)
    await db.flush()
    await _audit(db, tenant, actor, "oauth.start", str(row.id), {"provider": row.provider})
    params = {"response_type": "code", "client_id": client_id,
              "redirect_uri": redirect_uri, "scope": " ".join(row.scopes or []),
              "state": state, "nonce": nonce,
              "code_challenge": challenge, "code_challenge_method": "S256"}
    return {"oauth_id": str(row.id), "state": state,
            "authorize_url": f"{authorization_endpoint}?{urlencode(params)}",
            "status": row.status}


async def oauth_callback(
    db: AsyncSession, tenant: str, state: str, code: str, *,
    token_endpoint: str = "", actor: str = "",
) -> dict:
    """Exchange an authorization code for tokens (PKCE) and activate."""
    from app.core.security import EncryptionService
    from app.integrations.outbound import execute as outbound

    if not state or not code:
        raise ValidationError("state and code required")
    if not token_endpoint:
        raise ValidationError("token_endpoint required")
    validate_url(token_endpoint)
    stmt = select(IntegrationOAuthConnection).where(
        IntegrationOAuthConnection.tenant == tenant,
        IntegrationOAuthConnection.state == state,
        IntegrationOAuthConnection.status == "PENDING",
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise NotFoundError("oauth request not found or already consumed")
    _require_crypto()
    service = EncryptionService()
    verifier = service.decrypt_field(row.encrypted_verifier) or ""
    body = urlencode({"grant_type": "authorization_code", "code": code,
                      "redirect_uri": row.redirect_uri, "client_id": row.client_id,
                      "code_verifier": verifier}).encode()
    result = await outbound(
        tenant=tenant, method="POST", url=token_endpoint,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=body, timeout=15.0, max_attempts=1,
        rate_limit_key=f"integrations:{tenant}:oauth", rate_limit_max=60, actor=actor,
    )
    if result["status_code"] >= 400:
        row.status = "NEEDS_REAUTH"
        await db.flush()
        raise ValidationError(f"token exchange failed: http_{result['status_code']}")
    import json as _json
    try:
        data = _json.loads((result["body"] or b"{}").decode())
    except Exception:
        raise ValidationError("token endpoint returned invalid data")
    access = str(data.get("access_token") or "")
    refresh = str(data.get("refresh_token") or "")
    if not access:
        raise ValidationError("token endpoint returned no access token")
    expires_in = int(data.get("expires_in") or 3600)
    row.encrypted_access = service.encrypt_field(access)
    row.encrypted_refresh = service.encrypt_field(refresh) if refresh else None
    row.encrypted_verifier = None
    row.expires_at = _utcnow() + timedelta(seconds=max(expires_in, 60))
    row.status = "ACTIVE"
    await db.flush()
    await _audit(db, tenant, actor, "oauth.connected", str(row.id), {"provider": row.provider})
    try:
        from app.integrations.common import emit_event
        await emit_event("oauth_connected", {"oauth_id": str(row.id), "provider": row.provider}, tenant)
    except Exception:
        pass
    return _serialize(row)


async def refresh_oauth(db: AsyncSession, tenant: str, oauth_id, *,
                        token_endpoint: str = "", actor: str = "") -> dict:
    """Refresh tokens under a per-connection lease. Concurrent refreshes
    collapse onto the winner; failures mark NEEDS_REAUTH."""
    from app.core.security import EncryptionService
    from app.integrations.outbound import execute as outbound
    from app.integrations.workers import acquire_lease, release_lease

    stmt = select(IntegrationOAuthConnection).where(
        IntegrationOAuthConnection.id == _as_uuid(oauth_id),
        IntegrationOAuthConnection.tenant == tenant,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise NotFoundError("oauth connection not found")
    if row.status == "REVOKED":
        raise ValidationError("oauth connection revoked")
    worker = f"oauth-refresh-{uuid.uuid4().hex[:8]}"
    if not await acquire_lease(tenant, f"oauth:{row.id}", worker, ttl_seconds=120):
        fresh = (await db.execute(select(IntegrationOAuthConnection).where(
            IntegrationOAuthConnection.id == row.id))).scalar_one_or_none()
        return {**_serialize(fresh or row), "deduplicated": True}
    try:
        _require_crypto()
        service = EncryptionService()
        refresh = service.decrypt_field(row.encrypted_refresh) or ""
        if not refresh:
            raise ValidationError("no refresh token stored")
        if not token_endpoint:
            raise ValidationError("token_endpoint required")
        validate_url(token_endpoint)
        body = urlencode({"grant_type": "refresh_token", "refresh_token": refresh,
                          "client_id": row.client_id}).encode()
        result = await outbound(
            tenant=tenant, method="POST", url=token_endpoint,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            body=body, timeout=15.0, max_attempts=1,
            rate_limit_key=f"integrations:{tenant}:oauth", rate_limit_max=60, actor=actor,
        )
        if result["status_code"] >= 400:
            row.status = "NEEDS_REAUTH"
            await db.flush()
            try:
                from app.integrations.common import emit_event
                await emit_event("oauth_reauth_required",
                                 {"oauth_id": str(row.id), "provider": row.provider}, tenant)
            except Exception:
                pass
            raise ValidationError(f"refresh failed: http_{result['status_code']}")
        import json as _json
        data = _json.loads((result["body"] or b"{}").decode())
        access = str(data.get("access_token") or "")
        if not access:
            raise ValidationError("refresh returned no access token")
        row.encrypted_access = service.encrypt_field(access)
        if data.get("refresh_token"):
            row.encrypted_refresh = service.encrypt_field(str(data["refresh_token"]))
        row.expires_at = _utcnow() + timedelta(seconds=max(int(data.get("expires_in") or 3600), 60))
        row.status = "ACTIVE"
        await db.flush()
        await _audit(db, tenant, actor, "oauth.refreshed", str(row.id), {"provider": row.provider})
        try:
            from app.integrations.common import emit_event
            await emit_event("oauth_refreshed", {"oauth_id": str(row.id)}, tenant)
        except Exception:
            pass
        return _serialize(row)
    finally:
        await release_lease(tenant, f"oauth:{row.id}", worker)


async def revoke_oauth(db: AsyncSession, tenant: str, oauth_id, *, actor: str = "") -> dict:
    stmt = select(IntegrationOAuthConnection).where(
        IntegrationOAuthConnection.id == _as_uuid(oauth_id),
        IntegrationOAuthConnection.tenant == tenant,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise NotFoundError("oauth connection not found")
    row.status = "REVOKED"
    row.encrypted_access = None
    row.encrypted_refresh = None
    await db.flush()
    await _audit(db, tenant, actor, "oauth.revoked", str(row.id), {"provider": row.provider})
    return _serialize(row)


async def get_oauth(db: AsyncSession, tenant: str, oauth_id) -> dict:
    stmt = select(IntegrationOAuthConnection).where(
        IntegrationOAuthConnection.id == _as_uuid(oauth_id),
        IntegrationOAuthConnection.tenant == tenant,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise NotFoundError("oauth connection not found")
    return _serialize(row)


async def list_oauth(db: AsyncSession, tenant: str, *, status: str = "", limit: int = 100) -> dict:
    from sqlalchemy import desc
    stmt = select(IntegrationOAuthConnection).where(IntegrationOAuthConnection.tenant == tenant)
    if status:
        stmt = stmt.where(IntegrationOAuthConnection.status == status)
    limit = min(max(int(limit or 100), 1), 1000)
    rows = (await db.execute(stmt.order_by(desc(IntegrationOAuthConnection.created_at)).limit(limit))).scalars().all()
    return {"items": [_serialize(r) for r in rows], "total": len(rows)}


async def refresh_if_expiring(db: AsyncSession, tenant: str, oauth_id, *,
                              token_endpoint: str = "", actor: str = "") -> dict:
    """Refresh only when expiry is near. Returns current metadata otherwise."""
    stmt = select(IntegrationOAuthConnection).where(
        IntegrationOAuthConnection.id == _as_uuid(oauth_id),
        IntegrationOAuthConnection.tenant == tenant,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise NotFoundError("oauth connection not found")
    if (row.status == "ACTIVE" and row.expires_at
            and row.expires_at > _utcnow() + timedelta(seconds=REFRESH_SKEW_SECONDS)):
        return {**_serialize(row), "refreshed": False}
    result = await refresh_oauth(db, tenant, oauth_id, token_endpoint=token_endpoint, actor=actor)
    return {**result, "refreshed": True}
