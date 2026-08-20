"""Tests for plan creation, validation, and workflow."""

import pytest
from app.automation.task_service import TaskService
from app.automation.plan_service import PlanService
from app.automation.schemas import TaskCreate, PlanCreate


@pytest.mark.asyncio
async def _create_task(db):
    svc = TaskService(db)
    return await svc.create(TaskCreate(
        tenant="t1", project="p1", repository="r1",
        request="implement feature", actor="u1",
    ))


@pytest.mark.asyncio
async def test_create_plan(db):
    task = await _create_task(db)
    svc = PlanService(db)
    plan = await svc.create_plan(task.id, PlanCreate(
        objective="Add login feature",
        affected_components=["auth"],
        files=["auth.py", "test_auth.py"],
        risks=["database change"],
        rollback_strategy="revert commit",
    ))
    assert plan.task_id == task.id
    assert plan.status == "draft"
    assert "Add login" in plan.objective


@pytest.mark.asyncio
async def test_approve_plan(db):
    task = await _create_task(db)
    svc = PlanService(db)
    plan = await svc.create_plan(task.id, PlanCreate(
        objective="Fix bug",
        rollback_strategy="revert",
    ))
    plan = await svc.approve_plan(plan.id)
    assert plan.status == "approved"


@pytest.mark.asyncio
async def test_reject_plan(db):
    task = await _create_task(db)
    svc = PlanService(db)
    plan = await svc.create_plan(task.id, PlanCreate(
        objective="Bad plan",
        rollback_strategy="none",
    ))
    plan = await svc.reject_plan(plan.id)
    assert plan.status == "rejected"


@pytest.mark.asyncio
async def test_add_steps(db):
    task = await _create_task(db)
    svc = PlanService(db)
    plan = await svc.create_plan(task.id, PlanCreate(
        objective="Multi-step",
        rollback_strategy="revert",
    ))
    await svc.add_step(plan.id, 1, "read", "Read existing code", risk_level="low")
    await svc.add_step(plan.id, 2, "write", "Write new code", risk_level="medium", requires_approval=True)
    steps = await svc.get_steps(plan.id)
    assert len(steps) == 2
    assert steps[0].step_order == 1
    assert steps[1].requires_approval is True


@pytest.mark.asyncio
async def test_validate_plan_valid(db):
    task = await _create_task(db)
    svc = PlanService(db)
    plan = await svc.create_plan(task.id, PlanCreate(
        objective="Valid plan",
        files=["a.py"],
        risks=["risk1 with mitigation"],
        rollback_strategy="revert",
    ))
    await svc.add_step(plan.id, 1, "read", "Read")
    result = await svc.validate_plan(plan.id)
    assert result["valid"] is True
    assert result["steps"] == 1


@pytest.mark.asyncio
async def test_validate_plan_no_objective(db):
    task = await _create_task(db)
    svc = PlanService(db)
    plan = await svc.create_plan(task.id, PlanCreate(
        objective="",
        rollback_strategy="revert",
    ))
    result = await svc.validate_plan(plan.id)
    assert result["valid"] is False
    assert any("objective" in e for e in result["errors"])


@pytest.mark.asyncio
async def test_validate_plan_no_rollback(db):
    task = await _create_task(db)
    svc = PlanService(db)
    plan = await svc.create_plan(task.id, PlanCreate(
        objective="Some plan",
        rollback_strategy="",
    ))
    result = await svc.validate_plan(plan.id)
    assert result["valid"] is False
    assert any("rollback" in e for e in result["errors"])


@pytest.mark.asyncio
async def test_validate_plan_no_steps(db):
    task = await _create_task(db)
    svc = PlanService(db)
    plan = await svc.create_plan(task.id, PlanCreate(
        objective="Plan",
        rollback_strategy="revert",
    ))
    result = await svc.validate_plan(plan.id)
    assert result["valid"] is False
    assert any("steps" in e for e in result["errors"])


@pytest.mark.asyncio
async def test_get_latest_plan(db):
    task = await _create_task(db)
    svc = PlanService(db)
    p1 = await svc.create_plan(task.id, PlanCreate(objective="First", rollback_strategy="r"))
    p2 = await svc.create_plan(task.id, PlanCreate(objective="Second", rollback_strategy="r"))
    latest = await svc.get_for_task(task.id)
    assert latest is not None
    assert latest.task_id == task.id
    assert latest.id in (p1.id, p2.id)
