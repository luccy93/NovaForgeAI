"""Resilience API — Volume 60 Commit 1.

Profiles, backup policies, backups, verification, restore, recovery plans,
disaster declarations, failover, RTO/RPO, dashboard.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import _get_current_user
from app.core.database import get_db
from app.resilience.platform import resilience_service

router = APIRouter(prefix="/resilience", tags=["Resilience"])


def _tenant(user) -> str:
    oid = getattr(user, "organization_id", None) or getattr(user, "id", None)
    if not oid:
        raise HTTPException(status_code=403, detail="No tenant context")
    return str(oid)


def _svc(db: AsyncSession = Depends(get_db)):
    return db


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


@router.get("/dashboard")
async def dashboard(user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    return await resilience_service.dashboard(db, _tenant(user))
