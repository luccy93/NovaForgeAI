"""Resilience API — Volume 60 Commit 1 + Commit 2.

Profiles, backup policies, backups, verification, restore, recovery plans,
disaster declarations, failover, RTO/RPO, chaos tests, recovery drills,
readiness, score, recommendations, reconciliation, hardening, dashboard.
"""

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import _get_current_user
from app.core.database import get_db
from app.resilience.platform import resilience_service
from app.resilience.chaos import chaos_service
from app.resilience.drills import drill_service
from app.resilience.hardening import hardening_service
from app.resilience.reconciliation import reconciliation_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/resilience", tags=["Resilience"])


def _tenant(user) -> str:
    oid = getattr(user, "organization_id", None) or getattr(user, "id", None)
    if not oid:
        raise HTTPException(status_code=403, detail="No tenant context")
    return str(oid)


def _svc(db: AsyncSession = Depends(get_db)):
    return db


def _iam_check(user, tenant: str, permission: str, resource_type: str = "resilience") -> None:
    try:
        from app.iam.policy_authorizer import policy_authorizer  # type: ignore

        ctx: dict[str, Any] = {}
        try:
            role = getattr(user, "role", None)
            if role:
                ctx["role"] = str(role)
        except Exception:
            pass
        decision = policy_authorizer.authorize(
            str(getattr(user, "id", "")),
            tenant,
            permission,
            resource_type=resource_type,
            context=ctx or {"role": "viewer"},
        )
        if not decision.get("allowed", True):
            raise HTTPException(status_code=403, detail=decision.get("reason", "Forbidden"))
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.debug("IAM check skipped (%s): %s", permission, exc)


def _audit_best(tenant: str, actor: str, action: str, resource_type: str, resource_id: str, details: dict | None = None) -> None:
    try:
        from app.iam.audit_service import audit_service  # type: ignore

        try:
            audit_service.log(
                org_id=tenant,
                actor_id=actor,
                actor_type="user",
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                result="success",
                details=details or {},
                tenant_id=tenant,
            )
        except TypeError:
            audit_service.log(tenant, resource_id, actor, action, resource_type=resource_type, resource_id=resource_id, details=details or {"tenant": tenant})
    except Exception as exc:  # noqa: BLE001
        logger.debug("audit skipped %s: %s", action, exc)


async def _emit_best(event_name: str, data: dict, tenant: str) -> None:
    try:
        from app.core.events import Event, EventType, event_bus  # type: ignore

        et = getattr(EventType, event_name, None)
        if et is None:
            et = getattr(EventType, "incident_detected", None)
            if et is None:
                return
        await event_bus.publish_nowait(Event(et, data, source="resilience-api", organization_id=tenant))
    except Exception as exc:  # noqa: BLE001
        logger.debug("emit failed %s: %s", event_name, exc)


class ProfileIn(BaseModel):
    service: str = Field(..., max_length=128)
    environment: str = "production"
    criticality: str = "MEDIUM"
    rto_minutes: Optional[int] = None
    rpo_minutes: Optional[int] = None
    region: Optional[str] = None
    availability_target: Optional[float] = None
    recovery_priority: int = 5
    dependencies: list = []
    fallback: dict = {}
    owner: Optional[str] = None


class BackupPolicyIn(BaseModel):
    name: str
    scope_type: str
    backup_type: str = "full"
    frequency: str = "daily"
    retention_days: int = 30
    destination: Optional[str] = None
    encryption_key_ref: Optional[str] = None
    immutable: bool = False
    isolated: bool = True
    verify_required: bool = True
    scope_target: Optional[str] = None


class BackupStartIn(BaseModel):
    scope_type: str
    scope_target: Optional[str] = None
    backup_type: str = "full"
    policy_id: Optional[str] = None
    retention_days: Optional[int] = None
    idempotency_key: Optional[str] = None
    metadata: dict = {}
    complete_immediately: bool = False
    location: Optional[str] = None


class VerifyIn(BaseModel):
    verification_type: str = "checksum"
    expected_checksum: Optional[str] = None
    restore_test: bool = False


