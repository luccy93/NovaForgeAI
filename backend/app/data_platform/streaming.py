"""Streaming — reuse EventBus, no duplicate bus."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data_platform.models import DataStream, DataCheckpoint
from app.core.events import Event, EventType, event_bus


async def create_stream(db: AsyncSession, tenant: str, topic: str, partition: int = 0, consumer_group: str | None = None, schema_id: str | None = None, region: str | None = None) -> DataStream:
    # Check region residency for restricted? Already handled at dataset level
    stream = DataStream(
        tenant=tenant,
        topic=topic,
        partition=partition,
        consumer_group=consumer_group,
        schema_id=uuid.UUID(schema_id) if schema_id else None,
        region=region,
    )
    db.add(stream)
    await db.flush()
    return stream


async def ingest_event(db: AsyncSession, tenant: str, topic: str, payload: dict, partition: int = 0, region: str | None = None) -> dict:
    # Reuse EventBus
    event = Event(EventType.analytics_event_ingested, {"topic": topic, "payload": payload, "tenant": tenant}, source="data_platform", organization_id=tenant)
    # Idempotency: hash payload
    import hashlib, json
    key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    event.data["idempotency_key"] = key
    await event_bus.publish_nowait(event)
    # Update offset
    q = select(DataStream).where(DataStream.tenant == tenant, DataStream.topic == topic, DataStream.partition == partition)
    res = await db.execute(q)
    stream = res.scalar_one_or_none()
    if stream:
        stream.offset += 1
        await db.flush()
    return {"event_id": event.id, "topic": topic, "partition": partition, "idempotency_key": key}


async def consume_events(db: AsyncSession, tenant: str, topic: str, consumer: str, partition: int = 0, limit: int = 10) -> list[dict]:
    # Get checkpoint
    from app.data_platform.ingestion import get_checkpoint
    chk = await get_checkpoint(db, tenant, consumer, topic, partition)
    offset = chk.offset if chk else 0
    # Replay from EventBus recent
    events = await event_bus.get_recent(event_type=None, limit=limit)
    # Filter by tenant and topic
    filtered = [e for e in events if e.get("organization_id") == tenant and e.get("data", {}).get("topic") == topic]
    # Idempotent: track processed idempotency keys
    seen = set()
    out = []
    for e in filtered[offset:offset+limit]:
        key = e.get("data", {}).get("idempotency_key")
        if key and key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


async def handle_out_of_order(events: list[dict], policy: str = "buffer") -> list[dict]:
    if policy == "buffer":
        # Sort by timestamp watermark
        return sorted(events, key=lambda x: x.get("timestamp", ""))
    elif policy == "watermark":
        # Drop late events beyond watermark
        import datetime as dt
        watermark = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=60)
        return [e for e in events if e.get("timestamp", "") >= watermark.isoformat()]
    return events


async def dead_letter(db: AsyncSession, tenant: str, topic: str, payload: dict, error: str) -> dict:
    # Governed DLQ handling
    dlq = {"tenant": tenant, "topic": topic, "payload": payload, "error": error, "timestamp": datetime.now(timezone.utc).isoformat()}
    # In real, would write to governance_dlp_events or dead_letter table
    return dlq


async def get_lag(db: AsyncSession, tenant: str, topic: str, consumer: str) -> dict:
    q = select(DataCheckpoint).where(DataCheckpoint.tenant == tenant, DataCheckpoint.consumer == consumer, DataCheckpoint.topic == topic)
    res = await db.execute(q)
    chks = res.scalars().all()
    # Find stream offset
    q2 = select(DataStream).where(DataStream.tenant == tenant, DataStream.topic == topic)
    res2 = await db.execute(q2)
    streams = res2.scalars().all()
    total_lag = 0
    for s in streams:
        chk = next((c for c in chks if c.partition == s.partition), None)
        if chk:
            total_lag += max(s.offset - chk.offset, 0)
        else:
            total_lag += s.offset
    return {"topic": topic, "consumer": consumer, "lag": total_lag}
