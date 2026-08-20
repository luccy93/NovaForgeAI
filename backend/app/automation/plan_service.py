"""Plan generation, validation and execution tracking."""

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.models import AutomationPlan, AutomationStep, AutomationTask, TaskStatus
from app.automation.schemas import PlanCreate

logger = logging.getLogger(__name__)


class PlanService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_plan(self, task_id: UUID, data: PlanCreate) -> AutomationPlan:
        plan = AutomationPlan(
            task_id=task_id,
            objective=data.objective,
            affected_components=data.affected_components,
            files=data.files,
            dependencies=data.dependencies,
            risks=data.risks,
            required_tools=data.required_tools,
            test_plan=data.test_plan,
            rollback_strategy=data.rollback_strategy,
            estimated_cost=data.estimated_cost,
            status="draft",
        )
        self.db.add(plan)
        await self.db.flush()
        return plan

    async def get(self, plan_id: UUID) -> Optional[AutomationPlan]:
        return await self.db.get(AutomationPlan, plan_id)

    async def get_for_task(self, task_id: UUID) -> Optional[AutomationPlan]:
        res = await self.db.execute(
            select(AutomationPlan)
            .where(AutomationPlan.task_id == task_id)
            .order_by(AutomationPlan.created_at.desc())
            .limit(1)
        )
        return res.scalar_one_or_none()

    async def approve_plan(self, plan_id: UUID) -> AutomationPlan:
        plan = await self.get(plan_id)
        if not plan:
            raise ValueError(f"plan {plan_id} not found")
        plan.status = "approved"
        await self.db.flush()
        return plan

    async def reject_plan(self, plan_id: UUID) -> AutomationPlan:
        plan = await self.get(plan_id)
        if not plan:
            raise ValueError(f"plan {plan_id} not found")
        plan.status = "rejected"
        await self.db.flush()
        return plan

    async def add_step(self, plan_id: UUID, step_order: int, step_type: str,
                       description: str, tool: Optional[str] = None,
                       inputs: Optional[dict] = None, risk_level: str = "low",
                       requires_approval: bool = False) -> AutomationStep:
        step = AutomationStep(
            plan_id=plan_id,
            step_order=step_order,
            step_type=step_type,
            description=description,
            tool=tool,
            inputs=inputs or {},
            risk_level=risk_level,
            requires_approval=requires_approval,
            status="pending",
        )
        self.db.add(step)
        await self.db.flush()
        return step

    async def get_steps(self, plan_id: UUID) -> list[AutomationStep]:
        res = await self.db.execute(
            select(AutomationStep)
            .where(AutomationStep.plan_id == plan_id)
            .order_by(AutomationStep.step_order)
        )
        return list(res.scalars().all())

    async def update_step(self, step_id: UUID, status: str, result: Optional[dict] = None) -> AutomationStep:
        step = await self.db.get(AutomationStep, step_id)
        if not step:
            raise ValueError(f"step {step_id} not found")
        step.status = status
        if result is not None:
            step.result = result
        await self.db.flush()
        return step

    async def validate_plan(self, plan_id: UUID) -> dict:
        plan = await self.get(plan_id)
        if not plan:
            raise ValueError(f"plan {plan_id} not found")
        errors = []
        if not plan.objective:
            errors.append("missing objective")
        if not plan.files and not plan.affected_components:
            errors.append("no files or components specified")
        if not plan.rollback_strategy:
            errors.append("missing rollback strategy")
        steps = await self.get_steps(plan_id)
        if not steps:
            errors.append("no steps defined")
        risks_withmitigation = [r for r in plan.risks if r]
        if len(plan.risks) > 0 and len(risks_withmitigation) == 0:
            errors.append("risks listed but none have mitigation")
        valid = len(errors) == 0
        return {"valid": valid, "errors": errors, "steps": len(steps)}
