"""SRE API (Volume 35).

Production reliability surface: service catalog, SLOs/error budgets,
alerts, incidents, postmortems, runbooks, regions, capacity, backups,
restore/failover tests, chaos experiments, maintenance windows, status
page, certificates, deployments, canaries, reports and automated
operations.

All endpoints require authentication. Mutating operational endpoints
require the admin_all permission; read-only endpoints require any
authenticated user.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import _get_current_user, require_permission
from app.core.authorization import Permission
from app.core.database import get_db
from app.models.user import User
from app.sre import events as sre_events
from app.sre.alerts import acknowledge_alert, create_alert, list_alerts, resolve_alert, resolve_by_rule  # noqa: F401
from app.sre.capacity import capacity_trend, record_capacity, saturation_summary
from app.sre.certificates import check_certificates, ensure_certificate
from app.sre.constants import (
    REGION_MODES,
    RUNBOOK_SCENARIOS,
    SEV2,
    SEVERITIES,
    SLI_TYPES,
    SLO_WINDOWS,
    STATUS_STATES,
)
from app.sre.deployments import (
    complete_deployment,
    evaluate_canary,
    list_canaries,
    list_deployments,
    record_deployment,
    rollback_safety,
    start_canary,
)
from app.sre.dependencies import (
    latest_dependency_health,
    outage_plan,
)
from app.sre.incidents import (
    InvalidTransitionError,
    add_event,
    ai_diagnosis,
    assign_responder,
    correlate_alerts,
    correlate_recent_changes,
    create_corrective_action,
    create_incident,
    create_postmortem,
    get_timeline,
    list_incidents,
    transition,
)
from app.sre.models import (
    SREAlert,
    SRECanaryRun,
    SRECertificate,
    SREChaosExperiment,
    SRECorrectiveAction,
    SREDeadLetterEntry,
    SREDeployment,
    SREErrorBudget,
    SREIncident,
    SREMaintenanceWindow,
    SREPostmortem,
    SRERegion,
    SRERegionHealth,
    SRERemediationAction,
    SRERestoreTest,
    SRERunbook,
    SREService,
    SREServiceDependency,
    SREServiceVersion,
    SRESLIMeasurement,
    SRESLO,
    SREStatusComponent,
    SREFailoverTest,
)
from app.sre.playbooks import create_runbook, search_runbooks
from app.sre.reports import build_report, list_reports
from app.sre.score import compute_reliability_score
from app.sre.seed import seed_defaults
from app.sre.slo import (
    burn_rate_status,
    compute_all_budgets,
    compute_error_budget,
    get_latest_budget,
    record_sli,
)
from app.sre.store import get_by_id, get_one, list_all, new_key

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------


class ServiceIn(BaseModel):
    service_id: Optional[str] = None
    name: str
    description: str = ""
    owner: str = ""
    team: str = ""
    tier: str = "tier1"
    criticality: str = "high"
    deployment_strategy: str = "rolling"
    scaling_strategy: str = ""
    backup_strategy: str = ""
    rto_minutes: int = 60
    rpo_minutes: int = 60
    on_call: str = ""
    metadata: dict = Field(default_factory=dict)


class DependencyIn(BaseModel):
    depends_on: str
    kind: str = "service"
    critical: bool = True


class SLOIn(BaseModel):
    slo_id: Optional[str] = None
    service_id: str
    name: str
    description: str = ""
    sli_type: str = "availability"
    target: float = 0.999
    window: str = "monthly"
    measurement: str = ""
    query: str = ""
    owner: str = ""
    severity: str = SEV2
    status: str = "active"


class SLIMeasurementIn(BaseModel):
    good: float = 1.0
    total: float = 1.0
    value: Optional[float] = None
    region: str = ""
    bucket_seconds: int = 60


class AlertIn(BaseModel):
    rule_name: str
    severity: str = SEV2
    message: str = ""
    service_id: str = ""
    region: str = ""
    metadata: dict = Field(default_factory=dict)


class IncidentIn(BaseModel):
    title: str
    description: str = ""
    severity: str = SEV2
    service_id: str = ""
    region: str = ""
    organization_id: str = ""
    detection: str = "manual"
    commander: str = ""
    impact: dict = Field(default_factory=dict)


class TransitionIn(BaseModel):
    target: str
    actor: str = "system"
    note: str = ""


class EventIn(BaseModel):
    event_type: str
    actor: str = "system"
    message: str = ""
    metadata: dict = Field(default_factory=dict)


class ResponderIn(BaseModel):
    role: str
    user_id: str


class PostmortemIn(BaseModel):
    summary: str
    impact: str = ""
    root_cause: str = ""
    contributing_factors: list = Field(default_factory=list)
    detection: str = ""
    response: str = ""
    what_went_well: list = Field(default_factory=list)
    what_went_wrong: list = Field(default_factory=list)
    created_by: str = "system"


class CorrectiveActionIn(BaseModel):
    description: str
    incident_id: str = ""
    postmortem_id: str = ""
    owner: str = ""
    priority: str = "medium"
    due_date: Optional[datetime] = None


class RunbookIn(BaseModel):
    runbook_id: Optional[str] = None
    service_id: str = ""
    title: str
    purpose: str = ""
    symptoms: list = Field(default_factory=list)
    impact: str = ""
    diagnosis: list = Field(default_factory=list)
    commands: list = Field(default_factory=list)
    checks: list = Field(default_factory=list)
    mitigation: list = Field(default_factory=list)
    rollback: list = Field(default_factory=list)
    recovery: list = Field(default_factory=list)
    escalation: list = Field(default_factory=list)
    post_incident: list = Field(default_factory=list)
    owner: str = ""


class RegionIn(BaseModel):
    region: str
    mode: str = "active-active"
    status: str = "operational"
    capacity_percent: float = 50.0


class RegionHealthIn(BaseModel):
    availability: float = 1.0
    latency_ms: float = 0.0
    error_rate: float = 0.0
    capacity_percent: float = 0.0
    dependency_health: dict = Field(default_factory=dict)


class CapacityIn(BaseModel):
    service_id: str = ""
    metric: str
    value: float
    limit: float = 100.0
    unit: str = "percent"
    region: str = ""


class BackupIn(BaseModel):
    target: str
    region: str = ""
    kind: str = "full"


class RestoreTestIn(BaseModel):
    backup_id: str = ""
    target: str
    scheduled_for: Optional[datetime] = None


class FailoverTestIn(BaseModel):
    target: str
    scope: str = ""
    scheduled_for: Optional[datetime] = None


class ChaosIn(BaseModel):
    name: str
    experiment_type: str
    target: str = ""
    scope: str = ""
    blast_radius: str = "test"
    owner: str = ""
    abort_condition: str = ""
    expected_result: str = ""
    duration_seconds: int = 30
    created_by: str = "system"


class MaintenanceIn(BaseModel):
    scope: str = "service"
    target: str = ""
    description: str = ""
    starts_at: datetime
    ends_at: datetime
    created_by: str = "system"


class StatusComponentIn(BaseModel):
    component_id: Optional[str] = None
    service_id: str = ""
    name: str
    description: str = ""
    status: str = "operational"
    region: str = ""
    public: bool = False


class CertificateIn(BaseModel):
    name: str
    hostname: str
    auto_renew: bool = False


class DeploymentIn(BaseModel):
    service_id: str
    version: str = ""
    strategy: str = "rolling"
    region: str = ""
    commit: str = ""
    environment: str = "production"


class DeploymentCompleteIn(BaseModel):
    status: str = "success"
    duration_seconds: int = 0
    error_rate_after: float = 0.0
    latency_after_ms: float = 0.0


class CanaryIn(BaseModel):
    deployment_id: str = ""
    service_id: str
    baseline_error_rate: float = 0.0
    baseline_latency_ms: float = 0.0
    error_rate_threshold: float = 0.5
    latency_threshold_multiplier: float = 1.5


class CanaryEvaluateIn(BaseModel):
    canary_error_rate: float
    canary_latency_ms: float


class RemediationIn(BaseModel):
    action: str
    target: str = ""
    reason: str = ""
    evidence: list = Field(default_factory=list)
    policy: str = "default"
    authorized: bool = False
    requires_approval: bool = False
    approved_by: str = ""
    max_attempts: int = 1


class DLQIn(BaseModel):
    event_id: str = ""
    source: str = ""
    queue: str
    error: str = ""
    attempts: int = 0
    payload_reference: str = ""
    correlation_id: str = ""
    status: str = "open"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _service_or_404(db: AsyncSession, service_id: str) -> SREService:
    service = await get_one(db, SREService, service_id=service_id)
    if service is None:
        raise HTTPException(status_code=404, detail=f"service {service_id} not found")
    return service


async def _incident_or_404(db: AsyncSession, incident_id: str) -> SREIncident:
    incident = await get_one(db, SREIncident, incident_id=incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail=f"incident {incident_id} not found")
    return incident


async def _alert_or_404(db: AsyncSession, alert_id: str):
    alert = await get_one(db, SREAlert, alert_id=alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail=f"alert {alert_id} not found")
    return alert


def _validate_tier(tier: str) -> None:
    if tier not in ("tier0", "tier1", "tier2", "tier3"):
        raise HTTPException(status_code=422, detail=f"invalid tier {tier}")


def _validate_sli_type(sli_type: str) -> None:
    if sli_type not in SLI_TYPES:
        raise HTTPException(status_code=422, detail=f"invalid sli_type {sli_type}")


def _validate_window(window: str) -> None:
    if window not in SLO_WINDOWS:
        raise HTTPException(status_code=422, detail=f"invalid window {window}")


# ---------------------------------------------------------------------------
# Services (service catalog)
# ---------------------------------------------------------------------------


@router.get("/services")
async def list_services(
    tier: Optional[str] = None,
    status: Optional[str] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    services, total = await list_all(db, SREService, offset=offset, limit=limit, order_by="name", tier=tier or "", status=status or "")
    return {"total": total, "items": [s.to_dict() for s in services]}


@router.post("/services", status_code=201)
async def create_service(
    body: ServiceIn,
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _validate_tier(body.tier)
    service_id = body.service_id or new_key("svc")
    if await get_one(db, SREService, service_id=service_id):
        raise HTTPException(status_code=409, detail=f"service {service_id} already exists")
    service = SREService(
        service_id=service_id,
        name=body.name,
        description=body.description,
        owner=body.owner,
        team=body.team,
        tier=body.tier,
        criticality=body.criticality,
        deployment_strategy=body.deployment_strategy,
        scaling_strategy=body.scaling_strategy,
        backup_strategy=body.backup_strategy,
        rto_minutes=body.rto_minutes,
        rpo_minutes=body.rpo_minutes,
        on_call=body.on_call,
        metadata_json=body.metadata,
    )
    db.add(service)
    await db.flush()
    version = SREServiceVersion(service_id=service_id, version=1, spec=service.to_dict(), created_by=str(current_user.id))
    db.add(version)
    await db.flush()
    return service.to_dict()


@router.get("/services/{service_id}")
async def get_service(service_id: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    service = await _service_or_404(db, service_id)
    return service.to_dict()


@router.put("/services/{service_id}")
async def update_service(
    service_id: str,
    body: ServiceIn,
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = await _service_or_404(db, service_id)
    for field in ("name", "description", "owner", "team", "tier", "criticality", "deployment_strategy", "scaling_strategy", "backup_strategy", "rto_minutes", "rpo_minutes", "on_call"):
        setattr(service, field, getattr(body, field))
    service.metadata_json = body.metadata
    await db.flush()
    return service.to_dict()


@router.delete("/services/{service_id}", status_code=204)
async def delete_service(
    service_id: str,
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> None:
    service = await _service_or_404(db, service_id)
    await db.delete(service)
    await db.flush()


@router.get("/services/{service_id}/dependencies")
async def service_dependencies(service_id: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    await _service_or_404(db, service_id)
    direct, _ = await list_all(db, SREServiceDependency, service_id=service_id)
    edges = {d.depends_on: d.to_dict() if hasattr(d, "to_dict") else {"depends_on": d.depends_on, "kind": d.kind, "critical": d.critical} for d in direct}
    return {"service_id": service_id, "dependencies": [{"depends_on": d.depends_on, "kind": d.kind, "critical": d.critical} for d in direct], "edges": edges}


@router.get("/services/{service_id}/impact")
async def service_impact(service_id: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    """Dependency graph traversal: 'if Service X fails, what breaks?'"""
    await _service_or_404(db, service_id)
    result = await db.execute(select(SREServiceDependency))
    all_edges = list(result.scalars().all())
    by_dependency: dict[str, list[SREServiceDependency]] = {}
    for edge in all_edges:
        by_dependency.setdefault(edge.depends_on, []).append(edge)
    affected: dict[str, list[dict]] = {}
    visited: set[str] = set()
    frontier = [service_id]
    depth = 0
    while frontier and depth < 6:
        next_frontier: list[str] = []
        for dependency in frontier:
            for edge in by_dependency.get(dependency, []):
                if edge.service_id in visited:
                    continue
                visited.add(edge.service_id)
                affected.setdefault(edge.service_id, []).append(
                    {"depends_on": dependency, "kind": edge.kind, "critical": edge.critical}
                )
                next_frontier.append(edge.service_id)
        frontier = next_frontier
        depth += 1
    return {"service_id": service_id, "direct_impact": len(affected), "affected": affected}


@router.post("/services/{service_id}/dependencies", status_code=201)
async def add_service_dependency(
    service_id: str,
    body: DependencyIn,
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _service_or_404(db, service_id)
    existing = await get_one(db, SREServiceDependency, service_id=service_id, depends_on=body.depends_on)
    if existing:
        raise HTTPException(status_code=409, detail="dependency already registered")
    edge = SREServiceDependency(service_id=service_id, depends_on=body.depends_on, kind=body.kind, critical=body.critical)
    db.add(edge)
    await db.flush()
    return {"service_id": service_id, "depends_on": body.depends_on, "kind": body.kind, "critical": body.critical}


# ---------------------------------------------------------------------------
# SLOs & error budgets
# ---------------------------------------------------------------------------


@router.get("/slos")
async def list_slos(
    service_id: Optional[str] = None,
    status: Optional[str] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    slos, total = await list_all(db, SRESLO, offset=offset, limit=limit, order_by="service_id", service_id=service_id or "", status=status or "")
    return {"total": total, "items": [s.to_dict() for s in slos]}


@router.post("/slos", status_code=201)
async def create_slo(
    body: SLOIn,
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _service_or_404(db, body.service_id)
    _validate_sli_type(body.sli_type)
    _validate_window(body.window)
    if not 0.0 < body.target <= 1.0:
        raise HTTPException(status_code=422, detail="target must be in (0, 1]")
    slo_id = body.slo_id or f"{body.service_id}-{body.sli_type}"
    if await get_one(db, SRESLO, slo_id=slo_id):
        raise HTTPException(status_code=409, detail=f"SLO {slo_id} already exists")
    slo = SRESLO(
        slo_id=slo_id,
        service_id=body.service_id,
        name=body.name,
        description=body.description,
        sli_type=body.sli_type,
        target=body.target,
        window=body.window,
        measurement=body.measurement,
        query=body.query,
        owner=body.owner,
        severity=body.severity if body.severity in SEVERITIES else SEV2,
        status=body.status,
        version=1,
    )
    db.add(slo)
    await db.flush()
    return slo.to_dict()


@router.post("/slos/{slo_id}/measure", status_code=201)
async def measure_sli(
    slo_id: str,
    body: SLIMeasurementIn,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    slo = await get_one(db, SRESLO, slo_id=slo_id)
    if slo is None:
        raise HTTPException(status_code=404, detail=f"SLO {slo_id} not found")
    measurement = await record_sli(
        db,
        slo=slo,
        good=body.good,
        total=body.total,
        value=body.value,
        region=body.region,
        bucket_seconds=body.bucket_seconds,
    )
    return {
        "id": measurement.id,
        "slo_id": slo.slo_id,
        "good": measurement.good,
        "total": measurement.total,
        "bucket_start": measurement.bucket_start.isoformat(),
    }


@router.post("/slos/{slo_id}/compute")
async def compute_slo_budget(slo_id: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    slo = await get_one(db, SRESLO, slo_id=slo_id)
    if slo is None:
        raise HTTPException(status_code=404, detail=f"SLO {slo_id} not found")
    return await compute_error_budget(db, slo, persist=True)


@router.get("/slos/{slo_id}/budget")
async def get_slo_budget(slo_id: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    slo = await get_one(db, SRESLO, slo_id=slo_id)
    if slo is None:
        raise HTTPException(status_code=404, detail=f"SLO {slo_id} not found")
    budget = await get_latest_budget(db, slo_id)
    return budget or {"slo_id": slo_id, "detail": "no budget computed yet - POST /slos/{id}/compute"}


@router.get("/slos/{slo_id}/burn-rate")
async def get_slo_burn_rate(slo_id: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    slo = await get_one(db, SRESLO, slo_id=slo_id)
    if slo is None:
        raise HTTPException(status_code=404, detail=f"SLO {slo_id} not found")
    return await burn_rate_status(db, slo)


@router.get("/error-budgets")
async def list_error_budgets(
    service_id: Optional[str] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    budgets, total = await list_all(db, SREErrorBudget, offset=offset, limit=limit, order_by="computed_at", service_id=service_id or "")
    return {
        "total": total,
        "items": [
            {
                "slo_id": b.slo_id,
                "service_id": b.service_id,
                "window": b.window,
                "allowed_failure": b.allowed_failure,
                "actual_failure": b.actual_failure,
                "remaining_budget": b.remaining_budget,
                "consumed_percent": b.consumed_percent,
                "burn_rate": b.burn_rate,
                "status": b.status,
                "computed_at": b.computed_at.isoformat(),
            }
            for b in budgets
        ],
    }


@router.post("/error-budgets/recompute")
async def recompute_error_budgets(
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    budgets = await compute_all_budgets(db, persist=True)
    return {"computed": len(budgets), "budgets": budgets}


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------


@router.get("/alerts")
async def get_alerts(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    service_id: Optional[str] = None,
    region: Optional[str] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    items, total = await list_alerts(db, status=status, severity=severity, service_id=service_id, region=region, offset=offset, limit=limit)
    return {"total": total, "items": items}


@router.post("/alerts", status_code=201)
async def fire_alert(
    body: AlertIn,
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    alert = await create_alert(
        db,
        rule_name=body.rule_name,
        severity=body.severity if body.severity in SEVERITIES else SEV2,
        message=body.message,
        service_id=body.service_id,
        region=body.region,
        metadata_json=body.metadata,
    )
    return alert.to_dict()


@router.post("/alerts/{alert_id}/ack")
async def ack_alert(alert_id: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    alert = await _alert_or_404(db, alert_id)
    alert = await acknowledge_alert(db, alert.id)
    return alert.to_dict()


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert_endpoint(alert_id: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    alert = await _alert_or_404(db, alert_id)
    alert = await resolve_alert(db, alert.id)
    return alert.to_dict()


# ---------------------------------------------------------------------------
# Incidents
# ---------------------------------------------------------------------------


@router.get("/incidents")
async def get_incidents(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    service_id: Optional[str] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    items, total = await list_incidents(db, status=status, severity=severity, service_id=service_id, offset=offset, limit=limit)
    return {"total": total, "items": items}


@router.post("/incidents", status_code=201)
async def new_incident(body: IncidentIn, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    incident = await create_incident(
        db,
        title=body.title,
        description=body.description,
        severity=body.severity,
        service_id=body.service_id,
        region=body.region,
        organization_id=body.organization_id,
        detection=body.detection,
        commander=body.commander,
        impact=body.impact,
    )
    sre_events.incident_created(incident.incident_id, title=incident.title, severity=incident.severity)
    return incident.to_dict()


@router.get("/incidents/{incident_id}")
async def get_incident(incident_id: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    incident = await _incident_or_404(db, incident_id)
    return incident.to_dict()


@router.post("/incidents/{incident_id}/transition")
async def transition_incident(
    incident_id: str,
    body: TransitionIn,
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    incident = await _incident_or_404(db, incident_id)
    try:
        incident = await transition(db, incident, body.target, actor=body.actor, note=body.note)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    sre_events.incident_updated(incident.incident_id, status=incident.status, actor=body.actor)
    if incident.status == "resolved":
        sre_events.incident_resolved(incident.incident_id, resolved_at=incident.resolved_at.isoformat() if incident.resolved_at else None)
    return incident.to_dict()


@router.post("/incidents/{incident_id}/events", status_code=201)
async def add_incident_event(incident_id: str, body: EventIn, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    incident = await _incident_or_404(db, incident_id)
    event = await add_event(db, incident.incident_id, body.event_type, actor=body.actor, message=body.message, metadata_json=body.metadata)
    return {"id": event.id, "event_type": event.event_type, "actor": event.actor, "message": event.message, "occurred_at": event.occurred_at.isoformat()}


@router.get("/incidents/{incident_id}/timeline")
async def incident_timeline(incident_id: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    incident = await _incident_or_404(db, incident_id)
    events = await get_timeline(db, incident.incident_id)
    return {
        "incident_id": incident.incident_id,
        "events": [
            {"event_type": e.event_type, "actor": e.actor, "message": e.message, "occurred_at": e.occurred_at.isoformat(), "metadata": e.metadata_json or {}}
            for e in events
        ],
    }


@router.post("/incidents/{incident_id}/responders", status_code=201)
async def add_responder(
    incident_id: str,
    body: ResponderIn,
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    incident = await _incident_or_404(db, incident_id)
    responder = await assign_responder(db, incident.incident_id, body.role, body.user_id)
    return {"id": responder.id, "role": responder.role, "user_id": responder.user_id, "assigned_at": responder.assigned_at.isoformat()}


@router.post("/incidents/{incident_id}/correlate")
async def correlate_incident(incident_id: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    incident = await _incident_or_404(db, incident_id)
    changes = await correlate_recent_changes(db, incident)
    alerts = await correlate_alerts(db, incident)
    return {"incident_id": incident.incident_id, "related_changes": changes, "related_alerts": alerts}


@router.post("/incidents/{incident_id}/diagnose")
async def diagnose_incident(incident_id: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    incident = await _incident_or_404(db, incident_id)
    diagnosis = await ai_diagnosis(db, incident)
    return diagnosis


@router.post("/incidents/{incident_id}/postmortem", status_code=201)
async def create_incident_postmortem(
    incident_id: str,
    body: PostmortemIn,
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    incident = await _incident_or_404(db, incident_id)
    if incident.status not in ("resolved", "closed"):
        raise HTTPException(status_code=422, detail="postmortem requires a resolved or closed incident")
    postmortem = await create_postmortem(
        db,
        incident=incident,
        summary=body.summary,
        impact=body.impact,
        root_cause=body.root_cause,
        contributing_factors=body.contributing_factors,
        detection=body.detection,
        response=body.response,
        what_went_well=body.what_went_well,
        what_went_wrong=body.what_went_wrong,
        created_by=body.created_by,
    )
    return postmortem.to_dict()


# ---------------------------------------------------------------------------
# Postmortems & corrective actions
# ---------------------------------------------------------------------------


@router.get("/postmortems")
async def get_postmortems(
    incident_id: Optional[str] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    items, total = await list_all(db, SREPostmortem, offset=offset, limit=limit, order_by="created_at", incident_id=incident_id or "")
    return {"total": total, "items": [p.to_dict() for p in items]}


@router.get("/postmortems/{postmortem_id}")
async def get_postmortem(postmortem_id: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    postmortem = await get_one(db, SREPostmortem, postmortem_id=postmortem_id)
    if postmortem is None:
        raise HTTPException(status_code=404, detail=f"postmortem {postmortem_id} not found")
    return postmortem.to_dict()


@router.post("/postmortems/{postmortem_id}/publish")
async def publish_postmortem(
    postmortem_id: str,
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    postmortem = await get_one(db, SREPostmortem, postmortem_id=postmortem_id)
    if postmortem is None:
        raise HTTPException(status_code=404, detail=f"postmortem {postmortem_id} not found")
    postmortem.status = "published"
    await db.flush()
    return postmortem.to_dict()


@router.get("/corrective-actions")
async def get_corrective_actions(
    incident_id: Optional[str] = None,
    status: Optional[str] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    items, total = await list_all(db, SRECorrectiveAction, offset=offset, limit=limit, order_by="created_at", incident_id=incident_id or "", status=status or "")
    return {"total": total, "items": [a.to_dict() for a in items]}


@router.post("/corrective-actions", status_code=201)
async def add_corrective_action(
    body: CorrectiveActionIn,
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    action = await create_corrective_action(
        db,
        description=body.description,
        incident_id=body.incident_id,
        postmortem_id=body.postmortem_id,
        owner=body.owner,
        priority=body.priority,
        due_date=body.due_date,
    )
    return action.to_dict()


@router.put("/corrective-actions/{action_id}")
async def update_corrective_action(
    action_id: str,
    status: str,
    verification: str = "",
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    action = await get_one(db, SRECorrectiveAction, action_id=action_id)
    if action is None:
        raise HTTPException(status_code=404, detail=f"action {action_id} not found")
    if status not in ("open", "in_progress", "done", "verified", "wont_do"):
        raise HTTPException(status_code=422, detail=f"invalid status {status}")
    action.status = status
    if verification:
        action.verification = verification
    await db.flush()
    return action.to_dict()


# ---------------------------------------------------------------------------
# Runbooks
# ---------------------------------------------------------------------------


@router.get("/runbooks")
async def get_runbooks(
    service_id: Optional[str] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    items, total = await search_runbooks(db, service_id=service_id or "", offset=offset, limit=limit)
    return {"total": total, "items": items}


@router.post("/runbooks", status_code=201)
async def add_runbook(
    body: RunbookIn,
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    runbook = await create_runbook(
        db,
        runbook_id=body.runbook_id or new_key("rb"),
        service_id=body.service_id,
        title=body.title,
        purpose=body.purpose,
        symptoms=body.symptoms,
        impact=body.impact,
        diagnosis=body.diagnosis,
        commands=body.commands,
        checks=body.checks,
        mitigation=body.mitigation,
        rollback=body.rollback,
        recovery=body.recovery,
        escalation=body.escalation,
        post_incident=body.post_incident,
        owner=body.owner,
    )
    return runbook.to_dict()


@router.get("/runbook-scenarios")
async def list_runbook_scenarios(current_user: User = Depends(_get_current_user)) -> dict:
    return {"scenarios": list(RUNBOOK_SCENARIOS)}


# ---------------------------------------------------------------------------
# Regions & region health
# ---------------------------------------------------------------------------


@router.get("/regions")
async def get_regions(current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    regions, total = await list_all(db, SRERegion, order_by="region")
    return {"total": total, "items": [{"region": r.region, "mode": r.mode, "status": r.status, "capacity_percent": r.capacity_percent} for r in regions]}


@router.post("/regions", status_code=201)
async def add_region(
    body: RegionIn,
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if body.mode not in REGION_MODES:
        raise HTTPException(status_code=422, detail=f"invalid mode {body.mode}")
    if body.status not in STATUS_STATES:
        raise HTTPException(status_code=422, detail=f"invalid status {body.status}")
    if await get_one(db, SRERegion, region=body.region):
        raise HTTPException(status_code=409, detail=f"region {body.region} already registered")
    region = SRERegion(region=body.region, mode=body.mode, status=body.status, capacity_percent=body.capacity_percent)
    db.add(region)
    await db.flush()
    return {"region": region.region, "mode": region.mode, "status": region.status, "capacity_percent": region.capacity_percent}


@router.get("/regions/{region}/health")
async def get_region_health(region: str, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    rows, total = await list_all(db, SRERegionHealth, order_by="measured_at", region=region, limit=1)
    if not rows:
        return {"region": region, "detail": "no health measurements recorded yet"}
    return {"region": region, "latest": rows[0].to_dict() if hasattr(rows[0], "to_dict") else vars(rows[0])}


@router.post("/regions/{region}/health", status_code=201)
async def record_region_health(
    region: str,
    body: RegionHealthIn,
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    snapshot = SRERegionHealth(
        region=region,
        availability=body.availability,
        latency_ms=body.latency_ms,
        error_rate=body.error_rate,
        capacity_percent=body.capacity_percent,
        dependency_health=body.dependency_health,
    )
    db.add(snapshot)
    await db.flush()
    status = "degraded" if body.error_rate > 0.01 or body.availability < 0.995 else "operational"
    return {"region": region, "status": status, "measured_at": snapshot.measured_at.isoformat()}


# ---------------------------------------------------------------------------
# Capacity
# ---------------------------------------------------------------------------


@router.get("/capacity/trend")
async def get_capacity_trend(
    service_id: Optional[str] = None,
    metric: str = "cpu",
    days: int = Query(7, ge=1, le=90),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await capacity_trend(db, service_id=service_id or "", metric=metric, days=days)


@router.get("/capacity/saturation")
async def get_saturation(current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    return {"items": await saturation_summary(db)}


@router.post("/capacity/record", status_code=201)
async def record_capacity_metric(
    body: CapacityIn,
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = await record_capacity(db, service_id=body.service_id, metric=body.metric, value=body.value, limit=body.limit, unit=body.unit, region=body.region)
    return {"id": row.id, "service_id": row.service_id, "metric": row.metric, "value": row.value, "measured_at": row.measured_at.isoformat()}


# ---------------------------------------------------------------------------
# Backups, restore tests, failover tests
# ---------------------------------------------------------------------------


@router.get("/backups")
async def get_backups(
    target: Optional[str] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.sre.models import SREBackupJob

    items, total = await list_all(db, SREBackupJob, offset=offset, limit=limit, order_by="created_at", target=target or "")
    return {"total": total, "items": [b.to_dict() for b in items]}


@router.post("/backups", status_code=201)
async def schedule_backup(
    body: BackupIn,
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.sre.models import SREBackupJob

    backup = SREBackupJob(backup_id=new_key("backup"), target=body.target, region=body.region, kind=body.kind)
    db.add(backup)
    await db.flush()
    return backup.to_dict()


@router.get("/restore-tests")
async def get_restore_tests(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    items, total = await list_all(db, SRERestoreTest, offset=offset, limit=limit, order_by="created_at")
    return {"total": total, "items": [t.to_dict() for t in items]}


@router.post("/restore-tests", status_code=201)
async def schedule_restore_test(
    body: RestoreTestIn,
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    test = SRERestoreTest(
        test_id=new_key("restore"),
        backup_id=body.backup_id,
        target=body.target,
        scheduled_for=body.scheduled_for or datetime.now(timezone.utc),
    )
    db.add(test)
    await db.flush()
    return test.to_dict()


@router.get("/failover-tests")
async def get_failover_tests(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    items, total = await list_all(db, SREFailoverTest, offset=offset, limit=limit, order_by="created_at")
    return {"total": total, "items": [t.to_dict() for t in items]}


@router.post("/failover-tests", status_code=201)
async def schedule_failover_test(
    body: FailoverTestIn,
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    test = SREFailoverTest(
        test_id=new_key("failover"),
        target=body.target,
        scope=body.scope,
        scheduled_for=body.scheduled_for or datetime.now(timezone.utc),
    )
    db.add(test)
    await db.flush()
    return test.to_dict()


@router.post("/restore-tests/{test_id}/complete")
async def complete_restore_test(
    test_id: str,
    integrity: bool = True,
    completeness: bool = True,
    consistency: bool = True,
    app_compatible: bool = True,
    duration_seconds: int = 0,
    notes: str = "",
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    test = await get_one(db, SRERestoreTest, test_id=test_id)
    if test is None:
        raise HTTPException(status_code=404, detail=f"restore test {test_id} not found")
    test.integrity = integrity
    test.completeness = completeness
    test.consistency = consistency
    test.app_compatible = app_compatible
    test.duration_seconds = duration_seconds
    test.notes = notes
    test.status = "completed"
    test.completed_at = datetime.now(timezone.utc)
    await db.flush()
    if not (integrity and completeness and consistency):
        sre_events.restore_failed(test.test_id, test.target, notes=notes)
    return test.to_dict()


@router.post("/failover-tests/{test_id}/complete")
async def complete_failover_test(
    test_id: str,
    rto_achieved_minutes: int = 0,
    data_loss_minutes: int = 0,
    passed: bool = False,
    notes: str = "",
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    test = await get_one(db, SREFailoverTest, test_id=test_id)
    if test is None:
        raise HTTPException(status_code=404, detail=f"failover test {test_id} not found")
    test.rto_achieved_minutes = rto_achieved_minutes
    test.data_loss_minutes = data_loss_minutes
    test.passed = passed
    test.notes = notes
    test.status = "completed"
    test.completed_at = datetime.now(timezone.utc)
    await db.flush()
    return test.to_dict()


# ---------------------------------------------------------------------------
# Chaos experiments
# ---------------------------------------------------------------------------


@router.get("/chaos")
async def get_chaos_experiments(
    status: Optional[str] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    items, total = await list_all(db, SREChaosExperiment, offset=offset, limit=limit, order_by="created_at", status=status or "")
    return {"total": total, "items": [e.to_dict() for e in items]}


@router.post("/chaos", status_code=201)
async def create_chaos_experiment(
    body: ChaosIn,
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if body.blast_radius not in ("test", "staging", "prod-limited"):
        raise HTTPException(status_code=422, detail="blast_radius must be test, staging or prod-limited")
    experiment = SREChaosExperiment(
        experiment_id=new_key("chaos"),
        organization_id=body.scope,
        name=body.name,
        experiment_type=body.experiment_type,
        target=body.target,
        scope=body.scope,
        blast_radius=body.blast_radius,
        owner=body.owner,
        abort_condition=body.abort_condition,
        expected_result=body.expected_result,
        duration_seconds=body.duration_seconds,
        created_by=body.created_by,
    )
    db.add(experiment)
    await db.flush()
    return experiment.to_dict()


@router.post("/chaos/{experiment_id}/run")
async def run_chaos_experiment(
    experiment_id: str,
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    experiment = await get_one(db, SREChaosExperiment, experiment_id=experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail=f"chaos experiment {experiment_id} not found")
    if experiment.blast_radius not in ("test", "staging", "prod-limited"):
        raise HTTPException(status_code=422, detail="experiment scope not permitted")
    experiment.status = "running"
    experiment.started_at = datetime.now(timezone.utc)
    await db.flush()
    return {
        "experiment_id": experiment.experiment_id,
        "status": "running",
        "note": "experiment execution is orchestrator-driven; completion recorded via /chaos/{id}/complete",
    }


@router.post("/chaos/{experiment_id}/complete")
async def complete_chaos_experiment(
    experiment_id: str,
    actual_result: str = "",
    recovery_seconds: float = 0.0,
    passed: bool = False,
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    experiment = await get_one(db, SREChaosExperiment, experiment_id=experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail=f"chaos experiment {experiment_id} not found")
    experiment.status = "completed"
    experiment.actual_result = actual_result
    experiment.recovery_seconds = recovery_seconds
    experiment.passed = passed
    experiment.completed_at = datetime.now(timezone.utc)
    await db.flush()
    return experiment.to_dict()


# ---------------------------------------------------------------------------
# Maintenance windows
# ---------------------------------------------------------------------------


@router.get("/maintenance")
async def get_maintenance_windows(
    status: Optional[str] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    items, total = await list_all(db, SREMaintenanceWindow, offset=offset, limit=limit, order_by="starts_at", status=status or "")
    return {
        "total": total,
        "items": [
            {"maintenance_id": m.maintenance_id, "scope": m.scope, "target": m.target, "description": m.description, "status": m.status, "starts_at": m.starts_at.isoformat(), "ends_at": m.ends_at.isoformat()}
            for m in items
        ],
    }


@router.post("/maintenance", status_code=201)
async def schedule_maintenance(
    body: MaintenanceIn,
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if body.ends_at <= body.starts_at:
        raise HTTPException(status_code=422, detail="ends_at must be after starts_at")
    window = SREMaintenanceWindow(
        maintenance_id=new_key("maint"),
        organization_id=body.created_by,
        scope=body.scope,
        target=body.target,
        description=body.description,
        starts_at=body.starts_at,
        ends_at=body.ends_at,
        created_by=body.created_by,
    )
    db.add(window)
    await db.flush()
    return {"maintenance_id": window.maintenance_id, "scope": window.scope, "target": window.target, "status": window.status, "starts_at": window.starts_at.isoformat(), "ends_at": window.ends_at.isoformat()}


# ---------------------------------------------------------------------------
# Status page
# ---------------------------------------------------------------------------


@router.get("/status/summary")
async def status_summary(current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    components, total = await list_all(db, SREStatusComponent, order_by="name")
    by_status: dict[str, int] = {}
    for component in components:
        by_status[component.status] = by_status.get(component.status, 0) + 1
    overall = "operational"
    if by_status.get("major_outage", 0):
        overall = "major_outage"
    elif by_status.get("partial_outage", 0) or by_status.get("degraded", 0):
        overall = "degraded"
    return {"overall": overall, "components": total, "by_status": by_status}


@router.get("/status/components")
async def get_status_components(
    public_only: bool = False,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    stmt = select(SREStatusComponent)
    if public_only:
        stmt = stmt.where(SREStatusComponent.public.is_(True))
    total = len(list((await db.execute(stmt)).scalars().all()))
    stmt = stmt.order_by(SREStatusComponent.name).offset(offset).limit(limit)
    components = list((await db.execute(stmt)).scalars().all())
    return {"total": total, "items": [c.to_dict() for c in components]}


@router.post("/status/components", status_code=201)
async def upsert_status_component(
    body: StatusComponentIn,
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if body.status not in STATUS_STATES:
        raise HTTPException(status_code=422, detail=f"invalid status {body.status}")
    component_id = body.component_id or f"status-{body.service_id or body.name}"
    component = await get_one(db, SREStatusComponent, component_id=component_id)
    if component is None:
        component = SREStatusComponent(component_id=component_id, service_id=body.service_id, name=body.name, description=body.description, status=body.status, region=body.region, public=body.public)
        db.add(component)
    else:
        component.name = body.name
        component.description = body.description
        component.status = body.status
        component.region = body.region
        component.public = body.public
        history = list(component.history or [])
        history.append({"status": body.status, "at": datetime.now(timezone.utc).isoformat()})
        component.history = history[-100:]
    await db.flush()
    return component.to_dict()


# ---------------------------------------------------------------------------
# Certificates
# ---------------------------------------------------------------------------


@router.get("/certificates")
async def get_certificates(
    status: Optional[str] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    items, total = await list_all(db, SRECertificate, offset=offset, limit=limit, order_by="hostname", status=status or "")
    return {"total": total, "items": [c.to_dict() for c in items]}


@router.post("/certificates", status_code=201)
async def add_certificate(
    body: CertificateIn,
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    cert = await ensure_certificate(db, name=body.name, hostname=body.hostname, auto_renew=body.auto_renew)
    return cert.to_dict()


@router.post("/certificates/check")
async def check_all_certificates(current_user: User = Depends(require_permission(Permission.admin_all)), db: AsyncSession = Depends(get_db)) -> dict:
    changed = await check_certificates(db)
    return {"checked": True, "flagged": len(changed), "items": changed}


# ---------------------------------------------------------------------------
# Deployments & canaries
# ---------------------------------------------------------------------------


@router.get("/deployments")
async def get_deployments(
    service_id: Optional[str] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    items, total = await list_deployments(db, service_id=service_id or "", offset=offset, limit=limit)
    return {"total": total, "items": items}


@router.post("/deployments", status_code=201)
async def start_deployment(
    body: DeploymentIn,
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    deployment = await record_deployment(db, service_id=body.service_id, version=body.version, strategy=body.strategy, region=body.region, commit=body.commit, environment=body.environment)
    return deployment.to_dict()


@router.post("/deployments/{deployment_id}/complete")
async def finish_deployment(
    deployment_id: str,
    body: DeploymentCompleteIn,
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    deployment = await get_one(db, SREDeployment, deployment_id=deployment_id)
    if deployment is None:
        raise HTTPException(status_code=404, detail=f"deployment {deployment_id} not found")
    deployment = await complete_deployment(db, deployment, status=body.status, duration_seconds=body.duration_seconds, error_rate_after=body.error_rate_after, latency_after_ms=body.latency_after_ms)
    if body.status == "failed":
        sre_events.deployment_failed(deployment.deployment_id, deployment.service_id, version=deployment.version)
    return deployment.to_dict()


@router.post("/deployments/{deployment_id}/rollback-check")
async def check_rollback_safety(
    deployment_id: str,
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    deployment = await get_one(db, SREDeployment, deployment_id=deployment_id)
    if deployment is None:
        raise HTTPException(status_code=404, detail=f"deployment {deployment_id} not found")
    safety = await rollback_safety(db, deployment.service_id, current_version=deployment.version)
    if not safety["safe"]:
        raise HTTPException(status_code=409, detail=safety["reason"])
    return safety


@router.get("/canaries")
async def get_canaries(
    service_id: Optional[str] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    items, total = await list_canaries(db, service_id=service_id or "", offset=offset, limit=limit)
    return {"total": total, "items": items}


@router.post("/canaries", status_code=201)
async def begin_canary(
    body: CanaryIn,
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    canary = await start_canary(
        db,
        deployment_id=body.deployment_id,
        service_id=body.service_id,
        baseline_error_rate=body.baseline_error_rate,
        baseline_latency_ms=body.baseline_latency_ms,
        error_rate_threshold=body.error_rate_threshold,
        latency_threshold_multiplier=body.latency_threshold_multiplier,
    )
    return canary.to_dict()


@router.post("/canaries/{canary_id}/evaluate")
async def evaluate_canary_run(
    canary_id: str,
    body: CanaryEvaluateIn,
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    canary = await get_one(db, SRECanaryRun, canary_id=canary_id)
    if canary is None:
        raise HTTPException(status_code=404, detail=f"canary {canary_id} not found")
    result = await evaluate_canary(db, canary, canary_error_rate=body.canary_error_rate, canary_latency_ms=body.canary_latency_ms)
    if result["abort"]:
        sre_events.rollback_triggered(canary.deployment_id, canary.service_id, reason=result["violations"][0] if result["violations"] else "canary regression")
    return result


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


@router.get("/dependencies/health")
async def get_dependency_health(current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    return {"dependencies": await latest_dependency_health(db)}


@router.post("/dependencies/check")
async def run_dependency_checks(current_user: User = Depends(require_permission(Permission.admin_all)), db: AsyncSession = Depends(get_db)) -> dict:
    from app.sre.dependencies import record_from_check_results
    from app.sre.health import health_checker

    results = await health_checker.run()
    await record_from_check_results(db, results)
    return {"status": health_checker.overall(results), "checks": {r.name: r.to_dict() for r in results}}


@router.post("/dependencies/{dependency}/outage-mode")
async def dependency_outage_mode(
    dependency: str,
    kind: str = "external",
    status: str = "down",
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return outage_plan(dependency, kind, status)


# ---------------------------------------------------------------------------
# Dead letter queue registry
# ---------------------------------------------------------------------------


@router.get("/dead-letters")
async def get_dead_letters(
    queue: Optional[str] = None,
    status: Optional[str] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    items, total = await list_all(db, SREDeadLetterEntry, offset=offset, limit=limit, order_by="created_at", queue=queue or "", status=status or "")
    return {"total": total, "items": [d.to_dict() for d in items]}


@router.post("/dead-letters", status_code=201)
async def register_dead_letter(
    body: DLQIn,
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    entry = SREDeadLetterEntry(
        entry_id=new_key("dlq"),
        event_id=body.event_id,
        source=body.source,
        queue=body.queue,
        error=body.error,
        attempts=body.attempts,
        payload_reference=body.payload_reference,
        correlation_id=body.correlation_id,
        status=body.status,
    )
    db.add(entry)
    await db.flush()
    return entry.to_dict()


@router.post("/dead-letters/{entry_id}/replay")
async def replay_dead_letter(
    entry_id: str,
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    entry = await get_by_id(db, SREDeadLetterEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"DLQ entry {entry_id} not found")
    entry.status = "replayed"
    await db.flush()
    return entry.to_dict()


# ---------------------------------------------------------------------------
# Reliability score & SRE analytics
# ---------------------------------------------------------------------------


@router.get("/reliability-score")
async def reliability_score(
    service_id: Optional[str] = None,
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await compute_reliability_score(db, service_id=service_id, days=days)


@router.get("/analytics")
async def sre_analytics(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """SRE analytics: incident metrics (MTTD/MTTA/MTTM/MTTR), change
    failure rate, alert counts. All computed from real records."""
    from datetime import timedelta

    since = datetime.now(timezone.utc) - timedelta(days=days)
    incidents = list(
        (await db.execute(select(SREIncident).where(SREIncident.detected_at >= since))).scalars().all()
    )
    deployments = list(
        (await db.execute(select(SREDeployment).where(SREDeployment.started_at >= since))).scalars().all()
    )
    alerts = list((await db.execute(select(SREAlert).where(SREAlert.fired_at >= since))).scalars().all())

    def _mean(deltas: list) -> Optional[float]:
        if not deltas:
            return None
        return round(sum(deltas) / len(deltas), 2)

    def _hours(seconds: Optional[float]) -> Optional[float]:
        return round(seconds / 3600, 2) if seconds is not None else None

    acked = [i for i in incidents if i.acknowledged_at and i.detected_at]
    mitigated = [i for i in incidents if i.mitigated_at and i.detected_at]
    resolved = [i for i in incidents if i.resolved_at and i.detected_at]
    failed = [d for d in deployments if d.status == "failed"]

    return {
        "period_days": days,
        "incidents": {
            "total": len(incidents),
            "mttd_hours": _hours(_mean([(i.acknowledged_at - i.detected_at).total_seconds() for i in acked])),
            "mtta_hours": _hours(_mean([(i.acknowledged_at - i.detected_at).total_seconds() for i in acked])),
            "mttm_hours": _hours(_mean([(i.mitigated_at - i.detected_at).total_seconds() for i in mitigated])),
            "mttr_hours": _hours(_mean([(i.resolved_at - i.detected_at).total_seconds() for i in resolved])),
            "open": sum(1 for i in incidents if i.status not in ("resolved", "closed")),
        },
        "deployments": {
            "total": len(deployments),
            "failed": len(failed),
            "change_failure_rate": round(len(failed) / len(deployments), 4) if deployments else 0.0,
        },
        "alerts": {"total": len(alerts), "firing": sum(1 for a in alerts if a.status == "firing")},
    }


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


@router.get("/reports")
async def get_reports(
    kind: Optional[str] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    items, total = await list_reports(db, kind=kind or "", offset=offset, limit=limit)
    return {"total": total, "items": items}


@router.post("/reports/generate")
async def generate_report(
    kind: str,
    days: int = Query(30, ge=1, le=365),
    service_id: Optional[str] = None,
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from datetime import timedelta

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    report_id = await build_report(db, kind=kind, period_start=start, period_end=end, service_id=service_id or "")
    report = await get_one(db, SREReport, report_id=report_id)
    return report.to_dict() if report else {"report_id": report_id}


# ---------------------------------------------------------------------------
# Automated operations (policy-controlled remediation)
# ---------------------------------------------------------------------------


@router.get("/ops/actions")
async def list_remediation_actions(
    result: Optional[str] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    items, total = await list_all(db, SRERemediationAction, offset=offset, limit=limit, order_by="created_at", result=result or "")
    return {"total": total, "items": [a.to_dict() for a in items]}


@router.post("/ops/actions", status_code=201)
async def execute_remediation(
    body: RemediationIn,
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Execute a policy-controlled remediation action.

    Unsafe actions (failover, drain, credential rotation) always require
    approval. Bounded by max_attempts - no infinite self-healing loops.
    """
    from app.sre.constants import UNSAFE_ACTIONS

    action = SRERemediationAction(
        action_id=new_key("remed"),
        action=body.action,
        target=body.target,
        reason=body.reason,
        evidence=body.evidence,
        policy=body.policy,
        authorized=body.authorized,
        requires_approval=body.requires_approval or body.action in UNSAFE_ACTIONS,
        approved_by=body.approved_by,
        max_attempts=max(1, min(body.max_attempts, 5)),
    )
    db.add(action)
    await db.flush()
    if action.requires_approval and not action.approved_by:
        action.result = "pending"
        return action.to_dict()
    # Safe, authorized action executes (record-only for auditability).
    action.authorized = True
    action.result = "success"
    action.executed_at = datetime.now(timezone.utc)
    await db.flush()
    return action.to_dict()


