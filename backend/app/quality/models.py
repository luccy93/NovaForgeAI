"""AI Software Quality Engine -- Database Models (Volume 48)."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from app.core.database import Base, TimestampMixin


class QualityReview(Base, TimestampMixin):
    __tablename__ = "quality_reviews"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False)
    repo_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    review_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="file"
    )  # file/commit/branch/pr/release/patch
    target_ref: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="queued"
    )  # queued/analyzing/completed/failed/cancelled/blocked
    mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default="standard"
    )  # quick/standard/deep/security/performance/release
    prompt_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default="1.0"
    )
    model_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    total_findings: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    critical_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    high_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    medium_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    low_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    info_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quality_scores: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    gate_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    triggered_by: Mapped[str] = mapped_column(
        String(64), nullable=False, default="system"
    )
    metadata_extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_quality_reviews_tenant", "tenant"),
        Index("ix_quality_reviews_repo", "repo_id"),
        Index("ix_quality_reviews_status", "status"),
        Index("ix_quality_reviews_tenant_repo", "tenant", "repo_id"),
    )


class QualityReviewRun(Base, TimestampMixin):
    __tablename__ = "quality_review_runs"

    review_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("quality_reviews.id", ondelete="CASCADE"), nullable=True
    )
    analyzer_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )  # pending/running/completed/failed
    findings_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_quality_review_runs_review", "review_id"),
        Index("ix_quality_review_runs_analyzer", "analyzer_name"),
    )


class QualityFinding(Base, TimestampMixin):
    __tablename__ = "quality_findings"

    review_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("quality_reviews.id", ondelete="CASCADE"), nullable=True
    )
    tenant: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # correctness/security/reliability/performance/maintainability/architecture/testing/api_compat/database/dependency/observability/documentation
    severity: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # critical/high/medium/low/info
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    line_start: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    line_end: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    symbol: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    rule_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    source: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # sast/sca/ai_review/code_smell/test/integration
    finding_hash: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="open"
    )  # open/acknowledged/in_progress/fixed/verified/false_positive/risk_accepted/reopened
    provenance: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    suggestion: Mapped[str] = mapped_column(Text, nullable=False, default="")
    diff_context: Mapped[str] = mapped_column(Text, nullable=False, default="")

    __table_args__ = (
        Index("ix_quality_findings_review", "review_id"),
        Index("ix_quality_findings_tenant", "tenant"),
        Index("ix_quality_findings_category", "category"),
        Index("ix_quality_findings_severity", "severity"),
        Index("ix_quality_findings_status", "status"),
        Index("ix_quality_findings_hash", "finding_hash"),
        Index("ix_quality_findings_file", "file_path"),
    )


class QualityBaseline(Base, TimestampMixin):
    __tablename__ = "quality_baselines"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False)
    repo_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    name: Mapped[str] = mapped_column(String(128), nullable=False, default="default")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    prompt_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default="1.0"
    )
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")

    __table_args__ = (
        Index("ix_quality_baselines_tenant", "tenant"),
        Index("ix_quality_baselines_repo", "repo_id"),
        Index("ix_quality_baselines_tenant_repo", "tenant", "repo_id"),
    )


class QualityGate(Base, TimestampMixin):
    __tablename__ = "quality_gates"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False)
    repo_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    gate_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="merge"
    )  # merge/release/deploy
    rules: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    block_on_failure: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    __table_args__ = (
        Index("ix_quality_gates_tenant", "tenant"),
        Index("ix_quality_gates_repo", "repo_id"),
    )


class QualityGateEvaluation(Base, TimestampMixin):
    __tablename__ = "quality_gate_evaluations"

    review_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("quality_reviews.id", ondelete="CASCADE"), nullable=True
    )
    gate_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("quality_gates.id", ondelete="SET NULL"), nullable=True
    )
    verdict: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pass"
    )  # pass/fail/block
    triggered_by: Mapped[str] = mapped_column(
        String(64), nullable=False, default="system"
    )
    evaluated_rules: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    failures: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("ix_quality_gate_evaluations_review", "review_id"),
        Index("ix_quality_gate_evaluations_verdict", "verdict"),
    )


class QualityReviewFeedback(Base, TimestampMixin):
    __tablename__ = "quality_review_feedback"

    finding_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("quality_findings.id", ondelete="CASCADE"), nullable=True
    )
    developer_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # accept/dismiss/comment/false_positive/request_fix/clarification
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")

    __table_args__ = (
        Index("ix_quality_review_feedback_finding", "finding_id"),
        Index("ix_quality_review_feedback_action", "action"),
    )


class QualityTestAnalysis(Base, TimestampMixin):
    __tablename__ = "quality_test_analysis"

    review_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("quality_reviews.id", ondelete="CASCADE"), nullable=True
    )
    repo_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    files_analyzed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tests_added: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tests_modified: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tests_removed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    coverage_delta: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    assertion_quality_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )
    gaps_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    edge_cases_missing: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    flaky_suspects: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_quality_test_analysis_review", "review_id"),
    )


class QualityReviewVersion(Base, TimestampMixin):
    __tablename__ = "quality_review_versions"

    version: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    prompt_hash: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    model_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    tools: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    retrieval_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default=""
    )
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class QualityRemediation(Base, TimestampMixin):
    __tablename__ = "quality_remediations"

    finding_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("quality_findings.id", ondelete="SET NULL"), nullable=True
    )
    review_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("quality_reviews.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="proposed"
    )  # proposed/validated/applied/verified/failed
    patch_diff: Mapped[str] = mapped_column(Text, nullable=False, default="")
    validation_results: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    verification_results: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict
    )
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    generated_by: Mapped[str] = mapped_column(
        String(64), nullable=False, default="ai"
    )

    __table_args__ = (
        Index("ix_quality_remediations_finding", "finding_id"),
        Index("ix_quality_remediations_review", "review_id"),
        Index("ix_quality_remediations_status", "status"),
    )


class QualityMetricsHistory(Base, TimestampMixin):
    __tablename__ = "quality_metrics_history"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False)
    repo_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    scores: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    finding_counts: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    coverage: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    gate_pass_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("ix_quality_metrics_history_tenant", "tenant"),
        Index("ix_quality_metrics_history_repo", "repo_id"),
        Index("ix_quality_metrics_history_ts", "timestamp"),
    )


class QualityDuplicationGroup(Base, TimestampMixin):
    __tablename__ = "quality_duplication_groups"

    review_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("quality_reviews.id", ondelete="CASCADE"), nullable=True
    )
    group_hash: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    finding_ids: Mapped[dict] = mapped_column(JSON, nullable=False, default=list)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="low")

    __table_args__ = (
        Index("ix_quality_dup_groups_review", "review_id"),
        Index("ix_quality_dup_groups_hash", "group_hash"),
    )
