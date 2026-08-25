"""Observability API — Volume 59 Commit 1.

Endpoints for metrics, logs, traces, services, health, alerts, SLOs, synthetics, service-map.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import _get_current_user
from app.core.database import get_db
from app.observability.platform import platform_service

router = APIRouter(prefix="/observability", tags=["Observability"])


def _tenant(user) -> str:
    oid = getattr(user, "organization_id", None) or getattr(user, "id", None)
    if not oid:
        raise HTTPException(status_code=403, detail="No tenant context")
    return str(oid)


def _check_limit(limit: int, timeout: int):
    if limit > 1000:
        raise HTTPException(status_code=400, detail="limit too large (max 1000)")
    if timeout > 30:
        raise HTTPException(status_code=400, detail="timeout too large (max 30s)")


@router.post("/services", status_code=201)
async def register_service(payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    svc = await platform_service.register_service(db, tenant=tenant, name=payload.get("name"), type=payload.get("type", "service"), environment=payload.get("environment", "production"), resource=payload.get("resource"), **payload)
    await db.commit()
    return {"id": str(svc.id), "resource": svc.resource, "health_status": svc.health_status}


@router.get("/services")
async def list_services(environment: Optional[str] = None, limit: int = Query(100, ge=1, le=1000), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    _check_limit(limit, 5)
    tenant = _tenant(user)
    rows = await platform_service.list_services(db, tenant, environment=environment)
    return {"items": [{"id": str(r.id), "resource": r.resource, "name": r.name, "type": r.type, "environment": r.environment, "health_status": r.health_status} for r in rows[:limit]], "total": len(rows)}


@router.get("/service-map")
async def get_service_map(user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    return await platform_service.get_service_map(db, tenant)


@router.post("/metrics")
async def ingest_metric(payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    if not payload.get("metric"):
        raise HTTPException(status_code=422, detail="metric required")
    if not payload.get("time_range"):
        # Require time range for queries, but ingestion needs timestamp — allow now
        pass
    res = await platform_service.ingest_metric(db, tenant=tenant, metric=payload["metric"], type=payload.get("type", "gauge"), value=float(payload.get("value", 0)), tags=payload.get("tags"), timestamp=None)
    return res


@router.post("/logs")
async def ingest_log(payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    res = await platform_service.ingest_log(db, tenant=tenant, service=payload.get("service", "unknown"), environment=payload.get("environment", "production"), level=payload.get("level", "INFO"), message=payload.get("message", ""), trace_id=payload.get("trace_id"), span_id=payload.get("span_id"), request_id=payload.get("request_id"), event_type=payload.get("event_type"))
    return res


@router.post("/traces")
async def ingest_trace(payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    res = await platform_service.ingest_trace(db, tenant=tenant, trace_id=payload["trace_id"], span_id=payload["span_id"], parent_span_id=payload.get("parent_span_id"), service=payload["service"], operation=payload["operation"], duration_ms=int(payload.get("duration_ms", 0)), status=payload.get("status", "ok"))
    return res


@router.get("/traces/{trace_id}/correlate")
async def correlate_trace(trace_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    return await platform_service.correlate(db, tenant, trace_id)


@router.post("/health")
async def record_health(payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    snap = await platform_service.record_health(db, tenant=tenant, resource=payload["resource"], health=payload["health"], checks=payload.get("checks"))
    await db.commit()
    return {"id": str(snap.id), "resource": snap.resource, "health": snap.health}


@router.get("/health/{resource}")
async def check_health(resource: str, check_type: str = Query("readiness"), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    return await platform_service.check_health(db, tenant, resource, check_type, config=None)


@router.post("/alert-rules", status_code=201)
async def create_alert_rule(payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    rule = await platform_service.create_alert_rule(db, tenant=tenant, name=payload["name"], resource=payload["resource"], condition=payload["condition"], severity=payload.get("severity", "WARNING"), fingerprint_fields=payload.get("fingerprint_fields"))
    await db.commit()
    return {"id": str(rule.id), "name": rule.name, "version": rule.version}


@router.get("/alert-rules")
async def list_alert_rules(limit: int = Query(100, ge=1, le=1000), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    _check_limit(limit, 5)
    from sqlalchemy import select
    from app.observability.models import ObservabilityAlertRule
    tenant = _tenant(user)
    res = await db.execute(select(ObservabilityAlertRule).where(ObservabilityAlertRule.tenant == tenant).limit(limit))
    rows = list(res.scalars().all())
    return {"items": [{"id": str(r.id), "name": r.name, "resource": r.resource, "severity": r.severity} for r in rows]}


@router.post("/alerts", status_code=201)
async def create_alert(payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    alert = await platform_service.create_alert(db, tenant=tenant, resource=payload["resource"], condition=payload["condition"], severity=payload.get("severity", "WARNING"), source=payload.get("source", "observability"), evidence=payload.get("evidence"))
    await db.commit()
    return {"id": str(alert.id), "status": alert.status, "fingerprint": alert.fingerprint}


@router.get("/alerts")
async def list_alerts(status: Optional[str] = None, limit: int = Query(100, ge=1, le=1000), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    _check_limit(limit, 5)
    from sqlalchemy import select
    from app.observability.models import ObservabilityAlert
    tenant = _tenant(user)
    stmt = select(ObservabilityAlert).where(ObservabilityAlert.tenant == tenant)
    if status:
        stmt = stmt.where(ObservabilityAlert.status == status)
    stmt = stmt.order_by(ObservabilityAlert.created_at.desc()).limit(limit)
    res = await db.execute(stmt)
    rows = list(res.scalars().all())
    return {"items": [{"id": str(r.id), "resource": r.resource, "status": r.status, "severity": r.severity, "fingerprint": r.fingerprint} for r in rows]}


@router.post("/alerts/{alert_id}/acknowledge")
async def ack_alert(alert_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    alert = await platform_service.acknowledge_alert(db, tenant, alert_id, str(user.id))
    await db.commit()
    return {"id": str(alert.id), "status": alert.status}


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    alert = await platform_service.resolve_alert(db, tenant, alert_id, str(user.id))
    await db.commit()
    return {"id": str(alert.id), "status": alert.status}


@router.get("/alerts/{alert_id}/correlate")
async def correlate_alert(alert_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    return await platform_service.correlate_alerts(db, tenant, alert_id)


@router.get("/alerts/fatigue/report")
async def fatigue_report(user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    return await platform_service.detect_fatigue(db, tenant)


@router.post("/slos", status_code=201)
async def create_slo(payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    slo = await platform_service.create_slo(db, tenant=tenant, service=payload["service"], indicator=payload["indicator"], target=float(payload["target"]), window=payload.get("window", "30d"), owner=payload.get("owner"))
    await db.commit()
    return {"id": str(slo.id), "service": slo.service, "indicator": slo.indicator, "target": slo.target}


@router.get("/slos")
async def list_slos(user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    from app.observability.models import ObservabilitySLO
    tenant = _tenant(user)
    res = await db.execute(select(ObservabilitySLO).where(ObservabilitySLO.tenant == tenant).limit(100))
    rows = list(res.scalars().all())
    return {"items": [{"id": str(r.id), "service": r.service, "indicator": r.indicator, "target": r.target, "window": r.window} for r in rows]}


@router.post("/slos/{slo_id}/evaluate")
async def evaluate_slo(slo_id: str, payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    return await platform_service.evaluate_slo(db, tenant, slo_id, float(payload["observed"]))


@router.post("/synthetics", status_code=201)
async def create_synthetic(payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    chk = await platform_service.create_synthetic_check(db, tenant=tenant, name=payload["name"], check_type=payload.get("check_type", "HTTP"), target=payload["target"], config=payload.get("config"))
    await db.commit()
    return {"id": str(chk.id), "name": chk.name, "target": chk.target}


@router.post("/synthetics/{check_id}/run")
async def run_synthetic(check_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    res = await platform_service.run_synthetic_check(db, tenant, check_id)
    await db.commit()
    return res


@router.get("/dashboard")
async def dashboard(user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    services = await platform_service.list_services(db, tenant)
    # Metrics counts best-effort
    return {"tenant": tenant, "services": len(services), "health": {s.resource: s.health_status for s in services[:10]}}
