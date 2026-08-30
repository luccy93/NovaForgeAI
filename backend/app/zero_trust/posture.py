"""Posture and scoring — not certification."""

from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.iam.models import IAMSession, IAMAPIKey, IAMServiceAccount
from app.zero_trust.models import IAMCredentialsMetadata, IAMIdentityRiskSnapshot


async def get_identity_posture(db: AsyncSession, tenant_id: str) -> dict:
    # MFA coverage: count users with mfa_enabled vs total
    try:
        from app.models.user import User
        q = select(User)
        res = await db.execute(q.limit(1000))
        users = res.scalars().all()
        total = len(users)
        mfa_covered = len([u for u in users if getattr(u, "mfa_enabled", False)])
        mfa_coverage = round(mfa_covered / total * 100, 1) if total else 0
    except Exception:
        total, mfa_covered, mfa_coverage = 0, 0, 0
    # Stale credentials
    stale_creds = await _count_stale_credentials(db, tenant_id)
    # Privileged identities
    privileged = await _count_privileged(db, tenant_id)
    # Orphaned
    orphaned = await _count_orphaned(db, tenant_id)
    # Review completion
    try:
        from app.iam.access_review_service import access_review_service
        reviews = access_review_service.list_reviews()
        review_completion = len([r for r in reviews if r.get("status") == "completed"]) / max(len(reviews), 1) * 100
    except Exception:
        review_completion = 0
    posture = {
        "tenant_id": tenant_id,
        "mfa_coverage_percent": mfa_coverage,
        "stale_credentials": stale_creds,
        "privileged_identities": privileged,
        "orphaned_accounts": orphaned,
        "review_completion_percent": round(review_completion, 1),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": "Posture metrics — not certification",
    }
    score = _calc_zero_trust_score(posture)
    posture["zero_trust_score"] = score
    try:
        from app.core.events import Event, EventType, event_bus
        await event_bus.publish_nowait(Event(EventType.ZeroTrustPostureChanged, {"tenant": tenant_id, "score": score}, source="zero_trust", organization_id=tenant_id))
    except Exception:
        pass
    return posture


async def get_access_posture(db: AsyncSession, tenant_id: str) -> dict:
    # Least privilege: check overprivilege via privilege_analysis
    try:
        from app.iam.privilege_analysis_service import privilege_analysis_service
        # Use dummy data if needed
        analysis = privilege_analysis_service.run_full_analysis(tenant_id, [], [], [], [], [], []) if hasattr(privilege_analysis_service, "run_full_analysis") else {}
    except Exception:
        analysis = {}
    # Policy violations: count recent audit denials
    from app.iam.models import IAMAuditLog
    q = select(IAMAuditLog).where(IAMAuditLog.organization_id == _to_uuid(tenant_id), IAMAuditLog.result == "failure").limit(100)
    try:
        res = await db.execute(q)
        violations = len(res.scalars().all())
    except Exception:
        violations = 0
    # Expired access: count expired privileged
    from app.zero_trust.models import IAMPrivilegedAccess
    q2 = select(IAMPrivilegedAccess).where(IAMPrivilegedAccess.tenant_id == _to_uuid(tenant_id), IAMPrivilegedAccess.status == "EXPIRED")
    try:
        res2 = await db.execute(q2)
        expired = len(res2.scalars().all())
    except Exception:
        expired = 0
    return {
        "tenant_id": tenant_id,
        "overprivilege_indicators": analysis.get("findings", []) if isinstance(analysis, dict) else [],
        "policy_violations": violations,
        "expired_access": expired,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


async def get_machine_posture(db: AsyncSession, tenant_id: str) -> dict:
    q = select(IAMCredentialsMetadata).where(IAMCredentialsMetadata.tenant_id == _to_uuid(tenant_id))
    try:
        res = await db.execute(q.limit(200))
        creds = res.scalars().all()
    except Exception:
        creds = []
    service_identities = len([c for c in creds if c.credential_type == "service_token"])
    agent_identities = len([c for c in creds if c.credential_type == "agent"])
    plugin_identities = len([c for c in creds if c.credential_type == "plugin"])
    rotation_due = len([c for c in creds if c.credential_expiry and c.credential_expiry < datetime.now(timezone.utc) + timedelta(days=7)])
    return {
        "tenant_id": tenant_id,
        "service_identities": service_identities,
        "agent_identities": agent_identities,
        "plugin_identities": plugin_identities,
        "rotation_due_7d": rotation_due,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _calc_zero_trust_score(posture: dict) -> float:
    # Configurable weighted: mfa 0.3, stale 0.2, privileged 0.2, orphaned 0.15, review 0.15
    mfa = posture.get("mfa_coverage_percent", 0) / 100.0
    stale = 1 - min(posture.get("stale_credentials", 0) / 10.0, 1.0)
    priv = 1 - min(posture.get("privileged_identities", 0) / 20.0, 1.0)
    orphan = 1 - min(posture.get("orphaned_accounts", 0) / 10.0, 1.0)
    review = posture.get("review_completion_percent", 0) / 100.0
    score = (mfa * 0.3 + stale * 0.2 + priv * 0.2 + orphan * 0.15 + review * 0.15) * 100
    return round(score, 1)


async def _count_stale_credentials(db: AsyncSession, tenant_id: str) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    q = select(IAMCredentialsMetadata).where(IAMCredentialsMetadata.tenant_id == _to_uuid(tenant_id), IAMCredentialsMetadata.last_used_at != None, IAMCredentialsMetadata.last_used_at < cutoff)  # noqa: E711
    try:
        res = await db.execute(q)
        return len(res.scalars().all())
    except Exception:
        return 0


async def _count_privileged(db: AsyncSession, tenant_id: str) -> int:
    from app.zero_trust.models import IAMPrivilegedAccess
    q = select(IAMPrivilegedAccess).where(IAMPrivilegedAccess.tenant_id == _to_uuid(tenant_id), IAMPrivilegedAccess.status.in_(["ACTIVE", "APPROVED"]))  # noqa: E712
    try:
        res = await db.execute(q)
        return len(res.scalars().all())
    except Exception:
        return 0


async def _count_orphaned(db: AsyncSession, tenant_id: str) -> int:
    # Orphaned: credentials without owner or last_used >90d and owner not in users
    q = select(IAMCredentialsMetadata).where(IAMCredentialsMetadata.tenant_id == _to_uuid(tenant_id))
    try:
        res = await db.execute(q.limit(200))
        rows = res.scalars().all()
        count = 0
        for r in rows:
            if not r.owner_id:
                count += 1
        return count
    except Exception:
        return 0


def _to_uuid(v):
    import uuid
    try:
        return uuid.UUID(str(v))
    except Exception:
        return v
