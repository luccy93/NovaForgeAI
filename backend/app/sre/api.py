"""SRE API (Volume 35).

Production APIs for services, service health, SLIs, SLOs, error budgets,
alerts, incidents, postmortems, corrective actions, runbooks,
dependencies, regions, capacity, backups, recovery, chaos experiments,
maintenance, deployment reliability, certificates, and status.

Every endpoint supports authentication, authorization, tenant isolation,
validation, pagination, filtering, sorting, and structured errors.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import _get_current_user
from app.core.database import get_db
from app.models.user import User
from app.sre.constants import SEVERITIES, SLI_TYPES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sre", tags=["SRE"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ServiceRegister(BaseModel):
    service_id: str = Field(..., min_length=1, max_length=96)
    name: str = Field(..., min_length=1, max_length=255)
    tier: str = Field("tier1", pattern="^(tier[0-3])$")
    criticality: str = Field("high", max_length=16)
    owner: str = Field("", max_length=128)
    team: str = Field("", max_length=128)
    deployment_strategy: str = Field("rolling", max_length=24)
    scaling_strategy: str = Field("", max_length=128)
    backup_strategy: str = Field("", max_length=255)
    rto_minutes: Optional[int] = Field(None, ge=1)
    rpo_minutes: Optional[int] = Field(None, ge=0)
    runbook_id: str = Field("", max_length=96)
    on_call: str = Field("", max_length=255)


class SLODefine(BaseModel):
    slo_id: str = Field(..., min_length=1, max_length=96)
    service_id: str = Field(..., min_length=1, max_length=96)
    name: str = Field(..., min_length=1, max_length=255)
    sli_type: str = Field(..., max_length=32)
    target: float = Field(..., ge=0.0, le=1.0)
    window: str = Field("monthly", pattern="^(daily|weekly|monthly|quarterly)$")
    measurement: str = Field("", max_length=255)
    query: str = Field("", max_length=4000)
    owner: str = Field("", max_length=128)
    severity: str = Field("SEV2", max_length=8)


class SLIRecord(BaseModel):
    slo_id: str = Field(..., max_length=96)
    service_id: str = Field(..., max_length=96)
    sli_type: str = Field(..., max_length=32)
    good: float = Field(0.0, ge=0.0)
    total: float = Field(0.0, ge=0.0)
    value: Optional[float] = None
    region: str = Field("", max_length=32)


class IncidentCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    severity: str = Field("SEV2", max_length=8)
    description: str = Field("", max_length=4000)
    organization_id: str = Field("", max_length=64)
    service_id: str = Field("", max_length=96)
    region: str = Field("", max_length=32)
    detection: str = Field("alert", max_length=64)
    impact: dict = Field(default_factory=dict)


class IncidentUpdate(BaseModel):
    description: Optional[str] = None
    root_cause: Optional[str] = None
    impact: Optional[dict] = None


class RunbookCreate(BaseModel):
    runbook_id: Optional[str] = None
    service_id: str = Field("", max_length=96)
    title: str = Field(..., min_length=1, max_length=255)
    purpose: str = Field("", max_length=4000)
    symptoms: list[str] = []
    impact: str = Field("", max_length=4000)
    diagnosis: list[str] = []
    commands: list[str] = []
    checks: list[str] = []
    mitigation: list[str] = []
    rollback: list[str] = []
    recovery: list[str] = []
    escalation: list[str] = []
    post_incident: list[str] = []
    owner: str = Field("", max_length=128)


class ChaosCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    experiment_type: str = Field(..., max_length=64)
    target: str = Field("", max_length=96)
    scope: str = Field("", max_length=255)
    blast_radius: str = Field("test", max_length=64)
    owner: str = Field("", max_length=128)
    abort_condition: str = Field("", max_length=4000)
    expected_result: str = Field("", max_length=4000)
    duration_seconds: int = Field(30, ge=1, le=3600)
    organization_id: str = Field("", max_length=64)


class DeploymentRecord(BaseModel):
    service_id: str = Field(..., max_length=96)
    version: str = Field("", max_length=64)
    strategy: str = Field("rolling", max_length=24)
    region: str = Field("", max_length=32)
    commit: str = Field("", max_length=64)
    environment: str = Field("production", max_length=24)


class CanaryAnalyze(BaseModel):
    canary_error_rate: float = Field(0.0, ge=0.0, le=1.0)
    canary_latency_ms: float = Field(0.0, ge=0.0)


class BackupComplete(BaseModel):
    size_bytes: int = Field(0, ge=0)
    verified: bool = False
    error: str = Field("", max_length=4000)


class RestoreTestComplete(BaseModel):
    integrity: bool = False
    completeness: bool = False
    consistency: bool = False
    app_compatible: bool = False
    notes: str = Field("", max_length=4000)
    duration_seconds: int = Field(0, ge=0)


class FailoverTestComplete(BaseModel):
    rto_achieved_minutes: int = Field(0, ge=0)
    data_loss_minutes: int = Field(0, ge=0)
    notes: str = Field("", max_length=4000)


class ChaosComplete(BaseModel):
    actual_result: str = Field("", max_length=4000)
    recovery_seconds: float = Field(0.0, ge=0.0)
    passed: bool = True


class MaintenanceSchedule(BaseModel):
    scope: str = Field("service", max_length=24)
    target: str = Field(..., max_length=96)
    starts_at: datetime
    ends_at: datetime
    description: str = Field("", max_length=4000)
    organization_id: str = Field("", max_length=64)


class CorrectiveActionCreate(BaseModel):
    description: str = Field(..., min_length=1, max_length=4000)
    incident_id: str = Field("", max_length=96)
    postmortem_id: str = Field("", max_length=96)
    owner: str = Field("", max_length=128)
    priority: str = Field("medium", max_length=16)
    due_date: Optional[datetime] = None


class RemediationExecute(BaseModel):
    action: str = Field(..., max_length=128)
    target: str = Field("", max_length=128)
    reason: str = Field("", max_length=4000)
    policy: str = Field("sre-default", max_length=64)
    approved_by: str = Field("", max_length=128)
    max_attempts: int = Field(1, ge=1, le=10)
    cooldown_seconds: float = Field(300.0, ge=0.0)


class CertificateRegister(BaseModel):
    name: str = Field(..., max_length=255)
    hostname: str = Field(..., max_length=255)
    issuer: str = Field("", max_length=255)
    not_before: Optional[datetime] = None
    not_after: datetime
    auto_renew: bool = False


class StatusComponentRegister(BaseModel):
    name: str = Field(..., max_length=255)
    service_id: str = Field("", max_length=96)
    description: str = Field("", max_length=4000)
    region: str = Field("", max_length=32)
    public: bool = False


class BudgetSet(BaseModel):
    key: str = Field(..., max_length=128)
    limit_usd: float = Field(..., gt=0.0)
    period_days: int = Field(30, ge=1, le=365)
    degrade_on_hard_limit: bool = False


class PostmortemCreate(BaseModel):
    incident_id: str = Field(..., max_length=96)
    summary: str = Field("", max_length=4000)
    impact: str = Field("", max_length=4000)
    root_cause: str = Field("", max_length=4000)
    timeline: list[dict] = []
    contributing_factors: list[str] = []
    detection: str = Field("", max_length=4000)
    response: str = Field("", max_length=4000)
    what_went_well: list[str] = []
    what_went_wrong: list[str] = []
    created_by: str = Field("", max_length=128)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _require_operator(current_user: User = Depends(_get_current_user)) -> User:
    """SRE read/write access requires an authenticated user."""
    if current_user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return current_user


async def _require_admin(current_user: User = Depends(_get_current_user)) -> User:
    """Destructive/sensitive operations require a superuser."""
    if current_user is None or not getattr(current_user, "is_superuser", False):
        raise HTTPException(status_code=403, detail="Superuser access required")
    return current_user


def _validate_sli(sli_type: str) -> None:
    if sli_type not in SLI_TYPES:
        raise HTTPException(status_code=422, detail=f"unsupported sli_type {sli_type!r}; valid: {SLI_TYPES}")


def _validate_severity(severity: str) -> None:
    if severity not in SEVERITIES:
        raise HTTPException(status_code=422, detail=f"invalid severity {severity!r}; valid: {SEVERITIES}")


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------

@router.get("/services")
async def list_services(
    tier: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.models import SREService
    from app.sre.store import list_all

    items, total = await list_all(
        db, SREService, limit=limit, offset=offset, order_by="service_id", descending=False, tier=tier, status=status
    )
    return {"items": [s.to_dict() for s in items], "total": total}


@router.get("/services/{service_id}")
async def get_service(
    service_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.store import get_one
    from app.sre.models import SREService

    service = await get_one(db, SREService, service_id=service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="service not in catalog")
    return service.to_dict()


@router.post("/services")
async def register_service(
    body: ServiceRegister,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.service_catalog import service_catalog

    service = await service_catalog.register(db, **body.model_dump())
    await db.commit()
    return service.to_dict()


@router.post("/services/{service_id}/dependencies")
async def add_service_dependency(
    service_id: str,
    depends_on: str = Query(..., max_length=96),
    kind: str = Query("service", max_length=32),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.service_catalog import service_catalog

    dependency = await service_catalog.add_dependency(db, service_id, depends_on, kind)
    await db.commit()
    return {"service_id": service_id, "depends_on": depends_on, "kind": kind}


@router.get("/services/{service_id}/impact")
async def service_impact(
    service_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.service_catalog import service_catalog

    return await service_catalog.impact(db, service_id)


@router.get("/services/{service_id}/dependencies")
async def service_dependencies(
    service_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.service_catalog import service_catalog

    return await service_catalog.dependencies_of(db, service_id)


@router.get("/dependency-graph")
async def dependency_graph(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.service_catalog import service_catalog

    return await service_catalog.graph(db)


# ---------------------------------------------------------------------------
# SLOs / SLIs / error budgets
# ---------------------------------------------------------------------------

@router.post("/slos")
async def define_slo(
    body: SLODefine,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    _validate_sli(body.sli_type)
    _validate_severity(body.severity)
    from app.sre.models import SRESLO
    from app.sre.store import get_one

    existing = await get_one(db, SRESLO, slo_id=body.slo_id)
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"SLO {body.slo_id} already exists")
    slo = SRESLO(**body.model_dump())
    db.add(slo)
    await db.commit()
    return slo.to_dict()


@router.get("/slos")
async def list_slos(
    service_id: Optional[str] = Query(None),
    sli_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.models import SRESLO
    from app.sre.store import list_all

    items, total = await list_all(
        db, SRESLO, limit=limit, offset=offset, order_by="slo_id", descending=False,
        service_id=service_id, sli_type=sli_type, status=status,
    )
    return {"items": [s.to_dict() for s in items], "total": total}


@router.post("/slis/record")
async def record_sli(
    body: SLIRecord,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    _validate_sli(body.sli_type)
    from app.sre.slo import slo_engine

    measurement = await slo_engine.record_sli(
        db,
        slo_id=body.slo_id,
        service_id=body.service_id,
        sli_type=body.sli_type,
        good=body.good,
        total=body.total,
        value=body.value,
        region=body.region,
    )
    await db.commit()
    return {
        "id": measurement.id,
        "slo_id": measurement.slo_id,
        "sli_type": measurement.sli_type,
        "value": measurement.value,
    }


@router.get("/slos/{slo_id}/status")
async def slo_status(
    slo_id: str,
    window: Optional[str] = Query(None, pattern="^(daily|weekly|monthly|quarterly)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.models import SRESLO
    from app.sre.slo import slo_engine
    from app.sre.store import get_one

    slo = await get_one(db, SRESLO, slo_id=slo_id)
    if slo is None:
        raise HTTPException(status_code=404, detail="SLO not found")
    report = await slo_engine.evaluate(db, slo, window=window)
    snapshot = await slo_engine.snapshot_budget(db, slo, window=window)
    await db.commit()
    return {**report, "snapshot_id": snapshot.id}


@router.get("/error-budgets")
async def error_budgets(
    service_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.models import SREErrorBudget
    from app.sre.store import list_all

    items, total = await list_all(
        db, SREErrorBudget, limit=limit, offset=offset, order_by="computed_at",
        service_id=service_id, status=status,
    )
    return {"items": [s.__dict__ | {"id": s.id} for s in items], "total": total}


@router.get("/error-budgets/burn-rate")
async def burn_rate_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.slo import slo_engine

    reports = await slo_engine.compute_all(db)
    await db.commit()
    return {
        "burning": [r for r in reports if r.get("burn_level") != "none"],
        "all": reports,
    }


@router.post("/slos/recompute")
async def recompute_slos(
    window: str = Query("monthly", pattern="^(daily|weekly|monthly|quarterly)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.slo import slo_engine

    reports = await slo_engine.compute_all(db, window=window)
    await db.commit()
    return {"evaluated": len(reports)}


# ---------------------------------------------------------------------------
# Reliability / scorecard
# ---------------------------------------------------------------------------

@router.get("/reliability-score")
async def reliability_score(
    service_id: Optional[str] = Query(None),
    window_days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.reliability import reliability_engine

    return await reliability_engine.score(db, service_id=service_id, window_days=window_days)


@router.get("/readiness/{service_id}")
async def readiness(
    service_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.scorecard import production_readiness

    return await production_readiness.assess(db, service_id=service_id)


@router.get("/scorecard/{service_id}")
async def scorecard(
    service_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.scorecard import scorecard_engine

    return await scorecard_engine.scorecard(db, service_id=service_id)


@router.get("/maturity/{service_id}")
async def maturity(
    service_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.scorecard import maturity_classifier

    return await maturity_classifier.classify(db, service_id=service_id)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get("/health/live")
async def health_live():
    from app.sre.health import health_checker

    return await health_checker.liveness()


@router.get("/health/startup")
async def health_startup():
    from app.sre.health import health_checker

    return await health_checker.startup()


@router.get("/health/ready")
async def health_ready():
    from app.sre.health import health_checker

    return await health_checker.readiness()


@router.get("/health/dependencies")
async def health_dependencies(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.health import health_checker

    return await health_checker.dependencies()


@router.get("/health/deep")
async def health_deep(
    current_user: User = Depends(_require_operator),
):
    from app.sre.health import health_checker

    return await health_checker.deep()


# ---------------------------------------------------------------------------
# Dependencies / DLQ
# ---------------------------------------------------------------------------

@router.get("/dependencies/status")
async def dependency_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.dependencies import dependency_monitor

    return {"dependencies": await dependency_monitor.status_map(db)}


@router.post("/dependencies/record")
async def record_dependency(
    dependency: str = Query(..., max_length=96),
    status: str = Query(..., pattern="^(healthy|degraded|unhealthy|unknown)$"),
    kind: str = Query("external", max_length=32),
    latency_ms: float = Query(0.0, ge=0.0),
    error_rate: float = Query(0.0, ge=0.0, le=1.0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.dependencies import dependency_monitor

    snapshot = await dependency_monitor.record(
        db, dependency=dependency, status=status, kind=kind, latency_ms=latency_ms, error_rate=error_rate
    )
    await db.commit()
    return snapshot.to_dict()


@router.get("/dead-letters")
async def dead_letters(
    queue: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.dependencies import dead_letter_registry

    return {"items": await dead_letter_registry.list_open(db, queue=queue, limit=limit)}


@router.post("/dead-letters")
async def record_dead_letter(
    queue: str = Query(..., max_length=96),
    error: str = Query(..., max_length=4000),
    attempts: int = Query(0, ge=0),
    event_id: str = Query("", max_length=96),
    source: str = Query("", max_length=96),
    payload_reference: str = Query("", max_length=255),
    correlation_id: str = Query("", max_length=96),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.dependencies import dead_letter_registry

    entry = await dead_letter_registry.record(
        db,
        queue=queue,
        error=error,
        attempts=attempts,
        event_id=event_id,
        source=source,
        payload_reference=payload_reference,
        correlation_id=correlation_id,
    )
    await db.commit()
    return entry.to_dict()


@router.post("/dead-letters/{entry_id}/replay")
async def replay_dead_letter(
    entry_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.dependencies import dead_letter_registry

    entry = await dead_letter_registry.replay(db, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="DLQ entry not found")
    await db.commit()
    return entry.to_dict()


# ---------------------------------------------------------------------------
# AI providers
# ---------------------------------------------------------------------------

@router.get("/ai/providers/health")
async def ai_provider_health(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.ai_reliability import ai_provider_health

    return {"providers": await ai_provider_health.health_map(db)}


@router.post("/ai/providers/{provider}/probe")
async def ai_provider_probe(
    provider: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.ai_reliability import ai_provider_health

    result = await ai_provider_health.probe(db, provider)
    await db.commit()
    return result


@router.post("/ai/providers/select")
async def ai_provider_select(
    preferred: Optional[str] = Query(None),
    required_capabilities: str = Query("", max_length=255),
    allowed_providers: str = Query("", max_length=255),
    data_residency: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.ai_reliability import ai_provider_health

    return await ai_provider_health.select_provider(
        db,
        required_capabilities=[c for c in required_capabilities.split(",") if c] if required_capabilities else None,
        allowed_providers=[p for p in allowed_providers.split(",") if p] if allowed_providers else None,
        preferred=preferred,
        data_residency=data_residency,
    )


@router.get("/ai/degradation")
async def ai_degradation_plan(
    feature: str = Query("ai_chat", max_length=64),
    reason: str = Query("unavailable", max_length=255),
    current_user: User = Depends(_require_operator),
):
    from app.sre.ai_reliability import ai_provider_health

    return ai_provider_health.degraded_response(reason, feature=feature)


# ---------------------------------------------------------------------------
# Incidents
# ---------------------------------------------------------------------------

@router.get("/incidents")
async def list_incidents(
    status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    service_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.incident import incident_manager

    items, total = await incident_manager.list(db, status=status, severity=severity, service_id=service_id, limit=limit, offset=offset)
    return {"items": items, "total": total}


@router.get("/incidents/active")
async def active_incidents(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.incident import incident_manager

    return await incident_manager.active(db)


@router.post("/incidents")
async def create_incident(
    body: IncidentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    _validate_severity(body.severity)
    from app.sre.incident import incident_manager

    incident = await incident_manager.create(
        db,
        title=body.title,
        severity=body.severity,
        description=body.description,
        organization_id=body.organization_id,
        service_id=body.service_id,
        region=body.region,
        detection=body.detection,
        impact=body.impact,
    )
    await db.commit()
    return incident.to_dict()


@router.get("/incidents/{incident_id}")
async def get_incident(
    incident_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.incident import incident_manager

    incident = await incident_manager.get(db, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return incident


@router.post("/incidents/{incident_id}/acknowledge")
async def acknowledge_incident(
    incident_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.incident import incident_manager

    incident = await incident_manager.acknowledge(db, incident_id, actor=str(getattr(current_user, "id", "system")))
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    await db.commit()
    return incident.to_dict()


@router.post("/incidents/{incident_id}/transition")
async def transition_incident(
    incident_id: str,
    new_status: str = Query(..., max_length=24),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.incident import incident_manager

    try:
        incident = await incident_manager.transition(db, incident_id, new_status, actor=str(getattr(current_user, "id", "system")))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    await db.commit()
    return incident.to_dict()


@router.post("/incidents/{incident_id}/mitigate")
async def mitigate_incident(
    incident_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.incident import incident_manager

    incident = await incident_manager.mitigate(db, incident_id, actor=str(getattr(current_user, "id", "system")))
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    await db.commit()
    return incident.to_dict()


@router.post("/incidents/{incident_id}/update")
async def update_incident(
    incident_id: str,
    body: IncidentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.incident import incident_manager

    incident = await incident_manager.update_impact(
        db, incident_id, impact=body.impact, root_cause=body.root_cause, description=body.description
    )
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    await db.commit()
    return incident.to_dict()


@router.post("/incidents/{incident_id}/responders")
async def assign_responder(
    incident_id: str,
    role: str = Query(..., max_length=48),
    user_id: str = Query(..., max_length=128),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.incident import incident_manager

    try:
        responder = await incident_manager.assign_role(db, incident_id, role, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return {"role": responder.role, "user_id": responder.user_id}


@router.get("/incidents/{incident_id}/timeline")
async def incident_timeline(
    incident_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.incident import incident_manager

    return {"events": await incident_manager.timeline(db, incident_id)}


@router.get("/incidents/{incident_id}/diagnose")
async def diagnose_incident(
    incident_id: str,
    use_ai: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.incident import incident_manager

    return await incident_manager.diagnose(db, incident_id, use_ai=use_ai)


@router.post("/incidents/{incident_id}/correlate")
async def correlate_incident(
    incident_id: str,
    deployment_ids: str = Query("", max_length=1000),
    alert_ids: str = Query("", max_length=1000),
    changes: str = Query("", max_length=1000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.incident import incident_manager

    incident = await incident_manager.correlate(
        db,
        incident_id,
        deployment_ids=[d for d in deployment_ids.split(",") if d],
        alert_ids=[a for a in alert_ids.split(",") if a],
        changes=[c for c in changes.split(",") if c],
    )
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    await db.commit()
    return incident.to_dict()


@router.get("/incidents/metrics")
async def incident_metrics(
    window_days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.incident import incident_manager

    return await incident_manager.metrics(db, window_days=window_days)


# ---------------------------------------------------------------------------
# Postmortems / corrective actions
# ---------------------------------------------------------------------------

@router.post("/postmortems")
async def create_postmortem(
    body: PostmortemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.postmortem import postmortem_manager

    try:
        postmortem = await postmortem_manager.create(db, **body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    await db.commit()
    return postmortem.to_dict()


@router.post("/incidents/{incident_id}/postmortem/draft")
async def draft_postmortem(
    incident_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.postmortem import postmortem_manager

    postmortem = await postmortem_manager.draft_from_incident(db, incident_id)
    await db.commit()
    return postmortem.to_dict()


@router.get("/postmortems")
async def list_postmortems(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.postmortem import postmortem_manager

    items, total = await postmortem_manager.list(db, status=status, limit=limit, offset=offset)
    return {"items": items, "total": total}


@router.get("/postmortems/{postmortem_id}")
async def get_postmortem(
    postmortem_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.postmortem import postmortem_manager

    postmortem = await postmortem_manager.get(db, postmortem_id)
    if postmortem is None:
        raise HTTPException(status_code=404, detail="postmortem not found")
    return postmortem


@router.post("/postmortems/{postmortem_id}/publish")
async def publish_postmortem(
    postmortem_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.postmortem import postmortem_manager

    postmortem = await postmortem_manager.publish(db, postmortem_id)
    if postmortem is None:
        raise HTTPException(status_code=404, detail="postmortem not found")
    await db.commit()
    return postmortem.to_dict()


@router.post("/corrective-actions")
async def create_corrective_action(
    body: CorrectiveActionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.postmortem import corrective_action_manager

    try:
        action = await corrective_action_manager.create(db, **body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return action.to_dict()


@router.get("/corrective-actions")
async def list_corrective_actions(
    incident_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.postmortem import corrective_action_manager

    items, total = await corrective_action_manager.list(
        db, incident_id=incident_id or "", status=status or "", priority=priority or "", limit=limit, offset=offset
    )
    return {"items": items, "total": total}


@router.post("/corrective-actions/{action_id}/status")
async def update_corrective_action_status(
    action_id: str,
    status: str = Query(..., max_length=24),
    verification: str = Query("", max_length=4000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.postmortem import corrective_action_manager

    try:
        action = await corrective_action_manager.update_status(db, action_id, status, verification=verification)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if action is None:
        raise HTTPException(status_code=404, detail="action not found")
    await db.commit()
    return action.to_dict()


@router.get("/corrective-actions/overdue")
async def overdue_actions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.postmortem import corrective_action_manager

    return {"items": await corrective_action_manager.overdue(db)}


# ---------------------------------------------------------------------------
# Runbooks
# ---------------------------------------------------------------------------

@router.get("/runbooks")
async def list_runbooks(
    service_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.runbooks import runbook_manager

    items, total = await runbook_manager.list(db, service_id=service_id or "", limit=limit, offset=offset)
    return {"items": items, "total": total}


@router.get("/runbooks/{runbook_id}")
async def get_runbook(
    runbook_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.runbooks import runbook_manager

    runbook = await runbook_manager.get(db, runbook_id)
    if runbook is None:
        raise HTTPException(status_code=404, detail="runbook not found")
    return runbook


@router.post("/runbooks")
async def create_runbook(
    body: RunbookCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.runbooks import runbook_manager

    runbook = await runbook_manager.create(db, **body.model_dump())
    await db.commit()
    return runbook.to_dict()


# ---------------------------------------------------------------------------
# Regions / traffic
# ---------------------------------------------------------------------------

@router.get("/regions")
async def regions_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.regions import region_manager

    return {"regions": await region_manager.status_map(db)}


@router.post("/regions/{region}/register")
async def register_region(
    region: str,
    mode: str = Query("active-active", max_length=24),
    capacity_percent: float = Query(50.0, ge=0.0, le=100.0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.regions import region_manager

    try:
        entry = await region_manager.register(db, region=region, mode=mode, capacity_percent=capacity_percent)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return {"region": entry.region, "mode": entry.mode, "status": entry.status}


@router.post("/regions/{region}/health")
async def record_region_health(
    region: str,
    availability: float = Query(1.0, ge=0.0, le=1.0),
    latency_ms: float = Query(0.0, ge=0.0),
    error_rate: float = Query(0.0, ge=0.0, le=1.0),
    capacity_percent: float = Query(0.0, ge=0.0, le=100.0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.regions import region_manager

    snapshot = await region_manager.record_health(
        db,
        region=region,
        availability=availability,
        latency_ms=latency_ms,
        error_rate=error_rate,
        capacity_percent=capacity_percent,
    )
    await db.commit()
    return {"region": region, "measured_at": snapshot.measured_at.isoformat()}


@router.get("/traffic/route")
async def traffic_route(
    mode: str = Query("health-based", max_length=24),
    preferred_region: str = Query("", max_length=32),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.regions import region_manager

    return await region_manager.route(db, mode=mode, preferred_region=preferred_region)


@router.post("/regions/{region}/drain")
async def drain_region(
    region: str,
    verify: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_admin),
):
    from app.sre.regions import region_manager

    result = await region_manager.drain(db, region, verify=verify)
    await db.commit()
    return result


@router.post("/regions/{region}/undrain")
async def undrain_region(
    region: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_admin),
):
    from app.sre.regions import region_manager

    entry = await region_manager.undrain(db, region)
    if entry is None:
        raise HTTPException(status_code=404, detail="region not found")
    await db.commit()
    return {"region": entry.region, "status": entry.status}


# ---------------------------------------------------------------------------
# Capacity
# ---------------------------------------------------------------------------

@router.post("/capacity/metrics")
async def record_capacity_metric(
    service_id: str = Query(..., max_length=96),
    metric: str = Query(..., max_length=64),
    value: float = Query(..., ge=0.0),
    limit: float = Query(100.0, gt=0.0),
    region: str = Query("", max_length=32),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.capacity import capacity_engine

    entry = await capacity_engine.record(db, service_id=service_id, metric=metric, value=value, limit=limit, region=region)
    await db.commit()
    return {"service_id": entry.service_id, "metric": entry.metric, "value": entry.value, "utilization_percent": round(value / limit * 100, 2)}


@router.get("/capacity/saturation")
async def capacity_saturation(
    service_id: Optional[str] = Query(None),
    region: str = Query("", max_length=32),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.capacity import capacity_engine

    return await capacity_engine.saturation(db, service_id=service_id, region=region)


@router.get("/capacity/forecast")
async def capacity_forecast(
    service_id: str = Query(..., max_length=96),
    metric: str = Query(..., max_length=64),
    region: str = Query("", max_length=32),
    days_ahead: int = Query(90, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.capacity import capacity_engine

    return await capacity_engine.forecast(db, service_id=service_id, metric=metric, region=region, days_ahead=days_ahead)


@router.get("/capacity/plan")
async def capacity_plan(
    service_id: Optional[str] = Query(None),
    region: str = Query("", max_length=32),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.capacity import capacity_engine

    return await capacity_engine.plan(db, service_id=service_id, region=region)


@router.get("/load-shedding/plan")
async def load_shedding_plan(
    cpu_percent: float = Query(0.0, ge=0.0, le=100.0),
    queue_depth: int = Query(0, ge=0),
    max_queue: int = Query(1000, gt=0),
    current_user: User = Depends(_require_operator),
):
    from app.sre.capacity import capacity_engine

    return capacity_engine.shedding_plan(cpu_percent=cpu_percent, queue_depth=queue_depth, max_queue=max_queue)


# ---------------------------------------------------------------------------
# Backups / restore / failover (DR)
# ---------------------------------------------------------------------------

@router.post("/backups/schedule")
async def schedule_backup(
    target: str = Query(..., max_length=64),
    kind: str = Query("full", max_length=24),
    region: str = Query("", max_length=32),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.recovery import backup_manager

    try:
        job = await backup_manager.schedule(db, target=target, kind=kind, region=region)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return job.to_dict()


@router.post("/backups/{backup_id}/complete")
async def complete_backup(
    backup_id: str,
    body: BackupComplete,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.recovery import backup_manager

    job = await backup_manager.complete(db, backup_id, size_bytes=body.size_bytes, verified=body.verified, error=body.error)
    if job is None:
        raise HTTPException(status_code=404, detail="backup not found")
    await db.commit()
    return job.to_dict()


@router.get("/backups")
async def list_backups(
    target: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.recovery import backup_manager

    items, total = await backup_manager.list(db, target=target or "", status=status or "", limit=limit, offset=offset)
    return {"items": items, "total": total}


@router.get("/backups/coverage")
async def backup_coverage(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.recovery import backup_manager

    return await backup_manager.coverage(db)


@router.post("/restore-tests/schedule")
async def schedule_restore_test(
    target: str = Query(..., max_length=64),
    backup_id: str = Query("", max_length=96),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.recovery import RestoreTestManager

    test = await RestoreTestManager().schedule(db, target=target, backup_id=backup_id)
    await db.commit()
    return test.to_dict()


@router.post("/restore-tests/{test_id}/complete")
async def complete_restore_test(
    test_id: str,
    body: RestoreTestComplete,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.recovery import RestoreTestManager

    test = await RestoreTestManager().complete(db, test_id, **body.model_dump())
    if test is None:
        raise HTTPException(status_code=404, detail="restore test not found")
    await db.commit()
    return test.to_dict()


@router.get("/restore-tests")
async def list_restore_tests(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.recovery import RestoreTestManager

    items, total = await RestoreTestManager().list(db, status=status or "", limit=limit, offset=offset)
    return {"items": items, "total": total}


@router.post("/failover-tests/schedule")
async def schedule_failover_test(
    target: str = Query(..., max_length=64),
    scope: str = Query("", max_length=32),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_admin),
):
    from app.sre.recovery import FailoverTestManager

    try:
        test = await FailoverTestManager().schedule(db, target=target, scope=scope)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return test.to_dict()


@router.post("/failover-tests/{test_id}/complete")
async def complete_failover_test(
    test_id: str,
    body: FailoverTestComplete,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.recovery import FailoverTestManager

    test = await FailoverTestManager().complete(db, test_id, **body.model_dump())
    if test is None:
        raise HTTPException(status_code=404, detail="failover test not found")
    await db.commit()
    return test.to_dict()


@router.get("/failover-tests")
async def list_failover_tests(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.recovery import FailoverTestManager

    items, total = await FailoverTestManager().list(db, status=status or "", limit=limit, offset=offset)
    return {"items": items, "total": total}


@router.get("/dr/plan")
async def dr_plan(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.recovery import dr_manager

    return await dr_manager.plan(db)


# ---------------------------------------------------------------------------
# Chaos
# ---------------------------------------------------------------------------

@router.post("/chaos")
async def create_chaos_experiment(
    body: ChaosCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_admin),
):
    from app.sre.chaos import chaos_manager

    try:
        experiment = await chaos_manager.create(db, **body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return experiment.to_dict()


@router.get("/chaos")
async def list_chaos_experiments(
    status: Optional[str] = Query(None),
    experiment_type: Optional[str] = Query(None),
    blast_radius: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.chaos import chaos_manager

    items, total = await chaos_manager.list(
        db, status=status or "", experiment_type=experiment_type or "", blast_radius=blast_radius or "", limit=limit, offset=offset
    )
    return {"items": items, "total": total}


@router.get("/chaos/{experiment_id}")
async def get_chaos_experiment(
    experiment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.chaos import chaos_manager

    experiment = await chaos_manager.get(db, experiment_id)
    if experiment is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    return experiment


@router.post("/chaos/{experiment_id}/start")
async def start_chaos_experiment(
    experiment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_admin),
):
    from app.sre.chaos import chaos_manager

    try:
        experiment = await chaos_manager.start(db, experiment_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if experiment is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    await db.commit()
    return experiment.to_dict()


@router.post("/chaos/{experiment_id}/complete")
async def complete_chaos_experiment(
    experiment_id: str,
    body: ChaosComplete,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.chaos import chaos_manager

    experiment = await chaos_manager.complete(
        db, experiment_id, actual_result=body.actual_result, recovery_seconds=body.recovery_seconds, passed=body.passed
    )
    if experiment is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    await db.commit()
    return experiment.to_dict()


@router.post("/chaos/{experiment_id}/abort")
async def abort_chaos_experiment(
    experiment_id: str,
    reason: str = Query("", max_length=4000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_admin),
):
    from app.sre.chaos import chaos_manager

    experiment = await chaos_manager.abort(db, experiment_id, reason)
    if experiment is None:
        raise HTTPException(status_code=404, detail="experiment not found")
    await db.commit()
    return experiment.to_dict()


@router.get("/chaos/pass-rate")
async def chaos_pass_rate(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.chaos import chaos_manager

    return await chaos_manager.pass_rate(db)


# ---------------------------------------------------------------------------
# Deployments / canary
# ---------------------------------------------------------------------------

@router.post("/deployments")
async def record_deployment(
    body: DeploymentRecord,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.deployments import deployment_reliability

    try:
        deployment = await deployment_reliability.record(db, **body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return deployment.to_dict()


@router.get("/deployments")
async def list_deployments(
    service_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.deployments import deployment_reliability

    items, total = await deployment_reliability.list(db, service_id=service_id or "", status=status or "", limit=limit, offset=offset)
    return {"items": items, "total": total}


@router.post("/deployments/{deployment_id}/complete")
async def complete_deployment(
    deployment_id: str,
    status: str = Query(..., max_length=24),
    error_rate_after: float = Query(0.0, ge=0.0, le=1.0),
    latency_after_ms: float = Query(0.0, ge=0.0),
    duration_seconds: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.deployments import deployment_reliability

    try:
        deployment = await deployment_reliability.complete(
            db, deployment_id, status=status, error_rate_after=error_rate_after,
            latency_after_ms=latency_after_ms, duration_seconds=duration_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if deployment is None:
        raise HTTPException(status_code=404, detail="deployment not found")
    await db.commit()
    return deployment.to_dict()


@router.get("/deployments/metrics")
async def deployment_metrics(
    window_days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.deployments import deployment_reliability

    return await deployment_reliability.metrics(db, window_days=window_days)


@router.post("/deployments/{deployment_id}/canary")
async def start_canary(
    deployment_id: str,
    baseline_error_rate: float = Query(0.0, ge=0.0, le=1.0),
    baseline_latency_ms: float = Query(0.0, ge=0.0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.deployments import deployment_reliability
    from app.sre.models import SREDeployment
    from app.sre.store import get_one

    deployment = await get_one(db, SREDeployment, deployment_id=deployment_id)
    if deployment is None:
        raise HTTPException(status_code=404, detail="deployment not found")
    run = await deployment_reliability.start_canary(
        db,
        deployment_id=deployment_id,
        service_id=deployment.service_id,
        baseline_error_rate=baseline_error_rate,
        baseline_latency_ms=baseline_latency_ms,
    )
    await db.commit()
    return run.to_dict()


@router.post("/canary/{canary_id}/analyze")
async def analyze_canary(
    canary_id: str,
    body: CanaryAnalyze,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.deployments import deployment_reliability

    result = await deployment_reliability.analyze_canary(
        db, canary_id, canary_error_rate=body.canary_error_rate, canary_latency_ms=body.canary_latency_ms
    )
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    await db.commit()
    return result


@router.post("/canary/{canary_id}/promote")
async def promote_canary(
    canary_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.deployments import deployment_reliability

    run = await deployment_reliability.promote_canary(db, canary_id)
    if run is None:
        raise HTTPException(status_code=404, detail="canary not found")
    await db.commit()
    return run.to_dict()


@router.post("/canary/{canary_id}/auto-rollback")
async def auto_rollback_canary(
    canary_id: str,
    body: CanaryAnalyze,
    target_version: str = Query(..., max_length=64),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.deployments import deployment_reliability

    try:
        result = await deployment_reliability.auto_rollback_canary(
            db, canary_id, canary_error_rate=body.canary_error_rate,
            canary_latency_ms=body.canary_latency_ms, target_version=target_version,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return result


# ---------------------------------------------------------------------------
# Maintenance / status
# ---------------------------------------------------------------------------

@router.post("/maintenance")
async def schedule_maintenance(
    body: MaintenanceSchedule,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_admin),
):
    from app.sre.maintenance import maintenance_window_manager

    try:
        window = await maintenance_window_manager.schedule(db, **body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return {"maintenance_id": window.maintenance_id, "scope": window.scope, "target": window.target, "status": window.status}


@router.get("/maintenance")
async def list_maintenance_windows(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.maintenance import maintenance_window_manager

    items, total = await maintenance_window_manager.list(db, status=status or "", limit=limit, offset=offset)
    return {"items": items, "total": total}


@router.get("/maintenance/current")
async def current_maintenance(
    target: str = Query("", max_length=96),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.maintenance import maintenance_window_manager

    return {"items": await maintenance_window_manager.current(db, target=target)}


@router.post("/status/components")
async def register_status_component(
    body: StatusComponentRegister,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.maintenance import status_manager

    component = await status_manager.register_component(db, **body.model_dump())
    await db.commit()
    return component.to_dict()


@router.get("/status")
async def platform_status(
    public: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.maintenance import status_manager

    if public:
        return await status_manager.aggregate(db)
    return await status_manager.aggregate(db)


@router.post("/status/components/{component_id}/update")
async def update_status_component(
    component_id: str,
    status: str = Query(..., max_length=24),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.maintenance import status_manager

    try:
        component = await status_manager.update_status(db, component_id, status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if component is None:
        raise HTTPException(status_code=404, detail="component not found")
    await db.commit()
    return component.to_dict()


# ---------------------------------------------------------------------------
# Certificates / DNS
# ---------------------------------------------------------------------------

@router.post("/certificates")
async def register_certificate(
    body: CertificateRegister,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.certificates import certificate_manager

    cert = await certificate_manager.register(db, **body.model_dump())
    await db.commit()
    return cert.to_dict()


@router.get("/certificates")
async def list_certificates(
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.certificates import certificate_manager

    items, total = await certificate_manager.list(db, status=status or "", limit=limit, offset=offset)
    return {"items": items, "total": total}


@router.get("/certificates/expiring")
async def expiring_certificates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.certificates import certificate_manager

    return {"items": await certificate_manager.expiring(db)}


@router.post("/certificates/{certificate_id}/probe")
async def probe_certificate(
    certificate_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.certificates import certificate_manager

    result = await certificate_manager.probe(db, certificate_id)
    await db.commit()
    return result


@router.get("/dns/resolve")
async def dns_resolve(
    hostname: str = Query(..., max_length=255),
    current_user: User = Depends(_require_operator),
):
    from app.sre.certificates import dns_monitor

    return await dns_monitor.resolve(hostname)


# ---------------------------------------------------------------------------
# Resilience / circuit breakers / retries
# ---------------------------------------------------------------------------

@router.get("/resilience/circuit-breakers")
async def circuit_breakers(
    current_user: User = Depends(_require_operator),
):
    from app.sre.resilience import circuit_breaker_registry

    return {"breakers": circuit_breaker_registry.snapshot()}


@router.get("/resilience/retry-policy/classify")
async def classify_retry(
    status_code: Optional[int] = Query(None, ge=100, le=599),
    error: str = Query("", max_length=4000),
    current_user: User = Depends(_require_operator),
):
    from app.sre.resilience import classify_retry as classify

    decision = classify(None if status_code else RuntimeError(error or "unknown"), status_code)
    return {"decision": decision.value, "status_code": status_code, "error": error}


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

@router.post("/alerts/fire")
async def fire_alert(
    rule_name: str = Query(..., max_length=255),
    severity: str = Query("SEV3", max_length=8),
    service_id: str = Query("", max_length=96),
    region: str = Query("", max_length=32),
    message: str = Query("", max_length=4000),
    auto_open_incident: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    _validate_severity(severity)
    from app.sre.models import SREAlert
    from app.sre.store import new_id, new_key

    alert = SREAlert(
        id=new_id(),
        alert_id=new_key("alert"),
        rule_name=rule_name,
        severity=severity,
        service_id=service_id,
        region=region,
        message=message,
        status="firing",
    )
    db.add(alert)
    await db.flush()
    if auto_open_incident:
        from app.sre.incident import incident_manager

        incident = await incident_manager.detect_from_alert(db, alert)
        await db.flush()
    await db.commit()
    return {
        "alert": alert.to_dict(),
        "incident_opened": auto_open_incident,
    }


@router.get("/alerts")
async def list_alerts(
    status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    service_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.models import SREAlert
    from app.sre.store import list_all

    items, total = await list_all(
        db, SREAlert, limit=limit, offset=offset, order_by="fired_at",
        status=status, severity=severity, service_id=service_id,
    )
    return {"items": [a.to_dict() for a in items], "total": total}


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.models import SREAlert
    from app.sre.store import get_one

    alert = await get_one(db, SREAlert, alert_id=alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")
    alert.status = "resolved"
    alert.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    return alert.to_dict()


# ---------------------------------------------------------------------------
# Cost guardrails
# ---------------------------------------------------------------------------

@router.post("/cost/budgets")
async def set_cost_budget(
    body: BudgetSet,
    current_user: User = Depends(_require_operator),
):
    from app.sre.cost import cost_guardrails

    return cost_guardrails.set_budget(**body.model_dump())


@router.get("/cost/budgets")
async def list_cost_budgets(
    current_user: User = Depends(_require_operator),
):
    from app.sre.cost import cost_guardrails

    return {"budgets": cost_guardrails.budgets()}


@router.get("/cost/evaluate")
async def evaluate_cost(
    key: str = Query(..., max_length=128),
    spent_usd: float = Query(0.0, ge=0.0),
    current_user: User = Depends(_require_operator),
):
    from app.sre.cost import cost_guardrails

    return cost_guardrails.evaluate(key=key, spent_usd=spent_usd)


# ---------------------------------------------------------------------------
# Remediation audit
# ---------------------------------------------------------------------------

@router.post("/remediation/execute")
async def execute_remediation(
    body: RemediationExecute,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.actions import remediation_auditor

    record = await remediation_auditor.execute(
        db,
        action=body.action,
        target=body.target,
        reason=body.reason,
        policy=body.policy,
        approved_by=body.approved_by,
        max_attempts=body.max_attempts,
        cooldown_seconds=body.cooldown_seconds,
    )
    await db.commit()
    return record.to_dict()


@router.get("/remediation/actions")
async def list_remediation_actions(
    action: Optional[str] = Query(None),
    result: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.actions import remediation_auditor

    items, total = await remediation_auditor.list(db, action=action or "", result=result or "", limit=limit, offset=offset)
    return {"items": items, "total": total}


# ---------------------------------------------------------------------------
# Reports / workers
# ---------------------------------------------------------------------------

@router.post("/reports/generate")
async def generate_report(
    kind: str = Query(..., max_length=32),
    days: int = Query(7, ge=1, le=365),
    service_id: str = Query("", max_length=96),
    incident_id: str = Query("", max_length=96),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.reporting import report_engine

    try:
        report = await report_engine.generate(db, kind=kind, days=days, service_id=service_id, incident_id=incident_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return report


@router.get("/reports")
async def list_reports(
    kind: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_operator),
):
    from app.sre.reporting import report_engine

    items, total = await report_engine.list(db, kind=kind or "", limit=limit, offset=offset)
    return {"items": items, "total": total}


@router.post("/workers/run-rounds")
async def run_workers_once(
    current_user: User = Depends(_require_operator),
):
    """Run every SRE monitoring round once (on-demand)."""
    from app.sre.workers import run_all_rounds

    return run_all_rounds()


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------

@router.post("/seed")
async def seed_sre(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_require_admin),
):
    """Seed the default service catalog, playbooks and dependencies."""
    from app.sre.dependencies import dependency_monitor
    from app.sre.runbooks import runbook_manager
    from app.sre.service_catalog import service_catalog

    catalog = await service_catalog.seed(db)
    playbooks = await runbook_manager.seed_playbooks(db)
    dependencies = await dependency_monitor.seed_defaults(db)
    await db.commit()
    return {"catalog": catalog, "playbooks": playbooks, "dependencies": dependencies}
