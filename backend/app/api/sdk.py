"""SDK & CLI API — well-known config, token exchange, whoami, machine-to-machine auth."""

import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import _get_current_user, _create_access_token, _create_refresh_token, pwd_context
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User

router = APIRouter(tags=["SDK & CLI"])


# ─── .well-known / SDK Configuration ──────────────────────────────────────

@router.get("/.well-known/novaforge.json")
async def well_known_config(request: Request) -> dict:
    """SDK and CLI configuration endpoint — provides auth URLs, supported flows, and version info."""
    base_url = str(request.base_url).rstrip("/")
    return {
        "issuer": settings.jwt_issuer,
        "authorization_endpoint": f"{base_url}/api/v1/auth/login",
        "token_endpoint": f"{base_url}/api/v1/auth/token-exchange",
        "userinfo_endpoint": f"{base_url}/api/v1/auth/me",
        "revocation_endpoint": f"{base_url}/api/v1/auth/api-keys",
        "supported_grant_types": ["password", "refresh_token", "client_credentials"],
        "supported_auth_methods": ["bearer", "api_key"],
        "api_key_header": "X-API-Key",
        "token_format": "jwt",
        "mfa_supported": True,
        "mfa_methods": ["totp", "backup_code"],
        "sdk_version": "1.0.0",
        "min_cli_version": "0.5.0",
        "rate_limits": {
            "auth": {"max": settings.rate_limit_auth_max, "window_seconds": settings.rate_limit_window_seconds},
            "default": {"max": settings.rate_limit_default_max, "window_seconds": settings.rate_limit_window_seconds},
        },
        "features": {
            "sso": True,
            "scim": True,
            "webhooks": True,
            "api_keys": True,
            "mfa": True,
        },
    }


# ─── Token Exchange ────────────────────────────────────────────────────────

class TokenExchangeRequest(BaseModel):
    grant_type: str = Field(..., pattern=r"^(password|refresh_token|client_credentials)$")
    username: Optional[str] = None
    password: Optional[str] = None
    refresh_token: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    scope: Optional[str] = None


class TokenExchangeResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    refresh_token: Optional[str] = None
    scope: Optional[str] = None


