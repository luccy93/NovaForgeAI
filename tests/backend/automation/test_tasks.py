"""Tests for task lifecycle management."""

import pytest
from uuid import uuid4
from app.automation.task_service import TaskService
from app.automation.schemas import TaskCreate, TaskUpdate
from app.automation.models import TaskStatus, RiskLevel


@pytest.mark.asyncio
async def test_create_task(db):
    svc = TaskService(db)
    task = await svc.create(TaskCreate(
        tenant="t1", project="p1", repository="r1",
        request="fix login bug", actor="user1", task_type="bug",
    ))
    assert task.status == TaskStatus.QUEUED
    assert task.tenant == "t1"
    assert task.task_type == "bug"
    assert task.risk_level in ("low", "medium", "high", "critical")


@pytest.mark.asyncio
async def test_get_task(db):
    svc = TaskService(db)
    task = await svc.create(TaskCreate(
        tenant="t1", project="p1", repository="r1",
        request="add feature", actor="user1",
    ))
    fetched = await svc.get(task.id)
    assert fetched is not None
    assert fetched.id == task.id


@pytest.mark.asyncio
async def test_list_tasks(db):
    svc = TaskService(db)
    await svc.create(TaskCreate(tenant="t1", project="p1", repository="r1", request="task1", actor="u1"))
    await svc.create(TaskCreate(tenant="t1", project="p1", repository="r1", request="task2", actor="u1"))
    await svc.create(TaskCreate(tenant="t2", project="p1", repository="r1", request="task3", actor="u1"))
    tasks, total = await svc.list_tasks(tenant="t1")
    assert total == 2
    assert len(tasks) == 2


@pytest.mark.asyncio
async def test_transition(db):
    svc = TaskService(db)
    task = await svc.create(TaskCreate(
        tenant="t1", project="p1", repository="r1",
        request="task", actor="u1",
    ))
    task = await svc.transition(task.id, TaskStatus.ANALYZING)
    assert task.status == TaskStatus.ANALYZING
    task = await svc.transition(task.id, TaskStatus.PLANNING)
    assert task.status == TaskStatus.PLANNING


@pytest.mark.asyncio
async def test_invalid_transition(db):
    svc = TaskService(db)
    task = await svc.create(TaskCreate(
        tenant="t1", project="p1", repository="r1",
        request="task", actor="u1",
    ))
    with pytest.raises(ValueError, match="cannot transition"):
        await svc.transition(task.id, TaskStatus.COMPLETED)


@pytest.mark.asyncio
async def test_cancel_task(db):
    svc = TaskService(db)
    task = await svc.create(TaskCreate(
        tenant="t1", project="p1", repository="r1",
        request="task", actor="u1",
    ))
    task = await svc.cancel(task.id)
    assert task.status == TaskStatus.CANCELLED


@pytest.mark.asyncio
async def test_risk_classification_security(db):
    svc = TaskService(db)
    task = await svc.create(TaskCreate(
        tenant="t1", project="p1", repository="r1",
        request="fix production access privilege escalation vulnerability", actor="u1", task_type="security",
    ))
    assert task.risk_level in ("medium", "high", "critical")


@pytest.mark.asyncio
async def test_risk_classification_low(db):
    svc = TaskService(db)
    task = await svc.create(TaskCreate(
        tenant="t1", project="p1", repository="r1",
        request="update readme", actor="u1", task_type="documentation",
    ))
    assert task.risk_level == "low"


@pytest.mark.asyncio
async def test_checkpoint_created(db):
    svc = TaskService(db)
    task = await svc.create(TaskCreate(
        tenant="t1", project="p1", repository="r1",
        request="task", actor="u1",
    ))
    cps = await svc.get_checkpoints(task.id)
    assert len(cps) >= 1
    assert cps[0].phase == "created"


@pytest.mark.asyncio
async def test_update_task(db):
    svc = TaskService(db)
    task = await svc.create(TaskCreate(
        tenant="t1", project="p1", repository="r1",
        request="task", actor="u1",
    ))
    updated = await svc.update(task.id, TaskUpdate(result={"key": "value"}))
    assert updated.result == {"key": "value"}


@pytest.mark.asyncio
async def test_list_with_status_filter(db):
    svc = TaskService(db)
    t1 = await svc.create(TaskCreate(tenant="t1", project="p1", repository="r1", request="t1", actor="u1"))
    await svc.create(TaskCreate(tenant="t1", project="p1", repository="r1", request="t2", actor="u1"))
    await svc.transition(t1.id, TaskStatus.ANALYZING)
    tasks, total = await svc.list_tasks(status=TaskStatus.QUEUED)
    assert total == 1
    tasks, total = await svc.list_tasks(status=TaskStatus.ANALYZING)
    assert total == 1
