"""Zero Trust API — Volume 64 Commit 1."""

import hashlib
import uuid
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import _get_current_user
from app.core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/zero-trust", tags=["Zero Trust"])


def _tenant(user) -> str:
    oid = getattr(user, "organization_id", None) or getattr(user, "id", None)
    if not oid:
        raise HTTPException(status_code=403, detail="No tenant context")
    return str(oid)


def _iam_check(user, tenant: str, permission: str, resource_type: str = "zero_trust") -> None:
    try:
        from app.iam.policy_authorizer import policy_authorizer
        ctx = {"role": str(getattr(user, "role", "viewer"))}
        decision = policy_authorizer.authorize(str(getattr(user, "id", "")), tenant, permission, resource_type=resource_type, context=ctx)
        if not decision.get("allowed", True):
            raise HTTPException(status_code=403, detail=decision.get("reason", "Forbidden"))
    except HTTPException:
        raise
    except Exception as exc:
        logger.debug("IAM check skipped %s: %s", permission, exc)


def _audit(tenant: str, actor: str, action: str, resource_type: str, resource_id: str, details: dict | None = None):
    try:
        from app.iam.audit_service import audit_service
        audit_service.log(org_id=tenant, actor_id=actor, actor_type="user", action=action, resource_type=resource_type, resource_id=resource_id, result="success", details=details or {}, tenant_id=tenant)
    except Exception as exc:
        logger.debug("audit skipped %s: %s", action, exc)


async def _emit(event_name: str, data: dict, tenant: str):
    try:
        from app.core.events import Event, EventType, event_bus
        et = getattr(EventType, event_name, None)
        if et:
            await event_bus.publish_nowait(Event(et, data, source="zero_trust", organization_id=tenant))
    except Exception as exc:
        logger.debug("emit failed %s: %s", event_name, exc)


def _to_uuid(v):
    import uuid as _u
    try:
        return _u.UUID(str(v))
    except Exception:
        return v


# ── Models ─────────────────────────────────────────────────────────────────
class AuthorizeIn(BaseModel):
    identity: str
    resource: str
    action: str
    session_id_hash: Optional[str] = None
    device_context: dict = {}
    region: Optional[str] = None
    data_classification: Optional[str] = None
    risk_state: Optional[str] = None


class SessionCreateIn(BaseModel):
    identity_id: str
    scope: dict = {}
    device_context: dict = {}
    region: Optional[str] = None
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    auth_method: str = "password"
    absolute_timeout: int = 900
    idle_timeout: int = 600


class CredentialCreateIn(BaseModel):
    owner_id: str
    credential_type: str
    scope: dict = {}
    expires_in_days: Optional[int] = None
    owner_type: str = "human"
    raw_value: str = Field(..., description="raw secret (hashed, never stored plaintext)")


class AccessRequestIn(BaseModel):
    identity_id: str
    resource: str
    action: str
    reason: str
    duration_seconds: int = 3600
    scope: dict = {}
    privilege_level: str = "HIGH"


class ReviewCreateIn(BaseModel):
    review_type: str = "periodic"
    scope: str = "all"


