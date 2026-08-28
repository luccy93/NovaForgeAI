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
from app.regions.placement import placement_service
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
