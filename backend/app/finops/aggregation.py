"""Idempotent cost aggregation — Volume 69 Commit 1.

Buckets cost records by hour/day/week/month with an optional dimension
filter. The unique key (tenant, granularity, bucket_start,
dimensions_hash) makes aggregation retry-safe and concurrency-safe:
retries upsert the same bucket instead of creating duplicates.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.finops.governed_common import (
    GRANULARITIES,
    ValidationError,
    _ensure_aware,
    _utcnow,
    clamp_range,
    dimensions_hash,
    parse_time,
)
from app.finops.governed_models import FinOpsCostAggregation, FinOpsCostRecord


def bucket_bounds(moment: datetime, granularity: str) -> tuple[datetime, datetime]:
    moment = _ensure_aware(moment)
    if granularity == "hour":
        start = moment.replace(minute=0, second=0, microsecond=0)
        return start, start + timedelta(hours=1)
    if granularity == "day":
        start = moment.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1)
    if granularity == "week":
        monday = (moment - timedelta(days=moment.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        return monday, monday + timedelta(days=7)
    if granularity == "month":
        start = moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
        return start, end
    raise ValidationError(f"unsupported granularity: {granularity!r}")


def _matches(record: FinOpsCostRecord, dimensions: dict) -> bool:
    for key, value in dimensions.items():
        if value in (None, ""):
            continue
        if str(getattr(record, key, "") or "") != str(value):
            return False
    return True


async def run_aggregation(
    db: AsyncSession,
    tenant: str,
    granularity: str,
    start,
    end,
    *,
    dimensions: Optional[dict] = None,
    actor: str = "",
) -> dict:
    if granularity not in GRANULARITIES:
        raise ValidationError(f"unsupported granularity: {granularity!r}")
    start, end = clamp_range(parse_time(start), parse_time(end))
    dimensions = {k: (v or "") for k, v in (dimensions or {}).items() if k}
    dim_hash = dimensions_hash(dimensions)

    stmt = select(FinOpsCostRecord).where(
        FinOpsCostRecord.tenant == tenant,
        FinOpsCostRecord.occurred_at >= start,
        FinOpsCostRecord.occurred_at <= end,
    )
    records = (await db.execute(stmt)).scalars().all()
    records = [r for r in records if _matches(r, dimensions)]

    buckets: dict[datetime, dict] = {}
    for record in records:
        bstart, bend = bucket_bounds(record.occurred_at, granularity)
        bucket = buckets.setdefault(bstart, {"end": bend, "total": 0, "count": 0, "tokens": 0})
        bucket["total"] += record.amount_cents or 0
        bucket["count"] += 1
        bucket["tokens"] += (record.input_tokens or 0) + (record.output_tokens or 0)

    written = 0
    for bstart, data in sorted(buckets.items()):
        stmt = select(FinOpsCostAggregation).where(
            FinOpsCostAggregation.tenant == tenant,
            FinOpsCostAggregation.granularity == granularity,
            FinOpsCostAggregation.bucket_start == bstart,
            FinOpsCostAggregation.dimensions_hash == dim_hash,
        )
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing is None:
            db.add(FinOpsCostAggregation(
                id=uuid.uuid4(), tenant=tenant, granularity=granularity,
                bucket_start=bstart, bucket_end=data["end"], dimensions_hash=dim_hash,
                dimensions=dimensions, total_cents=data["total"],
                record_count=data["count"], total_tokens=data["tokens"],
            ))
            try:
                await db.flush()
            except IntegrityError:
                await db.rollback()
                existing = (await db.execute(stmt)).scalar_one_or_none()
                if existing is None:
                    raise
        if existing is not None:
            existing.bucket_end = data["end"]
            existing.dimensions = dimensions
            existing.total_cents = data["total"]
            existing.record_count = data["count"]
            existing.total_tokens = data["tokens"]
            await db.flush()
        written += 1
    return {
        "tenant": tenant, "granularity": granularity, "buckets": written,
        "records_scanned": len(records), "dimensions": dimensions,
        "start": start.isoformat(), "end": end.isoformat(),
    }


async def list_aggregations(
    db: AsyncSession, tenant: str, *, granularity: str = "", start=None, end=None, limit: int = 100,
) -> dict:
    stmt = select(FinOpsCostAggregation).where(FinOpsCostAggregation.tenant == tenant)
    if granularity:
        if granularity not in GRANULARITIES:
            raise ValidationError(f"unsupported granularity: {granularity!r}")
        stmt = stmt.where(FinOpsCostAggregation.granularity == granularity)
    if start or end:
        s, e = clamp_range(parse_time(start), parse_time(end))
        stmt = stmt.where(FinOpsCostAggregation.bucket_start >= s, FinOpsCostAggregation.bucket_start <= e)
    limit = min(max(int(limit or 100), 1), 1000)
    rows = (await db.execute(stmt.order_by(desc(FinOpsCostAggregation.bucket_start)).limit(limit))).scalars().all()
    return {
        "items": [{
            "id": str(r.id), "granularity": r.granularity,
            "bucket_start": r.bucket_start.isoformat() if r.bucket_start else None,
            "bucket_end": r.bucket_end.isoformat() if r.bucket_end else None,
            "dimensions": r.dimensions or {}, "total_cents": r.total_cents,
            "record_count": r.record_count, "total_tokens": r.total_tokens,
        } for r in rows],
        "total": len(rows),
    }
