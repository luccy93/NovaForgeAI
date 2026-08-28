"""Multi-Region API — Volume 62 Commit 1.

Regions registry, region-health, placement, routing, replication, failover,
failback, regional-capacity. Control-plane metadata only; regional operational
data stays in regional data planes. Reuses Volume 57 policy bridge, Volume 59
observability, Volume 60 resilience failover records.
"""

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import _get_current_user
from app.core.database import get_db
from app.regions.config import global_config_service
from app.regions.failover import failover_service
from app.regions.migration import tenant_migration_service
from app.regions.orchestrator import failover_orchestrator
from app.regions.placement import placement_service
from app.regions.recovery import (
    aiops_advisor,
    config_drift_service,
    drill_service,
    rejoin_service,
    traffic_shift_service,
)
from app.regions.registry import region_service
from app.regions.replication import replication_service
from app.regions.routing import routing_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/regions", tags=["Multi-Region"])


def _tenant(user) -> str:
    oid = getattr(user, "organization_id", None) or getattr(user, "id", None)
    if not oid:
        raise HTTPException(status_code=403, detail="No tenant context")
    return str(oid)


def _iam_check(user, tenant: str, permission: str, resource_type: str = "region") -> None:
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
            str(getattr(user, "id", "")), tenant, permission,
            resource_type=resource_type, context=ctx or {"role": "viewer"},
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
                org_id=tenant, actor_id=actor, actor_type="user", action=action,
                resource_type=resource_type, resource_id=resource_id, result="success",
                details=details or {}, tenant_id=tenant,
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
            return
        await event_bus.publish_nowait(Event(et, data, source="regions-api", organization_id=tenant))
    except Exception as exc:  # noqa: BLE001
        logger.debug("emit failed %s: %s", event_name, exc)


# ── Pydantic models ──────────────────────────────────────────────────────────

class RegionIn(BaseModel):
    region_id: str = Field(..., max_length=64)
    name: str = Field(..., max_length=128)
    provider: str = Field(..., max_length=64)
    location: str = Field(..., max_length=128)
    environment: str = "production"
    data_residency: dict = {}
    capacity: dict = {}
    status: str = "ACTIVE"
    capabilities: dict = {}


class RegionStatusIn(BaseModel):
    status: str
    reason: Optional[str] = None


class CapabilitiesIn(BaseModel):
    capabilities: dict


class HealthIn(BaseModel):
    status: str
    checks: dict = {}


class PlacementIn(BaseModel):
    primary_region: Optional[str] = None
    secondary_region: Optional[str] = None
    allowed_regions: list = []
    data_classification: Optional[str] = None
    residency_policy: dict = {}
    policy_version: str = "1.0.0"


class PlacementEvalIn(BaseModel):
    data_classification: Optional[str] = None
    region: str
    provider: Optional[str] = None
    capacity: dict = {}


class RoutingResolveIn(BaseModel):
    service: str
    data_classification: Optional[str] = None
    preferred_region: Optional[str] = None
    criticality: str = "HIGH"
    capacity_aware: bool = True


class RoutingPolicyIn(BaseModel):
    service: str
    primary_region: Optional[str] = None
    preferred_secondary: Optional[str] = None
    emergency_fallback: Optional[str] = None
    consistency: str = "CONFIGURABLE"
    metadata: dict = {}


class ReplicationIn(BaseModel):
    source_region: str
    dest_region: str
    resource: str
    resource_type: Optional[str] = None
    tenant: str = ""
    lag_seconds: float = 0.0
    status: str = "HEALTHY"
    last_sync: Optional[datetime] = None


class FailoverIn(BaseModel):
    source_region: str
    target_region: str
    service: Optional[str] = None
    data_classification: Optional[str] = None
    authorized_by: Optional[str] = None
    failover_type: str = "failover"


# ── Regions ──────────────────────────────────────────────────────────────────

