"""Volume 61 Commit 1 — PerformanceBudgetService (DB-backed, tenant-isolated).

Reuses analytics/budget_service threshold semantics but for latency/throughput/
error budgets. Supports P50/P95/P99 thresholds via ``target`` — callers create
separate budgets for p50_latency, p95_latency, etc. rather than averaging.

Tenant isolation enforced on every query. Real AsyncSession, no in-memory
placeholders.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.performance.models import PerformanceBudget, PerformanceServiceMetric


# Thresholds mirroring analytics BudgetService but collapsed to ok/warning/hard
# required by the spec for check_budget.
_OK_THRESHOLD = 0.80   # <80% consumed -> ok
_HARD_THRESHOLD = 1.0  # >=100% -> hard / breached


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _status_for_ratio(ratio: float) -> tuple[str, bool]:
    """Map consumed ratio to (status, breached)."""
    if ratio >= _HARD_THRESHOLD:
        return "hard", True
    if ratio >= _OK_THRESHOLD:
        return "warning", False
    return "ok", False


def _validate_budget_inputs(
    *,
    tenant: str,
    service: str,
    metric_type: str,
    metric_name: str,
    target: float,
    window: str,
) -> None:
    if not tenant or not str(tenant).strip():
        raise ValueError("tenant is required")
    if not service or not str(service).strip():
        raise ValueError("service is required")
    if not metric_type or not str(metric_type).strip():
        raise ValueError("metric_type is required")
    if not metric_name or not str(metric_name).strip():
        raise ValueError("metric_name is required")
    if not isinstance(target, (int, float)) or isinstance(target, bool):
        raise ValueError("target must be a number")
    if float(target) <= 0:
        raise ValueError("target must be > 0")
    if not window or not str(window).strip():
        raise ValueError("window is required")


class PerformanceBudgetService:
    """DB-backed performance budget registry."""

    # ------------------------------------------------------------------ create

    async def create_budget(
        self,
        db: AsyncSession,
        tenant: str,
        service: str,
        metric_type: str,
        metric_name: str,
        target: float,
        window: str = "1h",
        owner: str | None = None,
    ) -> PerformanceBudget:
        _validate_budget_inputs(
            tenant=tenant,
            service=service,
            metric_type=metric_type,
            metric_name=metric_name,
            target=float(target),
            window=window,
        )
        # Normalize P50/P95 support: metric_name may be e.g. "p95_latency_ms"
        # or dimensions-based. We store target as-is; check_budget compares
        # observed p50/p95 directly against its target, not an averaged value.
        budget = PerformanceBudget(
            tenant=str(tenant).strip(),
            service=str(service).strip(),
            metric_type=str(metric_type).strip().lower(),
            metric_name=str(metric_name).strip(),
            target=float(target),
            window=str(window).strip(),
            owner=str(owner).strip() if owner else None,
            status="ok",
        )
        db.add(budget)
        await db.flush()
        await db.refresh(budget)
        return budget

    # ------------------------------------------------------------------ read

    async def get_budget(
        self,
        db: AsyncSession,
        tenant: str,
        budget_id: str | uuid.UUID,
    ) -> PerformanceBudget | None:
        if not tenant:
            raise ValueError("tenant is required")
        try:
            bid = uuid.UUID(str(budget_id)) if not isinstance(budget_id, uuid.UUID) else budget_id
        except ValueError:
            return None
        result = await db.execute(
            select(PerformanceBudget).where(
                PerformanceBudget.id == bid,
                PerformanceBudget.tenant == str(tenant).strip(),
            )
        )
        return result.scalars().first()

    async def list_budgets(
        self,
        db: AsyncSession,
        tenant: str,
        service: str | None = None,
        metric_type: str | None = None,
    ) -> list[PerformanceBudget]:
        if not tenant:
            raise ValueError("tenant is required")
        stmt = select(PerformanceBudget).where(PerformanceBudget.tenant == str(tenant).strip())
        if service:
            stmt = stmt.where(PerformanceBudget.service == str(service).strip())
        if metric_type:
            stmt = stmt.where(PerformanceBudget.metric_type == str(metric_type).strip().lower())
        stmt = stmt.order_by(PerformanceBudget.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    # ---------------------------------------------------------------- check

    async def check_budget(
        self,
        db: AsyncSession,
        tenant: str,
        budget_id: str | uuid.UUID,
        observed: float,
    ) -> dict[str, Any]:
        """Evaluate observed value against budget target.

        Returns dict with ``budget_id, target, observed, remaining,
        consumed_percent, status (ok/warning/hard), breached bool``.
        """
        if not tenant:
            raise ValueError("tenant is required")
        if not isinstance(observed, (int, float)) or isinstance(observed, bool):
            raise ValueError("observed must be a number")
        if float(observed) < 0:
            raise ValueError("observed must be >= 0")

        budget = await self.get_budget(db, tenant, budget_id)
        if budget is None:
            raise KeyError(f"budget not found: {budget_id} for tenant {tenant}")

        target = float(budget.target)
        obs = float(observed)
        remaining = target - obs
        consumed_percent = (obs / target * 100.0) if target > 0 else 0.0
        ratio = obs / target if target > 0 else 0.0
        status, breached = _status_for_ratio(ratio)

        # Persist status for observability; do not overwrite target/window.
        budget.status = status
        await db.flush()

        # Optionally emit observability hook via performance metrics (best-effort)
        try:
            from app.observability.service import svc as _obs_svc  # noqa: WPS433
            # Record budget check as metric for dashboards (fire-and-forget)
            # We reuse the metric engine directly if available.
            if hasattr(_obs_svc, "metrics"):
                _obs_svc.metrics.ingest(
                    f"perf.budget.{budget.metric_name}", obs, {"tenant": str(tenant), "budget_id": str(budget.id)}
                )
        except Exception:
            pass

        return {
            "budget_id": str(budget.id),
            "tenant": str(tenant),
            "service": budget.service,
            "metric_type": budget.metric_type,
            "metric_name": budget.metric_name,
            "target": round(target, 6),
            "observed": round(obs, 6),
            "remaining": round(remaining, 6),
            "consumed_percent": round(consumed_percent, 2),
            "status": status,
            "breached": breached,
            "window": budget.window,
            "owner": budget.owner,
            "checked_at": _utcnow().isoformat(),
        }

    async def evaluate_all(
        self,
        db: AsyncSession,
        tenant: str,
        observations: dict[str, float] | None = None,
    ) -> list[dict[str, Any]]:
        """Evaluate every budget for *tenant*.

        ``observations`` may map ``budget_id`` (str) or ``metric_name``
        to an observed value. This allows callers to supply P50/P95 values
        explicitly. When a budget has no entry in ``observations``, we
        attempt to fetch the latest ``PerformanceServiceMetric`` value for
        that service/metric_name; if none exists we report 0 observed.
        """
        budgets = await self.list_budgets(db, tenant)
        results: list[dict[str, Any]] = []
        obs_map = observations or {}

        for budget in budgets:
            # Resolve observed value: priority budget_id -> metric_name -> DB lookup
            observed: float | None = None
            bid_str = str(budget.id)
            if bid_str in obs_map:
                observed = float(obs_map[bid_str])
            elif budget.metric_name in obs_map:
                observed = float(obs_map[budget.metric_name])
            else:
                # Try to find latest metric for this service/metric_name
                try:
                    stmt = (
                        select(PerformanceServiceMetric)
                        .where(
                            PerformanceServiceMetric.tenant == str(tenant).strip(),
                            PerformanceServiceMetric.service == budget.service,
                            PerformanceServiceMetric.metric_name == budget.metric_name,
                        )
                        .order_by(PerformanceServiceMetric.period_start.desc())
                        .limit(1)
                    )
                    res = await db.execute(stmt)
                    latest = res.scalars().first()
                    if latest is not None:
                        # Use p95/p50 if metric is percentile-based and stored
                        # For p95 budgets, prefer latest.p95 if present
                        mname_lower = budget.metric_name.lower()
                        if "p95" in mname_lower and latest.p95 is not None:
                            observed = float(latest.p95)
                        elif "p50" in mname_lower and latest.p50 is not None:
                            observed = float(latest.p50)
                        elif "p99" in mname_lower and latest.p99 is not None:
                            observed = float(latest.p99)
                        else:
                            observed = float(latest.value)
                    else:
                        observed = 0.0
                except Exception:
                    observed = 0.0

            if observed is None:
                observed = 0.0
            evaluation = await self.check_budget(db, tenant, budget.id, observed)
            results.append(evaluation)

        # Sort breached first, then by consumed_percent desc
        results.sort(key=lambda r: (not r["breached"], -r["consumed_percent"]))
        return results


performance_budget_service = PerformanceBudgetService()