class RestoreRequestIn(BaseModel):
    backup_id: str
    mode: str = "full"
    target_environment: str = "production"
    target_resource: Optional[str] = None
    isolated_test: bool = False
    point_in_time: Optional[datetime] = None
    approved_by: Optional[str] = None
    idempotency_key: Optional[str] = None


class RestoreVerifyIn(BaseModel):
    checks: dict = {}


class PlanIn(BaseModel):
    name: str
    service: str
    environment: str = "production"
    disaster_type: Optional[str] = None
    steps: list = []
    owner: Optional[str] = None


class DisasterIn(BaseModel):
    disaster_type: str
    reason: str
    severity: str = "HIGH"
    scope: dict = {}
    incident_id: Optional[str] = None


class FailoverIn(BaseModel):
    failover_type: str
    source_target: Optional[str] = None
    destination_target: Optional[str] = None
    service: Optional[str] = None
    restricted_data_regions: Optional[list] = None
    idempotency_key: Optional[str] = None


# ── Volume 60 Commit 2 models ──────────────────────────────────────────────

class ChaosTestIn(BaseModel):
    name: str = Field(..., max_length=256)
    scope: Any = Field(...)
    failure_type: str = Field(...)
    config: Optional[dict] = None
    policy_approved: bool = False
    approved_by: Optional[str] = None
    target: Optional[str] = None


class ChaosRunIn(BaseModel):
    target: Optional[str] = None


class ChaosCompleteIn(BaseModel):
    success: Optional[bool] = None
    passed: Optional[bool] = None
    results: Optional[dict] = None


class DrillIn(BaseModel):
    drill_type: str = Field(...)
    scope: Any = None
    schedule: Optional[Any] = None
    target_environment: Optional[str] = None


class GameDayIn(BaseModel):
    scenario: Optional[str] = None
    scope: Optional[Any] = None
    participants: Optional[list] = None
    start: Optional[Any] = None
    end: Optional[Any] = None
    results: Optional[dict] = None
    findings: Optional[list] = None
    drill_id: Optional[str] = None


class ReconcileIn(BaseModel):
    pre_state: Optional[dict] = None
    restored_state: Optional[dict] = None
    expected_state: Optional[dict] = None
    pre: Optional[dict] = None
    restored: Optional[dict] = None
    expected: Optional[dict] = None


class BackupProtectionIn(BaseModel):
    scope: str = Field("all", max_length=64)
    reason: str = Field(..., max_length=2000)


class FailureInjectionIn(BaseModel):
    test_id: str = Field(...)
    target: Optional[str] = None


