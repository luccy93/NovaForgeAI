"""Access anomaly detection — evidence-backed."""

from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.iam.models import IAMAuditLog


async def detect_anomalies(db: AsyncSession, tenant_id: str, since_hours: int = 24) -> list[dict]:
    """Detect unusual resource/region/time/volume/privilege. AI-assisted remains evidence-backed."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    # Use audit logs as source
    q = select(IAMAuditLog).where(IAMAuditLog.organization_id == _to_uuid(tenant_id), IAMAuditLog.created_at >= cutoff).limit(1000)
    try:
        res = await db.execute(q)
        logs = res.scalars().all()
    except Exception:
        logs = []
    anomalies = []
    # Unusual resource
    resource_counts = Counter(log.resource_id for log in logs if log.resource_id)
    for res_id, cnt in resource_counts.items():
        if cnt == 1:
            # Check if resource never seen before for actor? Simplified: single access to sensitive resource
            anomalies.append({"type": "unusual_resource", "resource": res_id, "count": cnt, "evidence": f"single access to {res_id}", "confidence": 0.6})
    # Unusual region
    region_counts = Counter(log.details.get("region") for log in logs if log.details and log.details.get("region"))
    for region, cnt in region_counts.items():
        if cnt == 1 and region:
            anomalies.append({"type": "unusual_region", "region": region, "count": cnt, "evidence": f"first access from {region}", "confidence": 0.5})
    # Unusual time (outside 9-17 UTC)
    unusual_time = [log for log in logs if log.created_at.hour < 6 or log.created_at.hour > 22]
    if len(unusual_time) > 5:
        anomalies.append({"type": "unusual_time", "count": len(unusual_time), "evidence": "multiple accesses outside business hours", "confidence": 0.55})
    # Unusual volume
    actor_counts = Counter(log.actor_id for log in logs if log.actor_id)
    for actor, cnt in actor_counts.items():
        if cnt > 50:
            anomalies.append({"type": "unusual_volume", "actor": str(actor), "count": cnt, "evidence": f"high volume {cnt} in {since_hours}h", "confidence": 0.7})
    # Unusual privilege
    priv_logs = [log for log in logs if "privileged" in log.action or "admin" in log.action]
    for log in priv_logs:
        if log.risk_score > 0.7:
            anomalies.append({"type": "unusual_privilege", "action": log.action, "actor": str(log.actor_id), "evidence": log.details, "confidence": 0.65})
    # Filter to evidence-backed only (confidence >=0.5)
    anomalies = [a for a in anomalies if a.get("confidence", 0) >= 0.5]
    if anomalies:
        try:
            from app.core.events import Event, EventType, event_bus
            await event_bus.publish_nowait(Event(EventType.AccessAnomalyDetected, {"tenant": tenant_id, "count": len(anomalies)}, source="zero_trust", organization_id=tenant_id))
        except Exception:
            pass
    return anomalies[:20]


def _to_uuid(v):
    import uuid
    try:
        return uuid.UUID(str(v))
    except Exception:
        return v


async def detect_impossible_access(db: AsyncSession, tenant_id: str) -> list[dict]:
    """Where reliable location/time data exists, identify contradictory patterns. Never conclusive from IP alone."""
    # Check for same identity two regions within short time where device is managed
    q = select(IAMAuditLog).where(IAMAuditLog.organization_id == _to_uuid(tenant_id)).order_by(IAMAuditLog.created_at.desc()).limit(500)
    try:
        res = await db.execute(q)
        logs = res.scalars().all()
    except Exception:
        return []
    by_actor = defaultdict(list)
    for log in logs:
        by_actor[str(log.actor_id)].append(log)
    findings = []
    for actor, entries in by_actor.items():
        # Sort by time
        entries.sort(key=lambda x: x.created_at)
        for i in range(len(entries) - 1):
            a, b = entries[i], entries[i + 1]
            delta = (b.created_at - a.created_at).total_seconds()
            region_a = (a.details or {}).get("region") if a.details else None
            region_b = (b.details or {}).get("region") if b.details else None
            device_a = (a.details or {}).get("device_managed") if a.details else None
            # Only flag if device is managed and reliable
            if region_a and region_b and region_a != region_b and delta < 3600 and device_a is True:
                findings.append({"actor": actor, "type": "impossible_access", "regions": [region_a, region_b], "delta_seconds": delta, "evidence": "managed device rapid region change", "confidence": 0.6, "note": "hypothesis — not definitive from IP alone"})
    return findings
