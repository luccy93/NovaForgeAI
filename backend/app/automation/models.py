"""Autonomous Software-Engineering database models (Volume 45).

Stores the complete lifecycle of AI-driven engineering tasks: intake,
planning, patches, test runs, reviews, approvals, deployments, budgets
and checkpoints.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.core.database import Base, TimestampMixin


# ── Enums ──────────────────────────────────────────────────────────────


class TaskStatus(str):
    QUEUED = "queued"
    ANALYZING = "analyzing"
    PLANNING = "planning"
    APPROVAL_REQUIRED = "approval_required"
    IMPLEMENTING = "implementing"
    TESTING = "testing"
    REVIEWING = "reviewing"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ROLLED_BACK = "rolled_back"


class TaskType(str):
    BUG = "bug"
    FEATURE = "feature"
    REFACTOR = "refactor"
    SECURITY = "security"
    PERFORMANCE = "performance"
    DOCUMENTATION = "documentation"
    TESTING = "testing"
    DEPENDENCY = "dependency"
    ARCHITECTURE = "architecture"
    INCIDENT_REMEDIATION = "incident_remediation"


class AutonomyLevel(int):
    L0 = 0
    L1 = 1
    L2 = 2
    L3 = 3
    L4 = 4
    L5 = 5


class RiskLevel(str):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PatchStatus(str):
    DRAFT = "draft"
    VALIDATED = "validated"
    APPLIED = "applied"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


class ReviewStatus(str):
    PENDING = "pending"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    REJECTED = "rejected"


class DeploymentStatus(str):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class ApprovalDecision(str):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class TestResult(str):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


# ── Models ──────────────────────────────────────────────────────────────


class AutomationTask(Base, TimestampMixin):
    """Central entity tracking an autonomous engineering task."""

    __tablename__ = "automation_tasks"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project: Mapped[str] = mapped_column(String(128), nullable=False)
    repository: Mapped[str] = mapped_column(String(256), nullable=False)
    branch: Mapped[str] = mapped_column(String(256), default="main", nullable=False)
    request: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    autonomy_level: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), default=RiskLevel.LOW, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=TaskStatus.QUEUED, nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String(32), default=TaskType.FEATURE, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    workflow_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    workflow_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("workflow_versions.id", ondelete="SET NULL"), nullable=True, index=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    context: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    result: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_automation_tasks_tenant_status", "tenant", "status"),
        Index("ix_automation_tasks_repository", "repository"),
    )


class AutomationPlan(Base, TimestampMixin):
    """Machine-readable implementation plan for a task."""

    __tablename__ = "automation_plans"

    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("automation_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    affected_components: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    files: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    dependencies: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    risks: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    required_tools: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    test_plan: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    rollback_strategy: Mapped[str] = mapped_column(Text, nullable=False, default="")
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)

    __table_args__ = (Index("ix_automation_plans_task", "task_id"),)


class AutomationStep(Base, TimestampMixin):
    """Individual step within a plan."""

    __tablename__ = "automation_steps"

    plan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("automation_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    step_type: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    tool: Mapped[str | None] = mapped_column(String(64), nullable=True)
    inputs: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    result: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), default=RiskLevel.LOW, nullable=False)
    requires_approval: Mapped[bool] = mapped_column(default=False, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (Index("ix_automation_steps_plan", "plan_id"),)


class AutomationPatch(Base, TimestampMixin):
    """Generated code change (unified diff + metadata)."""

    __tablename__ = "automation_patches"

    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("automation_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("automation_plans.id", ondelete="SET NULL"), nullable=True
    )
    diff: Mapped[str] = mapped_column(Text, nullable=False)
    file_changes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    added_lines: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    removed_lines: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    files_changed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), default=PatchStatus.DRAFT, nullable=False)
    validation_errors: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    syntax_valid: Mapped[bool] = mapped_column(default=False, nullable=False)
    imports_valid: Mapped[bool] = mapped_column(default=False, nullable=False)
    security_clean: Mapped[bool] = mapped_column(default=False, nullable=False)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (Index("ix_automation_patches_task", "task_id"),)


class AutomationTestRun(Base, TimestampMixin):
    """Record of test execution against generated code."""

    __tablename__ = "automation_test_runs"

    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("automation_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    patch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("automation_patches.id", ondelete="SET NULL"), nullable=True
    )
    test_type: Mapped[str] = mapped_column(String(32), nullable=False)
    tests_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tests_passed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tests_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tests_skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    result: Mapped[str] = mapped_column(String(16), default=TestResult.PASSED, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output: Mapped[str] = mapped_column(Text, nullable=False, default="")
    failures: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    iteration: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (Index("ix_automation_test_runs_task", "task_id"),)


class AutomationReview(Base, TimestampMixin):
    """Independent code review of generated changes."""

    __tablename__ = "automation_reviews"

    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("automation_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    patch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("automation_patches.id", ondelete="SET NULL"), nullable=True
    )
    reviewer: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=ReviewStatus.PENDING, nullable=False)
    findings: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    correctness_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    security_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    maintainability_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    overall_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    __table_args__ = (Index("ix_automation_reviews_task", "task_id"),)


class AutomationApproval(Base, TimestampMixin):
    """Human or policy approval gate."""

    __tablename__ = "automation_approvals"

    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("automation_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("automation_steps.id", ondelete="SET NULL"), nullable=True
    )
    requested_by: Mapped[str] = mapped_column(String(64), nullable=False)
    decided_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision: Mapped[str] = mapped_column(String(16), default=ApprovalDecision.PENDING, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    planned_action: Mapped[str] = mapped_column(Text, nullable=False, default="")
    affected_resources: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), default=RiskLevel.LOW, nullable=False)
    diff_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_automation_approvals_task", "task_id"),)


class AutomationDeployment(Base, TimestampMixin):
    """Deployment record for a validated patch."""

    __tablename__ = "automation_deployments"

    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("automation_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    patch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("automation_patches.id", ondelete="SET NULL"), nullable=True
    )
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=DeploymentStatus.PENDING, nullable=False)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    deployed_by: Mapped[str] = mapped_column(String(64), nullable=False)
    rollback_available: Mapped[bool] = mapped_column(default=True, nullable=False)
    rollback_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    canary_weight: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (Index("ix_automation_deployments_task", "task_id"),)


class AutomationBudget(Base, TimestampMixin):
    """Per-tenant budget enforcement."""

    __tablename__ = "automation_budgets"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False)
    max_tokens: Mapped[int] = mapped_column(Integer, default=1_000_000, nullable=False)
    max_tool_calls: Mapped[int] = mapped_column(Integer, default=500, nullable=False)
    max_files: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    max_runtime_s: Mapped[int] = mapped_column(Integer, default=3600, nullable=False)
    max_cost_usd: Mapped[float] = mapped_column(Float, default=50.0, nullable=False)
    used_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    used_tool_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    used_files: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    used_runtime_s: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    used_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    active_tasks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index("ix_automation_budgets_tenant", "tenant", unique=True),
    )


class AutomationCheckpoint(Base, TimestampMixin):
    """Recovery checkpoint after critical phases."""

    __tablename__ = "automation_checkpoints"

    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("automation_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    phase: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    can_resume: Mapped[bool] = mapped_column(default=True, nullable=False)

    __table_args__ = (Index("ix_automation_checkpoints_task", "task_id"),)


class AutomationWorkflowTemplate(Base, TimestampMixin):
    """Reusable engineering workflow templates."""

    __tablename__ = "automation_workflow_templates"

    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    task_type: Mapped[str] = mapped_column(String(32), nullable=False)
    steps: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    permissions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    required_tools: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    model: Mapped[str] = mapped_column(String(128), default="gpt-4o", nullable=False)
    autonomy_level: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    max_iterations: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    timeout_s: Mapped[int] = mapped_column(Integer, default=1800, nullable=False)
    cost_budget_usd: Mapped[float] = mapped_column(Float, default=10.0, nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
