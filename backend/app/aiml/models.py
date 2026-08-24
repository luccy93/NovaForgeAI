"""Volume 58 — AIML models (14 tables, additive-only)."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from app.core.database import Base, TimestampMixin


class AIModelRegistry(Base, TimestampMixin):
    __tablename__ = "ai_model_registry"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False, default="foundation")
    capabilities: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    license: Mapped[str | None] = mapped_column(String(64), nullable=True)
    region: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", nullable=False, index=True)
    risk_level: Mapped[str] = mapped_column(String(16), default="LOW", nullable=False)
    owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)

    __table_args__ = (
        Index("ix_aimodel_tenant_provider_version", "tenant", "provider", "version"),
        UniqueConstraint("tenant", "provider", "name", "version", name="uq_aimodel_tenant_provider_name_version"),
    )


class AIModelVersion(Base, TimestampMixin):
    __tablename__ = "ai_model_versions"

    model_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("ai_model_registry.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source: Mapped[str | None] = mapped_column(String(256), nullable=True)
    training_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    evaluation_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    deployment_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    policy_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provenance: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    immutable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("model_id", "version", name="uq_aimodelver_model_version"),)


class AIProviderRegistry(Base, TimestampMixin):
    __tablename__ = "ai_provider_registry"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    models: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    regions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    pricing: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    data_processing_policy: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    availability: Mapped[str] = mapped_column(String(32), default="AVAILABLE", nullable=False)
    security_status: Mapped[str] = mapped_column(String(32), default="UNKNOWN", nullable=False)
    contract_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (Index("ix_aiprovider_tenant", "tenant"),)


class AIPromptRegistry(Base, TimestampMixin):
    __tablename__ = "ai_prompt_registry"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    prompt_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    purpose: Mapped[str | None] = mapped_column(String(256), nullable=True)
    classification: Mapped[str] = mapped_column(String(32), default="INTERNAL", nullable=False)
    model_compatibility: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", nullable=False)

    __table_args__ = (UniqueConstraint("tenant", "prompt_id", name="uq_aiprompt_tenant_prompt"),)


class AIPromptVersion(Base, TimestampMixin):
    __tablename__ = "ai_prompt_versions"

    prompt_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("ai_prompt_registry.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    purpose: Mapped[str | None] = mapped_column(String(256), nullable=True)
    classification: Mapped[str] = mapped_column(String(32), default="INTERNAL", nullable=False)
    immutable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("prompt_id", "version", name="uq_aipromptver_prompt_version"),)


class AIEvaluationSuite(Base, TimestampMixin):
    __tablename__ = "ai_evaluation_suites"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    suite_type: Mapped[str] = mapped_column(String(32), nullable=False)  # benchmark/regression/adversarial/domain/safety/security/golden
    dataset_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dataset_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (Index("ix_aievalsuite_tenant_type", "tenant", "suite_type"),)


class AIEvaluationRun(Base, TimestampMixin):
    __tablename__ = "ai_evaluation_runs"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    suite_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("ai_evaluation_suites.id", ondelete="CASCADE"), nullable=False, index=True)
    model_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("ai_model_registry.id", ondelete="SET NULL"), nullable=True)
    prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("ai_prompt_versions.id", ondelete="SET NULL"), nullable=True)
    dataset_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    artifacts: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", nullable=False)
    reproducible_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)

    __table_args__ = (Index("ix_aievalrun_tenant_suite", "tenant", "suite_id"),)


class AIGuardrail(Base, TimestampMixin):
    __tablename__ = "ai_guardrails"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, default="input")  # input/output
    policy: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)  # content policies, tool restrictions, classification checks
    rate_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    environment: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (Index("ix_aiguardrail_tenant_scope", "tenant", "scope"),)


class AIRiskRecord(Base, TimestampMixin):
    __tablename__ = "ai_risk_records"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    system: Mapped[str] = mapped_column(String(128), nullable=False)
    model_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("ai_model_registry.id", ondelete="SET NULL"), nullable=True)
    risk_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    likelihood: Mapped[str] = mapped_column(String(16), nullable=False)
    impact: Mapped[str] = mapped_column(String(16), nullable=False)
    owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mitigation: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    __table_args__ = (Index("ix_airisk_tenant_system", "tenant", "system"),)


class AIModelCard(Base, TimestampMixin):
    __tablename__ = "ai_model_cards"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("ai_model_registry.id", ondelete="CASCADE"), nullable=False, index=True)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    capabilities: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    limitations: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    risk: Mapped[str | None] = mapped_column(String(16), nullable=True)
    evaluation_summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    data_policy: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_environments: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    __table_args__ = (Index("ix_aimodelcard_tenant_model", "tenant", "model_id"),)


class AISystemCard(Base, TimestampMixin):
    __tablename__ = "ai_system_cards"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    system: Mapped[str] = mapped_column(String(128), nullable=False)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    inputs: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    outputs: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    models: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    tools: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    permissions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    human_oversight: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_modes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    evaluation: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    deployment_scope: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (Index("ix_aisystemcard_tenant_system", "tenant", "system"),)


class AIApprovalRequest(Base, TimestampMixin):
    __tablename__ = "ai_approval_requests"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    request_type: Mapped[str] = mapped_column(String(32), nullable=False)  # new_model/new_provider/restricted_data/production/high_risk
    model_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("ai_model_registry.id", ondelete="SET NULL"), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requested_by: Mapped[str] = mapped_column(String(64), nullable=False)
    approver: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_aiapproval_tenant_status", "tenant", "status"),)


class AIMonitoringSnapshot(Base, TimestampMixin):
    __tablename__ = "ai_monitoring_snapshots"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("ai_model_registry.id", ondelete="SET NULL"), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    availability: Mapped[str] = mapped_column(String(16), default="UNKNOWN", nullable=False)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    token_usage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    quality: Mapped[float | None] = mapped_column(Float, nullable=True)
    safety: Mapped[float | None] = mapped_column(Float, nullable=True)
    drift: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (Index("ix_aimonitoring_tenant_model", "tenant", "model_id"),)
