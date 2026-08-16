"""Deployment reliability, canary analysis and rollback policy (Volume 35).

Records deployments, runs canary analysis comparing canary metrics
against baselines, and decides rollback only when thresholds are
violated AND rollback is safe (previous version known good). Rollback
is never blind.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sre.models import SRECanaryRun, SREDeployment
from app.sre.store import new_key

logger = logging.getLogger(__name__)

CANARY_STATUS_IN_PROGRESS = "in_progress"
CANARY_STATUS_PASSED = "passed"
CANARY_STATUS_ABORTED = "aborted"


async def record_deployment(
    db: AsyncSession,
    *,
    service_id: str,
    version: str = "",
    strategy: str = "rolling",
    region: str = "",
    commit: str = "",
    environment: str = "production",
) -> SREDeployment:
    deployment = SREDeployment(
        deployment_id=new_key("deploy"),
        service_id=service_id,
        version=version,
        strategy=strategy,
        status="in_progress",
        region=region,
        commit=commit,
        environment=environment,
    )
    db.add(deployment)
    await db.flush()
    return deployment


async def complete_deployment(
    db: AsyncSession,
    deployment: SREDeployment,
    *,
    status: str = "success",
    duration_seconds: int = 0,
    error_rate_after: float = 0.0,
    latency_after_ms: float = 0.0,
) -> SREDeployment:
    deployment.status = status
    deployment.duration_seconds = duration_seconds
    deployment.error_rate_after = error_rate_after
    deployment.latency_after_ms = latency_after_ms
    deployment.completed_at = datetime.now(timezone.utc)
    await db.flush()
    return deployment


def canary_decision(
    *,
    baseline_error_rate: float,
    canary_error_rate: float,
    baseline_latency_ms: float,
    canary_latency_ms: float,
    error_rate_threshold: float = 0.5,
    latency_threshold_multiplier: float = 1.5,
) -> dict:
    """Pure canary analysis: abort when error rate delta or latency ratio
    exceeds configured thresholds."""
    error_delta = canary_error_rate - baseline_error_rate
    latency_ratio = (canary_latency_ms / baseline_latency_ms) if baseline_latency_ms > 0 else 1.0
    violations = []
    if error_delta > error_rate_threshold:
        violations.append(f"error rate +{error_delta * 100:.2f}pp exceeds threshold {error_rate_threshold * 100:.2f}pp")
    if latency_ratio > latency_threshold_multiplier:
        violations.append(f"latency ratio {latency_ratio:.2f}x exceeds threshold {latency_threshold_multiplier:.2f}x")
    return {
        "abort": bool(violations),
        "violations": violations,
        "error_delta_pp": round(error_delta * 100, 3),
        "latency_ratio": round(latency_ratio, 3),
        "thresholds": {"error_rate_pp": error_rate_threshold * 100, "latency_multiplier": latency_threshold_multiplier},
    }


async def start_canary(
    db: AsyncSession,
    *,
    deployment_id: str,
    service_id: str,
    baseline_error_rate: float = 0.0,
    baseline_latency_ms: float = 0.0,
    error_rate_threshold: float = 0.5,
    latency_threshold_multiplier: float = 1.5,
) -> SRECanaryRun:
    canary = SRECanaryRun(
        canary_id=new_key("canary"),
        deployment_id=deployment_id,
        service_id=service_id,
        status=CANARY_STATUS_IN_PROGRESS,
        baseline_error_rate=baseline_error_rate,
        baseline_latency_ms=baseline_latency_ms,
        error_rate_threshold=error_rate_threshold,
        latency_threshold_multiplier=latency_threshold_multiplier,
    )
    db.add(canary)
    await db.flush()
    return canary


async def evaluate_canary(
    db: AsyncSession,
    canary: SRECanaryRun,
    *,
    canary_error_rate: float,
    canary_latency_ms: float,
) -> dict:
    """Evaluate a canary against its baseline; mark the run and return
    the decision. When aborted, the matching deployment is flagged for
    rollback by the operator or policy-approved automation."""
    decision = canary_decision(
        baseline_error_rate=canary.baseline_error_rate,
        canary_error_rate=canary_error_rate,
        baseline_latency_ms=canary.baseline_latency_ms,
        canary_latency_ms=canary_latency_ms,
        error_rate_threshold=canary.error_rate_threshold,
        latency_threshold_multiplier=canary.latency_threshold_multiplier,
    )
    canary.canary_error_rate = canary_error_rate
    canary.canary_latency_ms = canary_latency_ms
    canary.status = CANARY_STATUS_ABORTED if decision["abort"] else CANARY_STATUS_PASSED
    canary.aborted = decision["abort"]
    canary.reason = "; ".join(decision["violations"])
    canary.completed_at = datetime.now(timezone.utc)
    await db.flush()
    if canary.deployment_id:
        deployment = (
            (await db.execute(select(SREDeployment).where(SREDeployment.deployment_id == canary.deployment_id))).scalar_one_or_none()
        )
        if deployment is not None and deployment.status == "in_progress":
            deployment.status = "rolled_back" if decision["abort"] else "success"
            deployment.rolled_back_at = datetime.now(timezone.utc) if decision["abort"] else deployment.rolled_back_at
            deployment.completed_at = datetime.now(timezone.utc)
            await db.flush()
    return {
        "canary_id": canary.canary_id,
        "abort": decision["abort"],
        "violations": decision["violations"],
        "status": canary.status,
    }


async def rollback_safety(db: AsyncSession, service_id: str, current_version: str = "") -> dict:
    """Verify a rollback is safe: a previous known-good deployment exists
    and is not itself failed/rolled back."""
    result = await db.execute(
        select(SREDeployment)
        .where(
            SREDeployment.service_id == service_id,
            SREDeployment.status == "success",
            SREDeployment.version != current_version,
        )
        .order_by(SREDeployment.started_at.desc())
        .limit(1)
    )
    previous = result.scalar_one_or_none()
    if previous is None:
        return {"safe": False, "reason": "no known-good previous version"}
    return {"safe": True, "target_version": previous.version, "deployment_id": previous.deployment_id, "reason": "previous known-good version exists"}


async def list_deployments(db: AsyncSession, *, service_id: str = "", offset: int = 0, limit: int = 50) -> tuple[list[dict], int]:
    stmt = select(SREDeployment)
    if service_id:
        stmt = stmt.where(SREDeployment.service_id == service_id)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    stmt = stmt.order_by(SREDeployment.started_at.desc()).offset(offset).limit(limit)
    rows = list((await db.execute(stmt)).scalars().all())
    return [row.to_dict() for row in rows], total


async def list_canaries(db: AsyncSession, *, service_id: str = "", offset: int = 0, limit: int = 50) -> tuple[list[dict], int]:
    stmt = select(SRECanaryRun)
    if service_id:
        stmt = stmt.where(SRECanaryRun.service_id == service_id)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    stmt = stmt.order_by(SRECanaryRun.created_at.desc()).offset(offset).limit(limit)
    rows = list((await db.execute(stmt)).scalars().all())
    return [row.to_dict() for row in rows], total