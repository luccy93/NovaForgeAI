"""Task lifecycle management for autonomous engineering.

Handles intake, state transitions, risk classification, and task memory.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.models import (
    AutomationBudget,
    AutomationCheckpoint,
    AutomationPlan,
    AutomationTask,
    AutonomyLevel,
    RiskLevel,
    TaskStatus,
    TaskType,
)
from app.automation.schemas import TaskCreate, TaskUpdate

logger = logging.getLogger(__name__)

# Valid state transitions
VALID_TRANSITIONS: dict[str, list[str]] = {
    TaskStatus.QUEUED: [TaskStatus.ANALYZING, TaskStatus.CANCELLED, TaskStatus.FAILED],
    TaskStatus.ANALYZING: [TaskStatus.PLANNING, TaskStatus.APPROVAL_REQUIRED, TaskStatus.CANCELLED, TaskStatus.FAILED],
    TaskStatus.PLANNING: [TaskStatus.APPROVAL_REQUIRED, TaskStatus.IMPLEMENTING, TaskStatus.CANCELLED, TaskStatus.FAILED],
    TaskStatus.APPROVAL_REQUIRED: [TaskStatus.IMPLEMENTING, TaskStatus.CANCELLED, TaskStatus.FAILED],
    TaskStatus.IMPLEMENTING: [TaskStatus.TESTING, TaskStatus.FAILED, TaskStatus.CANCELLED],
    TaskStatus.TESTING: [TaskStatus.REVIEWING, TaskStatus.FAILED, TaskStatus.WAITING],
    TaskStatus.REVIEWING: [TaskStatus.WAITING, TaskStatus.IMPLEMENTING, TaskStatus.COMPLETED, TaskStatus.FAILED],
    TaskStatus.WAITING: [TaskStatus.IMPLEMENTING, TaskStatus.TESTING, TaskStatus.REVIEWING, TaskStatus.COMPLETED, TaskStatus.FAILED],
    TaskStatus.COMPLETED: [TaskStatus.ROLLED_BACK],
    TaskStatus.FAILED: [TaskStatus.QUEUED],
    TaskStatus.CANCELLED: [],
    TaskStatus.ROLLED_BACK: [],
}

# Risk signals per task type
RISK_SIGNALS: dict[str, list[str]] = {
    TaskType.BUG: ["database_migration", "security", "authentication"],
    TaskType.FEATURE: ["new_endpoint", "database_migration", "breaking_change"],
    TaskType.REFACTOR: ["breaking_change", "large_scope"],
    TaskType.SECURITY: ["production_access", "privilege_escalation"],
    TaskType.PERFORMANCE: ["database_query", "caching_layer"],
    TaskType.INCIDENT_REMEDIATION: ["production_access", "emergency"],
    TaskType.ARCHITECTURE: ["breaking_change", "large_scope", "service_boundary"],
}


class TaskService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: TaskCreate) -> AutomationTask:
        risk_level = self._classify_risk(data)
        task = AutomationTask(
            tenant=data.tenant,
            project=data.project,
            repository=data.repository,
            branch=data.branch,
            request=data.request,
            actor=data.actor,
            task_type=data.task_type,
            autonomy_level=data.autonomy_level,
            risk_level=risk_level,
            status=TaskStatus.QUEUED,
            confidence=0.0,
            parent_task_id=data.parent_task_id,
            workflow_id=data.workflow_id,
            deadline=data.deadline,
            context=data.context,
        )
        self.db.add(task)
        await self.db.flush()
        await self._checkpoint(task, "created", {"request": data.request})
        return task

    async def get(self, task_id: UUID) -> Optional[AutomationTask]:
        return await self.db.get(AutomationTask, task_id)

    async def list_tasks(
        self,
        tenant: Optional[str] = None,
        status: Optional[str] = None,
        repository: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AutomationTask], int]:
        stmt = select(AutomationTask)
        count_stmt = select(func.count()).select_from(AutomationTask)
        if tenant:
            stmt = stmt.where(AutomationTask.tenant == tenant)
            count_stmt = count_stmt.where(AutomationTask.tenant == tenant)
        if status:
            stmt = stmt.where(AutomationTask.status == status)
            count_stmt = count_stmt.where(AutomationTask.status == status)
        if repository:
            stmt = stmt.where(AutomationTask.repository == repository)
            count_stmt = count_stmt.where(AutomationTask.repository == repository)
        total = await self.db.scalar(count_stmt)
        rows = (await self.db.execute(
            stmt.order_by(AutomationTask.created_at.desc()).limit(limit).offset(offset)
        )).scalars().all()
        return list(rows), total or 0

    async def transition(self, task_id: UUID, new_status: str, result: Optional[dict] = None, error: Optional[str] = None) -> AutomationTask:
        task = await self.get(task_id)
        if not task:
            raise ValueError(f"task {task_id} not found")
        allowed = VALID_TRANSITIONS.get(task.status, [])
        if new_status not in allowed:
            raise ValueError(f"cannot transition from '{task.status}' to '{new_status}'")
        task.status = new_status
        if result is not None:
            task.result = result
        if error is not None:
            task.error = error
        task.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self._checkpoint(task, f"transition:{new_status}", {"from_status": task.status, "to_status": new_status})
        return task

    async def cancel(self, task_id: UUID) -> AutomationTask:
        return await self.transition(task_id, TaskStatus.CANCELLED)

    async def update(self, task_id: UUID, data: TaskUpdate) -> AutomationTask:
        task = await self.get(task_id)
        if not task:
            raise ValueError(f"task {task_id} not found")
        if data.status is not None:
            task = await self.transition(task_id, data.status, result=data.result, error=data.error)
        else:
            if data.result is not None:
                task.result = data.result
            if data.error is not None:
                task.error = data.error
            if data.risk_level is not None:
                task.risk_level = data.risk_level
            task.updated_at = datetime.now(timezone.utc)
            await self.db.flush()
        return task

    async def _checkpoint(self, task: AutomationTask, phase: str, state: dict) -> None:
        cp = AutomationCheckpoint(task_id=task.id, phase=phase, state=state, can_resume=True)
        self.db.add(cp)

    def _classify_risk(self, data: TaskCreate) -> str:
        request_lower = data.request.lower()
        if data.autonomy_level >= AutonomyLevel.L5:
            return RiskLevel.CRITICAL
        signals = RISK_SIGNALS.get(data.task_type, [])
        hit_count = sum(1 for s in signals if s.replace("_", " ") in request_lower)
        if hit_count >= 2 or data.autonomy_level >= AutonomyLevel.L4:
            return RiskLevel.HIGH
        if hit_count >= 1 or data.autonomy_level >= AutonomyLevel.L3:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    async def get_checkpoints(self, task_id: UUID) -> list:
        res = await self.db.execute(
            select(AutomationCheckpoint)
            .where(AutomationCheckpoint.task_id == task_id)
            .order_by(AutomationCheckpoint.created_at)
        )
        return list(res.scalars().all())

    async def resume_from_checkpoint(self, task_id: UUID, checkpoint_id: UUID) -> Optional[AutomationCheckpoint]:
        cp = await self.db.get(AutomationCheckpoint, checkpoint_id)
        if cp and cp.task_id == task_id and cp.can_resume:
            return cp
        return None
