"""Unified Analytics Platform -- Schemas (Volume 50)."""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any, Optional
from datetime import datetime


# ── Event Ingestion ────────────────────────────────────────────────────

class AnalyticsEventIngest(BaseModel):
    tenant: str = "default"
    workspace: str = ""
    project: str = ""
    actor: str = ""
    source: str = "platform"
    event_type: str
    resource_type: str = ""
    resource_id: str = ""
    cost_usd: float = 0.0
    duration_ms: float = 0.0
    metadata_extra: dict = Field(default_factory=dict)
    event_timestamp: Optional[str] = None


class AnalyticsEventBatch(BaseModel):
    events: list[AnalyticsEventIngest]
    idempotency_key: str = ""


# ── Metric Definitions ─────────────────────────────────────────────────

class MetricDefinitionCreate(BaseModel):
    name: str
    description: str = ""
    formula: str = ""
    category: str = "platform"
    dimensions: list[str] = Field(default_factory=list)
    source: str = "platform"
    unit: str = ""
    aggregation: str = "sum"


class MetricDefinitionUpdate(BaseModel):
    description: Optional[str] = None
    formula: Optional[str] = None
    enabled: Optional[bool] = None


# ── Query ──────────────────────────────────────────────────────────────

class MetricQuery(BaseModel):
    metric_name: str
    granularity: str = "hour"
    dimensions: dict = Field(default_factory=dict)
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    limit: int = 1000


class TrendQuery(BaseModel):
    metric_names: list[str] = Field(default_factory=list)
    granularity: str = "day"
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    dimensions: dict = Field(default_factory=dict)


# ── Cost ───────────────────────────────────────────────────────────────

class CostRecordCreate(BaseModel):
    tenant: str = "default"
    cost_type: str = "total"
    amount_usd: float
    currency: str = "USD"
    organization: str = ""
    workspace: str = ""
    project: str = ""
    repository: str = ""
    environment: str = ""
    model: str = ""
    provider: str = ""
    agent: str = ""
    workflow: str = ""
    user_id: str = ""
    is_estimated: bool = False
    period_start: str = ""
    period_end: str = ""


class CostAttributionQuery(BaseModel):
    tenant: str = "default"
    group_by: str = "organization"
    cost_type: str = "total"
    start_time: Optional[str] = None
    end_time: Optional[str] = None


# ── Budget ─────────────────────────────────────────────────────────────

class BudgetCreate(BaseModel):
    tenant: str = "default"
    name: str
    scope: str = "organization"
    scope_value: str = ""
    cost_type: str = "total"
    limit_usd: float
    period: str = "monthly"
    warning_threshold: float = 0.8
    soft_limit_threshold: float = 0.95
    hard_limit_threshold: float = 1.0


class BudgetUpdate(BaseModel):
    limit_usd: Optional[float] = None
    warning_threshold: Optional[float] = None
    soft_limit_threshold: Optional[float] = None
    hard_limit_threshold: Optional[float] = None
    enabled: Optional[bool] = None


# ── Alert ──────────────────────────────────────────────────────────────

class AnalyticsAlertCreate(BaseModel):
    tenant: str = "default"
    name: str
    alert_type: str = "cost_spike"
    metric_name: str = ""
    condition: dict = Field(default_factory=dict)
    severity: str = "medium"
    cooldown_seconds: int = 3600


# ── Report ─────────────────────────────────────────────────────────────

class ReportGenerate(BaseModel):
    tenant: str = "default"
    report_type: str = "executive"
    period_start: str = ""
    period_end: str = ""
    format: str = "json"


class ReportExport(BaseModel):
    report_id: str
    format: str = "json"


# ── Forecast ───────────────────────────────────────────────────────────

class ForecastCreate(BaseModel):
    tenant: str = "default"
    metric_name: str
    scope: str = ""
    scope_value: str = ""
    horizon_days: int = 30


# ── Recommendation ─────────────────────────────────────────────────────

class RecommendationAction(BaseModel):
    recommendation_id: str
    action: str = "dismiss"


# ── DORA / Engineering ────────────────────────────────────────────────

class EngineeringQuery(BaseModel):
    tenant: str = "default"
    project: str = ""
    repository: str = ""
    team: str = ""
    start_time: Optional[str] = None
    end_time: Optional[str] = None


# ── Dashboard ──────────────────────────────────────────────────────────

class DashboardQuery(BaseModel):
    tenant: str = "default"
    filters: dict = Field(default_factory=dict)
    start_time: Optional[str] = None
    end_time: Optional[str] = None


# ── Data Quality ───────────────────────────────────────────────────────

class DataQualityQuery(BaseModel):
    tenant: str = "default"
    issue_type: str = ""
    resolved: Optional[bool] = None
    limit: int = 100
