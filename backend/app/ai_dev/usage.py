"""AI usage metering and rate limiting — Volume 67 Commit 1."""

from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_dev.common import _as_uuid, record_usage_best_effort, ingest_metric_best_effort
from app.ai_dev.models import CodeAIUsage


def check_rate_limit(tenant: str, endpoint: str, limit: int = 60) -> bool:
    try:
        from app.iam.rate_limiter import check_tenant

        return bool(check_tenant(tenant, endpoint, limit=limit))
    except Exception:
        return True


async def record_usage(
    db: AsyncSession,
    tenant: str,
    user_id: Optional[str],
    *,
    action: str,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    cost_cents: float = 0.0,
    latency_ms: Optional[int] = None,
    repository_id=None,
    patch_size: int = 0,
    test_cycles: int = 0,
    request_id: Optional[str] = None,
) -> CodeAIUsage:
    usage = CodeAIUsage(
        tenant=tenant,
        user_id=user_id,
        request_id=request_id,
        action=action,
        model=model,
        model_provider=provider,
        prompt_tokens=prompt_tokens or 0,
        completion_tokens=completion_tokens or 0,
        total_tokens=total_tokens or 0,
        cost_cents=cost_cents or 0.0,
        latency_ms=latency_ms,
        repository_id=_as_uuid(repository_id) if repository_id else None,
        patch_size=patch_size,
        test_cycles=test_cycles,
    )
    db.add(usage)
    await db.flush()
    record_usage_best_effort(
        tenant, action, quantity=max(1, total_tokens or 1)
    )
    ingest_metric_best_effort(
        "ai_dev_usage",
        1.0,
        tags={"tenant": tenant, "action": action, "model": model or "unknown"},
    )
    return usage


async def list_usage(
    db: AsyncSession, tenant: str, *, limit: int = 50, offset: int = 0, action: Optional[str] = None
) -> list[CodeAIUsage]:
    stmt = select(CodeAIUsage).where(CodeAIUsage.tenant == tenant)
    if action:
        stmt = stmt.where(CodeAIUsage.action == action)
    rows = (
        (
            await db.execute(
                stmt.order_by(desc(CodeAIUsage.created_at)).limit(limit).offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def usage_totals(db: AsyncSession, tenant: str) -> dict:
    rows = await list_usage(db, tenant, limit=1000)
    totals = {"requests": len(rows), "total_tokens": 0, "cost_cents": 0.0}
    for row in rows:
        totals["total_tokens"] += row.total_tokens or 0
        totals["cost_cents"] += row.cost_cents or 0.0
    return totals