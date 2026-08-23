"""Volume 56 — Release Management & Progressive Delivery models.

Additive-only. New tables for release_records, candidates, approvals, gates,
strategies, verifications, feature flags, locks. Reuses delivery artifacts.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from app.core.database import Base, TimestampMixin


class ReleaseStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    VALIDATING = "VALIDATING"
    READY = "READY"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    DEPLOYING = "DEPLOYING"
    CANARY = "CANARY"
    PROGRESSIVE = "PROGRESSIVE"
    PAUSED = "PAUSED"
    PROMOTING = "PROMOTING"
    ROLLED_BACK = "ROLLED_BACK"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ReleaseChannel(str, enum.Enum):
    DEV = "DEV"
    ALPHA = "ALPHA"
    BETA = "BETA"
    STAGING = "STAGING"
    CANARY = "CANARY"
    PRODUCTION = "PRODUCTION"


class RolloutStrategy(str, enum.Enum):
    ROLLING = "rolling"
    BLUE_GREEN = "blue-green"
    CANARY = "canary"
    WEIGHTED = "weighted"
    SHADOW = "shadow"
    DARK = "dark"


class FlagState(str, enum.Enum):
    OFF = "OFF"
    ON = "ON"
    ROLLOUT = "ROLLOUT"
    PAUSED = "PAUSED"
    ARCHIVED = "ARCHIVED"


class GateType(str, enum.Enum):
    TESTS = "tests"
    QUALITY = "quality"
    SECURITY = "security"
    DEPENDENCY = "dependency"
    ARTIFACT = "artifact"
    SBOM = "sbom"
    APPROVAL = "approval"
    SLO = "slo"
    INCIDENT = "incident"
    WINDOW = "window"
    COST = "cost"
    AI_GOVERNANCE = "ai_governance"


class VerificationStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"


# ── Release Records ──────────────────────────────────────────────────


class ReleaseRecord(Base, TimestampMixin):
    __tablename__ = "release_records"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project: Mapped[str] = mapped_column(String(128), nullable=False)
    service: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("delivery_artifacts.id", ondelete="SET NULL"), nullable=True)
    environment: Mapped[str] = mapped_column(String(64), nullable=False, default="DEV")
    release_channel: Mapped[str] = mapped_column(String(32), nullable=False, default="DEV")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT", index=True)
    strategy: Mapped[str] = mapped_column(String(32), nullable=False, default="rolling")
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    build_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (
        Index("ix_release_records_tenant_service_version", "tenant", "service", "version", unique=True),
        Index("ix_release_records_env_status", "environment", "status"),
    )


class ReleaseCandidate(Base, TimestampMixin):
    __tablename__ = "release_candidates"

    release_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("release_records.id", ondelete="CASCADE"), nullable=False, index=True)
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    build_id: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("delivery_artifacts.id", ondelete="CASCADE"), nullable=False)
    tests: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    security: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    quality: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    dependencies: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    configuration: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    approval_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    ai_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = ()


class ReleaseApproval(Base, TimestampMixin):
    __tablename__ = "release_approvals"

    release_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("release_records.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    approver_id: Mapped[str] = mapped_column(String(64), nullable=False)
    approver_role: Mapped[str] = mapped_column(String(32), nullable=False, default="reviewer")
    decision: Mapped[str] = mapped_column(String(16), nullable=False)  # approved/rejected
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    signature: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_release_approvals_release_version", "release_id", "version"),
    )


class ReleaseGate(Base, TimestampMixin):
    __tablename__ = "release_gates"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    gate_type: Mapped[str] = mapped_column(String(32), nullable=False)
    threshold: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    blocking: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (Index("ix_release_gates_tenant_type", "tenant", "gate_type"),)


class ReleaseGateResult(Base, TimestampMixin):
    __tablename__ = "release_gate_results"

    release_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("release_records.id", ondelete="CASCADE"), nullable=False, index=True)
    gate_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("release_gates.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # passed/failed/blocked
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    evaluated_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")

    __table_args__ = ()


class ReleaseStrategy(Base, TimestampMixin):
    __tablename__ = "release_strategies"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    strategy_type: Mapped[str] = mapped_column(String(32), nullable=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)  # initial/step/duration/max/success_criteria

    __table_args__ = ()


class ReleaseStep(Base, TimestampMixin):
    __tablename__ = "release_steps"

    release_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("release_records.id", ondelete="CASCADE"), nullable=False, index=True)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    weight: Mapped[int] = mapped_column(Integer, nullable=False)  # percentage
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (Index("ix_release_steps_release_order", "release_id", "step_order"),)


class ReleaseVerification(Base, TimestampMixin):
    __tablename__ = "release_verifications"

    release_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("release_records.id", ondelete="CASCADE"), nullable=False, index=True)
    verification_type: Mapped[str] = mapped_column(String(32), nullable=False, default="smoke")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    checks: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    result: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = ()


class ReleaseLock(Base, TimestampMixin):
    __tablename__ = "release_locks"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    service: Mapped[str] = mapped_column(String(128), nullable=False)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    locked_by: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_release_locks_tenant_service_env", "tenant", "service", "environment", unique=True),
    )


# ── Feature Flags (centralized) ──────────────────────────────────────


class FeatureFlag(Base, TimestampMixin):
    __tablename__ = "feature_flags"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    flag_type: Mapped[str] = mapped_column(String(32), default="boolean", nullable=False)  # boolean/percentage/segment
    default_value: Mapped[str] = mapped_column(String(64), default="false", nullable=False)
    state: Mapped[str] = mapped_column(String(32), default="OFF", nullable=False, index=True)
    owner: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    __table_args__ = (
        Index("ix_feature_flags_tenant_key", "tenant", "key", unique=True),
        {"extend_existing": True},
    )


class FeatureFlagVersion(Base, TimestampMixin):
    __tablename__ = "feature_flag_versions"

    flag_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("feature_flags.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    change: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    changed_by: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (Index("ix_flag_versions_flag_version", "flag_id", "version", unique=True),)


class FeatureFlagRule(Base, TimestampMixin):
    __tablename__ = "feature_flag_rules"

    flag_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("feature_flags.id", ondelete="CASCADE"), nullable=False, index=True)
    rule_type: Mapped[str] = mapped_column(String(32), nullable=False)  # percentage/segment/env/region/org/workspace/project
    value: Mapped[str] = mapped_column(String(256), nullable=False)
    percentage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rank: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (Index("ix_flag_rules_flag_rank", "flag_id", "rank"),)


class FeatureFlagEvaluation(Base, TimestampMixin):
    __tablename__ = "feature_flag_evaluations"

    flag_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("feature_flags.id", ondelete="CASCADE"), nullable=False, index=True)
    context: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    value: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = ()
