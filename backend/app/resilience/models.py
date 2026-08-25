"""Volume 60 — Resilience models (9 tables, additive-only).

Backup/recovery/disaster management metadata. Reuses existing storage and
incident infrastructure; this layer tracks catalog, verification, restore
jobs, recovery plans, disaster declarations and failover records.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from app.core.database import Base, TimestampMixin


class ResilienceProfile(Base, TimestampMixin):
    __tablename__ = "resilience_profiles"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    service: Mapped[str] = mapped_column(String(128), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False, default="production")
    region: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resource: Mapped[str | None] = mapped_column(String(256), nullable=True)
    criticality: Mapped[str] = mapped_column(String(16), default="MEDIUM", nullable=False)  # LOW/MEDIUM/HIGH/CRITICAL
    rto_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rpo_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    availability_target: Mapped[float | None] = mapped_column(Float, nullable=True)
    recovery_priority: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    dependencies: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    fallback: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    owner: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant", "service", "environment", name="uq_res_profile_tenant_service_env"),
    )


class ResilienceBackupPolicy(Base, TimestampMixin):
    __tablename__ = "resilience_backup_policies"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)  # database/object_storage/vector/graph/configuration/service
    scope_target: Mapped[str | None] = mapped_column(String(256), nullable=True)
    backup_type: Mapped[str] = mapped_column(String(32), nullable=False, default="full")  # full/incremental/snapshot/continuous
    frequency: Mapped[str] = mapped_column(String(32), nullable=False, default="daily")
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    destination: Mapped[str | None] = mapped_column(String(256), nullable=True)
    encryption_key_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)  # KMS reference only
    immutable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    isolated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    verify_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (Index("ix_res_backup_policies_tenant_scope", "tenant", "scope_type"),)


class ResilienceBackup(Base, TimestampMixin):
    __tablename__ = "resilience_backups"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    policy_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("resilience_backup_policies.id", ondelete="SET NULL"), nullable=True, index=True)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_target: Mapped[str | None] = mapped_column(String(256), nullable=True)
    backup_type: Mapped[str] = mapped_column(String(32), nullable=False, default="full")
    status: Mapped[str] = mapped_column(String(32), default="RUNNING", nullable=False, index=True)  # RUNNING/COMPLETED/FAILED
    location: Mapped[str | None] = mapped_column(String(512), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    checksum_algorithm: Mapped[str] = mapped_column(String(32), default="sha256", nullable=False)
    encryption_status: Mapped[str] = mapped_column(String(32), default="UNKNOWN", nullable=False)
    encryption_key_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    immutable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    isolated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    verification_status: Mapped[str] = mapped_column(String(16), default="UNVERIFIED", nullable=False, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (
        Index("ix_res_backups_tenant_scope_status", "tenant", "scope_type", "status"),
    )


class ResilienceBackupVerification(Base, TimestampMixin):
    __tablename__ = "resilience_backup_verifications"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    backup_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("resilience_backups.id", ondelete="CASCADE"), nullable=False, index=True)
    verification_type: Mapped[str] = mapped_column(String(32), nullable=False, default="checksum")  # checksum/restore_test/metadata/dependency
    status: Mapped[str] = mapped_column(String(32), default="PENDING", nullable=False, index=True)  # PENDING/RUNNING/PASSED/FAILED
    result: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    verified_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_res_verifications_tenant_backup", "tenant", "backup_id"),)


class ResilienceRestoreJob(Base, TimestampMixin):
    __tablename__ = "resilience_restore_jobs"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    backup_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("resilience_backups.id", ondelete="RESTRICT"), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="full")  # full/resource/point_in_time
    target_environment: Mapped[str] = mapped_column(String(32), nullable=False, default="production")
    target_resource: Mapped[str | None] = mapped_column(String(256), nullable=True)
    isolated_test: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # restore into isolated env for drills
    point_in_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    state: Mapped[str] = mapped_column(String(32), default="PLANNED", nullable=False, index=True)  # PLANNED/READY/RUNNING/PAUSED/FAILED/VERIFYING/COMPLETED/ROLLED_BACK
    approval_status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requested_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    safety_checks: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    verification_result: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    reconciliation: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (Index("ix_res_restore_tenant_state", "tenant", "state"),)


class ResilienceRecoveryPlan(Base, TimestampMixin):
    __tablename__ = "resilience_recovery_plans"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    service: Mapped[str] = mapped_column(String(128), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False, default="production")
    disaster_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    profile_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("resilience_profiles.id", ondelete="SET NULL"), nullable=True)
    state: Mapped[str] = mapped_column(String(32), default="PLANNED", nullable=False, index=True)
    declared_disaster_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    owner: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (Index("ix_res_plans_tenant_service", "tenant", "service"),)


class ResilienceRecoveryStep(Base, TimestampMixin):
    __tablename__ = "resilience_recovery_steps"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    plan_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("resilience_recovery_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)  # dependency_recovery/data_recovery/service_recovery/traffic_recovery/verification
    resource: Mapped[str | None] = mapped_column(String(256), nullable=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=3600, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rollback_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)  # pending/running/completed/failed/skipped/approval_required
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (Index("ix_res_steps_plan_order", "plan_id", "step_order"),)


class ResilienceDisasterEvent(Base, TimestampMixin):
    __tablename__ = "resilience_disaster_events"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    disaster_type: Mapped[str] = mapped_column(String(32), nullable=False)  # SERVICE_OUTAGE/REGION_OUTAGE/DATA_CORRUPTION/SECURITY_DISASTER/PROVIDER_OUTAGE/PLATFORM_DISASTER
    scope: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="HIGH")
    incident_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # Volume 49 incident reference
    declared_by: Mapped[str] = mapped_column(String(64), nullable=False)
    declared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="DECLARED", nullable=False, index=True)  # DECLARED/RECOVERING/RESOLVED

    __table_args__ = (Index("ix_res_disasters_tenant_type", "tenant", "disaster_type"),)


class ResilienceFailoverRecord(Base, TimestampMixin):
    __tablename__ = "resilience_failover_records"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    failover_type: Mapped[str] = mapped_column(String(32), nullable=False)  # service/database/region/provider
    source_target: Mapped[str | None] = mapped_column(String(256), nullable=True)
    destination_target: Mapped[str | None] = mapped_column(String(256), nullable=True)
    service: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="STARTED", nullable=False, index=True)  # STARTED/PROMOTED/COMPLETED/FAILED/ROLLED_BACK
    authorized_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    data_residency_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # restricted data region check
    health_verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    traffic_shifted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (Index("ix_res_failovers_tenant_type", "tenant", "failover_type"),)


class ResilienceChaosTest(Base, TimestampMixin):
    """Volume 60 Commit 2 — controlled chaos tests with production guard."""

    __tablename__ = "resilience_chaos_tests"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    scope: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)  # {environment, service, target, description} or freeform
    scope_raw: Mapped[str | None] = mapped_column(String(256), nullable=True)  # original scope string for simple queries
    failure_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # service/database/queue/network/ai_provider/storage/event_bus
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)  # latency/timeout/error_rate/unavailable/resource_exhaustion + allow_production
    status: Mapped[str] = mapped_column(String(32), default="PENDING", nullable=False, index=True)  # PENDING/RUNNING/COMPLETED/FAILED/ABORTED
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    policy_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target: Mapped[str | None] = mapped_column(String(256), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    results: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    injection_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (
        Index("ix_res_chaos_tenant_status", "tenant", "status"),
        Index("ix_res_chaos_tenant_failure_type", "tenant", "failure_type"),
    )


class ResilienceRecoveryDrill(Base, TimestampMixin):
    """Volume 60 Commit 2 — isolated recovery drills (never overwrite production)."""

    __tablename__ = "resilience_recovery_drills"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    drill_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # backup_restore/regional/database/provider_failover
    scope: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    scope_raw: Mapped[str | None] = mapped_column(String(256), nullable=True)
    schedule: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)  # {scheduled_at, cron, interval}
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    isolated_test: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    target_environment: Mapped[str] = mapped_column(String(32), default="isolated", nullable=False)  # isolated/staging — never production
    status: Mapped[str] = mapped_column(String(32), default="SCHEDULED", nullable=False, index=True)  # SCHEDULED/RUNNING/COMPLETED/FAILED
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Game-day fields
    scenario: Mapped[str | None] = mapped_column(Text, nullable=True)
    participants: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    results: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    findings: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    score: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    __table_args__ = (
        Index("ix_res_drills_tenant_type", "tenant", "drill_type"),
        Index("ix_res_drills_tenant_status", "tenant", "status"),
    )
