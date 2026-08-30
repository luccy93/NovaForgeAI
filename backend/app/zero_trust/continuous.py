"""Continuous trust — re-evaluate access using current identity/session/risk/resource/region/device/security events."""

import hashlib
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.zero_trust.models import IAMIdentityRiskSnapshot
from app.iam.models import IAMSession


RISK_LEVELS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
RISK_WEIGHTS = {
    "failed_auth": 0.3,
    "privilege_change": 0.4,
    "unusual_access": 0.3,
    "secops_alert": 0.4,
    "region_change": 0.2,
    "credential_anomaly": 0.3,
    "agent_anomaly": 0.25,
}


def _to_uuid(v):
    import uuid
    try:
        return uuid.UUID(str(v))
    except Exception:
        return v


async def calculate_access_risk(db: AsyncSession, tenant_id: str, identity_id: str, signals: dict) -> dict:
    """Calculate configurable risk LOW..CRITICAL. Risk is decision-support."""
    score = 0.0
    factors = {}
    for sig, weight in RISK_WEIGHTS.items():
        val = signals.get(sig, 0)
        if isinstance(val, bool):
            val = 1 if val else 0
        elif isinstance(val, (int, float)):
            val = min(val / 5.0, 1.0)  # normalize count
        else:
            val = 0
        contrib = val * weight
        score += contrib
        factors[sig] = round(contrib, 3)
    # Integrate Volume63 SecOps risk if available
    try:
        from app.secops.risk import calculate_risk
        secops_score = calculate_risk(severity=signals.get("severity", "LOW"), confidence=signals.get("confidence", 0.2)) / 100.0
        score = max(score, secops_score * 0.5)
        factors["secops"] = round(secops_score * 0.5, 3)
    except Exception:
        pass
    # Clamp
    score = min(max(score, 0), 1.0)
    if score >= 0.8:
        level = "CRITICAL"
    elif score >= 0.6:
        level = "HIGH"
    elif score >= 0.3:
        level = "MEDIUM"
    else:
        level = "LOW"
    # Persist snapshot with decay
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24 if level in ("HIGH", "CRITICAL") else 72)
    try:
        tenant_uuid = _to_uuid(tenant_id)
    except Exception:
        tenant_uuid = None
    snap = IAMIdentityRiskSnapshot(
        tenant_id=tenant_uuid,  # type: ignore
        identity_id=identity_id,
        identity_type=signals.get("identity_type", "human"),
        risk_level=level,
        risk_score=score,
        factors=factors,
        signals=signals,
        expires_at=expires_at,
    )
    db.add(snap)
    await db.flush()
    try:
        from app.core.events import Event, EventType, event_bus
        await event_bus.publish_nowait(Event(EventType.IdentityRiskChanged, {"identity": identity_id, "risk_level": level, "score": score}, source="zero_trust", organization_id=tenant_id))
    except Exception:
        pass
    return {"identity_id": identity_id, "risk_level": level, "risk_score": round(score, 3), "factors": factors, "expires_at": expires_at.isoformat(), "snapshot_id": str(snap.id)}


