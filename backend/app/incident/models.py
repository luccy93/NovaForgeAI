"""Incident Response Platform -- Database Models (Volume 49).

11 SQLAlchemy models for the AI-powered incident response pipeline.
Uses the NovaForge conventions: TimestampMixin, JSON columns, string PKs,
indexed tenant columns.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.database import Base, TimestampMixin


class Incident(Base, TimestampMixin):
    __tablename__ = "incident_incidents"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(8), nullable=False, default="SEV2")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="detected")
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="alert")
    incident_type: Mapped[str] = mapped_column(String(32), nullable=False, default="availability")
    service: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    environment: Mapped[str] = mapped_column(String(32), nullable=False, default="production")
    commander: Mapped[str] = mapped_column(String(128), default="")
    impact: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    symptoms: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    root_cause: Mapped[str] = mapped_column(Text, default="")
    remediation: Mapped[str] = mapped_column(Text, default="")
    fingerprint: Mapped[str] = mapped_column(String(128), default="", index=True)
    correlated_deployments: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    correlated_commits: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    correlated_alerts: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    correlated_security_findings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    blast_radius: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    ai_hypotheses: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    timeline_summary: Mapped[str] = mapped_column(Text, default="")
    metadata_extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    mitigated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_incident_incidents_tenant", "tenant"),
        Index("ix_incident_incidents_tenant_service", "tenant", "service"),
        Index("ix_incident_incidents_tenant_status", "tenant", "status"),
        Index("ix_incident_incidents_tenant_severity", "tenant", "severity"),
    )


class IncidentEvent(Base, TimestampMixin):
    __tablename__ = "incident_events"

    incident_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), default="system")
    source: Mapped[str] = mapped_column(String(32), default="system")
    message: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    metadata_extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_incident_events_incident", "incident_id"),
    )


class IncidentAlert(Base, TimestampMixin):
    __tablename__ = "incident_alerts"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False)
    incident_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    alert_source: Mapped[str] = mapped_column(String(32), nullable=False, default="external")
    alert_id: Mapped[str] = mapped_column(String(128), default="")
    severity: Mapped[str] = mapped_column(String(8), default="SEV2")
    fingerprint: Mapped[str] = mapped_column(String(128), default="", index=True)
    service: Mapped[str] = mapped_column(String(128), default="")
    environment: Mapped[str] = mapped_column(String(32), default="production")
    message: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="firing")
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    metadata_extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_incident_alerts_tenant", "tenant"),
        Index("ix_incident_alerts_tenant_fingerprint", "tenant", "fingerprint"),
    )


class IncidentHypothesis(Base, TimestampMixin):
    __tablename__ = "incident_hypotheses"

    incident_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    hypothesis: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    supporting_signals: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(24), default="proposed")
    source: Mapped[str] = mapped_column(String(16), default="ai")

    __table_args__ = (
        Index("ix_incident_hypotheses_incident", "incident_id"),
    )


class IncidentAction(Base, TimestampMixin):
    __tablename__ = "incident_actions"

    incident_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(48), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    risk_level: Mapped[str] = mapped_column(String(16), default="moderate")
    status: Mapped[str] = mapped_column(String(24), default="proposed")
    approval_required: Mapped[bool] = mapped_column(Boolean, default=True)
    approver: Mapped[str] = mapped_column(String(128), default="")
    dry_run_result: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    execution_result: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    rollback_result: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    runbook_id: Mapped[str] = mapped_column(String(64), default="")
    metadata_extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_incident_actions_incident", "incident_id"),
    )


class IncidentRunbook(Base, TimestampMixin):
    __tablename__ = "incident_runbooks"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(16), default="1.0")
    incident_type: Mapped[str] = mapped_column(String(32), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    steps: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    permissions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    risk_level: Mapped[str] = mapped_column(String(16), default="moderate")
    auto_executable: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_incident_runbooks_tenant", "tenant"),
        Index("ix_incident_runbooks_tenant_type", "tenant", "incident_type"),
    )


class IncidentPostmortem(Base, TimestampMixin):
    __tablename__ = "incident_postmortems"

    incident_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    impact: Mapped[str] = mapped_column(Text, default="")
    timeline: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    root_cause: Mapped[str] = mapped_column(Text, default="")
    contributing_factors: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    detection_quality: Mapped[str] = mapped_column(Text, default="")
    response_quality: Mapped[str] = mapped_column(Text, default="")
    resolution_quality: Mapped[str] = mapped_column(Text, default="")
    what_went_well: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    what_went_wrong: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    follow_up_actions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(24), default="draft")
    created_by: Mapped[str] = mapped_column(String(128), default="")

    __table_args__ = (
        Index("ix_incident_postmortems_incident", "incident_id"),
    )


class IncidentActionItem(Base, TimestampMixin):
    __tablename__ = "incident_action_items"

    incident_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    postmortem_id: Mapped[str] = mapped_column(String(64), default="")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    owner: Mapped[str] = mapped_column(String(128), default="")
    priority: Mapped[str] = mapped_column(String(16), default="medium")
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="open")
    linked_runbook_id: Mapped[str] = mapped_column(String(64), default="")
    metadata_extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_incident_action_items_incident", "incident_id"),
    )


class IncidentEscalationPolicy(Base, TimestampMixin):
    __tablename__ = "incident_escalation_policies"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    rules: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_incident_escalation_policies_tenant", "tenant"),
    )


class IncidentAlertPolicy(Base, TimestampMixin):
    __tablename__ = "incident_alert_policies"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    service: Mapped[str] = mapped_column(String(128), default="")
    environment: Mapped[str] = mapped_column(String(32), default="production")
    conditions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    severity: Mapped[str] = mapped_column(String(8), default="SEV2")
    window_seconds: Mapped[int] = mapped_column(Integer, default=300)
    dedup_window_seconds: Mapped[int] = mapped_column(Integer, default=300)
    notification_channels: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_incident_alert_policies_tenant", "tenant"),
    )


class IncidentReliabilityMetrics(Base, TimestampMixin):
    __tablename__ = "incident_reliability_metrics"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False)
    service: Mapped[str] = mapped_column(String(128), nullable=False)
    period: Mapped[str] = mapped_column(String(16), default="daily")
    mttd_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    mtta_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    mttr_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    incident_count: Mapped[int] = mapped_column(Integer, default=0)
    recurrence_count: Mapped[int] = mapped_column(Integer, default=0)
    alert_count: Mapped[int] = mapped_column(Integer, default=0)
    false_positive_rate: Mapped[float] = mapped_column(Float, default=0.0)
    change_failure_rate: Mapped[float] = mapped_column(Float, default=0.0)
    rollback_rate: Mapped[float] = mapped_column(Float, default=0.0)
    slo_compliance: Mapped[float] = mapped_column(Float, default=1.0)
    metadata_extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_incident_reliability_metrics_tenant", "tenant"),
        Index("ix_incident_reliability_metrics_tenant_service", "tenant", "service"),
    )
