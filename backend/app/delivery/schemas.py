"""Pydantic schemas for the Delivery Platform (Volume 46)."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class PipelineCreate(BaseModel):
    tenant: str
    project: str
    repository: str
    branch: str = "main"
    name: str
    trigger: str = "manual"
    stages: list[dict[str, Any]] = Field(default_factory=list)
    dependencies: dict[str, Any] = Field(default_factory=dict)
    environment: str = "development"
    permissions: list[str] = Field(default_factory=list)
    approvals: list[str] = Field(default_factory=list)
    variables: dict[str, Any] = Field(default_factory=dict)
    secrets_refs: list[str] = Field(default_factory=list)
    timeout_s: int = 3600
    retry_policy: dict[str, Any] = Field(default_factory=dict)
    deployment_strategy: str = "rolling"


class PipelineResponse(BaseModel):
    id: UUID
    tenant: str
    project: str
    repository: str
    branch: str
    name: str
    trigger: str
    stages: list[dict[str, Any]]
    environment: str
    deployment_strategy: str
    enabled: bool
    status: str
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class PipelineRunCreate(BaseModel):
    commit_sha: Optional[str] = None
    trigger: str = "manual"
    actor: str = "system"
    context: dict[str, Any] = Field(default_factory=dict)


class PipelineRunResponse(BaseModel):
    id: UUID
    pipeline_id: UUID
    commit_sha: Optional[str] = None
    trigger: str
    status: str
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_ms: int
    error: Optional[str] = None
    actor: str
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class JobResponse(BaseModel):
    id: UUID
    pipeline_run_id: UUID
    stage: str
    name: str
    runner_id: Optional[UUID] = None
    image: str
    status: str
    exit_code: Optional[int] = None
    duration_ms: int
    retry_count: int
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class RunnerCreate(BaseModel):
    name: str
    region: str = "default"
    runner_type: str = "ephemeral"
    capabilities: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    tenant: str = ""
    cpu: int = 4
    memory_mb: int = 8192
    disk_gb: int = 50
    capacity: int = 1


class RunnerResponse(BaseModel):
    id: UUID
    name: str
    region: str
    runner_type: str
    capabilities: list[str]
    labels: list[str]
    version: str
    status: str
    capacity: int
    current_jobs: int
    tenant: str
    quarantined: bool
    cpu: int = 4
    memory_mb: int = 8192
    disk_gb: int = 50
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class ArtifactCreate(BaseModel):
    name: str
    artifact_type: str
    hash: str
    size_bytes: int = 0
    storage_url: str = ""
    content_type: str = "application/octet-stream"
    version: str = "0.0.0"
    repository: str = ""
    commit_sha: str = ""
    provenance: dict[str, Any] = Field(default_factory=dict)
    sbom: Optional[dict] = None
    tenant: str = ""
    retention_days: int = 90


class ArtifactResponse(BaseModel):
    id: UUID
    name: str
    artifact_type: str
    hash: str
    size_bytes: int
    version: str
    repository: str
    commit_sha: str
    signed: bool
    immutable: bool
    tenant: str
    retention_days: int
    legal_hold: bool
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class EnvironmentCreate(BaseModel):
    tenant: str
    name: str
    env_type: str
    region: str = "default"
    cluster: str = ""
    variables: dict[str, Any] = Field(default_factory=dict)
    secrets_refs: list[str] = Field(default_factory=list)
    deployment_policy: dict[str, Any] = Field(default_factory=dict)
    approval_policy: dict[str, Any] = Field(default_factory=dict)
    resource_limits: dict[str, Any] = Field(default_factory=dict)
    network_policy: dict[str, Any] = Field(default_factory=dict)
    health_checks: dict[str, Any] = Field(default_factory=dict)


class EnvironmentResponse(BaseModel):
    id: UUID
    tenant: str
    name: str
    env_type: str
    region: str
    cluster: str
    locked: bool
    locked_by: Optional[str] = None
    frozen: bool
    freeze_reason: Optional[str] = None
    current_deployment_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class DeploymentCreate(BaseModel):
    environment_id: UUID
    artifact_id: Optional[UUID] = None
    pipeline_run_id: Optional[UUID] = None
    strategy: str = "rolling"
    version: str = "0.0.0"
    commit_sha: str = ""
    deployed_by: str = ""
    notes: Optional[str] = None


class DeploymentResponse(BaseModel):
    id: UUID
    tenant: str
    environment_id: UUID
    artifact_id: Optional[UUID] = None
    pipeline_run_id: Optional[UUID] = None
    strategy: str
    status: str
    version: str
    commit_sha: str
    deployed_by: str
    approved_by: Optional[str] = None
    health_status: str
    rollback_available: bool
    rollback_version: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class ReleaseCreate(BaseModel):
    tenant: str
    project: str
    repository: str
    version: str
    release_channel: str = "stable"
    commit_sha: str = ""
    artifact_ids: list[str] = Field(default_factory=list)
    release_notes: str = ""
    created_by: str = ""


class ReleaseResponse(BaseModel):
    id: UUID
    tenant: str
    project: str
    repository: str
    version: str
    release_channel: str
    status: str
    commit_sha: str
    artifact_ids: list[str]
    release_notes: str
    deployed_environments: list[str]
    created_by: str
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class RolloutResponse(BaseModel):
    id: UUID
    deployment_id: UUID
    strategy: str
    current_weight: int
    target_weight: int
    stages: list
    current_stage: int
    status: str
    auto_promote: bool
    auto_abort: bool
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class RollbackCreate(BaseModel):
    reason: str = ""
    initiated_by: str = ""
    automatic: bool = False


class RollbackResponse(BaseModel):
    id: UUID
    deployment_id: UUID
    reason: str
    initiated_by: str
    automatic: bool
    status: str
    previous_version: str
    target_version: str
    environment: str
    verified: bool
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class PreviewEnvironmentCreate(BaseModel):
    tenant: str
    name: str
    repository: str
    branch: str
    pr_number: Optional[int] = None
    commit_sha: str = ""
    ttl_seconds: int = 3600
    resource_limits: dict[str, Any] = Field(default_factory=dict)


class PreviewEnvironmentResponse(BaseModel):
    id: UUID
    tenant: str
    name: str
    repository: str
    branch: str
    pr_number: Optional[int] = None
    commit_sha: str
    url: str
    status: str
    expires_at: Optional[datetime] = None
    ttl_seconds: int
    cleanup_scheduled: bool
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class ApprovalDecision(BaseModel):
    decision: str = "pending"
    decided_by: str = "operator"
    reason: str = ""


class ApprovalResponse(BaseModel):
    id: UUID
    pipeline_run_id: Optional[UUID] = None
    deployment_id: Optional[UUID] = None
    requested_by: str
    decided_by: Optional[str] = None
    decision: str
    reason: Optional[str] = None
    gate_type: str
    context: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
