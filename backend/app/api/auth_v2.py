"""Auth API v2 — MFA, sessions, password reset, email verification, compliance."""

import uuid
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import settings
from app.core.security import encryption
from app.core.mfa import MFAService
from app.core.compliance import compliance_service
from app.core.threat_detection import threat_detector
from app.core.jwt_service import jwt_service
from app.models.user import User, UserSession
from app.schemas import UserOut
from app.api.auth import _get_current_user, pwd_context

router = APIRouter()


# ─── MFA ────────────────────────────────────────────────────────────────────

class MFASetupResponse(BaseModel):
    secret: str
    uri: str
    backup_codes: list[str]
    recovery_code: str


class MFAVerifyRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)


class MFAStatusResponse(BaseModel):
    enabled: bool
    setup_required: bool


@router.get("/mfa/setup", response_model=MFASetupResponse)
async def setup_mfa(
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MFASetupResponse:
    secret = MFAService.generate_totp_secret()
    uri = MFAService.get_totp_uri(secret, current_user.email)
    backup_codes = MFAService.generate_backup_codes(settings.mfa_backup_code_count)
    recovery_code = MFAService.generate_recovery_code()

    current_user.mfa_secret = encryption.encrypt(secret)
    current_user.mfa_backup_codes = [{"hash": c["hash"], "used": False} for c in backup_codes]
    current_user.mfa_recovery_code = hashlib.sha256(recovery_code.encode()).hexdigest()

    return MFASetupResponse(
        secret=secret,
        uri=uri,
        backup_codes=[c["plain"] for c in backup_codes],
        recovery_code=recovery_code,
    )


@router.post("/mfa/verify", response_model=MFAStatusResponse)
async def verify_mfa(
    request: MFAVerifyRequest,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MFAStatusResponse:
    if not current_user.mfa_secret:
        raise HTTPException(status_code=400, detail="MFA not set up. Call /mfa/setup first.")
    secret = encryption.decrypt(current_user.mfa_secret)
    if not MFAService.verify_totp(secret, request.code):
        raise HTTPException(status_code=400, detail="Invalid verification code")
    current_user.mfa_enabled = True
    return MFAStatusResponse(enabled=True, setup_required=False)


@router.post("/mfa/disable", response_model=MFAStatusResponse)
async def disable_mfa(
    request: MFAVerifyRequest,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MFAStatusResponse:
    if current_user.mfa_secret:
        secret = encryption.decrypt(current_user.mfa_secret)
        if not MFAService.verify_totp(secret, request.code):
            raise HTTPException(status_code=400, detail="Invalid verification code")
    current_user.mfa_enabled = False
    current_user.mfa_secret = None
    current_user.mfa_backup_codes = None
    current_user.mfa_recovery_code = None
    return MFAStatusResponse(enabled=False, setup_required=False)


@router.post("/mfa/verify-backup", response_model=dict)
async def verify_backup_code(
    code: str = Query(..., min_length=10, max_length=10),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    stored = current_user.mfa_backup_codes or []
    idx = MFAService.verify_backup_code(code, stored)
    if idx is None:
        raise HTTPException(status_code=400, detail="Invalid backup code")
    stored[idx]["used"] = True
    current_user.mfa_backup_codes = stored
    return {"status": "verified", "remaining": sum(1 for c in stored if not c["used"])}


# ─── Password Management ────────────────────────────────────────────────────

class PasswordChangeRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)


class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=128)


@router.post("/password/change", response_model=dict)
async def change_password(
    request: PasswordChangeRequest,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not pwd_context.verify(request.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    _validate_password_strength(request.new_password)
    prev = current_user.previous_passwords or []
    for old_hash in prev[-settings.password_history_count:]:
        if pwd_context.verify(request.new_password, old_hash):
            raise HTTPException(status_code=400, detail="Password was used recently")
    current_user.hashed_password = pwd_context.hash(request.new_password)
    prev.append(current_user.hashed_password)
    current_user.previous_passwords = prev[-settings.password_history_count:]
    current_user.password_changed_at = datetime.now(timezone.utc)
    return {"status": "password_updated"}


@router.post("/password/reset", response_model=dict)
async def request_password_reset(
    request: PasswordResetRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()
    if user:
        token = secrets.token_urlsafe(48)
        user.password_reset_token = hashlib.sha256(token.encode()).hexdigest()
        user.password_reset_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    return {"status": "if_email_exists_reset_link_sent"}


@router.post("/password/reset/confirm", response_model=dict)
async def confirm_password_reset(
    request: PasswordResetConfirm,
    db: AsyncSession = Depends(get_db),
) -> dict:
    token_hash = hashlib.sha256(request.token.encode()).hexdigest()
    result = await db.execute(
        select(User).where(
            User.password_reset_token == token_hash,
            User.password_reset_expires_at > datetime.now(timezone.utc),
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    _validate_password_strength(request.new_password)
    user.hashed_password = pwd_context.hash(request.new_password)
    user.password_reset_token = None
    user.password_reset_expires_at = None
    user.password_changed_at = datetime.now(timezone.utc)
    return {"status": "password_updated"}


# ─── Email Verification ─────────────────────────────────────────────────────

@router.post("/email/verify", response_model=dict)
async def verify_email(
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    result = await db.execute(
        select(User).where(User.email_verification_token == token_hash)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid verification token")
    user.email_verified_at = datetime.now(timezone.utc)
    user.email_verification_token = None
    return {"status": "email_verified"}


@router.post("/email/resend-verification", response_model=dict)
async def resend_verification(
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if current_user.email_verified_at:
        raise HTTPException(status_code=400, detail="Email already verified")
    token = secrets.token_urlsafe(48)
    current_user.email_verification_token = hashlib.sha256(token.encode()).hexdigest()
    return {"status": "verification_sent"}


# ─── Session Management ─────────────────────────────────────────────────────

class SessionOut(BaseModel):
    id: str
    ip_address: Optional[str]
    user_agent: Optional[str]
    created_at: str
    expires_at: str
    is_current: bool = False


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(
    current_user: User = Depends(_get_current_user),
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> list[SessionOut]:
    result = await db.execute(
        select(UserSession).where(
            UserSession.user_id == current_user.id,
            UserSession.revoked_at.is_(None),
        ).order_by(UserSession.created_at.desc())
    )
    sessions = result.scalars().all()
    current_jti = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ")
        current_jti = jwt_service.get_token_jti(token)
    return [
        SessionOut(
            id=str(s.id),
            ip_address=s.ip_address,
            user_agent=s.user_agent,
            created_at=s.created_at.isoformat() if s.created_at else "",
            expires_at=s.expires_at.isoformat() if s.expires_at else "",
            is_current=s.id == current_jti,
        )
        for s in sessions
    ]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: str,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session id")
    result = await db.execute(
        select(UserSession).where(
            UserSession.id == sid, UserSession.user_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.revoked_at = datetime.now(timezone.utc)


@router.delete("/sessions", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_all_sessions(
    current_user: User = Depends(_get_current_user),
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> None:
    current_jti = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ")
        current_jti = jwt_service.get_token_jti(token)
    await db.execute(
        text("UPDATE user_sessions SET revoked_at = :now WHERE user_id = :uid AND id != :sid"),
        {"now": datetime.now(timezone.utc), "uid": current_user.id.hex, "sid": current_jti or ""},
    )


# ─── Compliance (GDPR / Data Rights) ────────────────────────────────────────

@router.get("/data/export", response_model=dict)
async def export_my_data(
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    data = await compliance_service.export_user_data(str(current_user.id), db)
    return {"user_id": str(current_user.id), "data": data}


@router.post("/data/delete", response_model=dict)
async def delete_my_data(
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    deleted = await compliance_service.delete_user_data(str(current_user.id), db)
    await compliance_service.anonymize_user(str(current_user.id), db)
    return {"status": "deletion_initiated", "records_deleted": deleted}


# ─── Consent Management ─────────────────────────────────────────────────────

@router.post("/consent/terms", response_model=dict)
async def accept_terms(
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    current_user.terms_accepted_at = datetime.now(timezone.utc)
    return {"status": "terms_accepted", "accepted_at": current_user.terms_accepted_at.isoformat()}


@router.post("/consent/privacy", response_model=dict)
async def accept_privacy(
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    current_user.privacy_accepted_at = datetime.now(timezone.utc)
    return {"status": "privacy_accepted", "accepted_at": current_user.privacy_accepted_at.isoformat()}


@router.post("/consent/data-processing", response_model=dict)
async def accept_data_processing(
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    current_user.data_processing_consent = True
    return {"status": "consent_recorded"}


# ─── Helpers ────────────────────────────────────────────────────────────────

def _validate_password_strength(password: str) -> None:
    if len(password) < settings.password_min_length:
        raise HTTPException(status_code=400, detail=f"Password must be at least {settings.password_min_length} characters")
    if settings.password_require_uppercase and not any(c.isupper() for c in password):
        raise HTTPException(status_code=400, detail="Password must contain an uppercase letter")
    if settings.password_require_lowercase and not any(c.islower() for c in password):
        raise HTTPException(status_code=400, detail="Password must contain a lowercase letter")
    if settings.password_require_digit and not any(c.isdigit() for c in password):
        raise HTTPException(status_code=400, detail="Password must contain a digit")
    if settings.password_require_special and not any(c in "!@#$%^&*()_+-=[]{}|;':\",./<>?`~" for c in password):
        raise HTTPException(status_code=400, detail="Password must contain a special character")
