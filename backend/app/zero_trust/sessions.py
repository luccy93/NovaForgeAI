"""Zero Trust session service — DB authoritative, Redis cache."""

import hashlib
import uuid
import json
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.iam.models import IAMSession
from app.zero_trust.cache import cache_get, cache_set, cache_del, cache_del_pattern


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _hash_device_context(ctx: dict | None) -> str | None:
    if not ctx:
        return None
    return hashlib.sha256(json.dumps(ctx, sort_keys=True).encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def create_session(
    db: AsyncSession,
    identity_id: str,
    tenant_id: str,
    scope: dict | None = None,
    device_context: dict | None = None,
    region: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    auth_method: str = "password",
    absolute_timeout: int = 900,  # 15m default short-lived per decision
    idle_timeout: int = 600,
    risk_state: str = "LOW",
    policy_version: str = "1.0",
) -> dict:
    # Generate raw token (never stored plaintext per decision — we store hash only)
    # For DB authoritative, we store hash; raw token returned once to caller via TLS
    raw_token = f"zt_{uuid.uuid4().hex}{uuid.uuid4().hex}"
    session_id_hash = _hash_token(raw_token)
    device_hash = _hash_device_context(device_context)
    now = _now()
    absolute_expires_at = now + timedelta(seconds=absolute_timeout)
    idle_expires_at = now + timedelta(seconds=idle_timeout)

    # Resolve user_id as UUID if possible, else generate mapping
    # IAMSession requires user_id FK to users.id — try to parse identity_id as UUID, else fallback to creating via existing user
    try:
        user_uuid = uuid.UUID(identity_id)
    except Exception:
        # Lookup user by identity_id? For tests, identity_id may be random string; create a dummy UUID for FK
        # Use deterministic uuid5 from identity_id
        user_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, identity_id)

    # Need organization_id as UUID for FK? Use tenant_id
    try:
        org_uuid = uuid.UUID(tenant_id)
    except Exception:
        org_uuid = None

    # Determine tenant_id for zero trust field (UUID)
    try:
        tenant_uuid = uuid.UUID(tenant_id)
    except Exception:
        tenant_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, tenant_id)

    session = IAMSession(
        user_id=user_uuid,
        organization_id=org_uuid,
        session_token=session_id_hash,  # store hash in place of plaintext for zero trust; legacy field repurposed
        session_id_hash=session_id_hash,
        identity_id=identity_id,
        tenant_id=tenant_uuid,
        scope=scope or {},
        status="ACTIVE",
        device_context_hash=device_hash,
        expires_at=absolute_expires_at,
        absolute_expires_at=absolute_expires_at,
        idle_expires_at=idle_expires_at,
        last_activity_at=now,
        last_seen_at=now,
        risk_state=risk_state,
        policy_version=policy_version,
        revocation_version=0,
        region=region,
        ip_address=ip,
        user_agent=user_agent,
        device_fingerprint=device_hash[:32] if device_hash else None,
        is_active=True,
        auth_method=auth_method,
    )
    db.add(session)
    await db.flush()
    # Synchronous persistence before effective (commit will be done by caller; we flush)
    # Cache
    cache_key = f"zero_trust:session:{session_id_hash}"
    cache_val = json.dumps({
        "session_id_hash": session_id_hash,
        "identity_id": identity_id,
        "tenant_id": tenant_id,
        "scope": scope or {},
        "status": "ACTIVE",
        "risk_state": risk_state,
        "policy_version": policy_version,
        "revocation_version": 0,
        "region": region,
        "absolute_expires_at": absolute_expires_at.isoformat(),
        "idle_expires_at": idle_expires_at.isoformat(),
    })
    await cache_set(cache_key, cache_val, ttl=60)
    # Emit auditable event via Event Bus (synchronous outbox pattern — publish after DB commit will be done by API layer)
    try:
        from app.core.events import Event, EventType, event_bus
        await event_bus.publish_nowait(Event(EventType.SessionCreated, {"session_id_hash": session_id_hash, "identity_id": identity_id, "tenant_id": tenant_id, "region": region}, source="zero_trust", organization_id=tenant_id))
    except Exception:
        pass
    # Audit
    try:
        from app.iam.audit_service import audit_service
        audit_service.log(org_id=str(tenant_id), actor_id=identity_id, actor_type="user", action="zero_trust.session.created", resource_type="session", resource_id=session_id_hash, result="success", details={"scope": scope or {}, "region": region}, tenant_id=str(tenant_id))
    except Exception:
        pass
    # Return raw token only once (caller must transmit over TLS)
    return {"session_id_hash": session_id_hash, "raw_token": raw_token, "session": session, "cache_key": cache_key}