@router.post("/profiles", status_code=201)
async def create_profile(payload: ProfileIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    try:
        prof = await resilience_service.create_profile(db, tenant=tenant, **payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": str(prof.id), "service": prof.service, "rto_minutes": prof.rto_minutes, "rpo_minutes": prof.rpo_minutes}


@router.get("/profiles")
async def list_profiles(user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    rows = await resilience_service.list_profiles(db, _tenant(user))
    return {"items": [{"id": str(r.id), "service": r.service, "environment": r.environment, "criticality": r.criticality, "rto": r.rto_minutes, "rpo": r.rpo_minutes} for r in rows]}


@router.post("/backup-policies", status_code=201)
async def create_backup_policy(payload: BackupPolicyIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    try:
        pol = await resilience_service.create_backup_policy(db, tenant=tenant, **payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": str(pol.id), "name": pol.name, "scope_type": pol.scope_type}


@router.get("/backup-policies")
async def list_backup_policies(user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    rows = await resilience_service.list_backup_policies(db, _tenant(user))
    return {"items": [{"id": str(r.id), "name": r.name, "scope_type": r.scope_type, "backup_type": r.backup_type} for r in rows]}


@router.post("/backups", status_code=201)
async def start_backup(payload: BackupStartIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    try:
        backup = await resilience_service.start_backup(
            db, tenant=tenant, scope_type=payload.scope_type, scope_target=payload.scope_target,
            backup_type=payload.backup_type, policy_id=payload.policy_id,
            created_by=str(getattr(user, "id", "")), retention_days=payload.retention_days,
            idempotency_key=payload.idempotency_key, metadata_json=payload.metadata,
        )
        if payload.complete_immediately:
            backup = await resilience_service.complete_backup(db, tenant, str(backup.id), location=payload.location, success=True)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": str(backup.id), "status": backup.status, "verification_status": backup.verification_status, "checksum": backup.checksum}


@router.get("/backups")
async def list_backups(scope_type: Optional[str] = None, status: Optional[str] = None, limit: int = Query(100, ge=1, le=1000),
                       user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    rows = await resilience_service.list_backups(db, _tenant(user), scope_type=scope_type, status=status, limit=limit)
    return {"items": [{"id": str(b.id), "scope_type": b.scope_type, "status": b.status, "verified": b.verification_status, "created_at": str(b.created_at)} for b in rows]}


@router.get("/backups/{backup_id}")
async def get_backup(backup_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    b = await resilience_service.get_backup(db, _tenant(user), backup_id)
    if not b:
        raise HTTPException(status_code=404, detail="Backup not found")
    return {"id": str(b.id), "status": b.status, "verified": b.verification_status, "checksum": b.checksum, "immutable": b.immutable, "isolated": b.isolated}


@router.post("/backups/{backup_id}/verify")
async def verify_backup(backup_id: str, payload: VerifyIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    try:
        ver = await resilience_service.verify_backup(
            db, tenant=tenant, backup_id=backup_id, verification_type=payload.verification_type,
            verified_by=str(getattr(user, "id", "")), expected_checksum=payload.expected_checksum,
            restore_test=payload.restore_test,
        )
    except ValueError as e:
        raise HTTPException(status_code=422 if "invalid" in str(e) else 404, detail=str(e))
    await db.commit()
    return {"id": str(ver.id), "status": ver.status, "result": ver.result}


@router.post("/restore", status_code=202)
async def request_restore(payload: RestoreRequestIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    try:
        job = await resilience_service.request_restore(
            db, tenant=tenant, backup_id=payload.backup_id, mode=payload.mode,
            target_environment=payload.target_environment, target_resource=payload.target_resource,
            isolated_test=payload.isolated_test, point_in_time=payload.point_in_time,
            requested_by=str(getattr(user, "id", "")), approved_by=payload.approved_by,
            idempotency_key=payload.idempotency_key,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": str(job.id), "state": job.state, "approval_status": job.approval_status, "safety_checks": job.safety_checks}


@router.post("/restore/{job_id}/run")
async def run_restore(job_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    try:
        job = await resilience_service.run_restore(db, tenant, job_id, actor=str(getattr(user, "id", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": str(job.id), "state": job.state}


@router.post("/restore/{job_id}/verify")
async def verify_restore(job_id: str, payload: RestoreVerifyIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    try:
        job = await resilience_service.verify_restore(db, tenant, job_id, checks=payload.checks)
    except ValueError as e:
        raise HTTPException(status_code=404 if "not found" in str(e) else 422, detail=str(e))
    await db.commit()
    return {"id": str(job.id), "state": job.state, "missing": (job.verification_result or {}).get("missing")}


@router.post("/restore/{job_id}/reconcile")
async def reconcile_restore(job_id: str, payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    try:
        rec = await resilience_service.reconcile_restore(db, tenant, job_id, pre_state=payload.get("pre"), restored_state=payload.get("restored"), expected_state=payload.get("expected"))
    except ValueError as e:
        raise HTTPException(status_code=404 if "not found" in str(e) else 422, detail=str(e))
    await db.commit()
    return rec


@router.post("/recovery-plans", status_code=201)
async def create_recovery_plan(payload: PlanIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    try:
        plan = await resilience_service.create_recovery_plan(db, tenant=tenant, **payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": str(plan.id), "name": plan.name, "service": plan.service}


@router.get("/recovery-plans/{plan_id}")
async def get_recovery_plan(plan_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    bundle = await resilience_service.get_recovery_plan(db, _tenant(user), plan_id)
    if not bundle:
        raise HTTPException(status_code=404, detail="Recovery plan not found")
    plan = bundle["plan"]
    return {
        "id": str(plan.id), "name": plan.name, "state": plan.state,
        "steps": [{"order": s.step_order, "action": s.action, "status": s.status, "requires_approval": s.requires_approval} for s in bundle["steps"]],
    }


@router.post("/recovery-plans/{plan_id}/execute")
async def execute_recovery_plan(plan_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    try:
        res = await resilience_service.execute_recovery_plan(db, tenant, plan_id, actor=str(getattr(user, "id", "")))
    except ValueError as e:
        raise HTTPException(status_code=404 if "not found" in str(e) else 422, detail=str(e))
    await db.commit()
    return res


@router.post("/disasters", status_code=201)
async def declare_disaster(payload: DisasterIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    try:
        evt = await resilience_service.declare_disaster(
            db, tenant=tenant, disaster_type=payload.disaster_type, reason=payload.reason,
            declared_by=str(getattr(user, "id", "")), scope=payload.scope,
            severity=payload.severity, incident_id=payload.incident_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": str(evt.id), "disaster_type": evt.disaster_type, "status": evt.status}


@router.post("/failovers", status_code=202)
async def start_failover(payload: FailoverIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    try:
        rec = await resilience_service.start_failover(
            db, tenant=tenant, failover_type=payload.failover_type, source_target=payload.source_target,
            destination_target=payload.destination_target, service=payload.service,
            authorized_by=str(getattr(user, "id", "")), restricted_data_regions=payload.restricted_data_regions,
            idempotency_key=payload.idempotency_key,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": str(rec.id), "status": rec.status, "data_residency_ok": rec.data_residency_ok}


@router.post("/failovers/{record_id}/promote")
async def promote_failover(record_id: str, payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    health_verified = payload.get("health_verified")
    try:
        rec = await resilience_service.promote_failover(db, tenant, record_id, health_verified=health_verified, actor=str(getattr(user, "id", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": str(rec.id), "status": rec.status, "health_verified": rec.health_verified}


@router.post("/failovers/{record_id}/traffic-shift")
async def shift_traffic(record_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    try:
        rec = await resilience_service.shift_traffic(db, tenant, record_id, actor=str(getattr(user, "id", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": str(rec.id), "traffic_shifted": rec.traffic_shifted}


@router.get("/rto-rpo/{service}")
async def compute_rto_rpo(service: str, environment: str = "production", user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    return await resilience_service.compute_rto_rpo(db, _tenant(user), service, environment)


# ── Volume 60 Commit 2 — Chaos tests ───────────────────────────────────────

@router.post("/chaos-tests", status_code=201)
async def create_chaos_test(payload: ChaosTestIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "resilience:manage", "chaos_test")
    try:
        row = await chaos_service.create_chaos_test(
            db,
            tenant=tenant,
            name=payload.name,
            scope=payload.scope,
            failure_type=payload.failure_type,
            config=payload.config or {},
            created_by=str(getattr(user, "id", "")),
            policy_approved=payload.policy_approved,
            approved_by=payload.approved_by,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    _audit_best(tenant, str(getattr(user, "id", "")), "chaos.test.created", "chaos_test", str(row.id), {"failure_type": payload.failure_type})
    await _emit_best("incident_detected", {"chaos_test": str(row.id), "failure_type": payload.failure_type}, tenant)
    return {"id": str(row.id), "name": row.name, "failure_type": row.failure_type, "status": row.status, "scope": row.scope, "policy_approved": row.policy_approved}


@router.get("/chaos-tests")
async def list_chaos_tests(
    status: Optional[str] = None,
    failure_type: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    user=Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant = _tenant(user)
    _iam_check(user, tenant, "resilience:read", "chaos_test")
    rows = await chaos_service.list_chaos_tests(db, tenant, status=status, failure_type=failure_type, limit=limit)
    return {"items": [{"id": str(r.id), "name": r.name, "failure_type": r.failure_type, "status": r.status, "scope": r.scope, "target": r.target, "created_at": str(r.created_at)} for r in rows]}


@router.post("/chaos-tests/{test_id}/run")
async def run_chaos_test(test_id: str, payload: ChaosRunIn | None = None, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "resilience:manage", "chaos_test")
    target = (payload.target if payload else None)
    try:
        row = await chaos_service.run_chaos_test(db, tenant, test_id, target=target)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=422, detail=msg)
    await db.commit()
    _audit_best(tenant, str(getattr(user, "id", "")), "chaos.test.run", "chaos_test", str(row.id), {"target": target})
    await _emit_best("incident_detected", {"chaos_test": str(row.id), "status": row.status}, tenant)
    return {"id": str(row.id), "status": row.status, "target": row.target, "started_at": str(row.started_at) if row.started_at else None}


@router.post("/chaos-tests/{test_id}/complete")
async def complete_chaos_test(test_id: str, payload: ChaosCompleteIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "resilience:manage", "chaos_test")
    try:
        row = await chaos_service.complete_chaos_test(
            db, tenant, test_id, success=payload.success, passed=payload.passed, results=payload.results
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=422, detail=msg)
    await db.commit()
    _audit_best(tenant, str(getattr(user, "id", "")), "chaos.test.completed", "chaos_test", str(row.id), {"passed": payload.passed if payload.passed is not None else payload.success})
    await _emit_best("incident_platform_resolved", {"chaos_test": str(row.id), "passed": (payload.passed if payload.passed is not None else payload.success)}, tenant)
    return {"id": str(row.id), "status": row.status, "results": row.results, "completed_at": str(row.completed_at) if row.completed_at else None}


# ── Recovery drills ────────────────────────────────────────────────────────

@router.post("/recovery-drills", status_code=201)
async def create_recovery_drill(payload: DrillIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "resilience:manage", "recovery_drill")
    try:
        row = await drill_service.schedule_drill(
            db,
            tenant=tenant,
            drill_type=payload.drill_type,
            scope=payload.scope or {},
            schedule=payload.schedule,
            created_by=str(getattr(user, "id", "")),
            target_environment=payload.target_environment,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    _audit_best(tenant, str(getattr(user, "id", "")), "drill.scheduled", "recovery_drill", str(row.id), {"drill_type": payload.drill_type})
    await _emit_best("resilience_recovery_started", {"drill": str(row.id), "type": row.drill_type}, tenant)
    return {"id": str(row.id), "drill_type": row.drill_type, "status": row.status, "scope": row.scope, "scheduled_at": str(row.scheduled_at) if row.scheduled_at else None}


@router.get("/recovery-drills")
async def list_recovery_drills(
    drill_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    user=Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant = _tenant(user)
    _iam_check(user, tenant, "resilience:read", "recovery_drill")
    rows = await drill_service.list_drills(db, tenant, drill_type=drill_type, status=status, limit=limit)
    return {"items": [{"id": str(r.id), "drill_type": r.drill_type, "status": r.status, "scope": r.scope, "scheduled_at": str(r.scheduled_at) if r.scheduled_at else None} for r in rows]}


@router.post("/recovery-drills/{drill_id}/run")
async def run_recovery_drill(drill_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "resilience:manage", "recovery_drill")
    try:
        row = await drill_service.run_drill(db, tenant, drill_id, actor=str(getattr(user, "id", "")))
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=422, detail=msg)
    await db.commit()
    _audit_best(tenant, str(getattr(user, "id", "")), "drill.running", "recovery_drill", str(row.id))
    await _emit_best("resilience_recovery_started", {"drill": str(row.id), "status": row.status}, tenant)
    return {"id": str(row.id), "status": row.status, "results": row.results, "started_at": str(row.started_at) if row.started_at else None}


@router.post("/recovery-drills/{drill_id}/game-day")
async def game_day_drill(drill_id: str, payload: GameDayIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "resilience:manage", "recovery_drill")
    try:
        row = await drill_service.record_game_day(
            db,
            tenant=tenant,
            drill_id=drill_id,
            scenario=payload.scenario,
            scope=payload.scope,
            participants=payload.participants,
            start=payload.start,
            end=payload.end,
            results=payload.results,
            findings=payload.findings,
            actor=str(getattr(user, "id", "")),
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=422, detail=msg)
    await db.commit()
    _audit_best(tenant, str(getattr(user, "id", "")), "drill.game_day.recorded", "recovery_drill", str(row.id))
    await _emit_best("resilience_recovery_completed", {"drill": str(row.id), "game_day": True}, tenant)
    return {"id": str(row.id), "status": row.status, "scenario": row.scenario, "participants": row.participants, "results": row.results, "findings": row.findings}


# ── Readiness / Score / Recommendations / Drift ────────────────────────────

@router.get("/readiness")
async def get_readiness(user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "resilience:read", "readiness")
    result = await drill_service.calculate_readiness(db, tenant)
    await _emit_best("observability_telemetry_received", {"readiness": result.get("level"), "tenant": tenant}, tenant)
    return result


@router.get("/resilience-score")
async def get_resilience_score(user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "resilience:read", "score")
    result = await drill_service.calculate_score(db, tenant)
    await _emit_best("observability_telemetry_received", {"score": result.get("score"), "tenant": tenant}, tenant)
    return result


@router.get("/recovery-recommendations")
async def get_recovery_recommendations(user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "resilience:read", "recommendations")
    recs = await drill_service.recommend(db, tenant)
    return {"items": recs, "count": len(recs)}


@router.get("/drift")
async def get_drift(user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "resilience:read", "drift")
    result = await drill_service.detect_drift(db, tenant)
    return result


# ── Reconciliation ─────────────────────────────────────────────────────────

@router.post("/reconcile/{job_id}")
async def reconcile_job(job_id: str, payload: ReconcileIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "resilience:manage", "restore_job")
    pre = payload.pre_state if payload.pre_state is not None else payload.pre
    restored = payload.restored_state if payload.restored_state is not None else payload.restored
    expected = payload.expected_state if payload.expected_state is not None else payload.expected
    try:
        result = await reconciliation_service.reconcile(
            db, tenant, job_id, pre_state=pre or {}, restored_state=restored or {}, expected_state=expected or {}
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower() or "invalid" in msg.lower():
            raise HTTPException(status_code=404 if "not found" in msg.lower() else 422, detail=msg)
        raise HTTPException(status_code=422, detail=msg)
    await db.commit()
    _audit_best(tenant, str(getattr(user, "id", "")), "reconciliation.completed", "resilience_reconciliation", job_id, {"passed": result.get("passed")})
    await _emit_best("resilience_restore_completed" if result.get("passed") else "resilience_restore_failed", {"job": job_id, "passed": result.get("passed")}, tenant)
    return result


@router.get("/reconciliation/{job_id}")
async def get_reconciliation(job_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "resilience:read", "restore_job")
    try:
        # Use recovery_observability + audit and direct job lookup for reconciliation payload
        obs = await reconciliation_service.recovery_observability(db, tenant, job_id)
        aud = await reconciliation_service.recovery_audit(db, tenant, job_id)
        # Also fetch raw reconciliation dict from job
        from app.resilience.models import ResilienceRestoreJob
        import uuid

        try:
            rid = uuid.UUID(str(job_id))
        except Exception:
            raise HTTPException(status_code=422, detail="invalid restore_job_id")
        job = await db.get(ResilienceRestoreJob, rid)
        if not job or job.tenant != tenant:
            raise HTTPException(status_code=404, detail="restore job not found")
        reconciliation = job.reconciliation or {}
    except HTTPException:
        raise
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=422, detail=msg)
    return {"job_id": job_id, "reconciliation": reconciliation, "observability": obs, "audit": aud}


# ── Hardening / Chaos failure injection ────────────────────────────────────

@router.post("/backup-protection", status_code=201)
async def enable_backup_protection(payload: BackupProtectionIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "resilience:manage", "hardening")
    try:
        result = await hardening_service.enable_backup_protection(db, tenant, scope=payload.scope, reason=payload.reason, actor=str(getattr(user, "id", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    _audit_best(tenant, str(getattr(user, "id", "")), "hardening.backup_protection.enabled", "resilience_hardening", str(result.get("event_id", "")), {"scope": payload.scope})
    await _emit_best("resilience_backup_started", {"event": "BackupProtectionEnabled", "scope": payload.scope}, tenant)
    return result


@router.post("/chaos/failure-injection")
async def inject_chaos_failure(payload: FailureInjectionIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "resilience:manage", "chaos_test")
    try:
        result = await chaos_service.inject_failure(db, tenant, payload.test_id, target=payload.target)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=422, detail=msg)
    await db.commit()
    _audit_best(tenant, str(getattr(user, "id", "")), "chaos.failure.injected", "chaos_test", payload.test_id, {"target": payload.target})
    await _emit_best("incident_detected", {"chaos_test": payload.test_id, "target": payload.target}, tenant)
    return result


@router.get("/dashboard")
async def dashboard(user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    return await resilience_service.dashboard(db, _tenant(user))
