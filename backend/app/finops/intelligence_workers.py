"""FinOps intelligence workers — Volume 69 Commit 2.

Lease-guarded, idempotent jobs for forecast generation, anomaly
detection, recommendation generation and budget evaluation. All
underlying writes are idempotent, so retries are safe.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.finops.governed_workers import (
    _worker_id,
    acquire_aggregation_lease,
    release_aggregation_lease,
)

logger = logging.getLogger(__name__)


async def run_forecast_job(db: AsyncSession, tenant: str, *, horizon_days: int = 30,
                           dimensions: Optional[dict] = None, worker_id: Optional[str] = None,
                           actor: str = "") -> dict:
    from app.finops.governed_forecasting import generate_forecast

    worker_id = worker_id or _worker_id()
    job_key = f"forecast:{horizon_days}"
    if not await acquire_aggregation_lease(tenant, job_key, worker_id):
        return {"status": "skipped", "reason": "lease held by another worker"}
    try:
        result = await generate_forecast(db, tenant, horizon_days=horizon_days,
                                         dimensions=dimensions, actor=actor)
        return {"status": "completed", "forecast": result}
    except Exception as exc:
        logger.warning("forecast job failed: %s", exc)
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
    finally:
        await release_aggregation_lease(tenant, job_key, worker_id)


async def run_anomaly_job(db: AsyncSession, tenant: str, *, lookback_days: int = 14,
                          worker_id: Optional[str] = None, actor: str = "") -> dict:
    from app.finops.anomalies import detect_anomalies

    worker_id = worker_id or _worker_id()
    job_key = f"anomaly:{lookback_days}"
    if not await acquire_aggregation_lease(tenant, job_key, worker_id):
        return {"status": "skipped", "reason": "lease held by another worker"}
    try:
        result = await detect_anomalies(db, tenant, lookback_days=lookback_days, actor=actor)
        return {"status": "completed", "detection": result}
    except Exception as exc:
        logger.warning("anomaly job failed: %s", exc)
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
    finally:
        await release_aggregation_lease(tenant, job_key, worker_id)


async def run_recommendation_job(db: AsyncSession, tenant: str, *, worker_id: Optional[str] = None,
                                 actor: str = "") -> dict:
    from app.finops.recommendations import generate_recommendations

    worker_id = worker_id or _worker_id()
    job_key = "recommendations"
    if not await acquire_aggregation_lease(tenant, job_key, worker_id):
        return {"status": "skipped", "reason": "lease held by another worker"}
    try:
        result = await generate_recommendations(db, tenant, actor=actor)
        return {"status": "completed", "recommendations": result}
    except Exception as exc:
        logger.warning("recommendation job failed: %s", exc)
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
    finally:
        await release_aggregation_lease(tenant, job_key, worker_id)


async def run_budget_evaluation_job(db: AsyncSession, tenant: str, *, worker_id: Optional[str] = None,
                                    actor: str = "") -> dict:
    from app.finops.budgets import evaluate_budget
    from app.finops.governed_models import FinOpsBudget

    worker_id = worker_id or _worker_id()
    job_key = "budget-evaluation"
    if not await acquire_aggregation_lease(tenant, job_key, worker_id):
        return {"status": "skipped", "reason": "lease held by another worker"}
    try:
        rows = (await db.execute(select(FinOpsBudget).where(
            FinOpsBudget.tenant == tenant, FinOpsBudget.enabled == True,  # noqa: E712
            FinOpsBudget.status.notin_(["SUSPENDED", "CLOSED"]),
        ))).scalars().all()
        evaluated = []
        for budget in rows:
            try:
                evaluated.append(await evaluate_budget(db, tenant, budget.id, actor=actor))
            except Exception as exc:
                logger.warning("budget %s evaluation failed: %s", budget.id, exc)
        return {"status": "completed", "evaluated": len(evaluated), "budgets": evaluated}
    except Exception as exc:
        logger.warning("budget evaluation job failed: %s", exc)
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
    finally:
        await release_aggregation_lease(tenant, job_key, worker_id)
