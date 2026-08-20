"""Deployment lifecycle: create, execute, canary, verify, rollback."""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.delivery.models import (
    DeliveryDeployment, DeliveryEnvironment, DeliveryRollout,
    DeliveryRollback, DeliveryPipelineRun,
)

logger = logging.getLogger(__name__)


class DeploymentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, tenant: str, environment_id: UUID, strategy: str = "rolling",
                     version: str = "0.0.0", commit_sha: str = "", deployed_by: str = "",
                     artifact_id: Optional[UUID] = None, pipeline_run_id: Optional[UUID] = None,
                     notes: Optional[str] = None) -> DeliveryDeployment:
        env = await self.db.get(DeliveryEnvironment, environment_id)
        if not env:
            raise ValueError(f"environment {environment_id} not found")
        if env.frozen:
            raise ValueError(f"environment {env.name} is frozen")
        if env.locked:
            raise ValueError(f"environment {env.name} is locked by {env.locked_by}")
        dep = DeliveryDeployment(
            tenant=tenant, environment_id=environment_id, strategy=strategy,
            version=version, commit_sha=commit_sha, deployed_by=deployed_by,
            artifact_id=artifact_id, pipeline_run_id=pipeline_run_id,
            notes=notes, status="pending",
        )
        self.db.add(dep)
        await self.db.flush()
        return dep

    async def get(self, deployment_id: UUID) -> Optional[DeliveryDeployment]:
        return await self.db.get(DeliveryDeployment, deployment_id)

    async def list_deployments(self, tenant: Optional[str] = None, environment_id: Optional[UUID] = None,
                                status: Optional[str] = None, limit: int = 20, offset: int = 0) -> tuple[list, int]:
        from sqlalchemy import func
        stmt = select(DeliveryDeployment)
        count_stmt = select(func.count()).select_from(DeliveryDeployment)
        if tenant:
            stmt = stmt.where(DeliveryDeployment.tenant == tenant)
            count_stmt = count_stmt.where(DeliveryDeployment.tenant == tenant)
        if environment_id:
            stmt = stmt.where(DeliveryDeployment.environment_id == environment_id)
            count_stmt = count_stmt.where(DeliveryDeployment.environment_id == environment_id)
        if status:
            stmt = stmt.where(DeliveryDeployment.status == status)
            count_stmt = count_stmt.where(DeliveryDeployment.status == status)
        total = await self.db.scalar(count_stmt)
        rows = (await self.db.execute(stmt.order_by(DeliveryDeployment.created_at.desc()).limit(limit).offset(offset))).scalars().all()
        return list(rows), total or 0

    async def start(self, deployment_id: UUID) -> DeliveryDeployment:
        dep = await self.get(deployment_id)
        if not dep:
            raise ValueError(f"deployment {deployment_id} not found")
        dep.status = "in_progress"
        dep.started_at = datetime.now(timezone.utc)
        await self.db.flush()
        return dep

    async def complete(self, deployment_id: UUID, health_status: str = "healthy") -> DeliveryDeployment:
        dep = await self.get(deployment_id)
        if not dep:
            raise ValueError(f"deployment {deployment_id} not found")
        dep.status = "completed"
        dep.health_status = health_status
        dep.finished_at = datetime.now(timezone.utc)
        env = await self.db.get(DeliveryEnvironment, dep.environment_id)
        if env:
            env.current_deployment_id = dep.id
        await self.db.flush()
        return dep

    async def fail(self, deployment_id: UUID, error: str = "") -> DeliveryDeployment:
        dep = await self.get(deployment_id)
        if not dep:
            raise ValueError(f"deployment {deployment_id} not found")
        dep.status = "failed"
        dep.health_status = "unhealthy"
        dep.finished_at = datetime.now(timezone.utc)
        dep.notes = error
        await self.db.flush()
        return dep

    async def approve(self, deployment_id: UUID, approved_by: str) -> DeliveryDeployment:
        dep = await self.get(deployment_id)
        if not dep:
            raise ValueError(f"deployment {deployment_id} not found")
        dep.approved_by = approved_by
        dep.status = "approved"
        await self.db.flush()
        return dep

    async def should_rollback(self, deployment_id: UUID, error_rate_threshold: float = 0.05,
                               latency_threshold_ms: int = 1000) -> dict:
        dep = await self.get(deployment_id)
        if not dep:
            raise ValueError(f"deployment {deployment_id} not found")
        rollout = await self._get_rollout(deployment_id)
        if rollout and rollout.metrics_snapshot:
            metrics = rollout.metrics_snapshot
            error_rate = metrics.get("error_rate", 0)
            latency = metrics.get("latency_p99_ms", 0)
            reasons = []
            if error_rate > error_rate_threshold:
                reasons.append(f"error_rate {error_rate} > {error_rate_threshold}")
            if latency > latency_threshold_ms:
                reasons.append(f"latency {latency}ms > {latency_threshold_ms}ms")
            return {"should_rollback": len(reasons) > 0, "reasons": reasons}
        return {"should_rollback": False, "reasons": []}

    async def create_rollout(self, deployment_id: UUID, strategy: str = "canary",
                              stages: Optional[list] = None) -> DeliveryRollout:
        rollout = DeliveryRollout(
            deployment_id=deployment_id, strategy=strategy,
            stages=stages or [5, 25, 50, 100], current_weight=0, target_weight=100,
        )
        self.db.add(rollout)
        await self.db.flush()
        return rollout

    async def expand_rollout(self, rollout_id: UUID, increment: int = 10) -> DeliveryRollout:
        rollout = await self.db.get(DeliveryRollout, rollout_id)
        if not rollout:
            raise ValueError(f"rollout {rollout_id} not found")
        stages = rollout.stages or [5, 25, 50, 100]
        if rollout.current_stage < len(stages):
            rollout.current_weight = stages[rollout.current_stage]
            rollout.current_stage += 1
        else:
            rollout.current_weight = rollout.target_weight
        if rollout.current_weight >= rollout.target_weight:
            rollout.status = "completed"
        await self.db.flush()
        return rollout

    async def abort_rollout(self, rollout_id: UUID) -> DeliveryRollout:
        rollout = await self.db.get(DeliveryRollout, rollout_id)
        if not rollout:
            raise ValueError(f"rollout {rollout_id} not found")
        rollout.status = "aborted"
        await self.db.flush()
        return rollout

    async def _get_rollout(self, deployment_id: UUID) -> Optional[DeliveryRollout]:
        res = await self.db.execute(
            select(DeliveryRollout).where(DeliveryRollout.deployment_id == deployment_id).limit(1)
        )
        return res.scalar_one_or_none()

    async def create_rollback(self, deployment_id: UUID, reason: str = "", initiated_by: str = "",
                               automatic: bool = False) -> DeliveryRollback:
        dep = await self.get(deployment_id)
        if not dep:
            raise ValueError(f"deployment {deployment_id} not found")
        env = await self.db.get(DeliveryEnvironment, dep.environment_id)
        rb = DeliveryRollback(
            deployment_id=deployment_id, reason=reason, initiated_by=initiated_by,
            automatic=automatic, status="pending", previous_version=dep.version,
            target_version=dep.rollback_version or "previous",
            environment=env.name if env else "",
        )
        self.db.add(rb)
        dep.status = "rolled_back"
        dep.rollback_available = False
        await self.db.flush()
        return rb

    async def complete_rollback(self, rollback_id: UUID, verified: bool = True) -> DeliveryRollback:
        rb = await self.db.get(DeliveryRollback, rollback_id)
        if not rb:
            raise ValueError(f"rollback {rollback_id} not found")
        rb.status = "completed"
        rb.verified = verified
        rb.completed_at = datetime.now(timezone.utc)
        await self.db.flush()
        return rb
