"""Governed FinOps workers — Volume 69 Commit 1.

Lease-based, idempotent background execution following the ai_dev
worker conventions. Aggregation itself is retry-safe through the
unique bucket key; the in-memory lease only prevents redundant
concurrent runs within this process.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_aggregation_leases: dict[str, dict] = {}


def _worker_id() -> str:
    return f"finops-worker-{uuid.uuid4().hex[:8]}"


async def acquire_aggregation_lease(tenant: str, job_key: str, worker_id: str, ttl_seconds: int = 300) -> bool:
    now = datetime.now(timezone.utc)
    key = f"{tenant}:{job_key}"
    lease = _aggregation_leases.get(key)
    if lease and lease["expires_at"] > now and lease["worker_id"] != worker_id:
        return False
    _aggregation_leases[key] = {"worker_id": worker_id, "acquired_at": now, "expires_at": now}
    _aggregation_leases[key]["expires_at"] = now + timedelta_seconds(ttl_seconds)
    return True


def timedelta_seconds(value: int):
    from datetime import timedelta
    return timedelta(seconds=value)


async def release_aggregation_lease(tenant: str, job_key: str, worker_id: str) -> None:
    key = f"{tenant}:{job_key}"
    lease = _aggregation_leases.get(key)
    if lease and lease["worker_id"] == worker_id:
        _aggregation_leases.pop(key, None)


async def execute_aggregation(
    db: AsyncSession,
    tenant: str,
    granularity: str,
    start,
    end,
    *,
    dimensions: Optional[dict] = None,
    worker_id: Optional[str] = None,
    actor: str = "",
) -> dict:
    from app.finops.aggregation import run_aggregation

    worker_id = worker_id or _worker_id()
    job_key = f"agg:{granularity}:{start}:{end}"
    if not await acquire_aggregation_lease(tenant, job_key, worker_id):
        return {"status": "skipped", "reason": "lease held by another worker"}
    try:
        result = await run_aggregation(db, tenant, granularity, start, end, dimensions=dimensions, actor=actor)
        try:
            from app.finops.governed_common import emit_finops_event
            await emit_finops_event("finops_allocation_completed", {"aggregation": result}, tenant)
        except Exception:
            pass
        return {"status": "completed", **result}
    except Exception as exc:
        logger.warning("aggregation job failed: %s", exc)
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
    finally:
        await release_aggregation_lease(tenant, job_key, worker_id)


async def process_pending_aggregations(
    db: AsyncSession, tenant: str, jobs: list[dict], *, worker_id: Optional[str] = None, actor: str = "",
) -> list[dict]:
    """Execute a bounded list of aggregation jobs. Jobs are caller-supplied
    (scheduler-owned); each job: {granularity, start, end, dimensions}."""
    worker_id = worker_id or _worker_id()
    results: list[dict] = []
    for job in jobs[:10]:
        results.append(await execute_aggregation(
            db, tenant, job.get("granularity", "day"), job.get("start"), job.get("end"),
            dimensions=job.get("dimensions"), worker_id=worker_id, actor=actor,
        ))
    return results
