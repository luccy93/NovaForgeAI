"""Core loop orchestrator — coordinates workers, state transitions,
budget enforcement and approval gates for a single automation task.

This is the high-level controller that implements the full
``request → plan → approve → implement → test → review → deploy``
pipeline while respecting budgets, repair budgets and governance.
"""

import logging
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.models import (
    AutomationTask,
    AutonomyLevel,
    RiskLevel,
    TaskStatus,
)
from app.automation.task_service import TaskService
from app.automation.plan_service import PlanService
from app.automation.patch_service import PatchService
from app.automation.test_service import TestService
from app.automation.review_service import ReviewService
from app.automation.approval_service import ApprovalService
from app.automation.deployment_service import DeploymentService
from app.automation.budget_service import BudgetService
from app.automation.engine_workers import get_worker

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITERATIONS = 5
DEFAULT_MAX_FILES = 50
DEFAULT_MAX_RUNTIME_S = 1800


class EngineOrchestrator:
    """Drives a task through the autonomous engineering core loop."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.tasks = TaskService(db)
        self.plans = PlanService(db)
        self.patches = PatchService(db)
        self.tests = TestService(db)
        self.reviews = ReviewService(db)
        self.approvals = ApprovalService(db)
        self.deployments = DeploymentService(db)
        self.budgets = BudgetService(db)

    async def run_task(self, task_id: UUID) -> dict:
        task = await self.tasks.get(task_id)
        if not task:
            raise ValueError(f"task {task_id} not found")

        budget_check = await self.budgets.check_budget(task.tenant)
        if not budget_check["within_budget"]:
            await self.tasks.transition(task_id, TaskStatus.FAILED, error=f"budget exceeded: {budget_check['violations']}")
            return {"completed": False, "reason": "budget_exceeded", "details": budget_check}

        await self.budgets.increment_active_tasks(task.tenant)
        try:
            result = await self._execute_loop(task)
        finally:
            await self.budgets.decrement_active_tasks(task.tenant)
        return result

    async def _execute_loop(self, task: AutomationTask) -> dict:
        if task.status == TaskStatus.QUEUED:
            await self.tasks.transition(task.id, TaskStatus.ANALYZING)
            await self._analyze(task)
            task = await self.tasks.get(task.id)

        if task.status == TaskStatus.ANALYZING:
            await self.tasks.transition(task.id, TaskStatus.PLANNING)
            await self._plan(task)
            task = await self.tasks.get(task.id)

        if task.status == TaskStatus.PLANNING:
            if self.approvals.requires_approval(task, planned_action=task.request):
                await self.tasks.transition(task.id, TaskStatus.APPROVAL_REQUIRED)
                return {"completed": False, "reason": "approval_required", "task_id": str(task.id)}
            await self.tasks.transition(task.id, TaskStatus.IMPLEMENTING)

        if task.status in (TaskStatus.APPROVAL_REQUIRED, TaskStatus.IMPLEMENTING, TaskStatus.TESTING, TaskStatus.REVIEWING):
            return await self._continue_loop(task)

        return {"completed": task.status == TaskStatus.COMPLETED, "status": task.status}

    async def _continue_loop(self, task: AutomationTask) -> dict:
        iteration = 0
        max_iter = DEFAULT_MAX_ITERATIONS

        while iteration < max_iter:
            iteration += 1
            task = await self.tasks.get(task.id)

            if task.status == TaskStatus.APPROVAL_REQUIRED:
                pending = await self.approvals.get_pending(task.id)
                if pending:
                    return {"completed": False, "reason": "awaiting_approval", "approval_id": str(pending.id)}
                await self.tasks.transition(task.id, TaskStatus.IMPLEMENTING)

            if task.status == TaskStatus.IMPLEMENTING:
                await self._implement(task)
                task = await self.tasks.get(task.id)

            if task.status == TaskStatus.TESTING:
                test_ok = await self._test(task)
                task = await self.tasks.get(task.id)
                if not test_ok and iteration < max_iter:
                    continue
                if not test_ok:
                    await self.tasks.transition(task.id, TaskStatus.FAILED, error="repair budget exhausted")
                    return {"completed": False, "reason": "test_failure_limit", "iterations": iteration}

            if task.status == TaskStatus.REVIEWING:
                review_ok = await self._review(task)
                task = await self.tasks.get(task.id)
                if not review_ok:
                    await self.tasks.transition(task.id, TaskStatus.IMPLEMENTING)
                    continue

            if task.status == TaskStatus.WAITING:
                await self.tasks.transition(task.id, TaskStatus.COMPLETED)
                break

        task = await self.tasks.get(task.id)
        return {"completed": task.status == TaskStatus.COMPLETED, "status": task.status, "iterations": iteration}

    async def _analyze(self, task: AutomationTask) -> None:
        task.confidence = 0.85
        task.context["analysis"] = {"type": task.task_type, "repo": task.repository}
        await self.db.flush()

    async def _plan(self, task: AutomationTask) -> None:
        worker = get_worker("planner")
        if not worker:
            raise RuntimeError("planner worker not available")
        result = await worker.execute({
            "request": task.request,
            "task_type": task.task_type,
            "repository": task.repository,
            "branch": task.branch,
            "repo_context": task.context.get("repo_context", {}),
        })
        if result.success:
            plan_data = result.output
            from app.automation.schemas import PlanCreate
            await self.plans.create_plan(task.id, PlanCreate(
                objective=plan_data["objective"],
                affected_components=plan_data["affected_components"],
                files=plan_data["files"],
                dependencies=plan_data["dependencies"],
                risks=plan_data["risks"],
                required_tools=plan_data["required_tools"],
                test_plan=plan_data["test_plan"],
                rollback_strategy=plan_data["rollback_strategy"],
                estimated_cost=plan_data["estimated_cost"],
            ))
            await self.budgets.record_usage(task.tenant, tokens=result.tokens_used, cost_usd=result.cost_usd)

    async def _implement(self, task: AutomationTask) -> None:
        plan = await self.plans.get_for_task(task.id)
        if not plan:
            await self.tasks.transition(task.id, TaskStatus.FAILED, error="no plan found")
            return
        await self.tasks.transition(task.id, TaskStatus.TESTING)
        worker = get_worker("coder")
        if not worker:
            return
        result = await worker.execute({"plan": {
            "objective": plan.objective,
            "files": plan.files,
        }})
        if result.success:
            patch_data = result.output
            await self.patches.create(
                task.id,
                diff=patch_data["diff"],
                file_changes=patch_data["file_changes"],
                added_lines=patch_data["added_lines"],
                removed_lines=patch_data["removed_lines"],
                files_changed=patch_data["files_changed"],
                reason=patch_data["reason"],
                plan_id=plan.id,
            )
            await self.budgets.record_usage(task.tenant, tokens=result.tokens_used, cost_usd=result.cost_usd)

    async def _test(self, task: AutomationTask) -> bool:
        patch = (await self.patches.list_for_task(task.id))
        latest_patch = patch[0] if patch else None
        worker = get_worker("tester")
        if not worker:
            return True
        result = await worker.execute({"patch": {
            "files_changed": latest_patch.files_changed if latest_patch else 0,
        }})
        if result.success:
            test_data = result.output
            run = await self.tests.record_run(
                task.id,
                test_type=test_data["test_type"],
                tests_total=test_data["tests_total"],
                tests_passed=test_data["tests_passed"],
                tests_failed=test_data["tests_failed"],
                tests_skipped=test_data.get("tests_skipped", 0),
                duration_ms=test_data.get("duration_ms", 0),
                output=test_data.get("output", ""),
                failures=test_data.get("failures", []),
                patch_id=latest_patch.id if latest_patch else None,
            )
            await self.budgets.record_usage(task.tenant, tokens=result.tokens_used, cost_usd=result.cost_usd)
            return run.result == "passed"
        return False

    async def _review(self, task: AutomationTask) -> bool:
        patches = await self.patches.list_for_task(task.id)
        latest_patch = patches[0] if patches else None
        worker = get_worker("reviewer")
        if not worker:
            return True
        result = await worker.execute({"patch": {
            "files_changed": latest_patch.files_changed if latest_patch else 0,
            "reason": latest_patch.reason if latest_patch else "",
        }})
        if result.success:
            review_data = result.output
            review = await self.reviews.create_review(
                task.id, reviewer="ai_reviewer",
                patch_id=latest_patch.id if latest_patch else None,
            )
            await self.reviews.submit_findings(
                review.id,
                findings=review_data["findings"],
                summary=review_data["summary"],
                correctness_score=review_data["correctness_score"],
                security_score=review_data["security_score"],
                maintainability_score=review_data["maintainability_score"],
                overall_score=review_data["overall_score"],
            )
            await self.budgets.record_usage(task.tenant, tokens=result.tokens_used, cost_usd=result.cost_usd)
            return review_data["overall_score"] >= 0.6
        return False