async def reevaluate_session_risk(db: AsyncSession, tenant_id: str, session_id_hash: str, signals: dict) -> dict:
    """Re-evaluate session risk, transition ACTIVE→CHALLENGE_REQUIRED→REVOKED."""
    from app.zero_trust.sessions import get_session
    sess_data = await get_session(db, session_id_hash, tenant_id)
    if not sess_data:
        return {"error": "session not found"}
    identity = sess_data.get("identity_id")
    risk = await calculate_access_risk(db, tenant_id, identity, signals)
    level = risk["risk_level"]
    # Load DB row
    q = select(IAMSession).where(IAMSession.session_id_hash == session_id_hash)
    res = await db.execute(q)
    sess = res.scalar_one_or_none()
    if not sess:
        return risk
    old_state = sess.risk_state
    sess.risk_state = level
    # Transition
    if level in ("HIGH", "CRITICAL") and sess.status == "ACTIVE":
        # Check if automatic revocation allowed per policy
        allow_auto = signals.get("auto_revoke_allowed", False)
        # Only policy-approved strong signals allow auto revoke
        if level == "CRITICAL" and allow_auto:
            sess.status = "REVOKED"
            sess.is_active = False
            sess.revoked_at = datetime.now(timezone.utc)
            from app.zero_trust.cache import cache_del
            await cache_del(f"zero_trust:session:{session_id_hash}")
            try:
                from app.core.events import Event, EventType, event_bus
                await event_bus.publish_nowait(Event(EventType.SessionRiskChanged, {"session": session_id_hash, "old": old_state, "new": level}, source="zero_trust", organization_id=tenant_id))
            except Exception:
                pass
            await db.flush()
            return {"session_id_hash": session_id_hash, "old_risk": old_state, "new_risk": level, "transition": "REVOKED", "risk": risk}
        else:
            sess.status = "CHALLENGE_REQUIRED"
            await db.flush()
            try:
                from app.core.events import Event, EventType, event_bus
                await event_bus.publish_nowait(Event(EventType.StepUpRequired, {"session": session_id_hash, "reason": "high risk"}, source="zero_trust", organization_id=tenant_id))
                await event_bus.publish_nowait(Event(EventType.SessionRiskChanged, {"session": session_id_hash, "old": old_state, "new": level}, source="zero_trust", organization_id=tenant_id))
            except Exception:
                pass
            return {"session_id_hash": session_id_hash, "old_risk": old_state, "new_risk": level, "transition": "CHALLENGE_REQUIRED", "risk": risk}
    await db.flush()
    return {"session_id_hash": session_id_hash, "old_risk": old_state, "new_risk": level, "transition": "NONE", "risk": risk}


async def step_up_required(db: AsyncSession, tenant_id: str, session_id_hash: str) -> bool:
    q = select(IAMSession).where(IAMSession.session_id_hash == session_id_hash)
    res = await db.execute(q)
    sess = res.scalar_one_or_none()
    return bool(sess and sess.status == "CHALLENGE_REQUIRED")


async def continuous_authorization_check(db: AsyncSession, tenant_id: str, session_id_hash: str, resource: str, action: str) -> dict:
    """For sensitive long-running ops, periodically re-evaluate."""
    from app.zero_trust.sessions import get_session
    sess = await get_session(db, session_id_hash, tenant_id)
    if not sess:
        return {"allowed": False, "reason": "session not found — fail-closed"}
    if sess.get("status") != "ACTIVE":
        return {"allowed": False, "reason": f"session {sess.get('status')}"}
    # Re-evaluate with current risk
    identity = sess.get("identity_id")
    # Fetch latest risk
    from app.zero_trust.models import IAMIdentityRiskSnapshot
    q = select(IAMIdentityRiskSnapshot).where(IAMIdentityRiskSnapshot.tenant_id == _to_uuid(tenant_id), IAMIdentityRiskSnapshot.identity_id == identity).order_by(IAMIdentityRiskSnapshot.calculated_at.desc()).limit(1)
    res = await db.execute(q)
    snap = res.scalar_one_or_none()
    def _aware(dt):
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    risk_level = snap.risk_level if snap and _aware(snap.expires_at) and _aware(snap.expires_at) > datetime.now(timezone.utc) else "LOW"
    # If high risk, require step-up
    if risk_level in ("HIGH", "CRITICAL") and action in ("DELETE", "EXPORT", "DEPLOY", "ADMIN"):
        return {"allowed": False, "reason": "step-up required", "risk": risk_level, "challenge": True}
    # Otherwise delegate to contextual authorization
    from app.zero_trust.authorization import authorize
    return await authorize(db, identity_id=identity, tenant_id=tenant_id, resource=resource, action=action, session_id_hash=session_id_hash)
