"""SRE SQLAlchemy models (Volume 35).

Follows the NovaForge schema conventions: string UUID primary keys,
indexed organization_id columns, JSONB payload columns, and UTC
timestamps. Models are registered on the global Base metadata by the
`sre` package import.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return uuid.uuid4().hex


class SREService(Base):
    """Service catalog entry (SRE service registry)."""

    __tablename__ = "sre_services"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    service_id: Mapped[str] = mapped_column(String(96), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    owner: Mapped[str] = mapped_column(String(128), default="")
    team: Mapped[str] = mapped_column(String(128), default="")
    tier: Mapped[str] = mapped_column(String(16), default="tier1", index=True)
    criticality: Mapped[str] = mapped_column(String(16), default="high")
    deployment_strategy: Mapped[str] = mapped_column(String(24), default="rolling")
    scaling_strategy: Mapped[str] = mapped_column(String(128), default="")
    backup_strategy: Mapped[str] = mapped_column(String(255), default="")
    rto_minutes: Mapped[int] = mapped_column(Integer, default=60)
    rpo_minutes: Mapped[int] = mapped_column(Integer, default=60)
    runbook_id: Mapped[str] = mapped_column(String(64), default="")
    on_call: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(24), default="operational", index=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "service_id": self.service_id,
            "name": self.name,
            "description": self.description,
            "owner": self.owner,
            "team": self.team,
            "tier": self.tier,
            "criticality": self.criticality,
            "deployment_strategy": self.deployment_strategy,
            "scaling_strategy": self.scaling_strategy,
            "backup_strategy": self.backup_strategy,
            "rto_minutes": self.rto_minutes,
            "rpo_minutes": self.rpo_minutes,
            "runbook_id": self.runbook_id,
            "on_call": self.on_call,
            "status": self.status,
            "metadata": self.metadata_json or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class SREServiceVersion(Base):
    """Immutable service catalog version snapshots."""

    __tablename__ = "sre_service_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    service_id: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    spec: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    created_by: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class SREServiceDependency(Base):
    """Directed dependency edge: service -> depends_on."""

    __tablename__ = "sre_dependencies"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    service_id: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    depends_on: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), default="service")  # service | external
    critical: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class SRESLO(Base):
    """Service Level Objective definition."""

    __tablename__ = "sre_slos"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    slo_id: Mapped[str] = mapped_column(String(96), unique=True, nullable=False, index=True)
    service_id: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    sli_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target: Mapped[float] = mapped_column(Float, nullable=False)          # e.g. 0.999 availability
    window: Mapped[str] = mapped_column(String(16), default="monthly")    # daily|weekly|monthly|quarterly
    measurement: Mapped[str] = mapped_column(String(255), default="")
    query: Mapped[str] = mapped_column(Text, default="")
    owner: Mapped[str] = mapped_column(String(128), default="")
    severity: Mapped[str] = mapped_column(String(8), default="SEV2")
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "slo_id": self.slo_id,
            "service_id": self.service_id,
            "name": self.name,
            "description": self.description,
            "sli_type": self.sli_type,
            "target": self.target,
            "window": self.window,
            "measurement": self.measurement,
            "query": self.query,
            "owner": self.owner,
            "severity": self.severity,
            "status": self.status,
            "version": self.version,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SRESLIMeasurement(Base):
    """Raw SLI measurement point (time-bucketed)."""

    __tablename__ = "sre_sli_measurements"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    slo_id: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    service_id: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    sli_type: Mapped[str] = mapped_column(String(32), nullable=False)
    bucket_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    bucket_seconds: Mapped[int] = mapped_column(Integer, default=60)
    good: Mapped[float] = mapped_column(Float, default=0.0)    # good events (e.g. successful requests)
    total: Mapped[float] = mapped_column(Float, default=0.0)   # total events
    value: Mapped[float] = mapped_column(Float, default=0.0)   # measured value (latency percentiles etc.)
    region: Mapped[str] = mapped_column(String(32), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class SREErrorBudget(Base):
    """Computed error budget snapshot per SLO."""

    __tablename__ = "sre_error_budgets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    slo_id: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    service_id: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    window: Mapped[str] = mapped_column(String(16), default="monthly")
    allowed_failure: Mapped[float] = mapped_column(Float, nullable=False)     # fraction e.g. 0.001
    actual_failure: Mapped[float] = mapped_column(Float, nullable=False)      # fraction consumed
    remaining_budget: Mapped[float] = mapped_column(Float, nullable=False)    # fraction remaining
    consumed_percent: Mapped[float] = mapped_column(Float, default=0.0)
    burn_rate: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(16), default="healthy")
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False, index=True)


class SREAlert(Base):
    """Operational alert fired by SRE monitoring."""

    __tablename__ = "sre_alerts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    alert_id: Mapped[str] = mapped_column(String(96), unique=True, nullable=False, index=True)
    rule_name: Mapped[str] = mapped_column(String(255), nullable=False)
    severity: Mapped[str] = mapped_column(String(8), default="SEV3")
    service_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    region: Mapped[str] = mapped_column(String(32), default="")
    message: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="firing", index=True)  # firing | resolved | acked
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    fired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "alert_id": self.alert_id,
            "rule_name": self.rule_name,
            "severity": self.severity,
            "service_id": self.service_id,
            "region": self.region,
            "message": self.message,
            "status": self.status,
            "metadata": self.metadata_json or {},
            "fired_at": self.fired_at.isoformat() if self.fired_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


class SREIncident(Base):
    """Structured incident record with full lifecycle."""

    __tablename__ = "sre_incidents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    incident_id: Mapped[str] = mapped_column(String(96), unique=True, nullable=False, index=True)
    organization_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(8), default="SEV2", index=True)
    status: Mapped[str] = mapped_column(String(24), default="detected", index=True)
    service_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    region: Mapped[str] = mapped_column(String(32), default="")
    commander: Mapped[str] = mapped_column(String(128), default="")
    impact: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    root_cause: Mapped[str] = mapped_column(Text, default="")
    detection: Mapped[str] = mapped_column(String(64), default="alert")  # alert|user|monitoring|deployment|security|provider|infra|db|anomaly
    related_deployments: Mapped[list] = mapped_column(JSONB, default=list)
    related_changes: Mapped[list] = mapped_column(JSONB, default=list)
    related_alerts: Mapped[list] = mapped_column(JSONB, default=list)
    postmortem_id: Mapped[str] = mapped_column(String(64), default="")
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    mitigated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "incident_id": self.incident_id,
            "organization_id": self.organization_id,
            "title": self.title,
            "description": self.description,
            "severity": self.severity,
            "status": self.status,
            "service_id": self.service_id,
            "region": self.region,
            "commander": self.commander,
            "impact": self.impact or {},
            "root_cause": self.root_cause,
            "detection": self.detection,
            "related_deployments": self.related_deployments or [],
            "related_changes": self.related_changes or [],
            "related_alerts": self.related_alerts or [],
            "postmortem_id": self.postmortem_id,
            "detected_at": self.detected_at.isoformat() if self.detected_at else None,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "mitigated_at": self.mitigated_at.isoformat() if self.mitigated_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SREIncidentEvent(Base):
    """Automatic incident timeline entry."""

    __tablename__ = "sre_incident_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    incident_id: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)  # alert|ack|investigation|deployment|rollback|config|recovery|resolution|note
    actor: Mapped[str] = mapped_column(String(128), default="system")
    message: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False, index=True)


class SREIncidentResponder(Base):
    """Incident command assignment."""

    __tablename__ = "sre_incident_responders"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    incident_id: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(48), nullable=False)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class SREPostmortem(Base):
    """Incident postmortem (blame-free)."""

    __tablename__ = "sre_postmortems"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    postmortem_id: Mapped[str] = mapped_column(String(96), unique=True, nullable=False, index=True)
    incident_id: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    impact: Mapped[str] = mapped_column(Text, default="")
    timeline: Mapped[list] = mapped_column(JSONB, default=list)
    root_cause: Mapped[str] = mapped_column(Text, default="")
    contributing_factors: Mapped[list] = mapped_column(JSONB, default=list)
    detection: Mapped[str] = mapped_column(Text, default="")
    response: Mapped[str] = mapped_column(Text, default="")
    what_went_well: Mapped[list] = mapped_column(JSONB, default=list)
    what_went_wrong: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)  # draft | published
    created_by: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "postmortem_id": self.postmortem_id,
            "incident_id": self.incident_id,
            "summary": self.summary,
            "impact": self.impact,
            "timeline": self.timeline or [],
            "root_cause": self.root_cause,
            "contributing_factors": self.contributing_factors or [],
            "detection": self.detection,
            "response": self.response,
            "what_went_well": self.what_went_well or [],
            "what_went_wrong": self.what_went_wrong or [],
            "status": self.status,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SRECorrectiveAction(Base):
    """Corrective action tracking with verification."""

    __tablename__ = "sre_corrective_actions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    action_id: Mapped[str] = mapped_column(String(96), unique=True, nullable=False, index=True)
    incident_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    postmortem_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    owner: Mapped[str] = mapped_column(String(128), default="")
    priority: Mapped[str] = mapped_column(String(16), default="medium")  # high|medium|low
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)  # open|in_progress|done|verified|wont_do
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    verification: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "action_id": self.action_id,
            "incident_id": self.incident_id,
            "postmortem_id": self.postmortem_id,
            "description": self.description,
            "owner": self.owner,
            "priority": self.priority,
            "status": self.status,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "verification": self.verification,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SRERunbook(Base):
    """Runbook for a critical service / failure scenario."""

    __tablename__ = "sre_runbooks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    runbook_id: Mapped[str] = mapped_column(String(96), unique=True, nullable=False, index=True)
    service_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, default="")
    symptoms: Mapped[list] = mapped_column(JSONB, default=list)
    impact: Mapped[str] = mapped_column(Text, default="")
    diagnosis: Mapped[list] = mapped_column(JSONB, default=list)
    commands: Mapped[list] = mapped_column(JSONB, default=list)
    checks: Mapped[list] = mapped_column(JSONB, default=list)
    mitigation: Mapped[list] = mapped_column(JSONB, default=list)
    rollback: Mapped[list] = mapped_column(JSONB, default=list)
    recovery: Mapped[list] = mapped_column(JSONB, default=list)
    escalation: Mapped[list] = mapped_column(JSONB, default=list)
    post_incident: Mapped[list] = mapped_column(JSONB, default=list)
    owner: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "runbook_id": self.runbook_id,
            "service_id": self.service_id,
            "title": self.title,
            "purpose": self.purpose,
            "symptoms": self.symptoms or [],
            "impact": self.impact,
            "diagnosis": self.diagnosis or [],
            "commands": self.commands or [],
            "checks": self.checks or [],
            "mitigation": self.mitigation or [],
            "rollback": self.rollback or [],
            "recovery": self.recovery or [],
            "escalation": self.escalation or [],
            "post_incident": self.post_incident or [],
            "owner": self.owner,
        }


class SREMaintenanceWindow(Base):
    """Scheduled maintenance windows."""

    __tablename__ = "sre_maintenance"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    maintenance_id: Mapped[str] = mapped_column(String(96), unique=True, nullable=False, index=True)
    organization_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    scope: Mapped[str] = mapped_column(String(24), default="service")  # org|region|service|database
    target: Mapped[str] = mapped_column(String(96), default="")        # service id or region
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="scheduled", index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class SRERegion(Base):
    """Global region registry."""

    __tablename__ = "sre_regions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    region: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(24), default="active-active")  # active-active|active-passive|warm-standby|cold-standby
    status: Mapped[str] = mapped_column(String(24), default="operational", index=True)
    capacity_percent: Mapped[float] = mapped_column(Float, default=50.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class SRERegionHealth(Base):
    """Rolling region health measurements."""

    __tablename__ = "sre_region_health"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    region: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    availability: Mapped[float] = mapped_column(Float, default=1.0)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    error_rate: Mapped[float] = mapped_column(Float, default=0.0)
    capacity_percent: Mapped[float] = mapped_column(Float, default=0.0)
    dependency_health: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False, index=True)


class SRECapacityMetric(Base):
    """Capacity and saturation measurements."""

    __tablename__ = "sre_capacity"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    service_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    metric: Mapped[str] = mapped_column(String(64), nullable=False)  # cpu|memory|disk|requests|queue_depth|ai_requests
    value: Mapped[float] = mapped_column(Float, nullable=False)
    limit: Mapped[float] = mapped_column(Float, default=100.0)
    unit: Mapped[str] = mapped_column(String(16), default="percent")
    region: Mapped[str] = mapped_column(String(32), default="")
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False, index=True)


class SREBackupJob(Base):
    """Database backup job records."""

    __tablename__ = "sre_backups"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    backup_id: Mapped[str] = mapped_column(String(96), unique=True, nullable=False, index=True)
    target: Mapped[str] = mapped_column(String(64), nullable=False)  # postgresql|redis|qdrant|neo4j|object_storage
    region: Mapped[str] = mapped_column(String(32), default="")
    kind: Mapped[str] = mapped_column(String(24), default="full")    # full|incremental|pitr_snapshot
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)  # pending|running|completed|failed
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "backup_id": self.backup_id,
            "target": self.target,
            "region": self.region,
            "kind": self.kind,
            "status": self.status,
            "size_bytes": self.size_bytes,
            "verified": self.verified,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class SRERestoreTest(Base):
    """Scheduled restore verification tests."""

    __tablename__ = "sre_restore_tests"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    test_id: Mapped[str] = mapped_column(String(96), unique=True, nullable=False, index=True)
    backup_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    target: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    integrity: Mapped[bool] = mapped_column(Boolean, default=False)
    completeness: Mapped[bool] = mapped_column(Boolean, default=False)
    consistency: Mapped[bool] = mapped_column(Boolean, default=False)
    app_compatible: Mapped[bool] = mapped_column(Boolean, default=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "test_id": self.test_id,
            "backup_id": self.backup_id,
            "target": self.target,
            "status": self.status,
            "integrity": self.integrity,
            "completeness": self.completeness,
            "consistency": self.consistency,
            "app_compatible": self.app_compatible,
            "duration_seconds": self.duration_seconds,
            "notes": self.notes,
            "scheduled_for": self.scheduled_for.isoformat() if self.scheduled_for else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class SREFailoverTest(Base):
    """Failover verification tests (region, database, dependency)."""

    __tablename__ = "sre_failover_tests"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    test_id: Mapped[str] = mapped_column(String(96), unique=True, nullable=False, index=True)
    target: Mapped[str] = mapped_column(String(64), nullable=False)  # region|database|redis|qdrant|neo4j|object_storage|ai_provider|queue|worker|network
    scope: Mapped[str] = mapped_column(String(32), default="")
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    rto_achieved_minutes: Mapped[int] = mapped_column(Integer, default=0)
    data_loss_minutes: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "test_id": self.test_id,
            "target": self.target,
            "scope": self.scope,
            "status": self.status,
            "rto_achieved_minutes": self.rto_achieved_minutes,
            "data_loss_minutes": self.data_loss_minutes,
            "passed": self.passed,
            "notes": self.notes,
            "scheduled_for": self.scheduled_for.isoformat() if self.scheduled_for else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class SREChaosExperiment(Base):
    """Controlled chaos experiment with blast-radius controls."""

    __tablename__ = "sre_chaos_experiments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    experiment_id: Mapped[str] = mapped_column(String(96), unique=True, nullable=False, index=True)
    organization_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    experiment_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target: Mapped[str] = mapped_column(String(96), default="")
    scope: Mapped[str] = mapped_column(String(255), default="")
    blast_radius: Mapped[str] = mapped_column(String(64), default="test")  # test|staging|prod-limited
    owner: Mapped[str] = mapped_column(String(128), default="")
    abort_condition: Mapped[str] = mapped_column(Text, default="")
    expected_result: Mapped[str] = mapped_column(Text, default="")
    actual_result: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=30)
    recovery_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String(128), default="")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "experiment_id": self.experiment_id,
            "organization_id": self.organization_id,
            "name": self.name,
            "experiment_type": self.experiment_type,
            "target": self.target,
            "scope": self.scope,
            "blast_radius": self.blast_radius,
            "owner": self.owner,
            "abort_condition": self.abort_condition,
            "expected_result": self.expected_result,
            "actual_result": self.actual_result,
            "status": self.status,
            "duration_seconds": self.duration_seconds,
            "recovery_seconds": self.recovery_seconds,
            "passed": self.passed,
            "created_by": self.created_by,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class SREDependencyHealth(Base):
    """External dependency health snapshots."""

    __tablename__ = "sre_dependency_health"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    dependency: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), default="external")
    status: Mapped[str] = mapped_column(String(24), default="unknown", index=True)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    error_rate: Mapped[float] = mapped_column(Float, default=0.0)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    last_outage_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "dependency": self.dependency,
            "kind": self.kind,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "error_rate": self.error_rate,
            "metadata": self.metadata_json or {},
            "last_outage_at": self.last_outage_at.isoformat() if self.last_outage_at else None,
            "measured_at": self.measured_at.isoformat() if self.measured_at else None,
        }


class SREStatusComponent(Base):
    """Status page component."""

    __tablename__ = "sre_status_components"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    component_id: Mapped[str] = mapped_column(String(96), unique=True, nullable=False, index=True)
    service_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="operational", index=True)
    region: Mapped[str] = mapped_column(String(32), default="")
    public: Mapped[bool] = mapped_column(Boolean, default=False)
    history: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "component_id": self.component_id,
            "service_id": self.service_id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "region": self.region,
            "public": self.public,
            "history": self.history or [],
        }


class SREDeadLetterEntry(Base):
    """Dead-letter queue entry registry."""

    __tablename__ = "sre_dead_letter_entries"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    entry_id: Mapped[str] = mapped_column(String(96), unique=True, nullable=False, index=True)
    event_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    source: Mapped[str] = mapped_column(String(96), default="")
    queue: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    payload_reference: Mapped[str] = mapped_column(String(255), default="")
    correlation_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)  # open|replayed|discarded
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "entry_id": self.entry_id,
            "event_id": self.event_id,
            "source": self.source,
            "queue": self.queue,
            "error": self.error,
            "attempts": self.attempts,
            "payload_reference": self.payload_reference,
            "correlation_id": self.correlation_id,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SREDeployment(Base):
    """Deployment reliability record."""

    __tablename__ = "sre_deployments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    deployment_id: Mapped[str] = mapped_column(String(96), unique=True, nullable=False, index=True)
    service_id: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(64), default="")
    strategy: Mapped[str] = mapped_column(String(24), default="rolling")
    status: Mapped[str] = mapped_column(String(24), default="in_progress", index=True)  # in_progress|success|failed|rolled_back
    region: Mapped[str] = mapped_column(String(32), default="")
    commit: Mapped[str] = mapped_column(String(64), default="")
    environment: Mapped[str] = mapped_column(String(24), default="production")
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    error_rate_after: Mapped[float] = mapped_column(Float, default=0.0)
    latency_after_ms: Mapped[float] = mapped_column(Float, default=0.0)
    rolled_back_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "deployment_id": self.deployment_id,
            "service_id": self.service_id,
            "version": self.version,
            "strategy": self.strategy,
            "status": self.status,
            "region": self.region,
            "commit": self.commit,
            "environment": self.environment,
            "duration_seconds": self.duration_seconds,
            "error_rate_after": self.error_rate_after,
            "latency_after_ms": self.latency_after_ms,
            "rolled_back_at": self.rolled_back_at.isoformat() if self.rolled_back_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class SRECanaryRun(Base):
    """Canary analysis run."""

    __tablename__ = "sre_canary_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    canary_id: Mapped[str] = mapped_column(String(96), unique=True, nullable=False, index=True)
    deployment_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    service_id: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), default="in_progress", index=True)
    baseline_error_rate: Mapped[float] = mapped_column(Float, default=0.0)
    canary_error_rate: Mapped[float] = mapped_column(Float, default=0.0)
    baseline_latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    canary_latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    error_rate_threshold: Mapped[float] = mapped_column(Float, default=0.5)
    latency_threshold_multiplier: Mapped[float] = mapped_column(Float, default=1.5)
    aborted: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str] = mapped_column(Text, default="")
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "canary_id": self.canary_id,
            "deployment_id": self.deployment_id,
            "service_id": self.service_id,
            "status": self.status,
            "baseline_error_rate": self.baseline_error_rate,
            "canary_error_rate": self.canary_error_rate,
            "baseline_latency_ms": self.baseline_latency_ms,
            "canary_latency_ms": self.canary_latency_ms,
            "error_rate_threshold": self.error_rate_threshold,
            "latency_threshold_multiplier": self.latency_threshold_multiplier,
            "aborted": self.aborted,
            "reason": self.reason,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class SRECertificate(Base):
    """TLS certificate monitoring."""

    __tablename__ = "sre_certificates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    certificate_id: Mapped[str] = mapped_column(String(96), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    issuer: Mapped[str] = mapped_column(String(255), default="")
    not_before: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    not_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), default="valid", index=True)  # valid|expiring|expired|failed
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False)
    last_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "certificate_id": self.certificate_id,
            "name": self.name,
            "hostname": self.hostname,
            "issuer": self.issuer,
            "not_before": self.not_before.isoformat() if self.not_before else None,
            "not_after": self.not_after.isoformat() if self.not_after else None,
            "status": self.status,
            "auto_renew": self.auto_renew,
            "last_checked_at": self.last_checked_at.isoformat() if self.last_checked_at else None,
        }


class SRERemediationAction(Base):
    """Audit trail for automated operational remediation."""

    __tablename__ = "sre_remediation_actions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    action_id: Mapped[str] = mapped_column(String(96), unique=True, nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)   # restart_worker|scale_pool|retry_job|failover|drain|queue|rotate_credential
    target: Mapped[str] = mapped_column(String(128), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[list] = mapped_column(JSONB, default=list)
    policy: Mapped[str] = mapped_column(String(64), default="")
    authorized: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[str] = mapped_column(String(128), default="")
    result: Mapped[str] = mapped_column(String(24), default="pending", index=True)  # pending|success|failed|skipped|rolled_back
    rollback: Mapped[str] = mapped_column(Text, default="")
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    max_attempts: Mapped[int] = mapped_column(Integer, default=1)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "action_id": self.action_id,
            "action": self.action,
            "target": self.target,
            "reason": self.reason,
            "evidence": self.evidence or [],
            "policy": self.policy,
            "authorized": self.authorized,
            "requires_approval": self.requires_approval,
            "approved_by": self.approved_by,
            "result": self.result,
            "rollback": self.rollback,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SREReport(Base):
    """Generated SRE reports (daily/weekly/monthly/on-demand)."""

    __tablename__ = "sre_reports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    report_id: Mapped[str] = mapped_column(String(96), unique=True, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # daily|weekly|monthly|incident|service_health|slo|capacity|dr|dependency
    title: Mapped[str] = mapped_column(String(255), default="")
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "report_id": self.report_id,
            "kind": self.kind,
            "title": self.title,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "data": self.data or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