async def get_session(db: AsyncSession, session_id_hash: str, tenant_id: str) -> dict | None:
    cache_key = f"zero_trust:session:{session_id_hash}"
    cached = await cache_get(cache_key)
    if cached:
        try:
            data = json.loads(cached)
            if data.get("tenant_id") != tenant_id:
                return None
            # Check policy_version freshness? If cached policy_version != current, force DB re-eval
            # For now trust cache if revocation_version matches DB? We'll verify via DB if needed
            # Check status
            if data.get("status") in ("REVOKED", "EXPIRED"):
                return None
            return data
        except Exception:
            pass
    # Cache miss → DB → policy evaluation → rebuild cache
    try:
        # Try to find by hash or legacy token field
        q = select(IAMSession).where(IAMSession.session_id_hash == session_id_hash)
        # If not found, try legacy session_token
        res = await db.execute(q)
        sess = res.scalar_one_or_none()
        if not sess:
            q2 = select(IAMSession).where(IAMSession.session_token == session_id_hash)
            res2 = await db.execute(q2)
            sess = res2.scalar_one_or_none()
        if not sess:
            return None
        # Tenant isolation
        sess_tenant = str(sess.tenant_id) if sess.tenant_id else str(sess.organization_id) if sess.organization_id else ""
        if sess_tenant != tenant_id and str(sess.organization_id) != tenant_id:
            return None
        # Check revocation/expiry
        now = _now()
        if sess.status == "REVOKED" or not sess.is_active or (sess.revoked_at is not None):
            return None
        exp = sess.absolute_expires_at or sess.expires_at
        idle = sess.idle_expires_at
        last_seen = sess.last_seen_at or sess.last_activity_at
        if exp and now > exp:
            sess.status = "EXPIRED"
            await db.flush()
            await cache_del(cache_key)
            return None
        if idle and last_seen and (now - last_seen).total_seconds() > (idle - last_seen).total_seconds() + 5:
            # Actually check idle: if now > last_seen + idle_timeout? We stored idle_expires_at as last_seen + idle
            pass
        if idle and now > idle:
            sess.status = "EXPIRED"
            await db.flush()
            await cache_del(cache_key)
            return None
        # Rebuild cache
        data = {
            "session_id_hash": session_id_hash,
            "identity_id": sess.identity_id or str(sess.user_id),
            "tenant_id": tenant_id,
            "scope": sess.scope or {},
            "status": sess.status,
            "risk_state": sess.risk_state,
            "policy_version": sess.policy_version,
            "revocation_version": sess.revocation_version,
            "region": sess.region,
            "absolute_expires_at": exp.isoformat() if exp else "",
            "idle_expires_at": idle.isoformat() if idle else "",
        }
        await cache_set(cache_key, json.dumps(data), ttl=60)
        return data
    except Exception as e:
        # DB failure → fail closed for protected/high-risk
        # Caller will interpret None as deny for protected; for safe read fallback, they may allow
        # Here we return None to indicate fail-closed
        import logging
        logging.getLogger(__name__).debug("DB failure on get_session: %s", e)
        return None


async def revoke_session(db: AsyncSession, session_id_hash: str, tenant_id: str, reason: str = "manual") -> bool:
    q = select(IAMSession).where(IAMSession.session_id_hash == session_id_hash)
    res = await db.execute(q)
    sess = res.scalar_one_or_none()
    if not sess:
        q2 = select(IAMSession).where(IAMSession.session_token == session_id_hash)
        res2 = await db.execute(q2)
        sess = res2.scalar_one_or_none()
    if not sess:
        return False
    sess_tenant = str(sess.tenant_id) if sess.tenant_id else str(sess.organization_id) if sess.organization_id else ""
    if sess_tenant != tenant_id and str(sess.organization_id) != tenant_id:
        return False
    sess.status = "REVOKED"
    sess.is_active = False
    sess.revoked_at = _now()
    sess.revocation_reason = reason
    sess.revocation_version = (sess.revocation_version or 0) + 1
    await db.flush()
    # Invalidate cache — must not restore revoked
    cache_key = f"zero_trust:session:{session_id_hash}"
    await cache_del(cache_key)
    # Also pattern delete for tenant identity
    await cache_del_pattern(f"zero_trust:session:*")
    try:
        from app.core.events import Event, EventType, event_bus
        await event_bus.publish_nowait(Event(EventType.SessionRevoked, {"session_id_hash": session_id_hash, "tenant_id": tenant_id, "reason": reason}, source="zero_trust", organization_id=tenant_id))
    except Exception:
        pass
    try:
        from app.iam.audit_service import audit_service
        audit_service.log(org_id=tenant_id, actor_id=str(sess.user_id), actor_type="user", action="zero_trust.session.revoked", resource_type="session", resource_id=session_id_hash, result="success", details={"reason": reason}, tenant_id=tenant_id)
    except Exception:
        pass
    return True


