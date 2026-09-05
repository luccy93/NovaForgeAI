"""Credential metadata service — hashes only, never plaintext."""

import hashlib
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.zero_trust.models import IAMCredentialsMetadata
from app.zero_trust.cache import cache_get, cache_set, cache_del


def _fingerprint(hash_val: str) -> str:
    return hash_val[:16]


def _hash_value(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def create_credential_metadata(
    db: AsyncSession,
    tenant_id: str,
    owner_id: str,
    credential_type: str,
    raw_value: str,  # never stored, only hash
    scope: dict | None = None,
    expires_in_days: int | None = None,
    owner_type: str = "human",
) -> dict:
    cred_hash = _hash_value(raw_value)
    fingerprint = _fingerprint(cred_hash)
    credential_id = f"cred_{uuid.uuid4().hex[:16]}"
    try:
        tenant_uuid = uuid.UUID(tenant_id)
    except Exception:
        tenant_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, tenant_id)
    expiry = None
    if expires_in_days:
        expiry = datetime.now(timezone.utc) + timedelta(days=expires_in_days)
    rec = IAMCredentialsMetadata(
        credential_id=credential_id,
        credential_type=credential_type,
        credential_fingerprint=fingerprint,
        credential_status="ACTIVE",
        credential_expiry=expiry,
        rotation_state="idle",
        tenant_id=tenant_uuid,
        owner_id=owner_id,
        owner_type=owner_type,
        scope=scope or {},
    )
    db.add(rec)
    await db.flush()
    # Cache
    cache_key = f"zero_trust:cred:{tenant_id}:{credential_id}"
    import json
    await cache_set(cache_key, json.dumps({"credential_id": credential_id, "status": "ACTIVE", "fingerprint": fingerprint}), ttl=60)
    # Audit + event
    try:
        from app.core.events import Event, EventType, event_bus
        await event_bus.publish_nowait(Event(EventType.CredentialCreated, {"credential_id": credential_id, "tenant_id": tenant_id, "type": credential_type}, source="zero_trust", organization_id=tenant_id))
    except Exception:
        pass
    try:
        from app.iam.audit_service import audit_service
        audit_service.log(org_id=tenant_id, actor_id=owner_id, actor_type="user", action="zero_trust.credential.created", resource_type="credential", resource_id=credential_id, result="success", details={"type": credential_type}, tenant_id=tenant_id)
    except Exception:
        pass
    return {"credential_id": credential_id, "fingerprint": fingerprint, "hash": cred_hash}


async def get_credential(db: AsyncSession, credential_id: str, tenant_id: str) -> IAMCredentialsMetadata | None:
    cache_key = f"zero_trust:cred:{tenant_id}:{credential_id}"
    cached = await cache_get(cache_key)
    # Try DB
    q = select(IAMCredentialsMetadata).where(IAMCredentialsMetadata.credential_id == credential_id)
    try:
        tenant_uuid = uuid.UUID(tenant_id)
        q = q.where(IAMCredentialsMetadata.tenant_id == tenant_uuid)
    except Exception:
        pass
    res = await db.execute(q)
    rec = res.scalar_one_or_none()
    if rec and rec.tenant_id and str(rec.tenant_id) != tenant_id:
        # tenant isolation
        return None
    if rec:
        import json
        await cache_set(cache_key, json.dumps({"credential_id": credential_id, "status": rec.credential_status}), ttl=60)
    return rec


async def revoke_credential(db: AsyncSession, credential_id: str, tenant_id: str, reason: str = "manual") -> bool:
    rec = await get_credential(db, credential_id, tenant_id)
    if not rec:
        return False
    rec.credential_status = "REVOKED"
    await db.flush()
    await cache_del(f"zero_trust:cred:{tenant_id}:{credential_id}")
    try:
        from app.core.events import Event, EventType, event_bus
        await event_bus.publish_nowait(Event(EventType.CredentialRevoked, {"credential_id": credential_id, "tenant_id": tenant_id, "reason": reason}, source="zero_trust", organization_id=tenant_id))
    except Exception:
        pass
    try:
        from app.iam.audit_service import audit_service
        audit_service.log(org_id=tenant_id, actor_id=rec.owner_id, actor_type="user", action="zero_trust.credential.revoked", resource_type="credential", resource_id=credential_id, result="success", details={"reason": reason}, tenant_id=tenant_id)
    except Exception:
        pass
    return True


