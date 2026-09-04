"""Integration health monitoring summaries — Volume 70 Commit 2.

Aggregates health-check rows and execution outcomes into availability,
latency, error-rate, authentication-failure and rate-limit signals.
Read-only over governed tables; checks themselves run in workers.py.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Optional

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.common import (
    NotFoundError,
    ValidationError,
    _as_uuid,
    _utcnow,
)
from app.integrations.governed_models import (
    Integration,
    IntegrationExecution,
    IntegrationHealthCheck,
)


async def health_summary(db: AsyncSession, tenant: str, integration_id, *, days: int = 7) -> dict:
    if not tenant:
        raise ValidationError("tenant required")
    stmt = select(Integration).where(Integration.id == _as_uuid(integration_id),
                                    Integration.tenant == tenant)
    integration = (await db.execute(stmt)).scalar_one_or_none()
    if integration is None:
        raise NotFoundError("integration not found")
    cutoff = _utcnow() - timedelta(days=min(max(int(days or 7), 1), 90))

    checks = (await db.execute(select(IntegrationHealthCheck).where(
        IntegrationHealthCheck.tenant == tenant,
        IntegrationHealthCheck.integration_id == integration.id,
        IntegrationHealthCheck.checked_at >= cutoff,
    ).order_by(desc(IntegrationHealthCheck.checked_at)).limit(200))).scalars().all()

    execs = (await db.execute(select(IntegrationExecution).where(
        IntegrationExecution.tenant == tenant,
        IntegrationExecution.created_at >= cutoff,
    ).limit(2000))).scalars().all()

    latencies = [c.latency_ms or 0 for c in checks]
    failures = sum(1 for e in execs if e.status != "SUCCESS")
    auth_failures = sum(1 for e in execs if "401" in (e.error or "") or "403" in (e.error or ""))
    rate_limited = sum(1 for e in execs if "429" in (e.error or "") or "rate limit" in (e.error or "").lower())
    total = len(execs)
    return {
        "integration_id": str(integration.id),
        "tenant": tenant,
        "current_health": integration.health,
        "current_status": integration.status,
        "window_days": min(max(int(days or 7), 1), 90),
        "checks": len(checks),
        "last_check": checks[0].checked_at.isoformat() if checks and checks[0].checked_at else None,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
        "executions": total,
        "error_rate": round(failures / total, 4) if total else 0.0,
        "authentication_failures": auth_failures,
        "rate_limit_hits": rate_limited,
    }