@router.post("/auth/token-exchange", response_model=TokenExchangeResponse)
async def token_exchange(
    request: TokenExchangeRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenExchangeResponse:
    """OAuth2-compatible token exchange — supports password, refresh_token, and client_credentials grants."""
    from jose import JWTError, jwt

    if request.grant_type == "password":
        if not request.username or not request.password:
            raise HTTPException(status_code=400, detail="username and password required for password grant")

        # Support email or username
        result = await db.execute(
            select(User).where((User.email == request.username) | (User.username == request.username))
        )
        user = result.scalar_one_or_none()
        if not user or not pwd_context.verify(request.password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        if not user.is_active:
            raise HTTPException(status_code=401, detail="Account is inactive")

        access_token, expires_in = _create_access_token(str(user.id))
        refresh = _create_refresh_token(str(user.id))
        return TokenExchangeResponse(
            access_token=access_token,
            expires_in=expires_in,
            refresh_token=refresh,
        )

    elif request.grant_type == "refresh_token":
        if not request.refresh_token:
            raise HTTPException(status_code=400, detail="refresh_token required")

        try:
            payload = jwt.decode(
                request.refresh_token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
            )
            user_id = payload.get("sub")
            if user_id is None or payload.get("type") != "refresh":
                raise HTTPException(status_code=401, detail="Invalid refresh token")
        except JWTError:
            raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

        access_token, expires_in = _create_access_token(user_id)
        refresh = _create_refresh_token(user_id)
        return TokenExchangeResponse(
            access_token=access_token,
            expires_in=expires_in,
            refresh_token=refresh,
        )

    elif request.grant_type == "client_credentials":
        if not request.client_id or not request.client_secret:
            raise HTTPException(status_code=400, detail="client_id and client_secret required")

        # Look up service account
        from app.enterprise.sso_service import SSOService
        sso_svc = SSOService()
        sa = sso_svc.authenticate_service_account(request.client_id, request.client_secret)
        if not sa:
            raise HTTPException(status_code=401, detail="Invalid client credentials")

        # Create a machine-to-machine token
        access_token, expires_in = _create_access_token(
            f"service_account:{sa.client_id}",
        )
        return TokenExchangeResponse(
            access_token=access_token,
            expires_in=expires_in,
            scope=request.scope or " ".join(sa.scopes),
        )

    raise HTTPException(status_code=400, detail=f"Unsupported grant_type: {request.grant_type}")


# ─── CLI: Who Am I ────────────────────────────────────────────────────────

class WhoAmIResponse(BaseModel):
    user_id: str
    email: str
    username: str
    full_name: Optional[str] = None
    is_active: bool
    is_superuser: bool
    mfa_enabled: bool
    auth_method: str
    organizations: list[dict] = []
    permissions: list[str] = []


@router.get("/auth/whoami", response_model=WhoAmIResponse)
async def who_am_i(
    request: Request,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WhoAmIResponse:
    """CLI-friendly endpoint — returns current user info and permissions."""
    auth_method = getattr(request.state, "auth_method", "bearer")

    orgs = []
    try:
        from sqlalchemy import text
        result = await db.execute(
            text("SELECT organization_id, role FROM user_organizations WHERE user_id = :uid"),
            {"uid": current_user.id.hex},
        )
        for row in result.all():
            orgs.append({"organization_id": str(row[0]), "role": row[1]})
    except Exception:
        pass

    permissions = []
    if current_user.is_superuser:
        permissions = ["admin:all"]
    else:
        from app.core.authorization import ROLE_PERMISSIONS
        for org in orgs:
            perms = ROLE_PERMISSIONS.get(org["role"], set())
            permissions.extend([p.value for p in perms])

    return WhoAmIResponse(
        user_id=str(current_user.id),
        email=current_user.email,
        username=current_user.username,
        full_name=current_user.full_name,
        is_active=current_user.is_active,
        is_superuser=current_user.is_superuser,
        mfa_enabled=current_user.mfa_enabled,
        auth_method=auth_method,
        organizations=orgs,
        permissions=sorted(set(permissions)),
    )


# ─── CLI: Server Status ───────────────────────────────────────────────────

@router.get("/auth/status")
async def auth_status(
    request: Request,
    current_user: User = Depends(_get_current_user),
) -> dict:
    """Quick CLI status check — server version, user info, auth method."""
    return {
        "status": "authenticated",
        "server_version": settings.app_version,
        "user": {
            "id": str(current_user.id),
            "username": current_user.username,
            "email": current_user.email,
        },
        "auth_method": getattr(request.state, "auth_method", "bearer"),
        "mfa_enabled": current_user.mfa_enabled,
    }


# ─── MFA Challenge (Login Step 2) ─────────────────────────────────────────

class MFAChallengeRequest(BaseModel):
    challenge_token: str
    code: str = Field(..., min_length=6, max_length=10)


class MFAChallengeResponse(BaseModel):
    access_token: str
    expires_in: int
    refresh_token: Optional[str] = None


@router.post("/auth/mfa/challenge", response_model=MFAChallengeResponse)
async def mfa_challenge(
    request: MFAChallengeRequest,
    db: AsyncSession = Depends(get_db),
) -> MFAChallengeResponse:
    """Complete MFA challenge during login — exchange challenge_token + TOTP/backup code for access token."""
    from jose import JWTError, jwt
    from app.core.mfa import MFAService
    from app.core.security import encryption

    try:
        payload = jwt.decode(
            request.challenge_token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired challenge token")

    if payload.get("type") != "mfa_challenge":
        raise HTTPException(status_code=401, detail="Invalid challenge token type")

    user_id = payload.get("sub")
    try:
        uid = __import__("uuid").UUID(user_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid token payload")

    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Account is inactive")

    # Verify MFA code — try TOTP first, then backup codes
    verified = False
    if user.mfa_secret:
        secret = encryption.decrypt(user.mfa_secret)
        if MFAService.verify_totp(secret, request.code):
            verified = True

    if not verified and user.mfa_backup_codes:
        idx = MFAService.verify_backup_code(request.code, user.mfa_backup_codes)
        if idx is not None:
            user.mfa_backup_codes[idx]["used"] = True
            verified = True

    if not verified:
        raise HTTPException(status_code=401, detail="Invalid MFA code")

    # Issue full access token
    access_token, expires_in = _create_access_token(str(user.id))
    refresh = _create_refresh_token(str(user.id))
    return MFAChallengeResponse(
        access_token=access_token,
        expires_in=expires_in,
        refresh_token=refresh,
    )


# ─── CSRF Token Endpoint ──────────────────────────────────────────────────

@router.post("/auth/csrf-token")
async def get_csrf_token(
    current_user: User = Depends(_get_current_user),
) -> dict:
    """Generate a CSRF token for the current user session."""
    from app.core.csrf import generate_csrf_token
    token = generate_csrf_token(str(current_user.id))
    return {"csrf_token": token, "header": "X-CSRF-Token"}


# ─── Webhook Bridge ────────────────────────────────────────────────────────

@router.post("/webhooks/bridge/test/{webhook_id}")
async def test_webhook_bridge(
    webhook_id: str,
    current_user: User = Depends(_get_current_user),
) -> dict:
    """Send a test ping event through the webhook bridge to a specific webhook."""
    from app.core.webhook_bridge import webhook_bridge
    return await webhook_bridge.deliver_test_event(webhook_id, "test.ping")


@router.get("/webhooks/bridge/stats")
async def webhook_bridge_stats(
    current_user: User = Depends(_get_current_user),
) -> dict:
    """Get webhook bridge statistics."""
    from app.core.webhook_bridge import webhook_bridge
    return webhook_bridge.get_stats()
