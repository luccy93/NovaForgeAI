"""Incident Response Platform -- Schemas (Volume 49)."""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any, Optional


class IncidentCreate(BaseModel):
    tenant: str = "default"
    title: str
    description: str = ""
    severity: str = "SEV2"
    source: str = "alert"
    incident_type: str = "availability"
    service: str = ""
    environment: str = "production"
    symptoms: list[str] = Field(default_factory=list)
    impact: dict = Field(default_factory=dict)


class IncidentUpdate(BaseModel):
    severity: Optional[str] = None
    status: Optional[str] = None
    commander: Optional[str] = None
    description: Optional[str] = None


class IncidentAcknowledge(BaseModel):
    commander: str = "on-call"


class IncidentTransition(BaseModel):
    status: str
    message: str = ""
    actor: str = "user"


class AlertIngest(BaseModel):
    tenant: str = "default"
    alert_source: str = "external"
    alert_id: str = ""
    rule_name: str = ""
    severity: str = "SEV2"
    service: str = ""
    environment: str = "production"
    message: str = ""
    raw_payload: dict = Field(default_factory=dict)
    labels: dict = Field(default_factory=dict)
    timestamp: Optional[str] = None


class HypothesisCreate(BaseModel):
    incident_id: str
    hypothesis: str
    confidence: float = 0.5
    evidence: list[dict] = Field(default_factory=list)
    supporting_signals: list[dict] = Field(default_factory=list)
    source: str = "ai"


class HypothesisUpdate(BaseModel):
    status: str
    actor: str = "user"


class ActionCreate(BaseModel):
    incident_id: str
    action_type: str
    description: str = ""
    risk_level: str = "moderate"
    approval_required: bool = True
    runbook_id: str = ""


class ActionApprove(BaseModel):
    approver: str = "user"


class ActionExecute(BaseModel):
    dry_run: bool = False


class RunbookCreate(BaseModel):
    tenant: str = "default"
    name: str
    incident_type: str = ""
    description: str = ""
    steps: list[dict] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    risk_level: str = "moderate"
    auto_executable: bool = False


class PostmortemCreate(BaseModel):
    incident_id: str
    summary: str = ""
    impact: str = ""
    root_cause: str = ""
    contributing_factors: list[str] = Field(default_factory=list)
    what_went_well: list[str] = Field(default_factory=list)
    what_went_wrong: list[str] = Field(default_factory=list)


class EscalationPolicyCreate(BaseModel):
    tenant: str = "default"
    name: str
    description: str = ""
    rules: list[dict] = Field(default_factory=list)


class AlertPolicyCreate(BaseModel):
    tenant: str = "default"
    name: str
    service: str = ""
    environment: str = "production"
    conditions: dict = Field(default_factory=dict)
    severity: str = "SEV2"
    window_seconds: int = 300
    dedup_window_seconds: int = 300
    notification_channels: list[str] = Field(default_factory=list)


class InvestigateRequest(BaseModel):
    incident_id: str
    focus_areas: list[str] = Field(default_factory=list)
    max_tokens: int = 5000


class InvestigateResponse(BaseModel):
    incident_id: str
    summary: str = ""
    hypotheses: list[dict] = Field(default_factory=list)
    affected_services: list[str] = Field(default_factory=list)
    recent_changes: list[dict] = Field(default_factory=list)
    recommended_steps: list[str] = Field(default_factory=list)
    blast_radius: dict = Field(default_factory=dict)


class TriageRequest(BaseModel):
    incident_id: str


class TriageResponse(BaseModel):
    incident_id: str
    summary: str
    severity_suggestion: str
    affected_services: list[str]
    suspected_components: list[str]
    recent_changes: list[dict]
    investigation_steps: list[str]


class SLOStatus(BaseModel):
    service: str
    availability_target: float
    availability_actual: float
    error_budget_total: float
    error_budget_remaining: float
    burn_rate: float
    status: str


class ReliabilityMetricsResponse(BaseModel):
    service: str
    mttd_seconds: float
    mtta_seconds: float
    mttr_seconds: float
    incident_count: int
    recurrence_count: int
    alert_count: int
    false_positive_rate: float
    change_failure_rate: float
    rollback_rate: float
    slo_compliance: float


class TimelineEvent(BaseModel):
    event_type: str
    timestamp: str
    source: str
    message: str
    actor: str = "system"
    evidence: dict = Field(default_factory=dict)


class StatusUpdate(BaseModel):
    incident_id: str
    status: str
    summary: str
    severity: str
    affected_services: list[str]
    next_update: str = ""


class HealthCheckResponse(BaseModel):
    service: str
    status: str
    details: dict = Field(default_factory=dict)
