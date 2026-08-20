"""REST API for the Autonomous Software-Engineering layer (Volume 45)."""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.automation.schemas import (
    ApprovalDecision,
    ApprovalResponse,
    BudgetResponse,
    BudgetUpdate,
    CheckpointResponse,
    DeploymentCreate,
    DeploymentResponse,
    PatchResponse,
    PlanCreate,
    PlanResponse,
    ReviewResponse,
    TaskCreate,
    TaskListResponse,
    TaskResponse,
    TestRunResponse,
    WorkflowTemplateCreate,
    WorkflowTemplateResponse,
)
from app.automation.task_service import TaskService
from app.automation.plan_service import PlanService
from app.automation.patch_service import PatchService
from app.automation.test_service import TestService
from app.automation.review_service import ReviewService
from app.automation.approval_service import ApprovalService
from app.automation.deployment_service import DeploymentService
from app.automation.budget_service import BudgetService
from app.automation.engine_orchestrator import EngineOrchestrator
from app.automation.security_gate import SecurityGate
from app.automation.models import AutomationWorkflowTemplate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/automation", tags=["Autonomous Engineering"])


# ── Tasks ──────────────────────────────────────────────────────────────


@router.post("/tasks", response_model=TaskResponse, status_code=201)
async def create_task(data: TaskCreate, db: AsyncSession = Depends(get_db)):
    svc = TaskService(db)
    task = await svc.create(data)
    await db.commit()
    return task


