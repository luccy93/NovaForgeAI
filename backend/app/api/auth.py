import uuid
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from passlib.context import CryptContext
from jose import JWTError, jwt

from app.core.database import get_db
from app.core.config import settings
from app.models.user import User, ApiKey
from app.schemas import (
    RegisterRequest,
    AuthResponse,
    LoginRequest,
    RefreshRequest,
    UserOut,
    GitHubAuthUrl,
    GitHubAuthResponse,
    ApiKeyCreate,
    ApiKeyOut,
    ApiKeyCreated,
)
from app.core.authorization import Permission

router = APIRouter()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _create_access_token(user_id: str) -> tuple[str, int]:
    expire_minutes = settings.access_token_expire_minutes
    expires_delta = timedelta(minutes=expire_minutes)
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expire_minutes


def _create_refresh_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=7)
    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


async def _get_current_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if settings.testing and (not authorization or not authorization.startswith("Bearer ")):
        demo = await db.execute(select(User).where(User.email == "demo@novaforge.local"))
        user = demo.scalar_one_or_none()
        if not user:
            user = User(
                email="demo@novaforge.local",
                username="demo",
                hashed_password=pwd_context.hash("demo"),
                full_name="Demo User",
            )
            db.add(user)
            await db.flush()
            await db.refresh(user)
        return user
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
        )
    token = authorization.removeprefix("Bearer ")
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        user_id = payload.get("sub")
        if user_id is None or payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="User is inactive")
    return user


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    existing = await db.execute(
        select(User).where((User.email == request.email) | (User.username == request.username))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email or username already registered")

    user = User(
        email=request.email,
        username=request.username,
        hashed_password=pwd_context.hash(request.password),
        full_name=request.full_name,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    access_token, expires_in = _create_access_token(str(user.id))
    return AuthResponse(access_token=access_token, expires_in=expires_in)


@router.post("/login")
async def login(
    request: Request,
    login_req: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Login with MFA support — returns MFA challenge if MFA is enabled, else full token."""
    # Account lockout check
    result = await db.execute(select(User).where(User.email == login_req.email))
    user = result.scalar_one_or_none()

    if user:
        # Check if account is locked
        if user.locked_until and user.locked_until > datetime.now(timezone.utc):
            remaining = (user.locked_until - datetime.now(timezone.utc)).seconds
            raise HTTPException(
                status_code=423,
                detail=f"Account is locked. Try again in {remaining} seconds.",
            )

    if not user or not pwd_context.verify(login_req.password, user.hashed_password):
        # Record failed attempt
        if user:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= settings.account_lockout_attempts:
                user.locked_until = datetime.now(timezone.utc) + timedelta(
                    minutes=settings.account_lockout_duration_minutes
                )
                user.failed_login_attempts = 0
        await db.flush()

        # Record auth failure for rate limiting
        try:
            from app.core.security_middleware import rate_limiter
            client_ip = request.client.host if request.client else "unknown"
            await rate_limiter.record_auth_failure(client_ip, login_req.email)
        except Exception:
            pass

        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.is_active:
        raise HTTPException(status_code=401, detail="User account is inactive")

    # Reset failed attempts on successful password verification
    if user.failed_login_attempts > 0:
        user.failed_login_attempts = 0
        user.locked_until = None

    # Check MFA
    if user.mfa_enabled or settings.mfa_required:
        # Return challenge token — client must complete MFA
        challenge_payload = {
            "sub": str(user.id),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            "iat": datetime.now(timezone.utc),
            "type": "mfa_challenge",
        }
        challenge_token = jwt.encode(challenge_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
        await db.flush()
        return {
            "mfa_required": True,
            "challenge_token": challenge_token,
            "mfa_methods": ["totp", "backup_code"],
            "expires_in": 300,
        }

    # No MFA — issue full token
    user.last_login_at = datetime.now(timezone.utc)
    await db.flush()

    access_token, expires_in = _create_access_token(str(user.id))
    return AuthResponse(access_token=access_token, expires_in=expires_in)


@router.post("/refresh", response_model=AuthResponse)
async def refresh_token(
    request: RefreshRequest,
) -> AuthResponse:
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
    return AuthResponse(access_token=access_token, expires_in=expires_in)


@router.get("/me", response_model=UserOut)
async def get_current_user(
    current_user: User = Depends(_get_current_user),
) -> UserOut:
    return UserOut(
        id=str(current_user.id),
        email=current_user.email,
        username=current_user.username,
        full_name=current_user.full_name,
        avatar_url=current_user.avatar_url,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
    )


async def _get_current_user_optional(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ")
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = payload.get("sub")
        if user_id is None or payload.get("type") != "access":
            return None
        uid = uuid.UUID(user_id)
        result = await db.execute(select(User).where(User.id == uid))
        return result.scalar_one_or_none()
    except (JWTError, ValueError):
        return None


def require_permission(permission: Permission):
    async def _dependency(
        current_user: User = Depends(_get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        if current_user.is_superuser:
            return current_user
        from app.core.authorization import ROLE_PERMISSIONS
        from app.models.organization import Organization
        from sqlalchemy import text
        result = await db.execute(
            text("SELECT role FROM user_organizations WHERE user_id = :uid"),
            {"uid": current_user.id.hex},
        )
        rows = result.all()
        for row in rows:
            perms = ROLE_PERMISSIONS.get(row[0], set())
            if permission in perms:
                return current_user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing required permission: {permission.value}",
        )
    return _dependency


# ─── GitHub OAuth ───────────────────────────────────────────────────────

@router.get("/github/login", response_model=GitHubAuthUrl)
async def github_oauth_login():
    if not settings.github_oauth_client_id:
        raise HTTPException(status_code=501, detail="GitHub OAuth not configured")
    state = secrets.token_urlsafe(32)
    url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={settings.github_oauth_client_id}"
        f"&redirect_uri={settings.github_oauth_redirect_uri}"
        f"&state={state}"
        f"&scope=read:user+user:email"
    )
    return GitHubAuthUrl(url=url)


@router.get("/github/callback", response_model=GitHubAuthResponse)
async def github_oauth_callback(
    code: str = Query(...),
    state: str = Query(None),
    db: AsyncSession = Depends(get_db),
) -> GitHubAuthResponse:
    if not settings.github_oauth_client_id or not settings.github_oauth_client_secret:
        raise HTTPException(status_code=501, detail="GitHub OAuth not configured")

    import httpx

    token_url = "https://github.com/login/oauth/access_token"
    headers = {"Accept": "application/json"}
    data = {
        "client_id": settings.github_oauth_client_id,
        "client_secret": settings.github_oauth_client_secret,
        "code": code,
        "redirect_uri": settings.github_oauth_redirect_uri,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(token_url, data=data, headers=headers)
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="GitHub OAuth token exchange failed")
        token_data = resp.json()

    access_token_gh = token_data.get("access_token")
    if not access_token_gh:
        raise HTTPException(status_code=400, detail="Invalid GitHub OAuth code")

    async with httpx.AsyncClient() as client:
        user_resp = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {access_token_gh}", "Accept": "application/json"},
        )
        if user_resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Failed to fetch GitHub user")
        gh_user = user_resp.json()

    github_id = str(gh_user["id"])
    email_resp = await client.get(
        "https://api.github.com/user/emails",
        headers={"Authorization": f"Bearer {access_token_gh}", "Accept": "application/json"},
    )
    emails = email_resp.json() if email_resp.status_code == 200 else []
    primary_email = next((e["email"] for e in emails if e.get("primary")), gh_user.get("email")) or f"{github_id}@github.user"

    result = await db.execute(select(User).where(
        (User.email == primary_email) | (User.username == f"github_{github_id}")
    ))
    user = result.scalar_one_or_none()
    is_new_user = False

    if not user:
        username_base = gh_user.get("login", f"user_{github_id}")[:100]
        user = User(
            email=primary_email,
            username=f"github_{github_id}",
            hashed_password=pwd_context.hash(secrets.token_urlsafe(32)),
            full_name=gh_user.get("name"),
            avatar_url=gh_user.get("avatar_url"),
            profile={"github_id": github_id, "github_login": gh_user.get("login")},
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)
        is_new_user = True

    access_token, expires_in = _create_access_token(str(user.id))
    refresh_token = _create_refresh_token(str(user.id))
    return GitHubAuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        is_new_user=is_new_user,
    )


# ─── API Keys ───────────────────────────────────────────────────────────

@router.get("/api-keys", response_model=list[ApiKeyOut])
async def list_api_keys(
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ApiKeyOut]:
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == current_user.id).order_by(ApiKey.created_at.desc())
    )
    keys = result.scalars().all()
    return [
        ApiKeyOut(
            id=str(k.id),
            name=k.name,
            key_prefix=k.key_prefix,
            scopes=k.scopes,
            is_active=k.is_active,
            last_used_at=k.last_used_at,
            expires_at=k.expires_at,
            created_at=k.created_at,
        )
        for k in keys
    ]


@router.post("/api-keys", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    request: ApiKeyCreate,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyCreated:
    raw_key = f"nf_{secrets.token_urlsafe(32)}"
    key_prefix = raw_key[:10]
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    api_key = ApiKey(
        user_id=current_user.id,
        name=request.name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        scopes=request.scopes,
    )
    db.add(api_key)
    await db.flush()
    await db.refresh(api_key)

    return ApiKeyCreated(
        id=str(api_key.id),
        name=api_key.name,
        key_prefix=key_prefix,
        full_key=raw_key,
        scopes=api_key.scopes,
        created_at=api_key.created_at,
    )


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    key_id: str,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        kid = uuid.UUID(key_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid key id")
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == kid, ApiKey.user_id == current_user.id)
    )
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    await db.delete(key)
