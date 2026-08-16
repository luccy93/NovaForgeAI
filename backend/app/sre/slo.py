"""SLI recording, SLO computation, error budgets and burn-rate monitoring (Volume 35).

Every SLO has an SLI. SLIs are recorded as time-bucketed measurements
(see SRESLIMeasurement) and rolled up over the SLO window into error
budget snapshots (SREErrorBudget) with burn-rate classification.

Burn rate definition (industry standard):
    burn_rate = (budget consumed fraction) / (window elapsed fraction)

Multi-window burn-rate tiers (fast / medium / slow) use configurable
windows from sre.constants.BURN_RATE_CONFIG and drive alerts instead of
static threshold alerting.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sre.constants import (
    BUDGET_AT_RISK,
    BUDGET_EXHAUSTED,
    BUDGET_HEALTHY,
    BURN_FAST,
    BURN_MEDIUM,
    BURN_RATE_CONFIG,
    BURN_SLOW,
    WINDOW_SECONDS,
)
from app.sre.models import SREErrorBudget, SRESLO, SRESLIMeasurement
from app.sre.store import new_key

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SLI recording
# ---------------------------------------------------------------------------

async def record_sli(
    db: AsyncSession,
    *,
    slo: Optional[SRESLO] = None,
    slo_id: Optional[str] = None,
    service_id: Optional[str] = None,
    sli_type: Optional[str] = None,
    good: float = 1.0,
    total: float = 1.0,
    value: Optional[float] = None,
    region: str = "",
    bucket_seconds: int = 60,
) -> SRESLIMeasurement:
    """Record one SLI event. `good`/`total` are counts; `value` is the
    measured value for value-based SLIs (latency percentiles etc.)."""
    if slo is not None:
        slo_id = slo.slo_id
        service_id = slo.service_id
        sli_type = slo.sli_type
    now = datetime.now(timezone.utc)
    bucket_start = now - timedelta(seconds=now.second, microseconds=now.microsecond) % timedelta(seconds=bucket_seconds)
    measurement = SRESLIMeasurement(
        slo_id=slo_id or "",
        service_id=service_id or "",
        sli_type=sli_type or "availability",
        bucket_start=bucket_start,
        bucket_seconds=bucket_seconds,
        good=good,
        total=total,
        value=value if value is not None else 0.0,
        region=region,
    )
    db.add(measurement)
    await db.flush()
    return measurement


async def aggregate_window(
    db: AsyncSession,
    slo: SRESLO,
    *,
    since: Optional[datetime] = None,
    region: str = "",
) -> dict:
    """Aggregate good/total for an SLO over its configured window."""
    if since is None:
        window_seconds = WINDOW_SECONDS.get(slo.window, WINDOW_SECONDS["monthly"])
        since = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
    stmt = select(
        func.coalesce(func.sum(SRESLIMeasurement.good), 0.0),
        func.coalesce(func.sum(SRESLIMeasurement.total), 0.0),
        func.count(),
    ).where(
        SRESLIMeasurement.slo_id == slo.slo_id,
        SRESLIMeasurement.bucket_start >= since,
    )
    if region:
        stmt = stmt.where(SRESLIMeasurement.region == region)
    good, total, buckets = (await db.execute(stmt)).one()
    good = float(good or 0.0)
    total = float(total or 0.0)
    return {
        "good": good,
        "total": total,
        "buckets": int(buckets or 0),
        "value": (good / total) if total > 0 else None,
        "since": since,
    }


# ---------------------------------------------------------------------------
# Error budget
# ---------------------------------------------------------------------------

def _budget_status(allowed: float, actual: float) -> tuple[str, float]:
    """Return (status, consumed_percent)."""
    if allowed <= 0:
        return BUDGET_EXHAUSTED, 100.0
    consumed_percent = min(100.0, max(0.0, (actual / allowed) * 100.0))
    if actual >= allowed:
        return BUDGET_EXHAUSTED, 100.0
    if consumed_percent >= 80.0:
        return BUDGET_AT_RISK, consumed_percent
    return BUDGET_HEALTHY, consumed_percent


def compute_budget_values(target: float, good: float, total: float) -> dict:
    """Pure computation of error-budget values from an SLO target and SLI totals."""
    allowed_failure = max(0.0, 1.0 - target)
    total = float(total or 0.0)
    actual_failure = (1.0 - good / total) if total > 0 else 0.0
    remaining_budget = max(0.0, allowed_failure - actual_failure)
    status, consumed_percent = _budget_status(allowed_failure, actual_failure)
    return {
        "allowed_failure": allowed_failure,
        "actual_failure": actual_failure,
        "remaining_budget": remaining_budget,
        "consumed_percent": consumed_percent,
        "status": status,
        "total_events": total,
    }


def compute_burn_rate(target: float, good: float, total: float, *, measurement_seconds: float, window_seconds: float) -> float:
    """Burn rate over a measurement period relative to the SLO window."""
    if window_seconds <= 0 or measurement_seconds <= 0:
        return 0.0
    allowed_failure = max(0.0, 1.0 - target)
    if allowed_failure <= 0:
        return float("inf") if total > good else 0.0
    actual_failure = (1.0 - good / total) if total > 0 else 0.0
    budget_consumed = actual_failure / allowed_failure
    elapsed_fraction = min(1.0, measurement_seconds / window_seconds)
    return budget_consumed / elapsed_fraction if elapsed_fraction > 0 else 0.0


def classify_burn_rate(burn_rate: float) -> Optional[str]:
    """Classify a burn rate into fast/medium/slow tiers (or None when healthy)."""
    if burn_rate >= BURN_RATE_CONFIG[BURN_FAST]["threshold"]:
        return BURN_FAST
    if burn_rate >= BURN_RATE_CONFIG[BURN_MEDIUM]["threshold"]:
        return BURN_MEDIUM
    if burn_rate >= BURN_RATE_CONFIG[BURN_SLOW]["threshold"]:
        return BURN_SLOW
    return None


async def compute_error_budget(db: AsyncSession, slo: SRESLO, *, persist: bool = True) -> dict:
    """Compute (and optionally persist) the error budget snapshot for an SLO."""
    window_seconds = WINDOW_SECONDS.get(slo.window, WINDOW_SECONDS["monthly"])
    agg = await aggregate_window(db, slo)
    good = agg["good"]
    total = agg["total"]
    budget = compute_budget_values(slo.target, good, total)
    burn_rate = compute_burn_rate(slo.target, good, total, measurement_seconds=window_seconds, window_seconds=window_seconds)
    budget["burn_rate"] = round(burn_rate, 4)
    budget["slo_id"] = slo.slo_id
    budget["service_id"] = slo.service_id
    budget["window"] = slo.window
    budget["target"] = slo.target
    budget["buckets"] = agg["buckets"]
    if persist:
        snapshot = SREErrorBudget(
            slo_id=slo.slo_id,
            service_id=slo.service_id,
            window=slo.window,
            allowed_failure=budget["allowed_failure"],
            actual_failure=budget["actual_failure"],
            remaining_budget=budget["remaining_budget"],
            consumed_percent=budget["consumed_percent"],
            burn_rate=budget["burn_rate"],
            status=budget["status"],
        )
        db.add(snapshot)
        await db.flush()
    return budget


async def compute_burn_rate_for_window(db: AsyncSession, slo: SRESLO, window_minutes: int) -> float:
    """Burn rate over a short trailing window (for multi-window alerting)."""
    window_seconds = WINDOW_SECONDS.get(slo.window, WINDOW_SECONDS["monthly"])
    since = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    stmt = select(
        func.coalesce(func.sum(SRESLIMeasurement.good), 0.0),
        func.coalesce(func.sum(SRESLIMeasurement.total), 0.0),
    ).where(SRESLIMeasurement.slo_id == slo.slo_id, SRESLIMeasurement.bucket_start >= since)
    good, total = (await db.execute(stmt)).one()
    return compute_burn_rate(
        slo.target,
        float(good or 0.0),
        float(total or 0.0),
        measurement_seconds=window_minutes * 60,
        window_seconds=window_seconds,
    )


async def burn_rate_status(db: AsyncSession, slo: SRESLO) -> dict:
    """Evaluate multi-window burn-rate status for an SLO."""
    tiers: dict[str, float] = {}
    burning = False
    for tier, config in BURN_RATE_CONFIG.items():
        rate = await compute_burn_rate_for_window(db, slo, config["window_minutes"])
        tiers[tier] = round(rate, 4)
        if rate >= config["threshold"]:
            burning = True
    return {
        "slo_id": slo.slo_id,
        "service_id": slo.service_id,
        "burning": burning,
        "tiers": tiers,
        "thresholds": {tier: config["threshold"] for tier, config in BURN_RATE_CONFIG.items()},
        "windows_minutes": {tier: config["window_minutes"] for tier, config in BURN_RATE_CONFIG.items()},
    }


async def compute_all_budgets(db: AsyncSession, *, persist: bool = True) -> list[dict]:
    """Compute error budgets for every active SLO."""
    result = await db.execute(select(SRESLO).where(SRESLO.status == "active"))
    slos = list(result.scalars().all())
    budgets = []
    for slo in slos:
        try:
            budgets.append(await compute_error_budget(db, slo, persist=persist))
        except Exception as exc:  # one bad SLO must not break the batch
            logger.warning("budget computation failed for SLO %s: %s", slo.slo_id, exc)
    return budgets


async def get_latest_budget(db: AsyncSession, slo_id: str) -> Optional[dict]:
    result = await db.execute(
        select(SREErrorBudget)
        .where(SREErrorBudget.slo_id == slo_id)
        .order_by(SREErrorBudget.computed_at.desc())
        .limit(1)
    )
    snapshot = result.scalar_one_or_none()
    if snapshot is None:
        return None
    return {
        "id": snapshot.id,
        "slo_id": snapshot.slo_id,
        "service_id": snapshot.service_id,
        "window": snapshot.window,
        "allowed_failure": snapshot.allowed_failure,
        "actual_failure": snapshot.actual_failure,
        "remaining_budget": snapshot.remaining_budget,
        "consumed_percent": snapshot.consumed_percent,
        "burn_rate": snapshot.burn_rate,
        "status": snapshot.status,
        "computed_at": snapshot.computed_at.isoformat(),
    }


def slo_compliance(budget: dict) -> dict:
    """Explainable SLO compliance from a budget snapshot."""
    if budget is None:
        return {"compliant": None, "reason": "no budget data"}
    compliant = budget["status"] != BUDGET_EXHAUSTED
    reason = (
        f"consumed {budget['consumed_percent']:.1f}% of {budget.get('window', 'slo')} error budget "
        f"(allowed {budget['allowed_failure']:.5f}, actual {budget['actual_failure']:.5f})"
    )
    return {"compliant": compliant, "reason": reason}
