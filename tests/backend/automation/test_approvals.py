"""Tests for approval workflow."""

import pytest
from app.automation.task_service import TaskService
from app.automation.approval_service import ApprovalService
from app.automation.schemas import TaskCreate
from app.automation.models import ApprovalDecision, RiskLevel


@pytest.mark.asyncio
async def _create_task(db, risk_level="medium"):
    svc = TaskService(db)
    return await svc.create(TaskCreate(
        tenant="t1", project="p1", repository="r1",
        request="deploy to production", actor="u1",
        autonomy_level=3,
    ))


@pytest.mark.asyncio
async def test_request_approval(db):
    task = await _create_task(db)
    svc = ApprovalService(db)
    approval = await svc.request_approval(
        task.id, requested_by="ai_agent",
        planned_action="deploy to production",
        affected_resources=["prod-server"],
        risk_level="high",
    )
    assert approval.task_id == task.id
    assert approval.decision == ApprovalDecision.PENDING


@pytest.mark.asyncio
async def test_approve(db):
    task = await _create_task(db)
    svc = ApprovalService(db)
    approval = await svc.request_approval(task.id, requested_by="ai", planned_action="deploy")
    approved = await svc.approve(approval.id, decided_by="admin", reason="looks good")
    assert approved.decision == ApprovalDecision.APPROVED
    assert approved.decided_by == "admin"


@pytest.mark.asyncio
async def test_reject(db):
    task = await _create_task(db)
    svc = ApprovalService(db)
    approval = await svc.request_approval(task.id, requested_by="ai", planned_action="deploy")
    rejected = await svc.reject(approval.id, decided_by="admin", reason="too risky")
    assert rejected.decision == ApprovalDecision.REJECTED


@pytest.mark.asyncio
async def test_double_decide_fails(db):
    task = await _create_task(db)
    svc = ApprovalService(db)
    approval = await svc.request_approval(task.id, requested_by="ai", planned_action="deploy")
    await svc.approve(approval.id, decided_by="admin")
    with pytest.raises(ValueError, match="already decided"):
        await svc.approve(approval.id, decided_by="admin2")


@pytest.mark.asyncio
async def test_requires_approval_high_risk(db):
    task = await _create_task(db, risk_level="high")
    svc = ApprovalService(db)
    assert svc.requires_approval(task, "fix bug") is True


@pytest.mark.asyncio
async def test_requires_approval_deploy_action(db):
    from app.automation.models import AutomationTask
    task = AutomationTask(
        tenant="t1", project="p1", repository="r1",
        request="task", actor="u1", risk_level="low",
        autonomy_level=2, status="queued",
    )
    svc = ApprovalService(db)
    assert svc.requires_approval(task, "deploy to staging") is True


@pytest.mark.asyncio
async def test_does_not_require_approval(db):
    from app.automation.models import AutomationTask
    task = AutomationTask(
        tenant="t1", project="p1", repository="r1",
        request="task", actor="u1", risk_level="low",
        autonomy_level=1, status="queued",
    )
    svc = ApprovalService(db)
    assert svc.requires_approval(task, "read file") is False


@pytest.mark.asyncio
async def test_pending_count(db):
    task = await _create_task(db)
    svc = ApprovalService(db)
    assert await svc.pending_count() == 0
    await svc.request_approval(task.id, requested_by="ai", planned_action="a")
    assert await svc.pending_count() == 1


@pytest.mark.asyncio
async def test_get_pending(db):
    task = await _create_task(db)
    svc = ApprovalService(db)
    a1 = await svc.request_approval(task.id, requested_by="ai", planned_action="first")
    a2 = await svc.request_approval(task.id, requested_by="ai", planned_action="second")
    pending = await svc.get_pending(task.id)
    assert pending.id == a1.id


@pytest.mark.asyncio
async def test_list_for_task(db):
    task = await _create_task(db)
    svc = ApprovalService(db)
    await svc.request_approval(task.id, requested_by="ai", planned_action="a")
    await svc.request_approval(task.id, requested_by="ai", planned_action="b")
    approvals = await svc.list_for_task(task.id)
    assert len(approvals) == 2
