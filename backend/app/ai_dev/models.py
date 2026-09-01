"""AI Developer Experience models — Volume 67 Commit 1.

C1 tables: code_workspaces, code_patches, code_reviews,
code_review_findings, code_test_runs, code_ai_usage.
C2 tables (0035): code_agent_runs, code_agent_plans,
code_agent_checkpoints, code_agent_feedbacks, code_benchmarks,
code_benchmark_runs.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ─── 1. CodeWorkspace ──────────────────────────────────────────────────────


class CodeWorkspace(Base, TimestampMixin):
    __tablename__ = "code_workspaces"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    branch: Mapped[str] = mapped_column(String(255), nullable=False, default="main")
    commit_sha: Mapped[Optional[str]] = mapped_column(String(40))
    owner: Mapped[Optional[str]] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    classification: Mapped[str] = mapped_column(
        String(30), nullable=False, default="INTERNAL"
    )
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant", "name", name="uq_code_workspaces_tenant_name"),
    )


# ─── 2. CodePatch ──────────────────────────────────────────────────────────


class CodePatch(Base, TimestampMixin):
    __tablename__ = "code_patches"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    workspace_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), index=True)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    branch: Mapped[str] = mapped_column(String(255), nullable=False, default="main")
    base_commit_sha: Mapped[Optional[str]] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="ai")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="CREATED")
    files: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    diffs: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    rollback_diffs: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    author: Mapped[Optional[str]] = mapped_column(String(64))
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    rolled_back_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    error: Mapped[Optional[str]] = mapped_column(Text)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        Index("ix_code_patches_workspace", "workspace_id"),
    )


# ─── 3. CodeReview ─────────────────────────────────────────────────────────


class CodeReview(Base, TimestampMixin):
    __tablename__ = "code_reviews"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    branch: Mapped[str] = mapped_column(String(255), nullable=False, default="main")
    commit_sha: Mapped[Optional[str]] = mapped_column(String(40))
    patch_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True))
    workspace_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True))
    model: Mapped[Optional[str]] = mapped_column(String(100))
    rules_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    summary: Mapped[Optional[str]] = mapped_column(Text)
    context_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    created_by: Mapped[Optional[str]] = mapped_column(String(64))

    __table_args__ = (
        Index("ix_code_reviews_patch", "patch_id"),
    )


# ─── 4. CodeReviewFinding ──────────────────────────────────────────────────


class CodeReviewFinding(Base, TimestampMixin):
    __tablename__ = "code_review_findings"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    review_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("code_reviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    line_start: Mapped[Optional[int]] = mapped_column(Integer)
    line_end: Mapped[Optional[int]] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="MEDIUM")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    evidence: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    dismissed_by: Mapped[Optional[str]] = mapped_column(String(64))
    dismissed_reason: Mapped[Optional[str]] = mapped_column(Text)
    dismissed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


# ─── 5. CodeTestRun ────────────────────────────────────────────────────────


class CodeTestRun(Base, TimestampMixin):
    __tablename__ = "code_test_runs"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    branch: Mapped[str] = mapped_column(String(255), nullable=False, default="main")
    commit_sha: Mapped[Optional[str]] = mapped_column(String(40))
    patch_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="GENERATED")
    framework: Mapped[Optional[str]] = mapped_column(String(50))
    command: Mapped[Optional[str]] = mapped_column(Text)
    test_plan: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    test_results: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    logs: Mapped[Optional[str]] = mapped_column(Text)
    failures_analysis: Mapped[Optional[str]] = mapped_column(Text)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    ci_pipeline_run_id: Mapped[Optional[str]] = mapped_column(String(64))
    model: Mapped[Optional[str]] = mapped_column(String(100))
    created_by: Mapped[Optional[str]] = mapped_column(String(64))

    __table_args__ = (
        Index("ix_code_test_runs_patch", "patch_id"),
    )


# ─── 6. CodeAIUsage ────────────────────────────────────────────────────────


class CodeAIUsage(Base, TimestampMixin):
    __tablename__ = "code_ai_usage"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(64))
    request_id: Mapped[Optional[str]] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String(100))
    model_provider: Mapped[Optional[str]] = mapped_column(String(50))
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_cents: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)
    repository_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True))
    patch_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    test_cycles: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("ix_code_ai_usage_tenant_action", "tenant", "action"),
    )


# ─── 7. CodeAgentRun (C2) ──────────────────────────────────────────────────


class CodeAgentRun(Base, TimestampMixin):
    __tablename__ = "code_agent_runs"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # refactor|migrate|seed|review|fix|release
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    goal: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ENQUEUED")
    worker_id: Mapped[Optional[str]] = mapped_column(String(64))
    model: Mapped[Optional[str]] = mapped_column(String(100))
    root_run_id: Mapped[Optional[str]] = mapped_column(String(64))
    throttle: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    budget_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=120000)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    start_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    attempted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    result: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    checkpoint_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        Index("ix_code_agent_runs_status", "status"),
        Index("ix_code_agent_runs_tenant_status", "tenant", "status"),
    )


# ─── 8. CodeAgentPlan (C2) ─────────────────────────────────────────────────


class CodeAgentPlan(Base, TimestampMixin):
    __tablename__ = "code_agent_plans"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("code_agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plan_type: Mapped[str] = mapped_column(String(30), nullable=False, default="PLAN")
    name: Mapped[str] = mapped_column(String(128), default="Plan")
    steps: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    rationale: Mapped[Optional[str]] = mapped_column(Text)
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approved_by: Mapped[Optional[str]] = mapped_column(String(64))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    rejected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text)


# ─── 9. CodeAgentCheckpoint (C2) ───────────────────────────────────────────


class CodeAgentCheckpoint(Base, TimestampMixin):
    __tablename__ = "code_agent_checkpoints"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("code_agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    state: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint(
            "agent_run_id", "sequence", name="uq_code_agent_checkpoints_run_seq"
        ),
    )


# ─── 10. CodeAgentFeedback (C2) ────────────────────────────────────────────


class CodeAgentFeedback(Base, TimestampMixin):
    __tablename__ = "code_agent_feedbacks"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("code_agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    feedback_type: Mapped[str] = mapped_column(String(20), nullable=False, default="CONTINUE")
    message: Mapped[Optional[str]] = mapped_column(Text)
    patch_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True))
    checkpoint_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True))
    created_by: Mapped[Optional[str]] = mapped_column(String(64))


# ─── 11. CodeBenchmark (C2) ────────────────────────────────────────────────


class CodeBenchmark(Base, TimestampMixin):
    __tablename__ = "code_benchmarks"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    dataset_spec: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="CREATED")
    best_eval_id: Mapped[Optional[str]] = mapped_column(String(64))
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant", "name", name="uq_code_benchmarks_tenant_name"),
    )


# ─── 12. CodeBenchmarkRun (C2) ─────────────────────────────────────────────


class CodeBenchmarkRun(Base, TimestampMixin):
    __tablename__ = "code_benchmark_runs"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    benchmark_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("code_benchmarks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    eval_id: Mapped[Optional[str]] = mapped_column(String(64))
    commit_sha: Mapped[Optional[str]] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="RUNNING")
    model: Mapped[Optional[str]] = mapped_column(String(100))
    system_prompt: Mapped[Optional[str]] = mapped_column(Text)
    budget_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer)
    cost_cents: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    score: Mapped[Optional[float]] = mapped_column(Float)
    results: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    patches: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    took_ms: Mapped[Optional[int]] = mapped_column(Integer)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))