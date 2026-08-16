"""Cost reliability (Volume 35).

Budget / quota guardrails with soft and hard limits. Integration points
for the existing FinOps analytics (backend/app/finops) - this module
provides the SRE-side guardrail evaluation and alerting surface without
duplicating cost accounting.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sre.models import SREAlert
from app.sre.alerts import create_alert, resolve_by_rule
from app.sre.store import new_id

logger = logging.getLogger(__name__)

COST_GUARDRAIL_BUDGET = "budget"
COST_GUARDRAIL_QUOTA = "quota"
COST_GUARDRAIL_SOFT_LIMIT = "soft_limit"
COST_GUARDRAIL_HARD_LIMIT = "hard_limit"


async def evaluate_cost_guardrail(
    db: AsyncSession,
    *,
    scope: str,  # organization | workspace | service
    scope_id: str,
    kind: str,  # ai_cost | storage | compute | network
    current: float,
    limit: float,
    hard_limit: Optional[float] = None,
    unit: str = "usd",
) -> dict:
    """Evaluate a cost guardrail against current spend.

    0-79%  -> within budget
    80-99% -> soft limit alert (SEV3)
    >=100% -> hard limit alert (SEV2) + suggested degradation
    """
    if limit <= 0:
        return {"scope": scope_id, "kind": kind, "status": "disabled", "current": current, "limit": limit}
    utilization = current / limit * 100.0
    alert_name = f"cost.{kind}.{scope}"
    if utilization >= 100.0 or (hard_limit and current >= hard_limit):
        await create_alert(
            db,
            rule_name=f"cost.guardrail.{kind}",
            severity="SEV2",
            message=f"{scope} {kind} cost {current:.2f}{unit} exceeded limit {limit:.2f}{unit} ({utilization:.1f}%)",
            service_id=scope,
            region="",
            metadata_json={"scope": scope, "scope_id": scope_id, "kind": kind, "current": current, "limit": limit, "utilization": round(utilization, 2)},
        )
        status = "hard_limit"
        degradation = "reduce AI model tier, pause non-critical jobs, require approval for further spend"
    elif utilization >= 80.0:
        await create_alert(
            db,
            rule_name=f"cost.guardrail.{kind}",
            severity="SEV3",
            message=f"{scope} {kind} cost at {utilization:.1f}% of limit",
            service_id=scope,
            region="",
            metadata_json={"scope": scope, "scope_id": scope_id, "kind": kind, "current": current, "limit": limit, "utilization": round(utilization, 2)},
        )
        status = "soft_limit"
        degradation = "review spend; hold non-essential runs"
    else:
        await resolve_by_rule(db, f"cost.guardrail.{kind}", service_id=scope)
        status = "within_budget"
        degradation = ""
    return {
        "scope": scope,
        "scope_id": scope_id,
        "kind": kind,
        "current": round(current, 2),
        "limit": round(limit, 2),
        "utilization_percent": round(utilization, 2),
        "status": status,
        "suggested_degradation": degradation,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


async def ai_cost_anomaly(
    db: AsyncSession,
    *,
    provider: str,
    expected_daily: float,
    actual_daily: float,
    threshold_multiplier: float = 1.5,
) -> dict:
    """Detect unexpected AI cost: actual > expected * multiplier."""
    ratio = actual_daily / expected_daily if expected_daily > 0 else 0.0
    if ratio >= threshold_multiplier:
        await create_alert(
            db,
            rule_name="cost.ai.anomaly",
            severity="SEV3",
            message=f"AI cost anomaly for {provider}: {actual_daily:.2f} vs expected {expected_daily:.2f} ({ratio:.1f}x)",
            service_id="model-gateway",
            metadata_json={"provider": provider, "expected_daily": expected_daily, "actual_daily": actual_daily, "ratio": round(ratio, 2)},
        )
        return {"provider": provider, "anomaly": True, "ratio": round(ratio, 2), "action": "review provider weightings and runaway workflows"}
    await resolve_by_rule(db, "cost.ai.anomaly")
    return {"provider": provider, "anomaly": False, "ratio": round(ratio, 2)}