# ── Authorize ────────────────────────────────────────────────────────────────
@router.post("/authorize", status_code=200)
async def authorize(payload: AuthorizeIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.zero_trust.authorization import authorize as _auth, invalidate_cache_for_tenant
    result = await _auth(
        db,
        identity_id=payload.identity,
        tenant_id=tenant,
        resource=payload.resource,
        action=payload.action,
        session_id_hash=payload.session_id_hash,
        device_context=payload.device_context,
        region=payload.region,
        data_classification=payload.data_classification,
        risk_state=payload.risk_state,
    )
    # Audit
    _audit(tenant, payload.identity, f"zero_trust.authorize:{payload.action}", "resource", payload.resource, {"decision": result["decision"]})
    return result


# ── Sessions ─────────────────────────────────────────────────────────────────
@router.post("/sessions", status_code=201)
async def create_session(payload: SessionCreateIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "zero_trust:write", "zero_trust")
    from app.zero_trust.sessions import create_session as _create
    try:
        res = await _create(
            db,
            identity_id=payload.identity_id,
            tenant_id=tenant,
            scope=payload.scope,
            device_context=payload.device_context,
            region=payload.region,
            ip=payload.ip,
            user_agent=payload.user_agent,
            auth_method=payload.auth_method,
            absolute_timeout=payload.absolute_timeout,
            idle_timeout=payload.idle_timeout,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    # Do not return plaintext beyond raw_token once
    _audit(tenant, payload.identity_id, "zero_trust.session.created", "session", res["session_id_hash"])
    await _emit("SessionCreated", {"session_id_hash": res["session_id_hash"], "identity": payload.identity_id}, tenant)
    return {"session_id_hash": res["session_id_hash"], "raw_token": res["raw_token"][:12] + "...", "status": "ACTIVE"}


@router.get("/sessions")
async def list_sessions(identity_id: str = Query(...), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.zero_trust.sessions import list_sessions_for_identity
    rows = await list_sessions_for_identity(db, identity_id, tenant)
    return {"items": rows, "total": len(rows)}


@router.post("/sessions/{session_id_hash}/revoke", status_code=200)
async def revoke_session(session_id_hash: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "zero_trust:write", "zero_trust")
    from app.zero_trust.sessions import revoke_session as _revoke
    ok = await _revoke(db, session_id_hash, tenant, reason="manual")
    if not ok:
        raise HTTPException(status_code=404, detail="session not found")
    await db.commit()
    _audit(tenant, str(getattr(user, "id", "")), "zero_trust.session.revoked", "session", session_id_hash)
    await _emit("SessionRevoked", {"session_id_hash": session_id_hash}, tenant)
    return {"revoked": True}


@router.post("/sessions/revoke-all", status_code=200)
async def revoke_all_sessions(identity_id: str = Query(...), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "zero_trust:write", "zero_trust")
    from app.zero_trust.sessions import revoke_all_for_identity
    count = await revoke_all_for_identity(db, identity_id, tenant)
    await db.commit()
    return {"revoked": count}


# ── Credentials ──────────────────────────────────────────────────────────────
@router.post("/credentials", status_code=201)
async def create_credential(payload: CredentialCreateIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "zero_trust:write", "zero_trust")
    from app.zero_trust.credentials import create_credential_metadata
    res = await create_credential_metadata(db, tenant, payload.owner_id, payload.credential_type, payload.raw_value, scope=payload.scope, expires_in_days=payload.expires_in_days, owner_type=payload.owner_type)
    await db.commit()
    _audit(tenant, payload.owner_id, "zero_trust.credential.created", "credential", res["credential_id"])
    await _emit("CredentialCreated", {"credential_id": res["credential_id"]}, tenant)
    return {"credential_id": res["credential_id"], "fingerprint": res["fingerprint"]}


@router.get("/credentials")
async def list_credentials(owner_id: Optional[str] = None, limit: int = Query(20, ge=1, le=100), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.zero_trust.models import IAMCredentialsMetadata
    q = select(IAMCredentialsMetadata).where(IAMCredentialsMetadata.tenant_id == _to_uuid(tenant))
    if owner_id:
        q = q.where(IAMCredentialsMetadata.owner_id == owner_id)
    q = q.order_by(IAMCredentialsMetadata.created_at.desc()).limit(limit)
    res = await db.execute(q)
    rows = res.scalars().all()
    return {"items": [{"credential_id": r.credential_id, "type": r.credential_type, "status": r.credential_status, "fingerprint": r.credential_fingerprint, "expiry": r.credential_expiry.isoformat() if r.credential_expiry else None} for r in rows]}


@router.post("/credentials/{credential_id}/revoke", status_code=200)
async def revoke_credential(credential_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "zero_trust:write", "zero_trust")
    from app.zero_trust.credentials import revoke_credential as _revoke
    ok = await _revoke(db, credential_id, tenant)
    if not ok:
        raise HTTPException(status_code=404, detail="credential not found")
    await db.commit()
    await _emit("CredentialRevoked", {"credential_id": credential_id}, tenant)
    return {"revoked": True}


@router.post("/credentials/{credential_id}/rotate", status_code=200)
async def rotate_credential(credential_id: str, payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "zero_trust:write", "zero_trust")
    new_raw = payload.get("raw_value")
    if not new_raw:
        raise HTTPException(status_code=422, detail="raw_value required")
    from app.zero_trust.credentials import rotate_credential as _rotate
    try:
        res = await _rotate(db, credential_id, tenant, new_raw, requested_by=str(getattr(user, "id", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    await _emit("CredentialRotationCompleted", {"old": credential_id, "new": res["new_credential_id"]}, tenant)
    return res


# ── Access requests (JIT) ────────────────────────────────────────────────────
@router.post("/access-requests", status_code=201)
async def create_access_request(payload: AccessRequestIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.zero_trust.jit import request_access
    try:
        rec = await request_access(db, tenant, payload.identity_id, payload.resource, payload.action, payload.reason, duration_seconds=payload.duration_seconds, scope=payload.scope, privilege_level=payload.privilege_level, requested_by=str(getattr(user, "id", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    await _emit("AccessRequested", {"access_id": str(rec.id)}, tenant)
    return {"id": str(rec.id), "status": rec.status, "binding_hash": rec.binding_hash}


@router.get("/access-requests")
async def list_access_requests(status: Optional[str] = None, limit: int = Query(20, ge=1, le=100), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.zero_trust.jit import list_access
    rows = await list_access(db, tenant, status=status, limit=limit)
    return {"items": [{"id": str(r.id), "identity": r.identity_id, "resource": r.resource_id, "action": r.action, "status": r.status, "binding_hash": r.binding_hash} for r in rows]}


@router.post("/access-requests/{access_id}/approve", status_code=200)
async def approve_access_request(access_id: str, payload: dict | None = None, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "zero_trust:write", "zero_trust")
    from app.zero_trust.jit import approve_access, activate_access
    try:
        rec = await approve_access(db, tenant, access_id, approver=str(getattr(user, "id", "")), expected_binding=(payload or {}).get("binding_hash"))
        # auto-activate after approval
        rec = await activate_access(db, tenant, access_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    await _emit("AccessApproved", {"access_id": access_id}, tenant)
    await _emit("PrivilegedAccessGranted", {"access_id": access_id}, tenant)
    return {"id": str(rec.id), "status": rec.status, "expires_at": rec.expires_at.isoformat() if rec.expires_at else None}


@router.post("/access-requests/{access_id}/revoke", status_code=200)
async def revoke_access_request(access_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.zero_trust.jit import revoke_access
    try:
        rec = await revoke_access(db, tenant, access_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await db.commit()
    return {"id": str(rec.id), "status": rec.status}


# ── Reviews ──────────────────────────────────────────────────────────────────
@router.post("/reviews", status_code=201)
async def create_review(payload: ReviewCreateIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.iam.access_review_service import access_review_service
    review = access_review_service.create_review(tenant, review_type=payload.review_type, scope=payload.scope, initiated_by=str(getattr(user, "id", "")))
    # Persist also to DB? Keep in-memory for now, but also emit
    await _emit("AccessReviewStarted", {"review_id": review["id"]}, tenant)
    return review


@router.get("/reviews")
async def list_reviews(status: Optional[str] = None, limit: int = Query(20, ge=1, le=100), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    _tenant(user)
    from app.iam.access_review_service import access_review_service
    rows = access_review_service.list_reviews(status=status) if hasattr(access_review_service, "list_reviews") else []
    # Filter by tenant? In-memory stores all; filter manually if needed
    return {"items": rows[:limit]}


@router.post("/reviews/{review_id}/certify", status_code=200)
async def certify_review(review_id: str, payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "zero_trust:write", "zero_trust")
    from app.iam.access_review_service import access_review_service
    # Explicit certification, not inferred
    cert = payload.get("certify")
    if not cert:
        raise HTTPException(status_code=422, detail="certify=true required for explicit certification")
    review = access_review_service.complete_review(review_id, results=payload.get("results", {}), actions_taken=payload.get("actions_taken"))
    if not review:
        raise HTTPException(status_code=404, detail="review not found")
    await _emit("AccessReviewCompleted", {"review_id": review_id}, tenant)
    return review


# ── Privileged access ────────────────────────────────────────────────────────
@router.get("/privileged-access")
async def list_privileged(status: Optional[str] = None, limit: int = Query(20, ge=1, le=100), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.zero_trust.jit import list_access
    rows = await list_access(db, tenant, status=status, limit=limit)
    priv = [r for r in rows if r.privilege_level in ("HIGH", "CRITICAL")]
    return {"items": [{"id": str(r.id), "identity": r.identity_id, "resource": r.resource_id, "status": r.status, "privilege_level": r.privilege_level} for r in priv]}


# ── Identity risk ────────────────────────────────────────────────────────────
@router.post("/identity-risk/evaluate", status_code=200)
async def evaluate_risk(payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    identity = payload.get("identity_id") or payload.get("identity")
    if not identity:
        raise HTTPException(status_code=422, detail="identity required")
    # Integrate Volume63 SecOps risk signals
    signals = payload.get("signals", {})
    # Calculate risk via existing risk logic + identity signals
    level = "LOW"
    score = 0.2
    if signals.get("failed_auth", 0) > 5:
        score = 0.8
        level = "HIGH"
    if signals.get("privilege_change"):
        score = max(score, 0.9)
        level = "CRITICAL"
    # Store snapshot
    from app.zero_trust.models import IAMIdentityRiskSnapshot
    try:
        tenant_uuid = _to_uuid(tenant)
    except Exception:
        tenant_uuid = None
    snap = IAMIdentityRiskSnapshot(
        tenant_id=tenant_uuid,  # type: ignore
        identity_id=identity,
        identity_type=payload.get("identity_type", "human"),
        risk_level=level,
        risk_score=score,
        factors={"signals": signals},
        signals=signals,
    )
    db.add(snap)
    await db.flush()
    await db.commit()
    await _emit("IdentityRiskChanged", {"identity": identity, "risk_level": level}, tenant)
    return {"identity": identity, "risk_level": level, "risk_score": score, "snapshot_id": str(snap.id)}


@router.get("/identity-risk/{identity_id}")
async def get_risk(identity_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.zero_trust.models import IAMIdentityRiskSnapshot
    q = select(IAMIdentityRiskSnapshot).where(IAMIdentityRiskSnapshot.tenant_id == _to_uuid(tenant), IAMIdentityRiskSnapshot.identity_id == identity_id).order_by(IAMIdentityRiskSnapshot.calculated_at.desc()).limit(1)
    res = await db.execute(q)
    snap = res.scalar_one_or_none()
    if not snap:
        return {"identity": identity_id, "risk_level": "LOW", "risk_score": 0.0}
    return {"identity": identity_id, "risk_level": snap.risk_level, "risk_score": snap.risk_score, "calculated_at": snap.calculated_at.isoformat()}
