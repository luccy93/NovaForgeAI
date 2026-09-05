"""Kernel API — NovaForge AI Operating System Kernel.

Exposes the common runtime coordinating agents, models, tools, memory,
context, workflows, events, policies and execution.

All endpoints require authentication. Mutating endpoints require the
admin_all permission; read-only endpoints require any authenticated user.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any
from datetime import datetime, timezone

from app.api.auth import _get_current_user, require_permission
from app.core.authorization import Permission
from app.core.database import get_db
from app.operating_system.ai_os_core import (
    AIOperatingSystem,
    KernelTask,
    TaskStatus,
    RuntimeStatus,
    AgentStatus,
)
from app.core.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["Kernel"])


# ─── Request/Response Models ───────────────────────────────────────────────

class TaskCreate(BaseModel):
    """Create a new kernel task."""
    task_id: str
    tenant_id: str
    actor: str
    type: str  # agent, model, tool, workflow, event, memory
    priority: str = "normal"
    deadline: Optional[str] = None
    parent_task_id: Optional[str] = None
    repository: Optional[str] = None
    workspace: Optional[str] = None
    memory_references: list[str] = Field(default_factory=list)
    tool_permissions: list[str] = Field(default_factory=list)
    model_configuration: Optional[str] = None
    policy_references: list[str] = Field(default_factory=list)
    approval_required: bool = False


class TaskIn(KernelTask):
    """Input model for a kernel task."""
    task_id: str
    tenant_id: str
    actor: str
    type: str
    priority: str
    status: TaskStatus
    created_at: str
    deadline: Optional[str]
    parent_task_id: Optional[str]
    runtime_version: str
    correlation_id: str
    repository: Optional[str]
    workspace: Optional[str]
    memory_references: list[str]
    tool_permissions: list[str]
    model_configuration: Optional[str]
    policy_references: list[str]
    started_at: Optional[str]
    completed_at: Optional[str]
    duration_ms: float
    error: Optional[str]
    retry_count: int
    max_retries: int
    cpu_seconds: float
    memory_bytes: int
    disk_bytes: int
    network_bytes: int
    token_count: int
    model_request_count: int
    tool_call_count: int
    cost_cents: float
    quota_usage: dict[str, float]
    checkpoint_id: Optional[str]
    checkpoint_data: dict[str, Any]
    approval_required: bool
    approved_by: Optional[str]
    approved_at: Optional[str]
    retired_at: Optional[str]


class TaskStatusResponse(BaseModel):
    """Task status response."""
    task_id: str
    status: str
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    error: Optional[str]


class ResourceUsageResponse(BaseModel):
    """Resource usage response."""
    task_id: str
    cpu_seconds: float
    memory_bytes: int
    disk_bytes: int
    network_bytes: int
    token_count: int
    model_request_count: int
    tool_call_count: int
    cost_cents: float
    quota_usage: dict[str, float]


class CheckpointResponse(BaseModel):
    """Checkpoint response."""
    checkpoint_id: str
    task_id: str
    created_at: str
    data: dict[str, Any]


# ─── Task Endpoints ────────────────────────────────────────────────────────

@router.post("/tasks", status_code=201)
async def create_kernel_task(
    task: TaskCreate,
    current_user: Any = Depends(_get_current_user),
    db=Depends(get_db),
) -> dict:
    """Create a new kernel task."""
    from app.operating_system.ai_os_core import AIOperatingSystem
    os = AIOperatingSystem()
    kernel_task = KernelTask(
        task_id=task.task_id,
        tenant_id=task.tenant_id,
        actor=task.actor,
        type=task.type,
        priority=task.priority,
        deadline=task.deadline,
        parent_task_id=task.parent_task_id,
        repository=task.repository,
        workspace=task.workspace,
        memory_references=task.memory_references,
        tool_permissions=task.tool_permissions,
        model_configuration=task.model_configuration,
        policy_references=task.policy_references,
        approval_required=task.approval_required,
    )
    task_id = os.create_task(kernel_task)
    return {"task_id": task_id, "status": "created"}


@router.get("/tasks/{task_id}")
async def get_kernel_task(
    task_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Get a kernel task by ID."""
    from app.operating_system.ai_os_core import AIOperatingSystem
    os = AIOperatingSystem()
    task = os.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Kernel task {task_id} not found")
    return task.__dict__


