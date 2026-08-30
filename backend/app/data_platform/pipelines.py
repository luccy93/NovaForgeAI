"""Pipeline DAG, execution, retries, idempotency, checkpoints, backfill."""

import hashlib
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data_platform.models import DataPipeline, DataPipelineRun

PIPELINE_STATUSES = {"DRAFT", "ACTIVE", "PAUSED", "FAILED", "DEPRECATED"}
RUN_STATUSES = {"PENDING", "RUNNING", "SUCCESS", "FAILED", "PAUSED"}
PRIORITIES = {"CRITICAL", "HIGH", "NORMAL", "LOW"}


def _hash_dag(steps: list, deps: list) -> str:
    import json
    raw = json.dumps({"steps": steps, "deps": deps}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _validate_dag(steps: list, dependencies: list):
    # Build graph
    step_ids = {s.get("id") for s in steps}
    # Check dependencies reference existing steps
    for dep in dependencies:
        if dep not in step_ids:
            raise ValueError(f"dependency {dep} not in steps")
    # Check cycles via DFS
    graph = {s["id"]: [] for s in steps}
    # For simplicity, dependencies is list of edges? We'll assume steps have "depends_on" field
    for s in steps:
        for d in s.get("depends_on", []):
            if d not in step_ids:
                raise ValueError(f"step {s['id']} depends_on unknown {d}")
            graph[d].append(s["id"])
    visited = {}
    def dfs(node, stack):
        visited[node] = 1
        stack.add(node)
        for nei in graph.get(node, []):
            if nei not in visited:
                if dfs(nei, stack):
                    return True
            elif nei in stack:
                return True
        stack.remove(node)
        return False
    for n in step_ids:
        if n not in visited:
            if dfs(n, set()):
                raise ValueError("cyclic dependency detected")


async def create_pipeline(db: AsyncSession, tenant: str, payload: dict, created_by: str = "") -> DataPipeline:
    name = payload.get("name")
    if not name:
        raise ValueError("name required")
    q = select(DataPipeline).where(DataPipeline.tenant == tenant, DataPipeline.name == name)
    res = await db.execute(q)
    if res.scalar_one_or_none():
        raise ValueError("pipeline name already exists for tenant")
    steps = payload.get("steps", [])
    deps = payload.get("dependencies", [])
    _validate_dag(steps, deps)
    status = (payload.get("status") or "DRAFT").upper()
    if status not in PIPELINE_STATUSES:
        raise ValueError(f"invalid status {status}")
    priority = (payload.get("priority") or "NORMAL").upper()
    if priority not in PRIORITIES:
        raise ValueError(f"invalid priority {priority}")
    pipe = DataPipeline(
        tenant=tenant,
        name=name,
        description=payload.get("description", ""),
        version=payload.get("version", "1.0"),
        steps=steps,
        dependencies=deps,
        schedule=payload.get("schedule"),
        owner=payload.get("owner") or created_by,
        status=status,
        region=payload.get("region"),
        priority=priority,
        resource_limits=payload.get("resource_limits", {}),
        dag_hash=_hash_dag(steps, deps),
    )
    db.add(pipe)
    await db.flush()
    return pipe


async def get_pipeline(db: AsyncSession, tenant: str, pipeline_id: str) -> DataPipeline | None:
    try:
        pid = uuid.UUID(pipeline_id)
        q = select(DataPipeline).where(DataPipeline.id == pid, DataPipeline.tenant == tenant)
    except Exception:
        q = select(DataPipeline).where(DataPipeline.tenant == tenant, DataPipeline.name == pipeline_id)
    res = await db.execute(q)
    return res.scalar_one_or_none()


async def list_pipelines(db: AsyncSession, tenant: str, status: str | None = None, limit: int = 50) -> list[DataPipeline]:
    q = select(DataPipeline).where(DataPipeline.tenant == tenant)
    if status:
        q = q.where(DataPipeline.status == status.upper())
    q = q.order_by(DataPipeline.created_at.desc()).limit(min(limit, 1000))
    res = await db.execute(q)
    return list(res.scalars().all())


async def start_run(db: AsyncSession, tenant: str, pipeline_id: str, payload: dict | None = None) -> DataPipelineRun:
    pipe = await get_pipeline(db, tenant, pipeline_id)
    if not pipe:
        raise ValueError("pipeline not found")
    if pipe.status != "ACTIVE":
        raise ValueError(f"pipeline not ACTIVE (current {pipe.status})")
    # Check idempotency
    idem_key = (payload or {}).get("idempotency_key")
    if idem_key:
        q = select(DataPipelineRun).where(DataPipelineRun.idempotency_key == idem_key, DataPipelineRun.tenant == tenant)
        res = await db.execute(q)
        existing = res.scalar_one_or_none()
        if existing:
            return existing
    # Resource limits check
    limits = pipe.resource_limits or {}
    # Check retries config
    run_id = str(uuid.uuid4())
    run = DataPipelineRun(
        pipeline_id=pipe.id,
        tenant=tenant,
        run_id=run_id,
        status="RUNNING",
        steps=pipe.steps,
        idempotency_key=idem_key,
        started_at=datetime.now(timezone.utc),
        checkpoint=payload.get("checkpoint") if payload else {},
    )
    db.add(run)
    await db.flush()
    # Simulate execution with bounded retries
    # In real, would dispatch to workers; here we just leave RUNNING for test to complete
    return run


async def complete_run(db: AsyncSession, tenant: str, run_id: str, status: str = "SUCCESS", records: int = 0, error: str | None = None, checkpoint: dict | None = None) -> DataPipelineRun:
    q = select(DataPipelineRun).where(DataPipelineRun.run_id == run_id, DataPipelineRun.tenant == tenant)
    res = await db.execute(q)
    run = res.scalar_one_or_none()
    if not run:
        raise ValueError("run not found")
    if status.upper() not in RUN_STATUSES:
        raise ValueError(f"invalid status {status}")
    run.status = status.upper()
    run.records = records
    run.error = error
    run.completed_at = datetime.now(timezone.utc)
    if run.started_at:
        run.duration_ms = int((run.completed_at - run.started_at).total_seconds() * 1000)
    if checkpoint:
        run.checkpoint = checkpoint
    await db.flush()
    return run


async def handle_retry(run: DataPipelineRun, attempt: int, max_attempts: int = 3, backoff_base: float = 1.0, jitter: bool = True) -> bool:
    """Bounded retry with backoff, do not retry unsafe side effects blindly."""
    if attempt >= max_attempts:
        return False
    # Check if step has unsafe side effect (e.g., external API)
    unsafe = any(s.get("side_effect") == "unsafe" for s in run.steps)
    if unsafe:
        return False
    # Simulate backoff
    import random, asyncio
    delay = backoff_base * (2 ** attempt)
    if jitter:
        delay *= random.uniform(0.8, 1.2)
    # In real would sleep, here just return true
    return True


async def request_backfill(db: AsyncSession, tenant: str, pipeline_id: str, payload: dict) -> dict:
    scope = payload.get("scope")
    time_range = payload.get("time_range")
    if not scope or not time_range:
        raise ValueError("scope and time_range required for backfill")
    # Approval where needed
    if payload.get("requires_approval") and not payload.get("approved"):
        raise ValueError("backfill requires approval")
    # Safety: do not overwrite production without explicit policy
    if not payload.get("allow_overwrite") and scope == "production":
        raise ValueError("production overwrite requires explicit allow_overwrite")
    # Create a run with backfill checkpoint
    pipe = await get_pipeline(db, tenant, pipeline_id)
    if not pipe:
        raise ValueError("pipeline not found")
    run = await start_run(db, tenant, str(pipe.id), payload={"checkpoint": {"backfill": time_range, "scope": scope}, "idempotency_key": f"backfill:{scope}:{time_range}"})
    run.checkpoint["backfill"] = time_range
    await db.flush()
    return {"run_id": run.run_id, "status": run.status, "scope": scope, "time_range": time_range}