@router.post("/regions", status_code=201)
async def register_region(payload: RegionIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "region:manage", "region")
    try:
        region = await region_service.register_region(
            db, region_id=payload.region_id, name=payload.name, provider=payload.provider,
            location=payload.location, environment=payload.environment,
            data_residency=payload.data_residency, capacity=payload.capacity, status=payload.status,
            capabilities=payload.capabilities, actor=str(getattr(user, "id", "")),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    _audit_best(tenant, str(getattr(user, "id", "")), "region.registered", "region", payload.region_id)
    await _emit_best("region_registered", {"region_id": region.region_id, "status": region.status}, tenant)
    return {"region_id": region.region_id, "status": region.status, "name": region.name}


@router.get("/regions")
async def list_regions(status: Optional[str] = None, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    _tenant(user)
    rows = await region_service.discover_regions(db, status=status)
    return {"items": [{"region_id": r.region_id, "name": r.name, "provider": r.provider,
                       "location": r.location, "status": r.status, "environment": r.environment} for r in rows]}


@router.get("/regions/{region_id}")
async def get_region(region_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    _tenant(user)
    r = await region_service.get_region(db, region_id)
    if not r:
        raise HTTPException(status_code=404, detail="region not found")
    caps = await region_service.get_capabilities(db, region_id)
    return {"region_id": r.region_id, "name": r.name, "provider": r.provider, "location": r.location,
            "status": r.status, "environment": r.environment, "capacity": r.capacity,
            "data_residency": r.data_residency, "capabilities": caps}


@router.patch("/regions/{region_id}/status")
async def update_region_status(region_id: str, payload: RegionStatusIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "region:manage", "region")
    try:
        region = await region_service.update_status(db, region_id, payload.status, reason=payload.reason, actor=str(getattr(user, "id", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"region_id": region.region_id, "status": region.status}


@router.post("/regions/{region_id}/capabilities", status_code=201)
async def set_capabilities(region_id: str, payload: CapabilitiesIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "region:manage", "region")
    try:
        caps = await region_service.set_capabilities(db, region_id, payload.capabilities)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"region_id": region_id, "capabilities": {c.service: c.supported for c in caps}}


@router.get("/regions/{region_id}/capabilities")
async def get_capabilities(region_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    _tenant(user)
    caps = await region_service.get_capabilities(db, region_id)
    return {"region_id": region_id, "capabilities": caps}


@router.post("/regions/{region_id}/health", status_code=201)
async def record_health(region_id: str, payload: HealthIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "region:manage", "region")
    try:
        snap = await region_service.record_health(db, region_id, payload.status, checks=payload.checks)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"region_id": region_id, "status": snap.status, "observed_at": str(snap.observed_at)}


@router.get("/regions/{region_id}/health")
async def get_health(region_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    _tenant(user)
    snap = await region_service.latest_health(db, region_id)
    if not snap:
        raise HTTPException(status_code=404, detail="no health snapshot")
    return {"region_id": region_id, "status": snap.status, "checks": snap.checks, "observed_at": str(snap.observed_at)}


@router.get("/regions/health")
async def all_health(user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    _tenant(user)
    return {"items": await region_service.list_health(db)}


@router.get("/regions/{region_id}/capacity")
async def regional_capacity(region_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    _tenant(user)
    r = await region_service.get_region(db, region_id)
    if not r:
        raise HTTPException(status_code=404, detail="region not found")
    # Capacity is region-level operational data; reported as-is (never faked)
    return {"region_id": region_id, "capacity": r.capacity, "status": r.status}


# ── Draining ───────────────────────────────────────────────────────────────

@router.post("/regions/{region_id}/drain", status_code=202)
async def drain_region(region_id: str, payload: dict | None = None, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "region:manage", "region")
    try:
        res = await routing_service.mark_draining(db, region_id, reason=(payload or {}).get("reason"), actor=str(getattr(user, "id", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    _audit_best(tenant, str(getattr(user, "id", "")), "region.draining.started", "region", region_id)
    return res


@router.post("/regions/{region_id}/drain/complete", status_code=200)
async def complete_drain(region_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "region:manage", "region")
    try:
        res = await routing_service.complete_draining(db, region_id, actor=str(getattr(user, "id", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    _audit_best(tenant, str(getattr(user, "id", "")), "region.draining.completed", "region", region_id)
    return res


# ── Placement ─────────────────────────────────────────────────────────────

@router.post("/placements", status_code=201)
async def set_placement(payload: PlacementIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "region:manage", "placement")
    try:
        p = await placement_service.set_placement(
            db, tenant=tenant, primary_region=payload.primary_region, secondary_region=payload.secondary_region,
            allowed_regions=payload.allowed_regions, data_classification=payload.data_classification,
            residency_policy=payload.residency_policy, policy_version=payload.policy_version,
            actor=str(getattr(user, "id", "")),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"tenant": p.tenant, "primary_region": p.primary_region, "secondary_region": p.secondary_region,
            "allowed_regions": p.allowed_regions, "policy_version": p.policy_version}


@router.get("/placements/{tenant_id}")
async def get_placement(tenant_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    _tenant(user)
    p = await placement_service.get_placement(db, tenant_id)
    if not p:
        raise HTTPException(status_code=404, detail="placement not found")
    return {"tenant": p.tenant, "primary_region": p.primary_region, "secondary_region": p.secondary_region,
            "allowed_regions": p.allowed_regions, "data_classification": p.data_classification,
            "residency_policy": p.residency_policy, "policy_version": p.policy_version}


@router.post("/placements/{tenant_id}/evaluate")
async def evaluate_placement(tenant_id: str, payload: PlacementEvalIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    _tenant(user)
    result = await placement_service.evaluate(
        db, tenant=tenant_id, data_classification=payload.data_classification, region=payload.region,
        provider=payload.provider, capacity=payload.capacity, actor=str(getattr(user, "id", "")),
    )
    return result


# ── Routing ──────────────────────────────────────────────────────────────────

@router.post("/routing/resolve")
async def resolve_routing(payload: RoutingResolveIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    res = await routing_service.route(
        db, tenant=tenant, service=payload.service, data_classification=payload.data_classification,
        preferred_region=payload.preferred_region, criticality=payload.criticality,
        capacity_aware=payload.capacity_aware, actor=str(getattr(user, "id", "")),
    )
    return res


@router.post("/routing-policies", status_code=201)
async def set_routing_policy(payload: RoutingPolicyIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "region:manage", "routing_policy")
    try:
        pol = await routing_service.set_policy(
            db, tenant=tenant, service=payload.service, primary_region=payload.primary_region,
            preferred_secondary=payload.preferred_secondary, emergency_fallback=payload.emergency_fallback,
            consistency=payload.consistency, metadata=payload.metadata,
            publisher=str(getattr(user, "id", "")),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"tenant": pol.tenant, "service": pol.service, "primary_region": pol.primary_region,
            "preferred_secondary": pol.preferred_secondary, "emergency_fallback": pol.emergency_fallback,
            "consistency": pol.consistency, "policy_version": pol.policy_version}


@router.post("/config", status_code=201)
async def publish_config(payload: RoutingPolicyIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "region:manage", "global_config")
    pol = await global_config_service.publish_routing_config(
        db, tenant=tenant, service=payload.service, primary_region=payload.primary_region,
        preferred_secondary=payload.preferred_secondary, emergency_fallback=payload.emergency_fallback,
        consistency=payload.consistency, region_overrides=payload.metadata,
        publisher=str(getattr(user, "id", "")),
    )
    await db.commit()
    return {"tenant": pol.tenant, "service": pol.service, "policy_version": pol.policy_version,
            "propagation_status": (pol.metadata_json or {}).get("propagation_status", "PUBLISHED")}


@router.get("/config")
async def list_config(tenant: Optional[str] = None, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    _tenant(user)
    return {"items": await global_config_service.list_config(db, tenant=tenant)}


@router.post("/config/{tenant_id}/{service}/ack")
async def ack_config(tenant_id: str, service: str, payload: dict | None = None, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "region:manage", "global_config")
    region = (payload or {}).get("region", tenant_id)
    try:
        pol = await global_config_service.acknowledge_propagation(db, tenant_id, service, region, actor=str(getattr(user, "id", "")))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await db.commit()
    return {"tenant": pol.tenant, "service": pol.service, "propagation_status": (pol.metadata_json or {}).get("propagation_status")}


@router.get("/regions/{region_id}/slo")
async def regional_slo(region_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    _tenant(user)
    return await global_config_service.regional_slo(db, region_id)


# ── Replication ─────────────────────────────────────────────────────────────

@router.post("/replication", status_code=201)
async def record_replication(payload: ReplicationIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "region:manage", "replication")
    try:
        rec = await replication_service.record_replication(
            db, source_region=payload.source_region, dest_region=payload.dest_region, resource=payload.resource,
            resource_type=payload.resource_type, tenant=payload.tenant, lag_seconds=payload.lag_seconds,
            status=payload.status, last_sync=payload.last_sync, actor=str(getattr(user, "id", "")),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": rec.id, "status": rec.status, "lag_seconds": rec.lag_seconds}


@router.get("/replication")
async def list_replication(tenant: Optional[str] = None, source_region: Optional[str] = None, dest_region: Optional[str] = None,
                           user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    _tenant(user)
    rows = await replication_service.list_replication(db, tenant=tenant, source_region=source_region, dest_region=dest_region)
    return {"items": [{"id": r.id, "source_region": r.source_region, "dest_region": r.dest_region, "resource": r.resource,
                       "lag_seconds": r.lag_seconds, "status": r.status, "last_sync": str(r.last_sync) if r.last_sync else None}
                      for r in rows]}


# ── Failover / Failback ──────────────────────────────────────────────────────

@router.post("/failover", status_code=202)
async def start_failover(payload: FailoverIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "region:failover", "failover")
    try:
        rec = await failover_service.start_failover(
            db, tenant=tenant, source_region=payload.source_region, target_region=payload.target_region,
            service=payload.service, data_classification=payload.data_classification,
            authorized_by=payload.authorized_by, failover_type=payload.failover_type,
            actor=str(getattr(user, "id", "")),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    _audit_best(tenant, str(getattr(user, "id", "")), "region.failover.started", "failover", str(rec.id),
                {"target_region": payload.target_region, "data_residency_ok": rec.data_residency_ok})
    return {"id": rec.id, "status": rec.status, "data_residency_ok": rec.data_residency_ok, "target_region": rec.target_region}


@router.post("/failover/{record_id}/complete")
async def complete_failover(record_id: int, payload: dict | None = None, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "region:failover", "failover")
    try:
        rec = await failover_service.complete(db, record_id, health_verified=(payload or {}).get("health_verified"), actor=str(getattr(user, "id", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": rec.id, "status": rec.status, "health_verified": rec.health_verified}


@router.post("/failover/{record_id}/fail")
async def fail_failover(record_id: int, payload: dict | None = None, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "region:failover", "failover")
    try:
        rec = await failover_service.fail(db, record_id, reason=(payload or {}).get("reason"), actor=str(getattr(user, "id", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": rec.id, "status": rec.status}


@router.post("/failback", status_code=202)
async def start_failback(payload: FailoverIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "region:failover", "failback")
    try:
        rec = await failover_service.start_failover(
            db, tenant=tenant, source_region=payload.source_region, target_region=payload.target_region,
            service=payload.service, data_classification=payload.data_classification,
            authorized_by=payload.authorized_by, failover_type="failback",
            actor=str(getattr(user, "id", "")),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": rec.id, "status": rec.status, "target_region": rec.target_region}


# ── Commit 2: Orchestration / Split-brain / Verification ──────────────────────

class OrchestrateIn(BaseModel):
    source_region: str
    target_region: str
    service: str
    data_classification: Optional[str] = None
    authorized_by: Optional[str] = None
    automatic: bool = False
    rpo_minutes: Optional[int] = None


@router.post("/orchestrate", status_code=202)
async def orchestrate_failover(payload: OrchestrateIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "region:failover", "failover")
    try:
        out = await failover_orchestrator.orchestrate_failover(
            db, tenant=tenant, service=payload.service, source_region=payload.source_region,
            target_region=payload.target_region, authorized_by=payload.authorized_by,
            automatic=payload.automatic, data_classification=payload.data_classification,
            rpo_minutes=payload.rpo_minutes, actor=str(getattr(user, "id", "")),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return out


class VerifyRecoveryIn(BaseModel):
    source_region: str
    target_region: str
    checks: dict = {}


@router.post("/recovery/verify", status_code=200)
async def verify_recovery(payload: VerifyRecoveryIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "region:failover", "failover")
    try:
        out = await failover_orchestrator.verify_recovery(db, payload.source_region, payload.target_region, checks=payload.checks)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return out


class LeaseIn(BaseModel):
    region_id: str
    holder: str
    ttl_seconds: int = 60
    generation: int = 1


@router.post("/lease", status_code=200)
async def acquire_lease(payload: LeaseIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "region:manage", "region")
    try:
        lease = await failover_orchestrator.acquire_lease(db, payload.region_id, payload.holder, ttl_seconds=payload.ttl_seconds, generation=payload.generation)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    await db.commit()
    return {"region_id": lease.region_id, "holder": lease.holder, "epoch": lease.epoch, "generation": lease.generation, "fenced": lease.fenced}


@router.post("/lease/{region_id}/fence", status_code=200)
async def fence_primary(region_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "region:failover", "failover")
    lease = await failover_orchestrator.fence_primary(db, region_id, by=str(getattr(user, "id", "")))
    await db.commit()
    return {"region_id": lease.region_id, "fenced": lease.fenced}


@router.get("/lease/{region_id}/stale")
async def stale_primary(region_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    _tenant(user)
    return {"region_id": region_id, "stale": await failover_orchestrator.detect_stale_primary(db, region_id)}


class ConflictIn(BaseModel):
    source_region: str
    dest_region: str
    resource: str
    conflict_type: str
    tenant: str = ""
    details: dict = {}


@router.post("/conflicts", status_code=201)
async def detect_conflict(payload: ConflictIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "region:manage", "region")
    c = await failover_orchestrator.detect_conflict(db, payload.source_region, payload.dest_region, payload.resource, payload.conflict_type, tenant=payload.tenant, details=payload.details, actor=str(getattr(user, "id", "")))
    await db.commit()
    return {"id": c.id, "resolution": c.resolution}


class ConflictResolveIn(BaseModel):
    policy: str
    resolved_by: Optional[str] = None


@router.post("/conflicts/{conflict_id}/resolve", status_code=200)
async def resolve_conflict(conflict_id: int, payload: ConflictResolveIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "region:manage", "region")
    try:
        c = await failover_orchestrator.resolve_conflict(db, conflict_id, payload.policy, resolved_by=payload.resolved_by)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": c.id, "resolution": c.resolution, "resolved_at": str(c.resolved_at) if c.resolved_at else None}


# ── Commit 2: Tenant Migration ─────────────────────────────────────────────────

class MigrationPlanIn(BaseModel):
    source_region: str
    target_region: str
    service: Optional[str] = None
    data_classification: Optional[str] = None
    authorized_by: str
    rollback_strategy: Optional[str] = None


@router.post("/migrations", status_code=201)
async def plan_migration(payload: MigrationPlanIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "region:migrate", "migration")
    try:
        m = await tenant_migration_service.plan(db, tenant, payload.source_region, payload.target_region,
            authorized_by=payload.authorized_by, service=payload.service, data_classification=payload.data_classification,
            rollback_strategy=payload.rollback_strategy, actor=str(getattr(user, "id", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": m.id, "state": m.state, "source_region": m.source_region, "target_region": m.target_region}


@router.get("/migrations/{migration_id}")
async def get_migration(migration_id: int, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    _tenant(user)
    from app.regions.models_c2 import TenantMigration
    from sqlalchemy import select
    res = await db.execute(select(TenantMigration).where(TenantMigration.id == migration_id))
    m = res.scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="migration not found")
    return {"id": m.id, "state": m.state, "source_region": m.source_region, "target_region": m.target_region,
            "service": m.service, "verification": m.verification, "rollback_strategy": m.rollback_strategy}


@router.post("/migrations/{migration_id}/advance", status_code=200)
async def advance_migration(migration_id: int, payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "region:migrate", "migration")
    try:
        m = await tenant_migration_service.advance(db, migration_id, payload.get("state"))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": m.id, "state": m.state}


@router.post("/migrations/{migration_id}/verify", status_code=200)
async def verify_migration(migration_id: int, payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "region:migrate", "migration")
    m = await tenant_migration_service.set_verification(db, migration_id, payload.get("verification", {}))
    await db.commit()
    return {"id": m.id, "verification": m.verification}


@router.post("/migrations/{migration_id}/rollback", status_code=200)
async def rollback_migration(migration_id: int, payload: dict | None = None, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "region:migrate", "migration")
    try:
        m = await tenant_migration_service.rollback(db, migration_id, reason=(payload or {}).get("reason"))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": m.id, "state": m.state}


# ── Commit 2: Traffic shift / Rejoin / Drift / Drills / AIOps ──────────────────

class TrafficShiftIn(BaseModel):
    region_id: str
    percentage: int
    actor: Optional[str] = None


@router.post("/traffic", status_code=201)
async def traffic_shift(payload: TrafficShiftIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "region:manage", "region")
    try:
        s = await traffic_shift_service.shift(db, payload.region_id, payload.percentage, actor=payload.actor or str(getattr(user, "id", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": s.id, "region_id": s.region_id, "percentage": s.percentage, "status": s.status}


@router.get("/traffic/{region_id}")
async def current_traffic(region_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    _tenant(user)
    return {"region_id": region_id, "percentage": await traffic_shift_service.current(db, region_id)}


class RejoinIn(BaseModel):
    region_id: str
    compromised: bool = False


@router.post("/rejoin", status_code=200)
async def begin_rejoin(payload: RejoinIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "region:failover", "failover")
    try:
        out = await rejoin_service.begin_rejoin(db, payload.region_id, compromised=payload.compromised, actor=str(getattr(user, "id", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return out


class RejoinVerifyIn(BaseModel):
    region_id: str
    source_region: str
    checks: dict = {}


@router.post("/rejoin/verify", status_code=200)
async def verify_rejoin(payload: RejoinVerifyIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "region:failover", "failover")
    out = await rejoin_service.verify_sync(db, payload.region_id, payload.source_region, checks=payload.checks)
    await db.commit()
    return out


@router.post("/rejoin/{region_id}/admit", status_code=200)
async def admit_rejoin(region_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "region:failover", "failover")
    try:
        out = await rejoin_service.admit_traffic(db, region_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return out


class DriftIn(BaseModel):
    service: str
    expected_version: str
    observed_version: str
    drift_type: str = "version"
    details: dict = {}


@router.post("/drift", status_code=201)
async def detect_drift(payload: DriftIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "region:manage", "region")
    d = await config_drift_service.detect(db, tenant, payload.service, payload.expected_version, payload.observed_version, drift_type=payload.drift_type, details=payload.details, actor=str(getattr(user, "id", "")))
    await db.commit()
    return {"id": d.id, "status": d.status}


@router.post("/drifts/{drift_id}/resolve", status_code=200)
async def resolve_drift(drift_id: int, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "region:manage", "region")
    d = await config_drift_service.resolve(db, drift_id)
    await db.commit()
    return {"id": d.id, "status": d.status}


class DrillIn(BaseModel):
    scenario: str
    region_id: Optional[str] = None


@router.post("/drills", status_code=200)
async def run_drill(payload: DrillIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "region:drill", "drill")
    out = await drill_service.run(db, payload.scenario, region_id=payload.region_id, actor=str(getattr(user, "id", "")))
    await db.commit()
    return out


@router.post("/aiops/recommend", status_code=200)
async def aiops_recommend(payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    _tenant(user)
    region_id = payload.get("region_id", "")
    return aiops_advisor.recommend(region_id, payload.get("signals", {}))