@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks(
    tenant: Optional[str] = None,
    status: Optional[str] = None,
    repository: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    svc = TaskService(db)
    tasks, total = await svc.list_tasks(tenant=tenant, status=status, repository=repository, limit=limit, offset=offset)
    return TaskListResponse(tasks=tasks, total=total)


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = TaskService(db)
    task = await svc.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@router.post("/tasks/{task_id}/run", response_model=dict)
async def run_task(task_id: UUID, db: AsyncSession = Depends(get_db)):
    orchestrator = EngineOrchestrator(db)
    try:
        result = await orchestrator.run_task(task_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return result


@router.post("/tasks/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(task_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = TaskService(db)
    try:
        task = await svc.cancel(task_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return task


@router.get("/tasks/{task_id}/checkpoints", response_model=list[CheckpointResponse])
async def get_checkpoints(task_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = TaskService(db)
    cps = await svc.get_checkpoints(task_id)
    return cps


# ── Plans ──────────────────────────────────────────────────────────────


@router.post("/tasks/{task_id}/plans", response_model=PlanResponse, status_code=201)
async def create_plan(task_id: UUID, data: PlanCreate, db: AsyncSession = Depends(get_db)):
    svc = PlanService(db)
    plan = await svc.create_plan(task_id, data)
    await db.commit()
    return plan


@router.get("/tasks/{task_id}/plans/latest", response_model=PlanResponse)
async def get_latest_plan(task_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = PlanService(db)
    plan = await svc.get_for_task(task_id)
    if not plan:
        raise HTTPException(status_code=404, detail="no plan found")
    return plan


@router.post("/plans/{plan_id}/approve", response_model=PlanResponse)
async def approve_plan(plan_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = PlanService(db)
    try:
        plan = await svc.approve_plan(plan_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return plan


@router.post("/plans/{plan_id}/validate")
async def validate_plan(plan_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = PlanService(db)
    try:
        result = await svc.validate_plan(plan_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


# ── Patches ────────────────────────────────────────────────────────────


@router.get("/tasks/{task_id}/patches", response_model=list[PatchResponse])
async def list_patches(task_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = PatchService(db)
    return await svc.list_for_task(task_id)


@router.get("/patches/{patch_id}", response_model=PatchResponse)
async def get_patch(patch_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = PatchService(db)
    patch = await svc.get(patch_id)
    if not patch:
        raise HTTPException(status_code=404, detail="patch not found")
    return patch


@router.post("/patches/{patch_id}/validate")
async def validate_patch(patch_id: UUID, db: AsyncSession = Depends(get_db)):
    patch_svc = PatchService(db)
    gate = SecurityGate()
    patch = await patch_svc.get(patch_id)
    if not patch:
        raise HTTPException(status_code=404, detail="patch not found")
    sec_result = gate.validate_patch(patch.diff, patch.file_changes)
    await patch_svc.validate(
        patch_id,
        syntax_valid=True,
        imports_valid=True,
        security_clean=not sec_result["blocks_delivery"],
        errors=[f["message"] for f in sec_result["findings"]],
    )
    await db.commit()
    return {"validation": sec_result, "patch_status": "validated" if not sec_result["blocks_delivery"] else "rejected"}


@router.get("/patches/{patch_id}/diff")
async def get_patch_diff(patch_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = PatchService(db)
    diff = await svc.get_diff(patch_id)
    if diff is None:
        raise HTTPException(status_code=404, detail="patch not found")
    return {"diff": diff}


# ── Test Runs ──────────────────────────────────────────────────────────


@router.get("/tasks/{task_id}/tests", response_model=list[TestRunResponse])
async def list_test_runs(task_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = TestService(db)
    return await svc.list_for_task(task_id)


# ── Reviews ────────────────────────────────────────────────────────────


@router.get("/tasks/{task_id}/reviews", response_model=list[ReviewResponse])
async def list_reviews(task_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = ReviewService(db)
    return await svc.list_for_task(task_id)


# ── Approvals ──────────────────────────────────────────────────────────


@router.get("/tasks/{task_id}/approvals", response_model=list[ApprovalResponse])
async def list_approvals(task_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = ApprovalService(db)
    return await svc.list_for_task(task_id)


@router.post("/approvals/{approval_id}/decide", response_model=ApprovalResponse)
async def decide_approval(approval_id: UUID, data: ApprovalDecision, db: AsyncSession = Depends(get_db)):
    svc = ApprovalService(db)
    try:
        approval = await svc.decide(approval_id, data.decision, data.decided_by, data.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return approval


# ── Deployments ────────────────────────────────────────────────────────


@router.post("/tasks/{task_id}/deploy", response_model=DeploymentResponse, status_code=201)
async def create_deployment(task_id: UUID, data: DeploymentCreate, db: AsyncSession = Depends(get_db)):
    svc = DeploymentService(db)
    dep = await svc.create_deployment(task_id, data.environment, data.deployed_by)
    await db.commit()
    return dep


@router.get("/tasks/{task_id}/deployments", response_model=list[DeploymentResponse])
async def list_deployments(task_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = DeploymentService(db)
    return await svc.list_for_task(task_id)


@router.post("/deployments/{deployment_id}/rollback", response_model=DeploymentResponse)
async def rollback_deployment(deployment_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = DeploymentService(db)
    try:
        dep = await svc.rollback(deployment_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return dep


@router.post("/deployments/{deployment_id}/canary", response_model=DeploymentResponse)
async def set_canary(deployment_id: UUID, weight: int = Query(0, ge=0, le=100), db: AsyncSession = Depends(get_db)):
    svc = DeploymentService(db)
    try:
        dep = await svc.set_canary(deployment_id, weight)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return dep


@router.post("/deployments/{deployment_id}/canary/expand", response_model=DeploymentResponse)
async def expand_canary(deployment_id: UUID, increment: int = Query(10, ge=1, le=50), db: AsyncSession = Depends(get_db)):
    svc = DeploymentService(db)
    try:
        dep = await svc.expand_canary(deployment_id, increment)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return dep


@router.get("/deployments/{deployment_id}/rollback-check")
async def check_rollback(deployment_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = DeploymentService(db)
    try:
        return await svc.should_rollback(deployment_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Budgets ────────────────────────────────────────────────────────────


@router.get("/budgets/{tenant}", response_model=BudgetResponse)
async def get_budget(tenant: str, db: AsyncSession = Depends(get_db)):
    svc = BudgetService(db)
    return await svc.get_or_create(tenant)


@router.put("/budgets/{tenant}", response_model=BudgetResponse)
async def update_budget(tenant: str, data: BudgetUpdate, db: AsyncSession = Depends(get_db)):
    svc = BudgetService(db)
    budget = await svc.update_limits(
        tenant,
        max_tokens=data.max_tokens,
        max_tool_calls=data.max_tool_calls,
        max_files=data.max_files,
        max_runtime_s=data.max_runtime_s,
        max_cost_usd=data.max_cost_usd,
    )
    await db.commit()
    return budget


@router.get("/budgets/{tenant}/check")
async def check_budget(tenant: str, db: AsyncSession = Depends(get_db)):
    svc = BudgetService(db)
    return await svc.check_budget(tenant)


@router.get("/budgets/{tenant}/summary")
async def budget_summary(tenant: str, db: AsyncSession = Depends(get_db)):
    svc = BudgetService(db)
    return await svc.get_usage_summary(tenant)


# ── Workflow Templates ─────────────────────────────────────────────────


@router.post("/templates", response_model=WorkflowTemplateResponse, status_code=201)
async def create_template(data: WorkflowTemplateCreate, db: AsyncSession = Depends(get_db)):
    tmpl = AutomationWorkflowTemplate(
        name=data.name,
        description=data.description,
        task_type=data.task_type,
        steps=data.steps,
        permissions=data.permissions,
        required_tools=data.required_tools,
        model=data.model,
        autonomy_level=data.autonomy_level,
        max_iterations=data.max_iterations,
        timeout_s=data.timeout_s,
        cost_budget_usd=data.cost_budget_usd,
    )
    db.add(tmpl)
    await db.commit()
    await db.refresh(tmpl)
    return tmpl


@router.get("/templates")
async def list_templates(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    res = await db.execute(select(AutomationWorkflowTemplate).where(AutomationWorkflowTemplate.enabled == True))
    return list(res.scalars().all())


# ── Security ───────────────────────────────────────────────────────────


@router.post("/security/scan")
async def scan_code(diff: str = "", file_changes: Optional[list] = None):
    gate = SecurityGate()
    return gate.validate_patch(diff, file_changes or [])
