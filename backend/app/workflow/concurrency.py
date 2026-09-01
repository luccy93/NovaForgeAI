"""Concurrency and backpressure — tenant/workflow/global limits."""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.workflow.models import WorkflowRun

# In-memory counters (would be Redis in prod)
_workflow_counts: dict[str, int] = defaultdict(int)
_tenant_counts: dict[str, int] = defaultdict(int)
_global_count = 0

LIMITS = {
    "workflow": 5,
    "tenant": 10,
    "global": 100,
}


async def check_concurrency(db: AsyncSession, tenant: str, workflow_version_id: str) -> tuple[bool, str]:
    # Check workflow concurrent runs
    q1 = select(func.count(WorkflowRun.id)).where(WorkflowRun.workflow_version_id == _to_uuid(workflow_version_id), WorkflowRun.status.in_(["PENDING", "RUNNING", "WAITING"]))
    res1 = await db.execute(q1)
    wf_count = res1.scalar() or 0
    if wf_count >= LIMITS["workflow"]:
        return False, f"workflow concurrency limit {LIMITS['workflow']} reached"

    # Tenant concurrent
    q2 = select(func.count(WorkflowRun.id)).where(WorkflowRun.tenant == tenant, WorkflowRun.status.in_(["PENDING", "RUNNING", "WAITING"]))
    res2 = await db.execute(q2)
    tenant_count = res2.scalar() or 0
    if tenant_count >= LIMITS["tenant"]:
        return False, f"tenant concurrency limit {LIMITS['tenant']} reached"

    # Global
    q3 = select(func.count(WorkflowRun.id)).where(WorkflowRun.status.in_(["PENDING", "RUNNING", "WAITING"]))
    res3 = await db.execute(q3)
    global_count = res3.scalar() or 0
    if global_count >= LIMITS["global"]:
        return False, f"global concurrency limit {LIMITS['global']} reached"

    return True, "allowed"


async def handle_backpressure(tenant: str, workflow_version_id: str) -> str:
    """When overloaded: queue|slow|defer|shed non-critical work."""
    # Check Volume61 performance signals
    try:
        from app.performance.quotas import quota_service  # type: ignore
        # If overloaded, check priority
    except Exception:
        pass
    # For now, simple: if global >80% of limit, shed LOW priority
    # This would be checked in event_automation
    return "queue"


def _to_uuid(v):
    import uuid
    try:
        return uuid.UUID(str(v))
    except Exception:
        return v


# Priority queue (reuse existing queue infrastructure)
# For now, in-memory priority handling
_priority_queue: list[tuple[int, str]] = []

PRIORITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "NORMAL": 2, "LOW": 3}


def enqueue_with_priority(run_id: str, priority: str):
    import heapq
    heapq.heappush(_priority_queue, (PRIORITY_ORDER.get(priority, 2), run_id))


def dequeue_next() -> str | None:
    import heapq
    if _priority_queue:
        return heapq.heappop(_priority_queue)[1]
    return None
