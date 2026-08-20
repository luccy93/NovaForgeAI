"""Software Delivery Platform database models (Volume 46).

Stores pipelines, jobs, runners, artifacts, environments, deployments,
releases, rollouts, rollbacks and preview environments for the complete
CI/CD delivery lifecycle.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from app.core.database import Base, TimestampMixin


# ── Pipeline ───────────────────────────────────────────────────────────


class DeliveryPipeline(Base, TimestampMixin):
    __tablename__ = "delivery_pipelines"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False)
    project: Mapped[str] = mapped_column(String(128), nullable=False)
    repository: Mapped[str] = mapped_column(String(256), nullable=False)
    branch: Mapped[str] = mapped_column(String(256), default="main", nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    trigger: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    stages: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    dependencies: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    environment: Mapped[str] = mapped_column(String(64), default="development", nullable=False)
    permissions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    approvals: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    variables: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    secrets_refs: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    timeout_s: Mapped[int] = mapped_column(Integer, default=3600, nullable=False)
    retry_policy: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    deployment_strategy: Mapped[str] = mapped_column(String(32), default="rolling", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)

    __table_args__ = (
        Index("ix_delivery_pipelines_tenant_project", "tenant", "project"),
        Index("ix_delivery_pipelines_repository", "repository"),
    )


class DeliveryPipelineRun(Base, TimestampMixin):
    __tablename__ = "delivery_pipeline_runs"

    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("delivery_pipelines.id", ondelete="CASCADE"), nullable=False, index=True
    )
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trigger: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    context: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=False, default="system")

    __table_args__ = ()


# ── Jobs ───────────────────────────────────────────────────────────────


class DeliveryJob(Base, TimestampMixin):
    __tablename__ = "delivery_jobs"

    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("delivery_pipeline_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    runner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("delivery_runners.id", ondelete="SET NULL"), nullable=True
    )
    image: Mapped[str] = mapped_column(String(256), default="ubuntu:22.04", nullable=False)
    commands: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    environment_vars: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    artifacts_in: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    artifacts_out: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    logs: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    timeout_s: Mapped[int] = mapped_column(Integer, default=600, nullable=False)
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index("ix_delivery_jobs_run_stage", "pipeline_run_id", "stage"),
    )


# ── Runners ────────────────────────────────────────────────────────────


class DeliveryRunner(Base, TimestampMixin):
    __tablename__ = "delivery_runners"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    region: Mapped[str] = mapped_column(String(64), default="default", nullable=False)
    runner_type: Mapped[str] = mapped_column(String(32), default="ephemeral", nullable=False)
    capabilities: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    labels: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    version: Mapped[str] = mapped_column(String(32), default="1.0.0", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="available", nullable=False, index=True)
    capacity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    current_jobs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cpu: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    memory_mb: Mapped[int] = mapped_column(Integer, default=8192, nullable=False)
    disk_gb: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    tenant: Mapped[str] = mapped_column(String(64), nullable=False)
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    quarantined: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    quarantine_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_delivery_runners_tenant_status", "tenant", "status"),
        Index("ix_delivery_runners_region", "region"),
    )


# ── Artifacts ──────────────────────────────────────────────────────────


class DeliveryArtifact(Base, TimestampMixin):
    __tablename__ = "delivery_artifacts"

    pipeline_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("delivery_pipeline_runs.id", ondelete="SET NULL"), nullable=True
    )
    repository: Mapped[str] = mapped_column(String(256), nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(32), nullable=False)
    hash: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    storage_url: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream", nullable=False)
    version: Mapped[str] = mapped_column(String(64), default="0.0.0", nullable=False)
    provenance: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    sbom: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    signed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    immutable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tenant: Mapped[str] = mapped_column(String(64), nullable=False)
    retention_days: Mapped[int] = mapped_column(Integer, default=90, nullable=False)
    legal_hold: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index("ix_delivery_artifacts_repository", "repository"),
        Index("ix_delivery_artifacts_tenant", "tenant"),
        Index("ix_delivery_artifacts_hash", "hash"),
    )


# ── Environments ───────────────────────────────────────────────────────


class DeliveryEnvironment(Base, TimestampMixin):
    __tablename__ = "delivery_environments"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    env_type: Mapped[str] = mapped_column(String(32), nullable=False)
    region: Mapped[str] = mapped_column(String(64), default="default", nullable=False)
    cluster: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    variables: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    secrets_refs: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    deployment_policy: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    approval_policy: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    resource_limits: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    network_policy: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    health_checks: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    locked_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    frozen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    freeze_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_deployment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)

    __table_args__ = (
        Index("ix_delivery_environments_tenant_name", "tenant", "name", unique=True),
    )


# ── Deployments ────────────────────────────────────────────────────────


class DeliveryDeployment(Base, TimestampMixin):
    __tablename__ = "delivery_deployments"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    environment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("delivery_environments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("delivery_artifacts.id", ondelete="SET NULL"), nullable=True
    )
    pipeline_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("delivery_pipeline_runs.id", ondelete="SET NULL"), nullable=True
    )
    strategy: Mapped[str] = mapped_column(String(32), default="rolling", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    deployed_by: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    health_status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    rollback_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    rollback_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_delivery_deployments_env_status", "environment_id", "status"),
    )


# ── Releases ───────────────────────────────────────────────────────────


class DeliveryRelease(Base, TimestampMixin):
    __tablename__ = "delivery_releases"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False)
    project: Mapped[str] = mapped_column(String(128), nullable=False)
    repository: Mapped[str] = mapped_column(String(256), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    release_channel: Mapped[str] = mapped_column(String(32), default="stable", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False, index=True)
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    release_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    deployment_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    deployed_environments: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        Index("ix_delivery_releases_tenant_project", "tenant", "project"),
        Index("ix_delivery_releases_version", "version"),
    )


# ── Rollouts (canary) ─────────────────────────────────────────────────


class DeliveryRollout(Base, TimestampMixin):
    __tablename__ = "delivery_rollouts"

    deployment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("delivery_deployments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    strategy: Mapped[str] = mapped_column(String(32), default="canary", nullable=False)
    current_weight: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    target_weight: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    stages: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    current_stage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="in_progress", nullable=False)
    metrics_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    auto_promote: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_abort: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    error_rate_threshold: Mapped[float] = mapped_column(Float, default=0.05, nullable=False)
    latency_threshold_ms: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    promotion_gates: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    __table_args__ = ()


# ── Rollbacks ──────────────────────────────────────────────────────────


class DeliveryRollback(Base, TimestampMixin):
    __tablename__ = "delivery_rollbacks"

    deployment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("delivery_deployments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    initiated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    automatic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False, index=True)
    previous_version: Mapped[str] = mapped_column(String(64), nullable=False)
    target_version: Mapped[str] = mapped_column(String(64), nullable=False)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = ()


# ── Preview Environments ───────────────────────────────────────────────


class DeliveryPreviewEnvironment(Base, TimestampMixin):
    __tablename__ = "delivery_preview_environments"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    repository: Mapped[str] = mapped_column(String(256), nullable=False)
    branch: Mapped[str] = mapped_column(String(256), nullable=False)
    pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    url: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="creating", nullable=False, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ttl_seconds: Mapped[int] = mapped_column(Integer, default=3600, nullable=False)
    resource_limits: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    deployment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    cleanup_scheduled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index("ix_delivery_previews_tenant", "tenant"),
        Index("ix_delivery_previews_repository_branch", "repository", "branch"),
    )


# ── Delivery Approvals ─────────────────────────────────────────────────


class DeliveryApproval(Base, TimestampMixin):
    __tablename__ = "delivery_approvals"

    pipeline_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("delivery_pipeline_runs.id", ondelete="CASCADE"), nullable=True
    )
    deployment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("delivery_deployments.id", ondelete="CASCADE"), nullable=True
    )
    requested_by: Mapped[str] = mapped_column(String(64), nullable=False)
    decided_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    gate_type: Mapped[str] = mapped_column(String(32), nullable=False)
    context: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_delivery_approvals_run", "pipeline_run_id"),
        Index("ix_delivery_approvals_deployment", "deployment_id"),
    )