@router.post("/ops/actions/{action_id}/approve")
async def approve_remediation(
    action_id: str,
    approved_by: str,
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    action = await get_one(db, SRERemediationAction, action_id=action_id)
    if action is None:
        raise HTTPException(status_code=404, detail=f"remediation action {action_id} not found")
    action.approved_by = approved_by
    action.authorized = True
    action.result = "success"
    action.executed_at = datetime.now(timezone.utc)
    await db.flush()
    return action.to_dict()


# ---------------------------------------------------------------------------
# Dashboard & seeding
# ---------------------------------------------------------------------------


@router.get("/dashboard")
async def sre_dashboard(current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)) -> dict:
    """Aggregated operational telemetry for the existing UI (no UI changes)."""
    from app.sre.dependencies import dependency_health_summary

    services, service_total = await list_all(db, SREService, limit=500)
    slos, slo_total = await list_all(db, SRESLO, limit=500, status="active")
    alerts, _ = await list_alerts(db, status="firing", limit=100)
    incidents, _ = await list_incidents(db, limit=100)
    active_incidents = [i for i in incidents if i["status"] not in ("resolved", "closed")]
    budgets = []
    for slo in slos:
        budget = await get_latest_budget(db, slo.slo_id)
        if budget:
            budgets.append(budget)
    exhausted = [b for b in budgets if b["status"] == "exhausted"]
    return {
        "services": {"total": service_total, "degraded": sum(1 for s in services if s.status == "degraded")},
        "slos": {"total": slo_total, "exhausted_budgets": len(exhausted)},
        "alerts": {"firing": len(alerts)},
        "incidents": {"active": len(active_incidents), "severe": sum(1 for i in active_incidents if i["severity"] in ("SEV0", "SEV1"))},
        "dependencies": await dependency_health_summary(db),
        "reliability": await compute_reliability_score(db, days=30),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/seed")
async def seed_catalog(
    force: bool = False,
    current_user: User = Depends(require_permission(Permission.admin_all)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await seed_defaults(db, force=force)
    return result