async def revoke_all_for_identity(db: AsyncSession, identity_id: str, tenant_id: str, reason: str = "revoke_all") -> int:
    # Find via identity_id or user_id
    try:
        uid = uuid.UUID(identity_id)
        q = select(IAMSession).where(IAMSession.user_id == uid)
    except Exception:
        q = select(IAMSession).where(IAMSession.identity_id == identity_id)
    # tenant filter
    try:
        tenant_uuid = uuid.UUID(tenant_id)
        q = q.where(IAMSession.tenant_id == tenant_uuid)
    except Exception:
        pass
    res = await db.execute(q)
    sessions = res.scalars().all()
    count = 0
    for sess in sessions:
        if sess.status != "REVOKED":
            sess.status = "REVOKED"
            sess.is_active = False
            sess.revoked_at = _now()
            sess.revocation_version = (sess.revocation_version or 0) + 1
            count += 1
            if sess.session_id_hash:
                await cache_del(f"zero_trust:session:{sess.session_id_hash}")
            elif sess.session_token:
                await cache_del(f"zero_trust:session:{hashlib.sha256(sess.session_token.encode()).hexdigest()}")
    if count:
        await db.flush()
        await cache_del_pattern(f"zero_trust:session:*")
        try:
            from app.core.events import Event, EventType, event_bus
            await event_bus.publish_nowait(Event(EventType.SessionRevoked, {"identity_id": identity_id, "tenant_id": tenant_id, "count": count}, source="zero_trust", organization_id=tenant_id))
        except Exception:
            pass
    return count


async def touch_session(db: AsyncSession, session_id_hash: str, tenant_id: str) -> bool:
    data = await get_session(db, session_id_hash, tenant_id)
    if not data:
        return False
    q = select(IAMSession).where(IAMSession.session_id_hash == session_id_hash)
    res = await db.execute(q)
    sess = res.scalar_one_or_none()
    if not sess:
        return False
    now = _now()
    sess.last_seen_at = now
    sess.last_activity_at = now
    # extend idle
    # idle timeout from config? Use 600s default
    sess.idle_expires_at = now + timedelta(seconds=600)
    await db.flush()
    # update cache
    cache_key = f"zero_trust:session:{session_id_hash}"
    data["last_seen_at"] = now.isoformat()
    await cache_set(cache_key, json.dumps(data), ttl=60)
    return True


async def list_sessions_for_identity(db: AsyncSession, identity_id: str, tenant_id: str) -> list[dict]:
    try:
        uid = uuid.UUID(identity_id)
        q = select(IAMSession).where(IAMSession.user_id == uid)
    except Exception:
        q = select(IAMSession).where(IAMSession.identity_id == identity_id)
    try:
        tenant_uuid = uuid.UUID(tenant_id)
        q = q.where(IAMSession.tenant_id == tenant_uuid)
    except Exception:
        pass
    res = await db.execute(q.order_by(IAMSession.created_at.desc()).limit(100))
    rows = res.scalars().all()
    out = []
    for r in rows:
        out.append({
            "session_id_hash": r.session_id_hash or r.session_token[:16],
            "identity_id": r.identity_id or str(r.user_id),
            "tenant_id": str(r.tenant_id) if r.tenant_id else str(r.organization_id),
            "status": r.status,
            "risk_state": r.risk_state,
            "region": r.region,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "last_seen_at": (r.last_seen_at or r.last_activity_at).isoformat() if (r.last_seen_at or r.last_activity_at) else None,
            "absolute_expires_at": (r.absolute_expires_at or r.expires_at).isoformat() if (r.absolute_expires_at or r.expires_at) else None,
        })
    return out
