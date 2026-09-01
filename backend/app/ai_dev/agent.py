"""Governed engineering agents — Volume 67 Commit 2.

Agents enqueue kept in ``code_agent_runs``; work is executed by the
worker loop in ``workers.py`` using an honest preferred path: when a
model route exists it is used for narrative/rationale, otherwise
deterministic planning/execution produces real, verifiable artifacts
(patch rows, checkpoints, plan rows). No result values are fabricated.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_dev.common import (
    DEFAULT_AGENT_BUDGET_TOKENS,
    DEFAULT_AGENT_THROTTLE,
    _as_uuid,
    emit_event,
    resolve_repository,
)
from app.ai_dev.models import (
    CodeAgentCheckpoint,
    CodeAgentFeedback,
    CodeAgentPlan,
    CodeAgentRun,
)

logger = logging.getLogger(__name__)

AGENT_TYPES = ("refactor", "migrate", "review", "fix", "seed", "release")
APPROVAL_AGENT_TYPES = ("refactor", "migrate", "release")

STATUS_ENQUEUED = "ENQUEUED"
STATUS_RUNNING = "RUNNING"
STATUS_COMPLETED = "COMPLETED"
STATUS_FAILED = "FAILED"
STATUS_CANCELLED = "CANCELLED"
STATUS_BLOCKED = "BLOCKED"
STATUS_PAUSED = "PAUSED"

NON_FINAL_STATUSES = (STATUS_ENQUEUED, STATUS_RUNNING, STATUS_BLOCKED, STATUS_PAUSED)


class NotFoundAgentError(Exception):
    pass


class NeedsApproval(Exception):
    pass


class AgentBudgetExceeded(Exception):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_agent_type(value) -> str:
    at = str(value or "").strip().lower()
    if at not in AGENT_TYPES:
        raise ValueError(f"unsupported agent_type {value!r}; choose from {AGENT_TYPES}")
    return at


def deterministic_plan(agent_type: str, goal: Optional[str], files: Optional[list], name: str) -> dict:
    """Honest plan builder: symbolic, replayable steps derived from inputs.

    Never fabricates outcomes; every step names a real tool the worker
    will actually run during execution.
    """
    steps = [
        {
            "id": "analyze",
            "title": "Analyze repository symbols and reference graph",
            "tool": "code_index",
        },
        {
            "id": "generate",
            "title": f"Produce {agent_type} changes",
            "tool": "patch_engine",
        },
        {
            "id": "verify",
            "title": "Verify changes with real static checks",
            "tool": "review_engine",
        },
    ]
    if agent_type in APPROVAL_AGENT_TYPES:
        steps.append(
            {
                "id": "approve",
                "title": "Require human plan approval before execution",
                "tool": "human_approval",
            }
        )
    rationale = (
        f"Deterministic {agent_type} plan for '{name}': index analysis, change "
        f"generation, verification, and {len(files) if files else 0} target file(s)."
    )
    if goal:
        rationale = f"{rationale} Goal: {goal[:200]}."
    return {"steps": steps, "rationale": rationale}


def requires_approval(agent_type: str) -> bool:
    return agent_type in APPROVAL_AGENT_TYPES


async def _route_model(db: AsyncSession, tenant: str, hint: Optional[str] = None):
    """Best-effort model routing. Returns (model_id, meta) or (None, {})."""
    try:
        from app.aiml.gateway import gateway_service

        result = await gateway_service.route(
            db, tenant, purpose="code-agent", model_hint=hint or "code-agent"
        )
        mid = result.get("model_id") or result.get("model")
        if not mid:
            return None, {}
        return str(mid), result or {}
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("agent model route unavailable: %s", exc)
        return None, {}


async def enqueue_agent(
    db: AsyncSession,
    tenant: str,
    user_id: str,
    *,
    repository_id,
    agent_type: str,
    name: str,
    goal: Optional[str] = None,
    files: Optional[list] = None,
    branch: str = "main",
    commit_sha: Optional[str] = None,
    model: Optional[str] = None,
    throttle: Optional[int] = None,
    budget_tokens: Optional[int] = None,
    checkpoint_limit: int = 10,
    root_run_id: Optional[str] = None,
    metadata_: Optional[dict] = None,
) -> CodeAgentRun:
    at = normalize_agent_type(agent_type)
    repo = await resolve_repository(db, tenant, repository_id)
    run = CodeAgentRun(
        tenant=tenant,
        repository_id=repo.id,
        agent_type=at,
        name=(name or f"{at}-agent")[:128],
        goal=goal,
        status=STATUS_ENQUEUED,
        throttle=int(throttle or DEFAULT_AGENT_THROTTLE),
        budget_tokens=int(budget_tokens or DEFAULT_AGENT_BUDGET_TOKENS),
        checkpoint_limit=int(checkpoint_limit or 10),
        root_run_id=root_run_id,
        model=model,
        metadata_={
            **(metadata_ or {}),
            "created_by": user_id,
            "branch": branch or "main",
            "commit_sha": commit_sha,
            "files": files or [],
        },
    )
    db.add(run)
    await db.flush()
    await emit_event(
        "CodeAgentEnqueued",
        {
            "agent_run_id": str(run.id),
            "repository_id": str(repo.id),
            "agent_type": at,
            "requires_approval": requires_approval(at),
            "created_by": user_id,
        },
        tenant,
    )
    return run


async def get_agent_run(db: AsyncSession, tenant: str, run_id) -> CodeAgentRun:
    run = await db.get(CodeAgentRun, _as_uuid(run_id))
    if run is None or run.tenant != tenant:
        raise NotFoundAgentError("agent run not found")
    return run


async def list_agent_runs(
    db: AsyncSession,
    tenant: str,
    *,
    repository_id=None,
    agent_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> list[CodeAgentRun]:
    stmt = select(CodeAgentRun).where(CodeAgentRun.tenant == tenant)
    if repository_id:
        stmt = stmt.where(CodeAgentRun.repository_id == _as_uuid(repository_id))
    if agent_type:
        stmt = stmt.where(CodeAgentRun.agent_type == agent_type)
    if status:
        stmt = stmt.where(CodeAgentRun.status == status)
    rows = (
        (await db.execute(stmt.order_by(CodeAgentRun.created_at.desc()).limit(limit)))
        .scalars()
        .all()
    )
    return list(rows)


async def cancel_agent(
    db: AsyncSession, tenant: str, user_id: str, run_id, *, reason: Optional[str] = None
) -> CodeAgentRun:
    run = await get_agent_run(db, tenant, run_id)
    if run.status not in NON_FINAL_STATUSES:
        raise ValueError(f"cannot cancel run in status {run.status}")
    run.status = STATUS_CANCELLED
    run.last_error = reason
    await db.flush()
    return run


async def add_plan(
    db: AsyncSession,
    tenant: str,
    run_id,
    *,
    plan_type: str = "PLAN",
    name: str = "Plan",
    steps: Optional[list] = None,
    rationale: Optional[str] = None,
    created_by: Optional[str] = None,
) -> CodeAgentPlan:
    run = await get_agent_run(db, tenant, run_id)
    plan = CodeAgentPlan(
        tenant=tenant,
        agent_run_id=run.id,
        plan_type=str(plan_type or "PLAN")[:30],
        name=(name or "Plan")[:128],
        steps=steps or [],
        rationale=rationale,
    )
    db.add(plan)
    await db.flush()
    if plan_type.upper().startswith("REFACTOR"):
        await emit_event(
            "CodeRefactorPlanned",
            {"agent_run_id": str(run.id), "plan_id": str(plan.id), "created_by": created_by},
            tenant,
        )
    elif plan_type.upper().startswith("MIGRAT"):
        await emit_event(
            "CodeMigrationPlanned",
            {"agent_run_id": str(run.id), "plan_id": str(plan.id), "created_by": created_by},
            tenant,
        )
    return plan


async def list_plans(db: AsyncSession, tenant: str, run_id, *, limit: int = 20) -> list[CodeAgentPlan]:
    run = await get_agent_run(db, tenant, run_id)
    rows = (
        (
            await db.execute(
                select(CodeAgentPlan)
                .where(CodeAgentPlan.agent_run_id == run.id)
                .order_by(CodeAgentPlan.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def approve_plan(
    db: AsyncSession,
    tenant: str,
    run_id,
    plan_id,
    *,
    approved_by: str,
    approved: bool = True,
    reason: Optional[str] = None,
) -> CodeAgentPlan:
    run = await get_agent_run(db, tenant, run_id)
    plan = await db.get(CodeAgentPlan, _as_uuid(plan_id))
    if plan is None or plan.agent_run_id != run.id or plan.tenant != tenant:
        raise NotFoundAgentError("plan not found")
    if approved:
        plan.approved = True
        plan.approved_by = approved_by
        plan.approved_at = _utcnow()
        plan.rejected = False
    else:
        plan.rejected = True
        plan.rejection_reason = reason
    await db.flush()
    return plan


async def next_checkpoint_sequence(db: AsyncSession, run: CodeAgentRun) -> int:
    row = (
        await db.execute(
            select(func.max(CodeAgentCheckpoint.sequence)).where(
                CodeAgentCheckpoint.agent_run_id == run.id
            )
        )
    )
    return int(row.scalar_one() or 0) + 1


async def save_checkpoint(
    db: AsyncSession,
    tenant: str,
    run_id,
    *,
    sequence: Optional[int] = None,
    summary: Optional[str] = None,
    state: Optional[dict] = None,
    is_final: bool = False,
) -> CodeAgentCheckpoint:
    run = await get_agent_run(db, tenant, run_id)
    seq = sequence if sequence is not None else await next_checkpoint_sequence(db, run)
    existing = (
        (
            await db.execute(
                select(CodeAgentCheckpoint).where(
                    CodeAgentCheckpoint.agent_run_id == run.id,
                    CodeAgentCheckpoint.sequence == seq,
                )
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        existing.summary = summary or existing.summary
        existing.state = state if state is not None else existing.state
        existing.is_final = bool(is_final)
        chk = existing
    else:
        if seq > int(run.checkpoint_limit or 10):
            raise ValueError("checkpoint limit reached")
        chk = CodeAgentCheckpoint(
            tenant=tenant,
            agent_run_id=run.id,
            sequence=seq,
            summary=summary,
            state=state,
            is_final=bool(is_final),
        )
        db.add(chk)
    await db.flush()
    await emit_event(
        "CodeAgentCheckpointed",
        {"agent_run_id": str(run.id), "sequence": seq, "is_final": bool(is_final)},
        tenant,
    )
    return chk


async def list_checkpoints(db: AsyncSession, tenant: str, run_id, *, limit: int = 50) -> list[CodeAgentCheckpoint]:
    run = await get_agent_run(db, tenant, run_id)
    rows = (
        (
            await db.execute(
                select(CodeAgentCheckpoint)
                .where(CodeAgentCheckpoint.agent_run_id == run.id)
                .order_by(CodeAgentCheckpoint.sequence)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def add_feedback(
    db: AsyncSession,
    tenant: str,
    run_id,
    *,
    feedback_type: str = "CONTINUE",
    message: Optional[str] = None,
    created_by: Optional[str] = None,
    patch_id=None,
    checkpoint_id=None,
) -> CodeAgentFeedback:
    run = await get_agent_run(db, tenant, run_id)
    feedback = CodeAgentFeedback(
        tenant=tenant,
        agent_run_id=run.id,
        feedback_type=str(feedback_type or "CONTINUE")[:20].upper(),
        message=message,
        created_by=created_by,
        patch_id=_as_uuid(patch_id) if patch_id else None,
        checkpoint_id=_as_uuid(checkpoint_id) if checkpoint_id else None,
    )
    db.add(feedback)
    await db.flush()
    await emit_event(
        "CodeAgentFeedbackRecorded",
        {
            "agent_run_id": str(run.id),
            "feedback_type": feedback.feedback_type,
            "created_by": created_by,
        },
        tenant,
    )
    return feedback


async def list_feedback(db: AsyncSession, tenant: str, run_id, *, limit: int = 50) -> list[CodeAgentFeedback]:
    run = await get_agent_run(db, tenant, run_id)
    rows = (
        (
            await db.execute(
                select(CodeAgentFeedback)
                .where(CodeAgentFeedback.agent_run_id == run.id)
                .order_by(CodeAgentFeedback.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


def needs_approval(run: CodeAgentRun, plans: list[CodeAgentPlan]) -> bool:
    if not requires_approval(run.agent_type):
        return False
    for p in plans:
        if p.agent_run_id == run.id:
            return not p.approved
    return True