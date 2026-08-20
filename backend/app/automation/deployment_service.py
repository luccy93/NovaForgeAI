"""Deployment lifecycle: staging, canary, production, rollback."""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.models import AutomationDeployment, AutomationPatch, AutomationTask, DeploymentStatus, PatchStatus, TaskStatus

logger = logging.getLogger(__name__)


class DeploymentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_deployment(
        self,
        task_id: UUID,
        environment: str,
        deployed_by: str,
        patch_id: Optional[UUID] = None,
    ) -> AutomationDeployment:
        dep = AutomationDeployment(
            task_id=task_id,
            patch_id=patch_id,
            environment=environment,
            status=DeploymentStatus.PENDING,
            deployed_by=deployed_by,
            rollback_available=True,
        )
        self.db.add(dep)
        await self.db.flush()
        return dep

    async def get(self, deployment_id: UUID) -> Optional[AutomationDeployment]:
        return await self.db.get(AutomationDeployment, deployment_id)

    async def list_for_task(self, task_id: UUID) -> list[AutomationDeployment]:
        res = await self.db.execute(
            select(AutomationDeployment)
            .where(AutomationDeployment.task_id == task_id)
            .order_by(AutomationDeployment.created_at.desc())
        )
        return list(res.scalars().all())

    async def mark_in_progress(self, deployment_id: UUID) -> AutomationDeployment:
        dep = await self.get(deployment_id)
        if not dep:
            raise ValueError(f"deployment {deployment_id} not found")
        dep.status =DeploymentStatus.IN_PROGRESS
        await self.db.flush()
        return dep

    async def complete(
        self,
        deployment_id: UUID,
        commit_sha: Optional[str] = None,
        metrics: Optional[dict] = None,
    ) -> AutomationDeployment:
        dep = await self.get(deployment_id)
        if not dep:
            raise ValueError(f"deployment {deployment_id} not found")
        dep.status = DeploymentStatus.COMPLETED
        dep.commit_sha = commit_sha
        if metrics:
            dep.metrics = metrics
        await self.db.flush()
        return dep

    async def fail(self, deployment_id: UUID, metrics: Optional[dict] = None) -> AutomationDeployment:
        dep = await self.get(deployment_id)
        if not dep:
            raise ValueError(f"deployment {deployment_id} not found")
        dep.status = DeploymentStatus.FAILED
        if metrics:
            dep.metrics = metrics
        await self.db.flush()
        return dep

    async def rollback(self, deployment_id: UUID) -> AutomationDeployment:
        dep = await self.get(deployment_id)
        if not dep:
            raise ValueError(f"deployment {deployment_id} not found")
        if not dep.rollback_available:
            raise ValueError("rollback not available for this deployment")
        dep.status = DeploymentStatus.ROLLED_BACK
        dep.rollback_available = False
        await self.db.flush()
        task = await self.db.get(AutomationTask, dep.task_id)
        if task:
            task.status = TaskStatus.ROLLED_BACK
        await self.db.flush()
        return dep

    async def set_canary(self, deployment_id: UUID, weight: int) -> AutomationDeployment:
        dep = await self.get(deployment_id)
        if not dep:
            raise ValueError(f"deployment {deployment_id} not found")
        if weight < 0 or weight > 100:
            raise ValueError("canary weight must be 0-100")
        dep.canary_weight = weight
        await self.db.flush()
        return dep

    async def expand_canary(self, deployment_id: UUID, increment: int = 10) -> AutomationDeployment:
        dep = await self.get(deployment_id)
        if not dep:
            raise ValueError(f"deployment {deployment_id} not found")
        new_weight = min(100, dep.canary_weight + increment)
        dep.canary_weight = new_weight
        await self.db.flush()
        return dep

    async def should_rollback(self, deployment_id: UUID, error_rate_threshold: float = 0.05,
                               latency_threshold_ms: float = 1000) -> dict:
        dep = await self.get(deployment_id)
        if not dep:
            raise ValueError(f"deployment {deployment_id} not found")
        metrics = dep.metrics or {}
        error_rate = metrics.get("error_rate", 0)
        latency = metrics.get("latency_p99_ms", 0)
        should = error_rate > error_rate_threshold or latency > latency_threshold_ms
        reasons = []
        if error_rate > error_rate_threshold:
            reasons.append(f"error_rate {error_rate} > {error_rate_threshold}")
        if latency > latency_threshold_ms:
            reasons.append(f"latency {latency}ms > {latency_threshold_ms}ms")
        return {"should_rollback": should, "reasons": reasons, "metrics": metrics}