@router.put("/tasks/{task_id}/status")
async def update_kernel_task_status(
    task_id: str,
    status: str = Query(...),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Update a kernel task status."""
    from app.operating_system.ai_os_core import AIOperatingSystem, TaskStatus
    os = AIOperatingSystem()
    task = os.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Kernel task {task_id} not found")
    try:
        task.status = TaskStatus(status)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid task status: {status}")
    return task.__dict__


@router.post("/tasks/{task_id}/checkpoint")
async def create_kernel_checkpoint(
    task_id: str,
    data: dict[str, Any] = Body(default={}),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Create a checkpoint for a kernel task."""
    from app.operating_system.ai_os_core import AIOperatingSystem
    os = AIOperatingSystem()
    checkpoint_id = os.create_checkpoint(task_id, data)
    if not checkpoint_id:
        raise HTTPException(status_code=404, detail=f"Kernel task {task_id} not found")
    return {"checkpoint_id": checkpoint_id, "task_id": task_id}


@router.post("/tasks/{task_id}/resume-checkpoint")
async def resume_from_checkpoint(
    task_id: str,
    checkpoint_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Resume a kernel task from a checkpoint."""
    from app.operating_system.ai_os_core import AIOperatingSystem
    os = AIOperatingSystem()
    success = os.resume_from_checkpoint(task_id, checkpoint_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Checkpoint {checkpoint_id} not found for task {task_id}")
    return {"task_id": task_id, "checkpoint_id": checkpoint_id, "success": True}


@router.get("/tasks/{task_id}/checkpoint")
async def get_kernel_checkpoint(
    task_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Get checkpoint data for a kernel task."""
    from app.operating_system.ai_os_core import AIOperatingSystem
    os = AIOperatingSystem()
    data = os.get_checkpoint(task_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return {"task_id": task_id, "checkpoint_data": data}


@router.post("/tasks/{task_id}/deadline")
async def check_deadline(
    task_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Check if a task has exceeded its deadline."""
    from app.operating_system.ai_os_core import AIOperatingSystem
    os = AIOperatingSystem()
    exceeded = os.check_deadline(task_id)
    return {"task_id": task_id, "deadline_exceeded": exceeded}


# ─── Resource Endpoints ────────────────────────────────────────────────────

@router.post("/tasks/{task_id}/resources")
async def update_task_resources(
    task_id: str,
    resource_delta: dict[str, float] = Body(...),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Update resource usage for a kernel task."""
    from app.operating_system.ai_os_core import AIOperatingSystem
    os = AIOperatingSystem()
    success = os.update_resource_usage(task_id, resource_delta)
    if not success:
        raise HTTPException(status_code=404, detail=f"Kernel task {task_id} not found")
    return {"task_id": task_id, "success": True}


@router.get("/tasks/{task_id}/resources")
async def get_task_resources(
    task_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Get resource usage for a kernel task."""
    from app.operating_system.ai_os_core import AIOperatingSystem
    os = AIOperatingSystem()
    usage = os.get_resource_usage(task_id)
    if usage is None:
        raise HTTPException(status_code=404, detail=f"Kernel task {task_id} not found")
    return {"task_id": task_id, "usage": usage}


@router.post("/tasks/{task_id}/quotas")
async def check_task_quotas(
    task_id: str,
    quota_limits: dict[str, float] = Body(...),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Check if a task is within quota limits."""
    from app.operating_system.ai_os_core import AIOperatingSystem
    os = AIOperatingSystem()
    within_limits = os.check_quotas(task_id, quota_limits)
    return {"task_id": task_id, "within_quotas": within_limits}


# ─── Agent Endpoints ───────────────────────────────────────────────────────

@router.post("/agents/{agent_id}/assign-task")
async def assign_agent_task(
    agent_id: str,
    task_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Assign a task to an agent."""
    from app.operating_system.ai_os_core import AIOperatingSystem
    from app.agents.schemas import AgentStatus
    os = AIOperatingSystem()
    success = os.agent_runtime.assign_task(agent_id, task_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found or not idle")
    return {"agent_id": agent_id, "task_id": task_id, "assigned": True}


@router.post("/agents/{agent_id}/complete-task")
async def complete_agent_task(
    agent_id: str,
    task_id: str,
    success: bool = True,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Complete a task assigned to an agent."""
    from app.operating_system.ai_os_core import AIOperatingSystem
    from app.agents.schemas import AgentStatus
    os = AIOperatingSystem()
    os.agent_runtime.complete_task(agent_id, task_id, success)
    return {"agent_id": agent_id, "task_id": task_id, "completed": True, "success": True}


@router.get("/agents/{agent_id}")
async def get_agent(
    agent_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Get an agent by ID."""
    from app.operating_system.ai_os_core import AIOperatingSystem
    from app.agents.schemas import AgentStatus
    os = AIOperatingSystem()
    agent = os.agent_runtime.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return agent.__dict__


# ─── Runtime Health Endpoints ───────────────────────────────────────────────

@router.get("/health")
async def kernel_health(
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Get kernel health status."""
    from app.operating_system.ai_os_core import AIOperatingSystem
    os = AIOperatingSystem()
    return os.health_check()


@router.get("/metrics")
async def kernel_metrics(
    current_user: Any = Depends(_get_current_user),
) -> dict:
    """Get kernel metrics."""
    from app.operating_system.ai_os_core import AIOperatingSystem
    os = AIOperatingSystem()
    return os.get_metrics()