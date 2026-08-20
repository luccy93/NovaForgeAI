"""Pydantic schemas for the Autonomous Software-Engineering layer."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Task ───────────────────────────────────────────────────────────────


class TaskCreate(BaseModel):
    tenant: str
    project: str
    repository: str
    branch: str = "main"
    request: str
    actor: str
    task_type: str = "feature"
    autonomy_level: int = 2
    parent_task_id: Optional[UUID] = None
    workflow_id: Optional[str] = None
    deadline: Optional[datetime] = None
    context: dict[str, Any] = Field(default_factory=dict)


class TaskUpdate(BaseModel):
    status: Optional[str] = None
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    risk_level: Optional[str] = None


class TaskResponse(BaseModel):
    id: UUID
    tenant: str
    project: str
    repository: str
    branch: str
    request: str
    actor: str
    task_type: str
    autonomy_level: int
    risk_level: str
    status: str
    confidence: float
    parent_task_id: Optional[UUID] = None
    workflow_id: Optional[str] = None
    deadline: Optional[datetime] = None
    context: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaskListResponse(BaseModel):
    tasks: list[TaskResponse]
    total: int


# ── Plan ───────────────────────────────────────────────────────────────


class PlanCreate(BaseModel):
    objective: str
    affected_components: list[str] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    test_plan: list[str] = Field(default_factory=list)
    rollback_strategy: str = ""
    estimated_cost: float = 0.0


class PlanResponse(BaseModel):
    id: UUID
    task_id: UUID
    objective: str
    affected_components: list[str]
    files: list[str]
    dependencies: list[str]
    risks: list[str]
    required_tools: list[str]
    test_plan: list[str]
    rollback_strategy: str
    estimated_cost: float
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Patch ──────────────────────────────────────────────────────────────


class PatchCreate(BaseModel):
    diff: str
    file_changes: list[dict[str, Any]] = Field(default_factory=list)
    added_lines: int = 0
    removed_lines: int = 0
    files_changed: int = 0
    reason: str = ""


class PatchResponse(BaseModel):
    id: UUID
    task_id: UUID
    plan_id: Optional[UUID] = None
    diff: str
    file_changes: list[dict[str, Any]]
    added_lines: int
    removed_lines: int
    files_changed: int
    reason: str
    status: str
    validation_errors: list[str]
    syntax_valid: bool
    imports_valid: bool
    security_clean: bool
    commit_sha: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Test Run ───────────────────────────────────────────────────────────


class TestRunResponse(BaseModel):
    id: UUID
    task_id: UUID
    patch_id: Optional[UUID] = None
    test_type: str
    tests_total: int
    tests_passed: int
    tests_failed: int
    tests_skipped: int
    result: str
    duration_ms: int
    output: str
    failures: list[dict[str, Any]]
    iteration: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Review ─────────────────────────────────────────────────────────────


class ReviewResponse(BaseModel):
    id: UUID
    task_id: UUID
    patch_id: Optional[UUID] = None
    reviewer: str
    status: str
    findings: list[dict[str, Any]]
    summary: str
    correctness_score: float
    security_score: float
    maintainability_score: float
    overall_score: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Approval ───────────────────────────────────────────────────────────


class ApprovalDecision(BaseModel):
    decision: str  # approved | rejected
    decided_by: str
    reason: str = ""


class ApprovalResponse(BaseModel):
    id: UUID
    task_id: UUID
    step_id: Optional[UUID] = None
    requested_by: str
    decided_by: Optional[str] = None
    decision: str
    reason: Optional[str] = None
    planned_action: str
    affected_resources: list[str]
    risk_level: str
    diff_summary: Optional[str] = None
    expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Deployment ─────────────────────────────────────────────────────────


class DeploymentCreate(BaseModel):
    environment: str = "staging"
    deployed_by: str = ""


class DeploymentResponse(BaseModel):
    id: UUID
    task_id: UUID
    patch_id: Optional[UUID] = None
    environment: str
    status: str
    commit_sha: Optional[str] = None
    deployed_by: str
    rollback_available: bool
    rollback_sha: Optional[str] = None
    canary_weight: int
    metrics: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Budget ─────────────────────────────────────────────────────────────


class BudgetUpdate(BaseModel):
    max_tokens: Optional[int] = None
    max_tool_calls: Optional[int] = None
    max_files: Optional[int] = None
    max_runtime_s: Optional[int] = None
    max_cost_usd: Optional[float] = None


class BudgetResponse(BaseModel):
    id: UUID
    tenant: str
    max_tokens: int
    max_tool_calls: int
    max_files: int
    max_runtime_s: int
    max_cost_usd: float
    used_tokens: int
    used_tool_calls: int
    used_files: int
    used_runtime_s: int
    used_cost_usd: float
    active_tasks: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Checkpoint ─────────────────────────────────────────────────────────


class CheckpointResponse(BaseModel):
    id: UUID
    task_id: UUID
    phase: str
    state: dict[str, Any]
    can_resume: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Workflow Template ──────────────────────────────────────────────────


class WorkflowTemplateCreate(BaseModel):
    name: str
    description: str = ""
    task_type: str = "feature"
    steps: list[dict[str, Any]] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    model: str = "gpt-4o"
    autonomy_level: int = 2
    max_iterations: int = 5
    timeout_s: int = 1800
    cost_budget_usd: float = 10.0


class WorkflowTemplateResponse(BaseModel):
    id: UUID
    name: str
    description: str
    task_type: str
    steps: list[dict[str, Any]]
    permissions: list[str]
    required_tools: list[str]
    model: str
    autonomy_level: int
    max_iterations: int
    timeout_s: int
    cost_budget_usd: float
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
