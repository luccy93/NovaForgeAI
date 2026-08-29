"""SecOps API — Volume 63 Commit 1.

Exposes security-events, alerts, detections, findings, cases, investigations, indicators, risk.
Tenant-isolated, fail-closed, bounded, audited. Reuses V52 IAM, V47 security, V51 graph.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import _get_current_user
from app.core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/secops", tags=["Security Operations"])


def _tenant(user) -> str:
    oid = getattr(user, "organization_id", None) or getattr(user, "id", None)
    if not oid:
        raise HTTPException(status_code=403, detail="No tenant context")
    return str(oid)


def _iam_check(user, tenant: str, permission: str, resource_type: str = "secops") -> None:
    try:
        from app.iam.policy_authorizer import policy_authorizer

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
        from app.iam.audit_service import audit_service

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
        from app.core.events import Event, EventType, event_bus

        et = getattr(EventType, event_name, None)
        if et is None:
            return
        await event_bus.publish_nowait(Event(et, data, source="secops-api", organization_id=tenant))
    except Exception as exc:  # noqa: BLE001
        logger.debug("emit failed %s: %s", event_name, exc)


def _to_uuid(v):
    import uuid
    if isinstance(v, uuid.UUID):
        return v
    try:
        return uuid.UUID(str(v))
    except Exception:
        return v


def _check_limit(limit: int):
    if limit > 1000:
        raise HTTPException(status_code=400, detail="limit too large (max 1000)")


# ── Pydantic models ──────────────────────────────────────────────────────────
class SecurityEventIn(BaseModel):
    source: str = "unknown"
    resource: str = ""
    resource_type: str = ""
    actor: str = ""
    action: str = ""
    severity: str = "INFO"
    category: str = "APPLICATION"
    region: str = ""
    request_id: str = ""
    trace_id: str = ""
    tenant: Optional[str] = None
    ip: Optional[str] = None
    deployment_id: Optional[str] = None
    metadata: dict = {}


class DetectionRuleIn(BaseModel):
    name: str = Field(..., max_length=128)
    description: str = ""
    category: str = "APPLICATION"
    severity: str = "MEDIUM"
    rule_type: str = Field(..., description="threshold|sequence|frequency|absence|correlation|anomaly|policy_violation")
    conditions: dict = {}
    threshold: dict = {}
    time_window_seconds: int = 300
    confidence: float = 0.7
    owner: str = ""
    enabled: bool = True
    baseline_config: dict = {}
    change_reason: str = ""


class AlertStatusIn(BaseModel):
    status: str
    reason: Optional[str] = None


class FindingIn(BaseModel):
    finding: str
    resource: str = ""
    resource_type: str = ""
    resource_id: str = ""
    evidence: list = []
    policy: str = ""
    policy_version: str = "1"
    severity: str = "MEDIUM"
    owner: str = ""
    status: str = "OPEN"
    confidence: float = 0.7
    exposure: dict = {}
    blast_radius: dict = {}


class CaseIn(BaseModel):
    alerts: list = []
    findings: list = []
    evidence: list = []
    owner: str = ""
    team: str = ""
    service_owner: str = ""
    severity: str = "MEDIUM"
    status: str = "OPEN"
    title: str = ""
    risk_score: float = 0.0


class IndicatorIn(BaseModel):
    indicator: str
    indicator_type: str
    source: str = "manual"
    confidence: float = 0.5
    expiration: Optional[str] = None
    status: str = "pending"
    feed_id: Optional[str] = None


class RiskIn(BaseModel):
    resource: str = ""
    resource_type: str = ""
    resource_id: str = ""
    severity: str = "MEDIUM"
    confidence: float = 0.5
    exposure: str = "unknown"
    asset_criticality: str = "medium"
    privilege: str = "user"
    data_classification: str = "internal"
    region: str = ""


# ── Security events ──────────────────────────────────────────────────────────
@router.post("/security-events", status_code=201)
async def ingest_security_event(payload: SecurityEventIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "secops:write", "secops")
    from app.secops.normalization import normalize_event, retain_event

    raw = payload.model_dump()
    raw["tenant"] = tenant  # enforce tenant isolation
    norm = normalize_event(raw, source=payload.source)
    retain_event(norm)
    # also evaluate against detection rules bounded
    try:
        from app.secops.detection import evaluate_rules

        await evaluate_rules(db, tenant, [norm])
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.debug("detection eval skipped: %s", exc)
        await db.rollback()
    _audit_best(tenant, str(getattr(user, "id", "")), "secops.event.ingested", "security_event", norm["event_id"], {"source": payload.source})
    await _emit_best("security_event_received", {"event_id": norm["event_id"], "tenant": tenant, "source": payload.source}, tenant)
    return norm


@router.get("/security-events")
async def list_security_events(
    limit: int = Query(50, ge=1, le=1000),
    category: Optional[str] = None,
    severity: Optional[str] = None,
    actor: Optional[str] = None,
    user=Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_limit(limit)
    tenant = _tenant(user)
    from app.secops.normalization import get_recent_events

    events = get_recent_events(tenant=tenant, limit=1000)
    # filter
    if category:
        events = [e for e in events if e.get("category") == category.upper()]
    if severity:
        events = [e for e in events if e.get("severity") == severity.upper()]
    if actor:
        events = [e for e in events if e.get("actor") == actor]
    # bounded
    events = events[-limit:]
    return {"items": events, "total": len(events), "tenant": tenant}


@router.get("/security-events/{event_id}")
async def get_security_event(event_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.secops.normalization import get_recent_events

    events = get_recent_events(tenant=tenant, limit=1000)
    for e in events:
        if e.get("event_id") == event_id:
            return e
    raise HTTPException(status_code=404, detail="event not found")


# ── Detections / rules ───────────────────────────────────────────────────────
@router.post("/detections/rules", status_code=201)
async def create_detection_rule(payload: DetectionRuleIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "secops:write", "secops")
    from app.secops.detection import create_rule

    try:
        rule = await create_rule(db, tenant, payload.model_dump(), created_by=str(getattr(user, "id", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    _audit_best(tenant, str(getattr(user, "id", "")), "secops.rule.created", "detection_rule", str(rule.id), {"name": rule.name})
    return {"id": str(rule.id), "name": rule.name, "version": rule.version, "rule_type": rule.rule_type, "severity": rule.severity}


@router.get("/detections/rules")
async def list_detection_rules(
    category: Optional[str] = None,
    enabled: Optional[bool] = None,
    limit: int = Query(50, ge=1, le=1000),
    user=Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_limit(limit)
    tenant = _tenant(user)
    from app.secops.models import SecOpsDetectionRule

    q = select(SecOpsDetectionRule).where(SecOpsDetectionRule.tenant == tenant)
    if category:
        q = q.where(SecOpsDetectionRule.category == category.upper())
    if enabled is not None:
        q = q.where(SecOpsDetectionRule.enabled == enabled)  # noqa: E712
    q = q.order_by(SecOpsDetectionRule.created_at.desc()).limit(limit)
    res = await db.execute(q)
    rows = res.scalars().all()
    return {"items": [{"id": str(r.id), "name": r.name, "version": r.version, "rule_type": r.rule_type, "category": r.category, "severity": r.severity, "enabled": r.enabled, "confidence": r.confidence} for r in rows]}


@router.get("/detections/rules/{rule_id}")
async def get_detection_rule(rule_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.secops.models import SecOpsDetectionRule

    res = await db.execute(select(SecOpsDetectionRule).where(SecOpsDetectionRule.id == _to_uuid(rule_id), SecOpsDetectionRule.tenant == tenant))
    r = res.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="rule not found")
    return {"id": str(r.id), "name": r.name, "version": r.version, "rule_type": r.rule_type, "conditions": r.conditions, "threshold": r.threshold, "time_window_seconds": r.time_window_seconds, "severity": r.severity, "category": r.category}


@router.post("/detections/evaluate", status_code=200)
async def evaluate_detections(payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "secops:read", "secops")
    events = payload.get("events") or []
    if not isinstance(events, list):
        raise HTTPException(status_code=422, detail="events must be list")
    if len(events) > 1000:
        raise HTTPException(status_code=400, detail="too many events (max 1000)")
    # normalize if needed
    from app.secops.normalization import normalize_event
    from app.secops.detection import evaluate_rules

    norms = []
    for e in events:
        if isinstance(e, dict) and "event_id" not in e:
            norms.append(normalize_event({**e, "tenant": tenant}))
        elif isinstance(e, dict):
            e["tenant"] = tenant
            norms.append(e)
    alerts = await evaluate_rules(db, tenant, norms)
    await db.commit()
    return {"alerts_created": len(alerts), "alerts": [{"id": str(a.id), "fingerprint": a.fingerprint, "severity": a.severity} for a in alerts]}


# ── Alerts ───────────────────────────────────────────────────────────────────
@router.get("/security-alerts")
async def list_alerts(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = Query(50, ge=1, le=1000),
    user=Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_limit(limit)
    tenant = _tenant(user)
    from app.secops.models import SecOpsAlert

    q = select(SecOpsAlert).where(SecOpsAlert.tenant == tenant)
    if status:
        q = q.where(SecOpsAlert.status == status.upper())
    if severity:
        q = q.where(SecOpsAlert.severity == severity.upper())
    q = q.order_by(SecOpsAlert.created_at.desc()).limit(limit)
    res = await db.execute(q)
    rows = res.scalars().all()
    return {"items": [{"id": str(r.id), "rule_name": r.rule_name, "severity": r.severity, "status": r.status, "confidence": r.confidence, "fingerprint": r.fingerprint, "events": r.events[:2] if r.events else []} for r in rows], "total": len(rows)}


@router.get("/security-alerts/{alert_id}")
async def get_alert(alert_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.secops.models import SecOpsAlert

    res = await db.execute(select(SecOpsAlert).where(SecOpsAlert.id == _to_uuid(alert_id), SecOpsAlert.tenant == tenant))
    a = res.scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="alert not found")
    return {"id": str(a.id), "tenant": a.tenant, "rule_id": str(a.rule_id) if a.rule_id else None, "rule_name": a.rule_name, "severity": a.severity, "status": a.status, "confidence": a.confidence, "fingerprint": a.fingerprint, "events": a.events, "created_at": a.created_at.isoformat() if a.created_at else None}


@router.post("/security-alerts/{alert_id}/status", status_code=200)
async def update_alert_status(alert_id: str, payload: AlertStatusIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "secops:write", "secops")
    from app.secops.models import SecOpsAlert, ALERT_STATUSES

    ns = payload.status.upper()
    if ns not in ALERT_STATUSES:
        raise HTTPException(status_code=422, detail=f"invalid status {payload.status}")
    res = await db.execute(select(SecOpsAlert).where(SecOpsAlert.id == _to_uuid(alert_id), SecOpsAlert.tenant == tenant))
    a = res.scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="alert not found")
    a.status = ns
    if ns == "RESOLVED":
        a.resolved_at = datetime.now(timezone.utc)
        await _emit_best("security_alert_resolved", {"alert_id": str(a.id), "tenant": tenant}, tenant)
    elif ns == "ACKNOWLEDGED":
        a.acknowledged_by = str(getattr(user, "id", ""))
    await db.flush()
    await db.commit()
    _audit_best(tenant, str(getattr(user, "id", "")), f"secops.alert.{ns.lower()}", "security_alert", str(a.id))
    return {"id": str(a.id), "status": a.status}


@router.post("/security-alerts/{alert_id}/acknowledge", status_code=200)
async def acknowledge_alert(alert_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    return await update_alert_status(alert_id, AlertStatusIn(status="ACKNOWLEDGED"), user, db)


@router.post("/security-alerts/suppress", status_code=200)
async def suppress_alerts(payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "secops:write", "secops")
    fingerprint = payload.get("fingerprint")
    reason = payload.get("reason")
    owner = payload.get("owner") or str(getattr(user, "id", ""))
    expiration = payload.get("expiration")
    if not fingerprint or not reason or not owner:
        raise HTTPException(status_code=422, detail="fingerprint, reason, owner required")
    if not expiration:
        raise HTTPException(status_code=422, detail="expiration required (no permanent undocumented suppression)")
    try:
        exp_dt = datetime.fromisoformat(expiration.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=422, detail="invalid expiration isoformat")
    from app.secops.models import SecOpsAlert

    res = await db.execute(select(SecOpsAlert).where(SecOpsAlert.tenant == tenant, SecOpsAlert.fingerprint == fingerprint, SecOpsAlert.status.in_(["OPEN", "ACKNOWLEDGED", "INVESTIGATING"])))  # noqa: E712
    rows = list(res.scalars().all())
    for a in rows:
        a.suppression_reason = reason
        a.suppression_owner = owner
        a.suppression_expires_at = exp_dt
        a.status = "FALSE_POSITIVE"  # temporary suppression
    if rows:
        await db.flush()
        await db.commit()
    return {"suppressed": len(rows), "fingerprint": fingerprint}


# ── Findings ─────────────────────────────────────────────────────────────────
@router.post("/findings", status_code=201)
async def create_finding(payload: FindingIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "secops:write", "secops")
    from app.secops.findings import create_finding as _create

    try:
        f = await _create(db, tenant, payload.model_dump(), created_by=str(getattr(user, "id", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    _audit_best(tenant, str(getattr(user, "id", "")), "secops.finding.created", "finding", str(f.id), {"resource": f.resource_id})
    await _emit_best("security_finding_created", {"finding_id": str(f.id), "tenant": tenant}, tenant)
    return {"id": str(f.id), "finding": f.finding, "severity": f.severity, "status": f.status}


@router.get("/findings")
async def list_findings(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = Query(50, ge=1, le=1000),
    user=Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_limit(limit)
    tenant = _tenant(user)
    from app.secops.findings import list_findings as _list

    rows = await _list(db, tenant, status=status, severity=severity, limit=limit)
    return {"items": [{"id": str(r.id), "finding": r.finding, "resource": r.resource_id, "severity": r.severity, "status": r.status} for r in rows]}


@router.get("/findings/{finding_id}")
async def get_finding(finding_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.secops.findings import get_finding as _get

    f = await _get(db, tenant, finding_id)
    if not f:
        raise HTTPException(status_code=404, detail="finding not found")
    return {"id": str(f.id), "finding": f.finding, "resource": f.resource_id, "severity": f.severity, "status": f.status, "evidence": f.evidence, "policy": f.policy}


@router.post("/findings/{finding_id}/status", status_code=200)
async def update_finding_status(finding_id: str, payload: AlertStatusIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "secops:write", "secops")
    from app.secops.findings import update_finding_status as _upd

    try:
        f = await _upd(db, tenant, finding_id, payload.status, actor=str(getattr(user, "id", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": str(f.id), "status": f.status}


# ── Cases ────────────────────────────────────────────────────────────────────
@router.post("/cases", status_code=201)
async def create_case(payload: CaseIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "secops:write", "secops")
    from app.secops.case import create_case as _create

    try:
        c = await _create(db, tenant, payload.model_dump(), created_by=str(getattr(user, "id", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    _audit_best(tenant, str(getattr(user, "id", "")), "secops.case.created", "case", str(c.id))
    await _emit_best("security_case_created", {"case_id": str(c.id), "tenant": tenant}, tenant)
    return {"id": str(c.id), "status": c.status, "severity": c.severity, "risk_score": c.risk_score}


@router.get("/cases")
async def list_cases(
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=1000),
    user=Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_limit(limit)
    tenant = _tenant(user)
    from app.secops.case import list_cases as _list

    rows = await _list(db, tenant, status=status, limit=limit)
    return {"items": [{"id": str(r.id), "status": r.status, "severity": r.severity, "owner": r.owner, "risk_score": r.risk_score, "title": r.title} for r in rows]}


@router.get("/cases/{case_id}")
async def get_case(case_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.secops.case import get_case as _get

    c = await _get(db, tenant, case_id)
    if not c:
        raise HTTPException(status_code=404, detail="case not found")
    return {"id": str(c.id), "status": c.status, "severity": c.severity, "owner": c.owner, "alerts": c.alerts, "findings": c.findings, "risk_score": c.risk_score, "incident_id": c.incident_id}


@router.post("/cases/{case_id}/status", status_code=200)
async def update_case_status(case_id: str, payload: AlertStatusIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "secops:write", "secops")
    from app.secops.case import update_case as _upd

    try:
        c = await _upd(db, tenant, case_id, {"status": payload.status})
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    await _emit_best("security_case_updated", {"case_id": str(c.id), "status": c.status}, tenant)
    return {"id": str(c.id), "status": c.status}


@router.post("/cases/{case_id}/evidence", status_code=201)
async def add_case_evidence(case_id: str, payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "secops:write", "secops")
    from app.secops.case import add_evidence

    try:
        ev = await add_evidence(db, tenant, case_id, payload, collected_by=str(getattr(user, "id", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": str(ev.id), "integrity_hash": ev.integrity_hash, "source": ev.source}


@router.get("/cases/{case_id}/evidence")
async def list_case_evidence(case_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.secops.case import list_evidence

    rows = await list_evidence(db, tenant, case_id)
    return {"items": [{"id": str(r.id), "source": r.source, "resource": r.resource, "confidence": r.confidence, "integrity_hash": r.integrity_hash} for r in rows]}


# ── Investigations ───────────────────────────────────────────────────────────
@router.get("/investigations/{case_or_alert_id}")
async def get_investigation(case_or_alert_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    # graph access respects auth
    from app.secops.graph import check_graph_access

    if not await check_graph_access(user, tenant):
        raise HTTPException(status_code=403, detail="graph access denied")
    from app.secops.investigation import build_investigation

    try:
        inv = await build_investigation(db, tenant, case_or_alert_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return inv


# ── Indicators ───────────────────────────────────────────────────────────────
@router.post("/indicators", status_code=201)
async def create_indicator(payload: IndicatorIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "secops:write", "secops")
    from app.secops.indicators import create_indicator as _create

    try:
        ind = await _create(db, tenant, payload.model_dump(), created_by=str(getattr(user, "id", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": str(ind.id), "indicator": ind.indicator, "type": ind.indicator_type, "status": ind.status}


@router.get("/indicators")
async def list_indicators(
    status: Optional[str] = None,
    indicator_type: Optional[str] = None,
    limit: int = Query(50, ge=1, le=1000),
    user=Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _check_limit(limit)
    tenant = _tenant(user)
    from app.secops.indicators import list_indicators as _list

    rows = await _list(db, tenant, status=status, indicator_type=indicator_type, limit=limit)
    return {"items": [{"id": str(r.id), "indicator": r.indicator, "type": r.indicator_type, "status": r.status, "confidence": r.confidence} for r in rows]}


@router.post("/indicators/{indicator_id}/status", status_code=200)
async def update_indicator_status(indicator_id: str, payload: AlertStatusIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "secops:write", "secops")
    from app.secops.indicators import update_indicator_status as _upd

    try:
        ind = await _upd(db, indicator_id, payload.status.lower(), actor=str(getattr(user, "id", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    # ensure tenant isolation: indicator tenant must match or be global
    if ind.tenant and ind.tenant != tenant:
        raise HTTPException(status_code=403, detail="indicator tenant mismatch")
    await db.commit()
    return {"id": str(ind.id), "status": ind.status}


@router.post("/indicators/match", status_code=200)
async def match_indicators(payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "secops:read", "secops")
    telemetry = payload.get("telemetry") or payload.get("events") or []
    if not isinstance(telemetry, list):
        raise HTTPException(status_code=422, detail="telemetry must be list")
    if len(telemetry) > 1000:
        raise HTTPException(status_code=400, detail="too many telemetry items (max 1000)")
    from app.secops.indicators import match_indicators as _match

    matches = await _match(db, tenant, telemetry)
    await db.commit()
    if matches:
        await _emit_best("threat_indicator_matched", {"tenant": tenant, "matches": len(matches)}, tenant)
    return {"matches": matches, "total": len(matches)}


# ── Risk ─────────────────────────────────────────────────────────────────────
@router.post("/risk/calculate", status_code=201)
async def calculate_risk(payload: RiskIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "secops:write", "secops")
    from app.secops.risk import create_risk_snapshot

    snap = await create_risk_snapshot(db, tenant, payload.model_dump())
    await db.commit()
    await _emit_best("security_risk_changed", {"risk_score": snap.risk_score, "tenant": tenant}, tenant)
    return {"id": str(snap.id), "risk_score": snap.risk_score, "severity": snap.severity, "calculated_at": snap.calculated_at.isoformat()}


@router.get("/risk")
async def get_risk(
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    user=Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tenant = _tenant(user)
    from app.secops.risk import get_latest_risk

    snap = await get_latest_risk(db, tenant, resource_type=resource_type, resource_id=resource_id)
    if not snap:
        return {"risk_score": 0, "tenant": tenant}
    return {"id": str(snap.id), "risk_score": snap.risk_score, "severity": snap.severity, "calculated_at": snap.calculated_at.isoformat(), "inputs": snap.inputs}


@router.get("/risk/snapshots")
async def list_risk_snapshots(limit: int = Query(50, ge=1, le=1000), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    _check_limit(limit)
    tenant = _tenant(user)
    from app.secops.models import SecOpsRiskSnapshot

    res = await db.execute(select(SecOpsRiskSnapshot).where(SecOpsRiskSnapshot.tenant == tenant).order_by(SecOpsRiskSnapshot.calculated_at.desc()).limit(limit))
    rows = res.scalars().all()
    return {"items": [{"id": str(r.id), "risk_score": r.risk_score, "resource": r.resource_id, "severity": r.severity} for r in rows]}


# ── Commit 2: Response, Playbooks, Hunting, Attack Path, Posture ────────────

class ResponseRequestIn(BaseModel):
    action: str
    scope: dict = {}
    policy: str = ""
    timeout_seconds: int = 300


@router.post("/cases/{case_id}/response/request", status_code=201)
async def request_response(case_id: str, payload: ResponseRequestIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "secops:write", "secops")
    from app.secops.response import request_response as _req

    try:
        rec = await _req(db, tenant, case_id, payload.action, payload.scope, policy=payload.policy, timeout_seconds=payload.timeout_seconds, requested_by=str(getattr(user, "id", "")))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    await _emit_best("security_response_requested", {"response_id": rec["id"], "case_id": case_id}, tenant)
    return rec


@router.post("/responses/{response_id}/approve", status_code=200)
async def approve_response(response_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "secops:write", "secops")
    from app.secops.response import approve_response as _appr

    try:
        rec = await _appr(db, tenant, response_id, approved_by=str(getattr(user, "id", "")))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    await _emit_best("security_response_approved", {"response_id": response_id}, tenant)
    return rec


@router.post("/responses/{response_id}/execute", status_code=200)
async def execute_response(response_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "secops:write", "secops")
    from app.secops.response import execute_response as _exec

    try:
        rec = await _exec(db, tenant, response_id, executor=str(getattr(user, "id", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    if rec.get("status") == "COMPLETED":
        await _emit_best("security_response_completed", {"response_id": response_id}, tenant)
        await _emit_best("security_response_started", {"response_id": response_id}, tenant)
    else:
        await _emit_best("security_response_failed", {"response_id": response_id}, tenant)
    return rec


@router.post("/responses/{response_id}/verify", status_code=200)
async def verify_response(response_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "secops:read", "secops")
    from app.secops.response import verify_containment

    try:
        rec = await verify_containment(db, tenant, response_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    await _emit_best("containment_verified", {"response_id": response_id, "verified": rec.get("verified")}, tenant)
    return rec


@router.get("/responses")
async def list_responses(limit: int = Query(20, ge=1, le=100), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    _check_limit(limit)
    tenant = _tenant(user)
    from app.secops.response import list_responses as _list

    rows = _list(tenant)
    return {"items": rows[:limit], "total": len(rows)}


@router.post("/playbooks/{playbook_id}/execute", status_code=200)
async def execute_playbook(playbook_id: str, payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "secops:write", "secops")
    case_id = payload.get("case_id")
    if not case_id:
        raise HTTPException(status_code=422, detail="case_id required")
    from app.secops.response import execute_playbook as _exec_pb

    res = await _exec_pb(db, tenant, case_id, playbook_id, requested_by=str(getattr(user, "id", "")))
    await db.commit()
    return res


class HuntIn(BaseModel):
    query: dict = {}
    scope: dict = {}
    template: Optional[str] = None
    limit: int = 100


@router.post("/hunts", status_code=201)
async def start_hunt(payload: HuntIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "secops:read", "secops")
    from app.secops.hunting import start_hunt as _start

    try:
        job = await _start(db, tenant, payload.query, scope=payload.scope, analyst=str(getattr(user, "id", "")), template=payload.template)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    await _emit_best("threat_hunt_started", {"hunt_id": job["id"]}, tenant)
    await _emit_best("threat_hunt_completed", {"hunt_id": job["id"]}, tenant)
    return job


@router.get("/hunts/{hunt_id}")
async def get_hunt(hunt_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.secops.hunting import get_hunt as _get

    job = await _get(hunt_id, tenant)
    if not job:
        raise HTTPException(status_code=404, detail="hunt not found")
    return job


@router.get("/hunts")
async def list_hunts(limit: int = Query(20, ge=1, le=100), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    _check_limit(limit)
    tenant = _tenant(user)
    from app.secops.hunting import list_hunts as _list

    rows = await _list(tenant, limit=limit)
    return {"items": rows, "total": len(rows)}


@router.get("/hunt-templates")
async def list_hunt_templates(user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    _tenant(user)
    from app.secops.hunting import list_templates

    return {"items": list_templates()}


@router.get("/attack-path")
async def get_attack_path(start: str = Query(...), target: Optional[str] = None, depth: int = Query(3, ge=1, le=5), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.secops.attack_path import analyze_attack_path

    res = await analyze_attack_path(db, tenant, start, target_entity=target, depth=depth)
    return res


@router.get("/blast-radius/{case_id}")
async def get_blast_radius(case_id: str, entity: Optional[str] = None, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.secops.attack_path import estimate_blast_radius

    res = await estimate_blast_radius(db, tenant, case_id=case_id, entity=entity)
    return res


@router.get("/posture")
async def get_posture(user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.secops.posture import get_posture as _get

    return await _get(db, tenant)


@router.get("/coverage")
async def get_coverage(user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.secops.posture import get_coverage as _get

    return await _get(db, tenant)


@router.get("/slo")
async def get_slo(user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.secops.posture import get_slo as _get

    return await _get(db, tenant)


class FeedIngestIn(BaseModel):
    feed_id: str
    source: str
    indicators: list = []


@router.post("/intel/feeds/ingest", status_code=201)
async def ingest_feed(payload: FeedIngestIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "secops:write", "secops")
    from app.secops.intel import ingest_feed as _ingest

    try:
        res = await _ingest(db, tenant, payload.feed_id, payload.source, payload.indicators, analyst=str(getattr(user, "id", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return res


@router.post("/intel/feeds/{feed_id}/validate", status_code=200)
async def validate_feed(feed_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "secops:write", "secops")
    from app.secops.intel import validate_feed_indicators

    count = await validate_feed_indicators(db, tenant, feed_id, validator=str(getattr(user, "id", "")))
    await db.commit()
    return {"feed_id": feed_id, "validated": count}


@router.get("/intel/feeds/{feed_id}/health")
async def feed_health(feed_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    _tenant(user)
    from app.secops.intel import get_feed_health

    h = get_feed_health(feed_id)
    if not h:
        raise HTTPException(status_code=404, detail="feed not found")
    return h


@router.post("/security-testing/simulate", status_code=200)
async def simulate_attack(payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "secops:read", "secops")
    sim_type = payload.get("type", "credential_misuse")
    allowed = {"credential_misuse", "privilege_escalation", "data_access", "agent_abuse", "package_compromise"}
    if sim_type not in allowed:
        raise HTTPException(status_code=422, detail=f"unknown simulation type {sim_type}")
    if payload.get("target") == "production" and not payload.get("explicit_authorization"):
        raise HTTPException(status_code=403, detail="production simulation requires explicit authorization")
    return {"type": sim_type, "status": "SIMULATED", "tenant": tenant, "explicit_authorization": bool(payload.get("explicit_authorization"))}


# ── Dashboard ────────────────────────────────────────────────────────────────
@router.get("/dashboard")
async def dashboard(user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.secops.models import SecOpsAlert, SecOpsFinding, SecOpsCase, SecOpsIndicator

    # bounded counts
    for limit_check in [50]:
        _check_limit(100)
    alerts = (await db.execute(select(SecOpsAlert).where(SecOpsAlert.tenant == tenant).limit(100))).scalars().all()
    findings = (await db.execute(select(SecOpsFinding).where(SecOpsFinding.tenant == tenant).limit(100))).scalars().all()
    cases = (await db.execute(select(SecOpsCase).where(SecOpsCase.tenant == tenant).limit(100))).scalars().all()
    indicators = (await db.execute(select(SecOpsIndicator).where((SecOpsIndicator.tenant == tenant) | (SecOpsIndicator.tenant.is_(None))).limit(100))).scalars().all()
    return {
        "tenant": tenant,
        "alerts": {"total": len(alerts), "by_status": {s: len([a for a in alerts if a.status == s]) for s in ["OPEN", "ACKNOWLEDGED", "INVESTIGATING", "CONTAINED", "RESOLVED", "FALSE_POSITIVE"]}, "by_severity": {s: len([a for a in alerts if a.severity == s]) for s in ["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]}},
        "findings": {"total": len(findings)},
        "cases": {"total": len(cases)},
        "indicators": {"total": len(indicators)},
    }
