"""Freshness tracking — FRESH|STALE|MISSING|UNKNOWN, SLO, contract monitoring."""

from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data_platform.models_lakehouse import DataFreshness


async def update_freshness(db: AsyncSession, tenant: str, dataset_id: str, last_update: datetime | None = None, expected_interval_hours: int = 24) -> DataFreshness:
    import uuid
    try:
        did = uuid.UUID(dataset_id)
    except Exception:
        raise ValueError("invalid dataset_id")
    q = select(DataFreshness).where(DataFreshness.tenant == tenant, DataFreshness.dataset_id == did)
    res = await db.execute(q)
    rec = res.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    lu = last_update or now
    # Ensure lu is aware
    if lu.tzinfo is None:
        lu = lu.replace(tzinfo=timezone.utc)
    age_hours = (now - lu).total_seconds() / 3600
    if age_hours <= expected_interval_hours + 0.01:  # tolerance for timing
        status = "FRESH"
    elif age_hours <= expected_interval_hours * 2 + 0.01:
        status = "STALE"
    elif age_hours > expected_interval_hours * 2:
        status = "MISSING"
    else:
        status = "UNKNOWN"
    if rec:
        rec.last_update = lu
        rec.expected_interval_hours = expected_interval_hours
        rec.status = status
    else:
        rec = DataFreshness(tenant=tenant, dataset_id=did, last_update=lu, expected_interval_hours=expected_interval_hours, status=status)
        db.add(rec)
    await db.flush()
    # Emit breach if stale/missing
    if status in ("STALE", "MISSING"):
        try:
            from app.core.events import Event, EventType, event_bus
            await event_bus.publish_nowait(Event(EventType.DataFreshnessBreached, {"dataset_id": dataset_id, "status": status}, source="data_platform", organization_id=tenant))
        except Exception:
            pass
    return rec


async def get_freshness(db: AsyncSession, tenant: str, dataset_id: str) -> DataFreshness | None:
    import uuid
    try:
        did = uuid.UUID(dataset_id)
        q = select(DataFreshness).where(DataFreshness.tenant == tenant, DataFreshness.dataset_id == did)
        res = await db.execute(q)
        return res.scalar_one_or_none()
    except Exception:
        return None


async def check_slo(db: AsyncSession, tenant: str, dataset_id: str) -> dict:
    rec = await get_freshness(db, tenant, dataset_id)
    if not rec:
        return {"slo": "unknown", "status": "UNKNOWN"}
    # SLO: freshness + quality + availability
    return {"freshness": rec.status, "expected_interval": rec.expected_interval_hours, "last_update": rec.last_update.isoformat() if rec.last_update else None}


async def detect_drift(db: AsyncSession, tenant: str, dataset_id: str, current_schema: list, previous_schema: list | None = None) -> dict | None:
    if not previous_schema:
        return None
    old_fields = {f["name"]: f["type"] for f in previous_schema}
    new_fields = {f["name"]: f["type"] for f in current_schema}
    unexpected = set(new_fields) - set(old_fields)
    missing = set(old_fields) - set(new_fields)
    type_changes = {k: (old_fields[k], new_fields[k]) for k in old_fields if k in new_fields and old_fields[k] != new_fields[k]}
    if unexpected or missing or type_changes:
        from app.data_platform.models_lakehouse import DataDriftEvent
        import uuid as _uuid
        try:
            did = _uuid.UUID(dataset_id)
        except Exception:
            did = _uuid.uuid4()
        drift = DataDriftEvent(tenant=tenant, dataset_id=did, drift_type="schema", details={"unexpected": list(unexpected), "missing": list(missing), "type_changes": type_changes})
        db.add(drift)
        await db.flush()
        try:
            from app.core.events import Event, EventType, event_bus
            await event_bus.publish_nowait(Event(EventType.SchemaDriftDetected, {"dataset_id": dataset_id, "details": drift.details}, source="data_platform", organization_id=tenant))
        except Exception:
            pass
        return {"drift": True, "details": drift.details}
    return {"drift": False}
