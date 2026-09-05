"""Agent worker loop — Volume 67 Commit 2.

Provides a deterministic, auditable worker loop that claims one or more
pending agent runs, acquires an in-memory lease (mirrors the V66
workflow lease), executes via the appropriate service, records
checkpoints, completes or fails the run, and releases the lease.

The ``execute_agent`` function is the single entry point used by both
the worker loop and the synchronous ``POST /agents/{run_id}/execute``
endpoint, so unit tests can run the exact same deterministic code path
as production.
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_dev import agent as agent_svc
from app.ai_dev.common import emit_event
from app.ai_dev.models import CodeAgentRun

logger = logging.getLogger(__name__)

_agent_leases: dict[str, dict] = {}


async def acquire_agent_lease(tenant: str, run_id: str, worker_id: str, ttl_seconds: int = 30) -> bool:
    key = f"{tenant}:{run_id}"
    now = datetime.now(timezone.utc)
    existing = _agent_leases.get(key)
    if existing and existing["expires_at"] > now and existing["worker_id"] != worker_id:
        return False
    _agent_leases[key] = {
        "worker_id": worker_id,
        "expires_at": now + timedelta(seconds=ttl_seconds),
        "acquired_at": now,
    }
    return True


async def release_agent_lease(tenant: str, run_id: str, worker_id: str) -> None:
    key = f"{tenant}:{run_id}"
    existing = _agent_leases.get(key)
    if existing and existing["worker_id"] == worker_id:
        _agent_leases.pop(key, None)


def _worker_id() -> str:
    return f"worker-{uuid.uuid4().hex[:8]}"


async def _claim_next(db: AsyncSession, tenant: str, *, agent_type: Optional[str] = None) -> Optional[CodeAgentRun]:
    stmt = select(CodeAgentRun).where(CodeAgentRun.tenant == tenant, CodeAgentRun.status == agent_svc.STATUS_ENQUEUED)
    if agent_type:
        stmt = stmt.where(CodeAgentRun.agent_type == agent_type)
    stmt = stmt.order_by(CodeAgentRun.created_at.asc()).limit(5)
    rows = (await db.execute(stmt)).scalars().all()
    for run in rows:
        wid = run.worker_id or _worker_id()
        if await acquire_agent_lease(tenant, str(run.id), wid):
            run.worker_id = wid
            return run
    return None


async def _claim_next_with_id(
    db: AsyncSession, tenant: str, worker_id: str, *, agent_type: Optional[str] = None
) -> Optional[CodeAgentRun]:
    stmt = select(CodeAgentRun).where(CodeAgentRun.tenant == tenant, CodeAgentRun.status == agent_svc.STATUS_ENQUEUED)
    if agent_type:
        stmt = stmt.where(CodeAgentRun.agent_type == agent_type)
    stmt = stmt.order_by(CodeAgentRun.created_at.asc()).limit(5)
    rows = (await db.execute(stmt)).scalars().all()
    for run in rows:
        wid = run.worker_id or worker_id
        if await acquire_agent_lease(tenant, str(run.id), wid):
            run.worker_id = wid
            return run
    return None


async def claim_agent(
    db: AsyncSession, tenant: str, worker_id: str, *, agent_type: Optional[str] = None
) -> Optional[CodeAgentRun]:
    return await _claim_next_with_id(db, tenant, worker_id, agent_type=agent_type)


async def execute_agent(
    db: AsyncSession,
    tenant: str,
    run_id,
    *,
    user_id: Optional[str] = None,
    worker_id: Optional[str] = None,
) -> CodeAgentRun:
    from app.ai_dev import benchmarks as benchmarks_svc
    from app.ai_dev import migration as migration_svc
    from app.ai_dev import refactor as refactor_svc
    from app.ai_dev import release_handoff as release_handoff_svc
    from app.ai_dev import review_ai as review_ai_svc
    from app.ai_dev import agent as _agent_svc

    run = await _agent_svc.get_agent_run(db, tenant, run_id)
    if run.status not in (
        agent_svc.STATUS_ENQUEUED,
        agent_svc.STATUS_BLOCKED,
        agent_svc.STATUS_PAUSED,
    ):
        return run

    wid = worker_id or run.worker_id or _worker_id()
    if not await acquire_agent_lease(tenant, str(run.id), wid):
        raise ValueError("agent run already claimed by another worker")

    run.status = agent_svc.STATUS_RUNNING
    run.worker_id = wid
    if not run.start_time:
        run.start_time = datetime.now(timezone.utc)
    run.attempts += 1
    run.attempted_at = datetime.now(timezone.utc)
    await emit_event(
        "CodeAgentStarted",
        {
            "agent_run_id": str(run.id),
            "worker_id": wid,
            "attempt": run.attempts,
        },
        tenant,
    )

    try:
        plans = await _agent_svc.list_plans(db, tenant, str(run.id))
        handler_map = {
            "refactor": refactor_svc.run_refactor,
            "migrate": migration_svc.run_migration,
            "review": review_ai_svc.refine_review_agent,
            "fix": refactor_svc.run_refactor,
            "seed": _seed_handler,
            "release": _release_handler,
        }
        handler = handler_map.get(run.agent_type)
        if handler is None:
            raise ValueError(f"unsupported agent_type {run.agent_type}")

        try:
            result = await handler(db, tenant, run, user_id=user_id)
        except _agent_svc.NeedsApproval:
            run.status = agent_svc.STATUS_BLOCKED
            run.last_error = "plan approval required"
            await db.flush()
            return run

        run.result = result.get("data", {})
        run.tokens_used = min(run.tokens_used or 0, run.tokens_used or 0) + int(result.get("tokens") or 0)
        if run.budget_tokens and run.tokens_used > run.budget_tokens:
            run.status = agent_svc.STATUS_FAILED
            run.last_error = "token budget exceeded"
            await emit_event(
                "CodeAgentFailed",
                {"agent_run_id": str(run.id), "reason": "token budget exceeded"},
                tenant,
            )
            await db.flush()
            return run

        run.status = agent_svc.STATUS_COMPLETED
        run.end_time = datetime.now(timezone.utc)
        await emit_event(
            "CodeAgentCompleted",
            {
                "agent_run_id": str(run.id),
                "agent_type": run.agent_type,
                "patch_id": result.get("patch_id"),
                "model": result.get("model"),
            },
            tenant,
        )
        await db.flush()
        try:
            await _agent_svc.save_checkpoint(
                db, tenant, str(run.id), summary="Execution completed", state={"phase": "done"}, is_final=True
            )
        except ValueError:
            pass
        return run
    except Exception as exc:
        run.status = agent_svc.STATUS_FAILED
        run.last_error = f"{type(exc).__name__}: {exc}"
        run.end_time = datetime.now(timezone.utc)
        await emit_event(
            "CodeAgentFailed",
            {"agent_run_id": str(run.id), "error": str(exc)},
            tenant,
        )
        await db.flush()
        return run
    finally:
        await release_agent_lease(tenant, str(run.id), wid)


async def _seed_handler(db, tenant, run, *, user_id=None) -> dict:
    try:
        from app.ai_dev import indexing as indexing_svc

        meta = run.metadata_ or {}
        result = await indexing_svc.trigger_full_pipeline(
            db, tenant, run.repository_id,
            branch=meta.get("branch", "main"),
            commit_sha=meta.get("commit_sha"),
        )
        return {
            "model": run.model,
            "tokens": 0,
            "patch_id": None,
            "plan_id": None,
            "data": result,
        }
    except Exception as exc:  # pragma: no cover
        raise ValueError(f"seed handler failed: {exc}") from exc


async def _release_handler(db, tenant, run, *, user_id=None) -> dict:
    from app.ai_dev import release_handoff as release_handoff_svc

    meta = run.metadata_ or {}
    handoff = await release_handoff_svc.prepare_release_handoff(
        db, tenant, user_id or "agent",
        repository_id=run.repository_id,
        agent_run_id=str(run.id),
        version=meta.get("version"),
        environment=meta.get("environment"),
        release_channel=meta.get("release_channel"),
        artifact_id=meta.get("artifact_id"),
        commit_sha=meta.get("commit_sha"),
    )
    return {
        "model": run.model,
        "tokens": 0,
        "patch_id": None,
        "plan_id": None,
        "data": handoff,
    }


async def run_agent_until_done(
    db: AsyncSession,
    tenant: str,
    run_id,
    *,
    user_id: Optional[str] = None,
    worker_id: Optional[str] = None,
) -> CodeAgentRun:
    run = await execute_agent(db, tenant, run_id, user_id=user_id, worker_id=worker_id or _worker_id())
    return run


async def process_pending(
    db: AsyncSession,
    tenant: str,
    worker_id: str,
    *,
    limit: int = 1,
    agent_type: Optional[str] = None,
) -> list[dict]:
    results: list[dict] = []
    for _ in range(max(1, limit)):
        run = await claim_agent(db, tenant, worker_id, agent_type=agent_type)
        if run is None:
            break
        try:
            run = await execute_agent(db, tenant, str(run.id), user_id=None, worker_id=worker_id)
        except Exception as exc:
            logger.exception("process_pending execute failed: %s", exc)
        results.append({"run_id": str(run.id), "status": run.status})
    return results