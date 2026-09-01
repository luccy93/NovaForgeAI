"""Event-driven automation — correlation, debouncing, throttling."""

import hashlib
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.workflow.models import WorkflowDefinition, WorkflowVersion

# In-memory debounce and throttle stores (would be Redis in prod)
_debounce_cache: dict[str, float] = {}
_throttle_cache: dict[str, list[float]] = {}
_dead_letter: list[dict] = []

# Maps event type -> list of workflow version ids listening
_event_triggers: dict[str, list[str]] = defaultdict(list)


def _fingerprint(tenant: str, workflow_version_id: str, event_type: str, resource: str) -> str:
    raw = f"{tenant}:{workflow_version_id}:{event_type}:{resource}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


async def register_event_trigger(db: AsyncSession, tenant: str, workflow_version_id: str, event_type: str, resource: str | None = None, time_window: int = 300, metadata_filter: dict | None = None):
    key = f"{event_type}:{resource or '*'}"
    _event_triggers[key].append(workflow_version_id)
    return {"workflow_version_id": workflow_version_id, "event_type": event_type, "resource": resource, "time_window": time_window}


async def handle_event(db: AsyncSession, tenant: str, event_type: str, resource: str, payload: dict | None = None, event_time: datetime | None = None) -> list[str]:
    """Handle incoming event, return list of triggered run_ids. Handles correlation, debouncing, throttling."""
    payload = payload or {}
    event_time = event_time or datetime.now(timezone.utc)
    triggered = []
    # Find matching workflows
    candidates = []
    for key, version_ids in _event_triggers.items():
        # key is "event_type:resource" or "event_type:*"
        et, res = key.split(":", 1) if ":" in key else (key, "*")
        if et == event_type and (res == "*" or res == resource):
            candidates.extend(version_ids)
    # Deduplicate
    candidates = list(set(candidates))
    for version_id in candidates:
        # Correlation: check tenant, resource, time window
        # For simplicity, use fingerprint debouncing
        fp = _fingerprint(tenant, version_id, event_type, resource)
        now = time.time()
        # Debouncing: prevent duplicate within 60s
        last = _debounce_cache.get(fp, 0)
        if now - last < 60:
            continue
        # Throttling: limit 10 per minute per workflow
        times = _throttle_cache.get(version_id, [])
        # Prune old
        times = [t for t in times if now - t < 60]
        if len(times) >= 10:
            continue
        # Check workflow still active and tenant
        try:
            from app.workflow.models import WorkflowVersion
            import uuid
            vid = uuid.UUID(version_id)
            q = select(WorkflowVersion).where(WorkflowVersion.id == vid, WorkflowVersion.tenant == tenant)
            res = await db.execute(q)
            ver = res.scalar_one_or_none()
            if not ver or ver.status != "PUBLISHED":
                continue
        except Exception:
            continue
        # Concurrency check
        from app.workflow.concurrency import check_concurrency
        allowed, reason = await check_concurrency(db, tenant, version_id)
        if not allowed:
            # Backpressure: queue or defer
            # For now, dead letter if not allowed due to concurrency
            _dead_letter.append({"workflow_version_id": version_id, "event_type": event_type, "tenant": tenant, "reason": reason, "timestamp": datetime.now(timezone.utc).isoformat()})
            continue
        # Trigger workflow
        from app.workflow.execution import start_run
        try:
            run = await start_run(db, tenant, version_id, trigger={"event_type": event_type, "resource": resource, "payload": payload}, idempotency_key=fp)
            await db.flush()
            triggered.append(str(run.id))
            _debounce_cache[fp] = now
            times.append(now)
            _throttle_cache[version_id] = times
        except Exception as e:
            _dead_letter.append({"workflow_version_id": version_id, "error": str(e), "tenant": tenant})
    return triggered


def get_dead_letter(limit: int = 20) -> list[dict]:
    return _dead_letter[-limit:]


def clear_caches():
    _debounce_cache.clear()
    _throttle_cache.clear()
    _dead_letter.clear()
    _event_triggers.clear()
