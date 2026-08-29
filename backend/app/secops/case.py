"""Case service — Volume 63."""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.secops.models import CASE_STATUSES, SecOpsCase, SecOpsCaseEvidence

import hashlib

def _to_uuid(v):
    if isinstance(v, uuid.UUID):
        return v
    try:
        return uuid.UUID(str(v))
    except Exception:
        return v

async def create_case(db: AsyncSession, tenant: str, payload: dict, created_by: str = "") -> SecOpsCase:
    status = (payload.get("status") or "OPEN").upper()
    if status not in CASE_STATUSES:
        raise ValueError(f"invalid case status {status}")
    severity = (payload.get("severity") or "MEDIUM").upper()
    case = SecOpsCase(
        tenant=tenant,
        alerts=payload.get("alerts") or [],
        findings=payload.get("findings") or [],
        evidence_ids=payload.get("evidence_ids") or payload.get("evidence") or [],
        owner=payload.get("owner") or created_by,
        team=payload.get("team") or "",
        service_owner=payload.get("service_owner") or "",
        status=status,
        severity=severity,
        risk_score=float(payload.get("risk_score", 0.0)),
        incident_id=payload.get("incident_id"),
        title=payload.get("title") or payload.get("finding") or f"Case {payload.get('severity','')}",
    )
    db.add(case)
    await db.flush()
    return case

async def get_case(db: AsyncSession, tenant: str, case_id: str) -> SecOpsCase | None:
    res = await db.execute(select(SecOpsCase).where(SecOpsCase.id == _to_uuid(case_id), SecOpsCase.tenant == tenant))
    return res.scalar_one_or_none()

async def list_cases(db: AsyncSession, tenant: str, status: str | None = None, limit: int = 50) -> list[SecOpsCase]:
    q = select(SecOpsCase).where(SecOpsCase.tenant == tenant)
    if status:
        q = q.where(SecOpsCase.status == status.upper())
    q = q.order_by(SecOpsCase.created_at.desc()).limit(min(limit, 1000))
    res = await db.execute(q)
    return list(res.scalars().all())

async def update_case(db: AsyncSession, tenant: str, case_id: str, updates: dict) -> SecOpsCase:
    case = await get_case(db, tenant, case_id)
    if not case:
        raise ValueError("case not found")
    if "status" in updates:
        ns = updates["status"].upper()
        if ns not in CASE_STATUSES:
            raise ValueError(f"invalid status {ns}")
        case.status = ns
    if "owner" in updates:
        case.owner = updates["owner"]
    if "team" in updates:
        case.team = updates["team"]
    if "service_owner" in updates:
        case.service_owner = updates["service_owner"]
    if "severity" in updates:
        case.severity = updates["severity"].upper()
    if "risk_score" in updates:
        case.risk_score = float(updates["risk_score"])
    if "alerts" in updates:
        case.alerts = updates["alerts"]
    if "findings" in updates:
        case.findings = updates["findings"]
    if "incident_id" in updates:
        case.incident_id = updates["incident_id"]
    if "title" in updates:
        case.title = updates["title"]
    await db.flush()
    return case

async def add_evidence(db: AsyncSession, tenant: str, case_id: str, evidence_payload: dict, collected_by: str = "") -> SecOpsCaseEvidence:
    case = await get_case(db, tenant, case_id)
    if not case:
        raise ValueError("case not found")
    source = evidence_payload.get("source") or "unknown"
    resource = evidence_payload.get("resource") or ""
    event = evidence_payload.get("event") or evidence_payload
    confidence = float(evidence_payload.get("confidence", 0.7))
    # integrity hash via audit/integrity mechanism — sha256 of event
    import json, hashlib
    integrity = hashlib.sha256(json.dumps(event, sort_keys=True).encode()).hexdigest()
    ev = SecOpsCaseEvidence(
        tenant=tenant,
        case_id=case.id,
        source=source,
        resource=resource,
        event=event,
        confidence=confidence,
        integrity_hash=integrity,
        collected_by=collected_by,
        chain_of_custody=[{"collected_by": collected_by, "at": datetime.now(timezone.utc).isoformat()}],
    )
    db.add(ev)
    await db.flush()
    # link to case
    case.evidence_ids = case.evidence_ids + [str(ev.id)]
    await db.flush()
    return ev

async def list_evidence(db: AsyncSession, tenant: str, case_id: str) -> list[SecOpsCaseEvidence]:
    res = await db.execute(select(SecOpsCaseEvidence).where(SecOpsCaseEvidence.tenant == tenant, SecOpsCaseEvidence.case_id == _to_uuid(case_id)).order_by(SecOpsCaseEvidence.timestamp.asc()))
    return list(res.scalars().all())
