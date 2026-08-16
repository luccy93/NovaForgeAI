"""Chaos engineering (Volume 35).

Controlled chaos experiments with owner, scope, blast radius, abort
conditions, expected vs actual results, and recovery verification.
Experiments never affect production beyond the approved scope.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sre.constants import (
    CHAOS_ABORTED,
    CHAOS_FAILED,
    CHAOS_PASSED,
    CHAOS_PENDING,
    CHAOS_RUNNING,
)
from app.sre.models import SREChaosExperiment
from app.sre.store import get_one, list_all, new_id, new_key

logger = logging.getLogger(__name__)

EXPERIMENT_TYPES = [
    "kill_worker",
    "network_latency",
    "drop_requests",
    "restart_database_replica",
    "disable_ai_provider",
    "increase_latency",
    "fill_disk",
    "queue_backlog",
    "dependency_failure",
    "database_failover",
]

BLAST_RADII = ["test", "staging", "prod-limited"]

# Experiment types that are safe to execute against a limited production scope.
PROD_SAFE_TYPES = {
    "kill_worker",
    "network_latency",
    "drop_requests",
    "disable_ai_provider",
    "dependency_failure",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ChaosManager:
    """Chaos experiment lifecycle with blast-radius controls."""

    async def create(
        self,
        db: AsyncSession,
        *,
        name: str,
        experiment_type: str,
        target: str = "",
        scope: str = "",
        blast_radius: str = "test",
        owner: str = "",
        abort_condition: str = "",
        expected_result: str = "",
        duration_seconds: int = 30,
        organization_id: str = "",
        created_by: str = "",
    ) -> SREChaosExperiment:
        if experiment_type not in EXPERIMENT_TYPES:
            raise ValueError(f"unsupported experiment type: {experiment_type}")
        if blast_radius not in BLAST_RADII:
            raise ValueError(f"unsupported blast radius: {blast_radius}")
        if blast_radius == "prod-limited" and experiment_type not in PROD_SAFE_TYPES:
            raise ValueError(f"experiment type {experiment_type} is not allowed in production")
        experiment = SREChaosExperiment(
            id=new_id(),
            experiment_id=new_key("chaos"),
            organization_id=organization_id,
            name=name,
            experiment_type=experiment_type,
            target=target,
            scope=scope,
            blast_radius=blast_radius,
            owner=owner,
            abort_condition=abort_condition,
            expected_result=expected_result,
            status=CHAOS_PENDING,
            duration_seconds=duration_seconds,
            created_by=created_by,
        )
        db.add(experiment)
        await db.flush()
        return experiment

    async def start(self, db: AsyncSession, experiment_id: str) -> Optional[SREChaosExperiment]:
        experiment = await get_one(db, SREChaosExperiment, experiment_id=experiment_id)
        if experiment is None:
            return None
        if experiment.status != CHAOS_PENDING:
            raise ValueError(f"cannot start experiment in state {experiment.status}")
        experiment.status = CHAOS_RUNNING
        experiment.started_at = _utcnow()
        await db.flush()
        return experiment

    async def complete(
        self,
        db: AsyncSession,
        experiment_id: str,
        *,
        actual_result: str,
        recovery_seconds: float = 0.0,
        passed: bool,
    ) -> Optional[SREChaosExperiment]:
        experiment = await get_one(db, SREChaosExperiment, experiment_id=experiment_id)
        if experiment is None:
            return None
        experiment.actual_result = actual_result
        experiment.recovery_seconds = recovery_seconds
        experiment.passed = passed
        experiment.status = CHAOS_PASSED if passed else CHAOS_FAILED
        experiment.completed_at = _utcnow()
        await db.flush()
        return experiment

    async def abort(self, db: AsyncSession, experiment_id: str, reason: str = "") -> Optional[SREChaosExperiment]:
        experiment = await get_one(db, SREChaosExperiment, experiment_id=experiment_id)
        if experiment is None:
            return None
        experiment.status = CHAOS_ABORTED
        experiment.actual_result = f"aborted: {reason}"
        experiment.completed_at = _utcnow()
        await db.flush()
        return experiment

    async def check_abort(self, db: AsyncSession, experiment_id: str, trigger: bool, condition: str = "") -> bool:
        """Abort an experiment when its abort condition triggers."""
        if not trigger:
            return False
        await self.abort(db, experiment_id, condition or "abort condition triggered")
        return True

    async def get(self, db: AsyncSession, experiment_id: str) -> Optional[dict]:
        experiment = await get_one(db, SREChaosExperiment, experiment_id=experiment_id)
        return experiment.to_dict() if experiment else None

    async def list(
        self,
        db: AsyncSession,
        *,
        status: str = "",
        experiment_type: str = "",
        blast_radius: str = "",
        organization_id: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        items, total = await list_all(
            db,
            SREChaosExperiment,
            limit=limit,
            offset=offset,
            order_by="created_at",
            status=status,
            experiment_type=experiment_type,
            blast_radius=blast_radius,
            organization_id=organization_id or "",
        )
        return [e.to_dict() for e in items], total

    async def pass_rate(self, db: AsyncSession) -> dict:
        result = await db.execute(
            select(SREChaosExperiment).where(
                SREChaosExperiment.status.in_([CHAOS_PASSED, CHAOS_FAILED])
            )
        )
        experiments = result.scalars().all()
        passed = sum(1 for e in experiments if e.status == CHAOS_PASSED)
        return {
            "total": len(experiments),
            "passed": passed,
            "failed": len(experiments) - passed,
            "pass_rate": round(passed / len(experiments), 4) if experiments else 0.0,
        }


chaos_manager = ChaosManager()
