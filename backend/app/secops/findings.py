"""Findings service — Volume 63.

Track finding/resource/evidence/policy/severity/owner/status.
Reuse Volume 37/52 policy engine for violation -> finding.
"""

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.secops.models import FINDING_STATUSES, SecOpsFinding


async def create_finding(db: AsyncSession, tenant: str, payload: dict, created_by: str = "") -> SecOpsFinding:
    # validate status
    status = (payload.get("status") or "OPEN").upper()
    if status not in FINDING_STATUSES:
        raise ValueError(f"invalid finding status {status}")
    severity = (payload.get("severity") or "MEDIUM").upper()
    finding = SecOpsFinding(
        tenant=tenant,
        finding=payload.get("finding") or payload.get("title") or "",
        resource_type=payload.get("resource_type") or payload.get("resource", "").split(":")[0] if ":" in payload.get("resource","") else payload.get("resource_type",""),
        resource_id=payload.get("resource_id") or payload.get("resource") or "",
        evidence=payload.get("evidence") or [],
        policy=payload.get("policy") or "",
        policy_version=str(payload.get("policy_version") or "1"),
        severity=severity,
        owner=payload.get("owner") or created_by,
        status=status,
        confidence=float(payload.get("confidence", 0.7)),
        exposure=payload.get("exposure") or {},
        blast_radius=payload.get("blast_radius") or {},
    )
    if not finding.finding:
        raise ValueError("finding required")
    db.add(finding)
    await db.flush()
    return finding

def _to_uuid(v):
    if isinstance(v, uuid.UUID):
        return v
    try:
        return uuid.UUID(str(v))
    except Exception:
        return v

async def get_finding(db: AsyncSession, tenant: str, finding_id: str) -> SecOpsFinding | None:
    res = await db.execute(select(SecOpsFinding).where(SecOpsFinding.id == _to_uuid(finding_id), SecOpsFinding.tenant == tenant))
    return res.scalar_one_or_none()

async def list_findings(db: AsyncSession, tenant: str, status: str | None = None, severity: str | None = None, limit: int = 50) -> list[SecOpsFinding]:
    q = select(SecOpsFinding).where(SecOpsFinding.tenant == tenant)
    if status:
        q = q.where(SecOpsFinding.status == status.upper())
    if severity:
        q = q.where(SecOpsFinding.severity == severity.upper())
    q = q.order_by(SecOpsFinding.created_at.desc()).limit(min(limit, 1000))
    res = await db.execute(q)
    return list(res.scalars().all())

async def update_finding_status(db: AsyncSession, tenant: str, finding_id: str, new_status: str, actor: str = "") -> SecOpsFinding:
    finding = await get_finding(db, tenant, finding_id)
    if not finding:
        raise ValueError("finding not found")
    ns = new_status.upper()
    if ns not in FINDING_STATUSES:
        raise ValueError(f"invalid status {new_status}")
    # transitions: allow any except check tenant isolation already done
    finding.status = ns
    await db.flush()
    return finding

async def create_finding_from_policy_violation(db: AsyncSession, tenant: str, resource: str, policy: str, evidence: list, severity: str = "HIGH", owner: str = "") -> SecOpsFinding:
    return await create_finding(db, tenant, {
        "finding": f"Policy violation: {policy} on {resource}",
        "resource": resource,
        "resource_type": resource.split(":")[0] if ":" in resource else "resource",
        "evidence": evidence,
        "policy": policy,
        "severity": severity,
        "owner": owner,
        "status": "OPEN",
    })
