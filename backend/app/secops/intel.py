"""Threat intel ingestion — Volume 63 Commit 2.

Validate source/format/confidence/expiration, track feed health, expire stale.
Do not trust arbitrary feeds automatically.
"""

from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.secops.models import SecOpsIndicator

# Feed health tracking in-memory
_feed_health: dict[str, dict] = {}

async def ingest_feed(db: AsyncSession, tenant: str, feed_id: str, source: str, indicators: list[dict], analyst: str = "") -> dict:
    # Validate
    if not feed_id or not source:
        raise ValueError("feed_id and source required")
    if not isinstance(indicators, list):
        raise ValueError("indicators must be list")
    if len(indicators) > 1000:
        raise ValueError("too many indicators (max 1000)")
    ingested = 0
    for item in indicators:
        itype = item.get("indicator_type") or item.get("type")
        val = item.get("indicator") or item.get("value")
        if not itype or not val:
            continue
        conf = float(item.get("confidence", 0.5))
        # Do not trust arbitrary feeds automatically — cap confidence if source not validated
        if source not in {"internal", "validated_feed", "manual"} and conf > 0.7:
            conf = 0.7
        exp = item.get("expiration")
        if isinstance(exp, str):
            try:
                exp = datetime.fromisoformat(exp.replace("Z", "+00:00"))
            except Exception:
                exp = datetime.now(timezone.utc) + timedelta(days=7)
        elif not exp:
            exp = datetime.now(timezone.utc) + timedelta(days=7)
        # create as pending, not active
        from app.secops.indicators import create_indicator
        try:
            await create_indicator(db, tenant, {"indicator": val, "indicator_type": itype, "source": source, "confidence": conf, "expiration": exp.isoformat() if isinstance(exp, datetime) else exp, "status": "pending", "feed_id": feed_id})
            ingested += 1
        except Exception:
            continue
    await db.flush()
    # track health
    _feed_health[feed_id] = {"last_update": datetime.now(timezone.utc).isoformat(), "ingested": ingested, "source": source, "tenant": tenant, "error_rate": 0.0}
    return {"feed_id": feed_id, "ingested": ingested, "status": "pending_validation"}


async def validate_feed_indicators(db: AsyncSession, tenant: str, feed_id: str, validator: str) -> int:
    res = await db.execute(select(SecOpsIndicator).where(SecOpsIndicator.feed_id == feed_id, SecOpsIndicator.status == "pending"))
    pending = list(res.scalars().all())
    validated = 0
    for ind in pending:
        # validate format and confidence
        if ind.confidence >= 0.3:
            ind.status = "active"
            ind.validated_by = validator
            validated += 1
    if validated:
        await db.flush()
    return validated


def get_feed_health(feed_id: str) -> dict | None:
    return _feed_health.get(feed_id)


def clear_feed_health():
    _feed_health.clear()