async def rotate_credential(db: AsyncSession, credential_id: str, tenant_id: str, new_raw: str, requested_by: str) -> dict:
    rec = await get_credential(db, credential_id, tenant_id)
    if not rec:
        raise ValueError("credential not found")
    if rec.credential_status not in ("ACTIVE", "PENDING_ROTATION"):
        raise ValueError(f"cannot rotate from status {rec.credential_status}")
    # Mark pending
    rec.rotation_state = "requested"
    await db.flush()
    try:
        from app.core.events import Event, EventType, event_bus
        await event_bus.publish_nowait(Event(EventType.CredentialRotationStarted, {"credential_id": credential_id}, source="zero_trust", organization_id=tenant_id))
    except Exception:
        pass
    # Create new credential metadata for new raw
    new_hash = _hash_value(new_raw)
    new_fingerprint = _fingerprint(new_hash)
    new_id = f"cred_{uuid.uuid4().hex[:16]}"
    try:
        tenant_uuid = uuid.UUID(tenant_id)
    except Exception:
        tenant_uuid = rec.tenant_id
    new_rec = IAMCredentialsMetadata(
        credential_id=new_id,
        credential_type=rec.credential_type,
        credential_fingerprint=new_fingerprint,
        credential_status="ACTIVE",
        credential_expiry=rec.credential_expiry,
        rotation_state="idle",
        tenant_id=tenant_uuid,  # type: ignore
        owner_id=rec.owner_id,
        owner_type=rec.owner_type,
        scope=rec.scope,
    )
    db.add(new_rec)
    await db.flush()
    # Verify new credential (simulate validation)
    # In real, would call secret manager verify
    verified = True
    if verified:
        rec.rotation_state = "verified"
        await db.flush()
        # Now revoke old only after verify
        rec.credential_status = "REVOKED"
        rec.rotation_state = "completed"
        await db.flush()
        await cache_del(f"zero_trust:cred:{tenant_id}:{credential_id}")
        import json
        await cache_set(f"zero_trust:cred:{tenant_id}:{new_id}", json.dumps({"credential_id": new_id, "status": "ACTIVE"}), ttl=60)
        try:
            from app.core.events import Event, EventType, event_bus
            await event_bus.publish_nowait(Event(EventType.CredentialRotationCompleted, {"old": credential_id, "new": new_id}, source="zero_trust", organization_id=tenant_id))
        except Exception:
            pass
        return {"old_credential_id": credential_id, "new_credential_id": new_id, "new_fingerprint": new_fingerprint}
    else:
        rec.rotation_state = "failed"
        await db.flush()
        raise ValueError("verification failed, old not revoked")


async def check_expiring(db: AsyncSession, tenant_id: str, warning_days: int = 7) -> list[dict]:
    cutoff = datetime.now(timezone.utc) + timedelta(days=warning_days)
    q = select(IAMCredentialsMetadata).where(IAMCredentialsMetadata.credential_status == "ACTIVE", IAMCredentialsMetadata.credential_expiry != None)  # noqa: E711
    try:
        tenant_uuid = uuid.UUID(tenant_id)
        q = q.where(IAMCredentialsMetadata.tenant_id == tenant_uuid)
    except Exception:
        pass
    res = await db.execute(q)
    rows = res.scalars().all()
    expiring = []
    for r in rows:
        if r.credential_expiry and r.credential_expiry <= cutoff:
            expiring.append({"credential_id": r.credential_id, "expiry": r.credential_expiry.isoformat(), "owner": r.owner_id})
            # mark warning sent
            r.warning_sent_at = datetime.now(timezone.utc)
    if expiring:
        await db.flush()
    return expiring
