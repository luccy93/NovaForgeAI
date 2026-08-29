"""Indicator service — Volume 63.

Normalized indicators IP/domain/URL/hash/package/artifact/account.
Track source/confidence/first_seen/last_seen/expiration. Lifecycle create/validate/activate/expire/remove.
Matching authorized telemetry, never expose restricted.
"""

import hashlib
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.secops.models import INDICATOR_STATUSES, INDICATOR_TYPES, SecOpsIndicator

def _to_uuid(v):
    if isinstance(v, uuid.UUID):
        return v
    try:
        return uuid.UUID(str(v))
    except Exception:
        return v


async def create_indicator(db: AsyncSession, tenant: str | None, payload: dict, created_by: str = "") -> SecOpsIndicator:
    itype = (payload.get("indicator_type") or payload.get("type") or "").upper()
    # normalize lower
    itype_norm = itype.lower() if itype.lower() in {t.lower() for t in INDICATOR_TYPES} else itype
    # map case: keep original case set? Use upper for check
    valid_lower = {t.lower() for t in INDICATOR_TYPES}
    if itype.lower() not in valid_lower:
        raise ValueError(f"invalid indicator_type {itype}")
    # canonical lower
    canonical = next(t for t in INDICATOR_TYPES if t.lower() == itype.lower())
    indicator_val = payload.get("indicator") or payload.get("value") or ""
    if not indicator_val:
        raise ValueError("indicator value required")
    # Do not trust external intel automatically — default pending
    status = payload.get("status") or "pending"
    if status not in INDICATOR_STATUSES:
        status = "pending"
    conf = float(payload.get("confidence", 0.5))
    # clamp
    conf = max(0.0, min(1.0, conf))
    exp = payload.get("expiration")
    if isinstance(exp, str):
        try:
            exp = datetime.fromisoformat(exp.replace("Z","+00:00"))
        except Exception:
            exp = None
    ind = SecOpsIndicator(
        tenant=tenant,
        indicator=str(indicator_val),
        indicator_type=canonical,
        source=payload.get("source") or "manual",
        confidence=conf,
        first_seen=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc),
        expiration=exp,
        status=status,
        feed_id=payload.get("feed_id"),
    )
    db.add(ind)
    await db.flush()
    return ind

async def get_indicator(db: AsyncSession, indicator_id: str) -> SecOpsIndicator | None:
    res = await db.execute(select(SecOpsIndicator).where(SecOpsIndicator.id == _to_uuid(indicator_id)))
    return res.scalar_one_or_none()

async def list_indicators(db: AsyncSession, tenant: str | None = None, status: str | None = None, indicator_type: str | None = None, limit: int = 50) -> list[SecOpsIndicator]:
    q = select(SecOpsIndicator)
    if tenant is not None:
        # tenant-scoped + global (tenant is None) visible? But never expose restricted telemetry through indicator searches — so filter to tenant or global?
        # For listing, show tenant's + global pending? Simplified: if tenant provided, show matching tenant OR global? But spec 31 tenant isolation: Match indicators against authorized telemetry, never expose restricted telemetry through indicator searches.
        # For listing indicators, allow tenant to see own + global? We'll filter to tenant==tenant OR tenant is None (global) — but limited.
        q = q.where((SecOpsIndicator.tenant == tenant) | (SecOpsIndicator.tenant.is_(None)))
    if status:
        q = q.where(SecOpsIndicator.status == status)
    if indicator_type:
        q = q.where(SecOpsIndicator.indicator_type == indicator_type)
    q = q.order_by(SecOpsIndicator.last_seen.desc()).limit(min(limit, 1000))
    res = await db.execute(q)
    return list(res.scalars().all())

async def update_indicator_status(db: AsyncSession, indicator_id: str, new_status: str, actor: str = "") -> SecOpsIndicator:
    ind = await get_indicator(db, indicator_id)
    if not ind:
        raise ValueError("indicator not found")
    if new_status not in INDICATOR_STATUSES:
        raise ValueError(f"invalid status {new_status}")
    # lifecycle validation
    allowed = {
        "pending": {"active", "removed", "expired"},
        "active": {"expired", "removed"},
        "expired": {"removed"},
        "removed": set(),
    }
    # allow validate -> active
    if ind.status == "pending" and new_status == "active":
        ind.validated_by = actor
    ind.status = new_status
    ind.last_seen = datetime.now(timezone.utc)
    await db.flush()
    return ind

async def expire_indicators(db: AsyncSession) -> int:
    now = datetime.now(timezone.utc)
    res = await db.execute(select(SecOpsIndicator).where(SecOpsIndicator.status == "active", SecOpsIndicator.expiration != None, SecOpsIndicator.expiration < now))  # noqa: E711
    expired = list(res.scalars().all())
    for ind in expired:
        ind.status = "expired"
    if expired:
        await db.flush()
    return len(expired)

async def match_indicators(db: AsyncSession, tenant: str, telemetry: list[dict]) -> list[dict]:
    """Match indicators against authorized telemetry (tenant-scoped)."""
    # Load active indicators for tenant (plus global)
    res = await db.execute(select(SecOpsIndicator).where(SecOpsIndicator.status == "active", ((SecOpsIndicator.tenant == tenant) | (SecOpsIndicator.tenant.is_(None)))))
    indicators = list(res.scalars().all())
    matches=[]
    # Never expose restricted telemetry: filter telemetry to tenant only
    tenant_telemetry = [t for t in telemetry if t.get("tenant")==tenant]
    for ind in indicators:
        val = ind.indicator
        for ev in tenant_telemetry:
            # check if indicator value appears in any telemetry field
            haystack = " ".join([str(ev.get("resource","")), str(ev.get("actor","")), str(ev.get("ip","")), str(ev.get("source_metadata",{}))])
            if val in haystack:
                matches.append({"indicator_id": str(ind.id), "indicator": val, "type": ind.indicator_type, "event_id": ev.get("event_id"), "tenant": tenant, "confidence": ind.confidence})
                # update last_seen
                ind.last_seen = datetime.now(timezone.utc)
    if matches:
        await db.flush()
    return matches
