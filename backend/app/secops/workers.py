"""SecOps workers — Volume 63.

Reuse existing worker patterns (observability/workers, resilience/workers).
Tasks: event_normalization, detection, correlation, indicator_matching, posture/coverage.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

logger = logging.getLogger(__name__)

async def event_normalization_worker(db, raw_events: list[dict] | None = None) -> int:
    if not raw_events:
        return 0
    from app.secops.normalization import normalize_event, retain_event
    count=0
    for raw in raw_events:
        norm = normalize_event(raw)
        retain_event(norm)
        count+=1
    return count

async def detection_worker(db, tenant: str, events: list[dict]) -> int:
    from app.secops.detection import evaluate_rules
    alerts = await evaluate_rules(db, tenant, events)
    return len(alerts)

async def correlation_worker(db, events: list[dict], window_seconds: int = 300) -> list[dict]:
    from app.secops.correlation import correlate_events
    return correlate_events(events, time_window_seconds=window_seconds)

async def indicator_matching_worker(db, tenant: str, telemetry: list[dict]) -> list[dict]:
    from app.secops.indicators import match_indicators
    return await match_indicators(db, tenant, telemetry)

async def posture_analysis_worker(db, tenant: str) -> dict:
    # simplified posture: count rules/alerts coverage
    from sqlalchemy import select
    from app.secops.models import SecOpsDetectionRule, SecOpsAlert
    r = await db.execute(select(SecOpsDetectionRule).where(SecOpsDetectionRule.tenant == tenant, SecOpsDetectionRule.enabled == True))  # noqa: E712
    rules = list(r.scalars().all())
    a = await db.execute(select(SecOpsAlert).where(SecOpsAlert.tenant == tenant))
    alerts = list(a.scalars().all())
    return {"tenant": tenant, "rule_coverage": len(rules), "alert_count": len(alerts), "analyzed_at": datetime.now(timezone.utc).isoformat()}

async def coverage_analysis_worker(db, tenant: str) -> dict:
    return await posture_analysis_worker(db, tenant)

async def indicator_expiry_worker(db) -> int:
    from app.secops.indicators import expire_indicators
    return await expire_indicators(db)

async def run_loop(worker_fn, db, interval_seconds: int = 60):
    while True:
        try:
            await worker_fn(db)
        except Exception as e:
            logger.debug("worker error: %s", e)
        await asyncio.sleep(interval_seconds)
