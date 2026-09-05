"""Compliance controls over existing authorities — Volume 71 Commit 2.

Thin wrapper on the V57 datagov ControlService (create/collect/
assess/package). No parallel control store is created. Evidence
collection references existing artifacts with integrity metadata and
never copies sensitive datasets.
"""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.governance.plane_common import (
    NotFoundError,
    ValidationError,
    _utcnow,
    sanitize_metadata,
)

EVIDENCE_VALIDITY_DAYS = 90


async def _service():
    from app.datagov.controls import ControlService
    return ControlService()


async def create_control(
    db: AsyncSession, tenant: str, framework: str, control_id: str, *,
    policy_id: Optional[str] = None, implementation: str = "",
    owner: str = "", actor: str = "",
) -> dict:
    if not tenant:
        raise ValidationError("tenant required")
    if not (control_id or "").strip():
        raise ValidationError("control_id required")
    service = await _service()
    row = await service.create_control(db, tenant, framework or "internal",
                                       control_id.strip(), policy_id=policy_id,
                                       implementation=implementation or "",
                                       owner=owner or "")
    return {"id": str(row.id), "tenant": row.tenant, "framework": row.framework,
            "control_id": row.control_id, "status": row.status,
            "owner": row.owner or ""}


async def list_controls(db: AsyncSession, tenant: str, *, framework: str = "",
                        limit: int = 100) -> dict:
    from app.datagov.models import GovernanceControl

    stmt = select(GovernanceControl).where(GovernanceControl.tenant == tenant)
    if framework:
        stmt = stmt.where(GovernanceControl.framework == framework)
    limit = min(max(int(limit or 100), 1), 1000)
    rows = (await db.execute(stmt.order_by(desc(GovernanceControl.created_at)).limit(limit))).scalars().all()
    return {"items": [{"id": str(r.id), "tenant": r.tenant, "framework": r.framework,
                       "control_id": r.control_id, "status": r.status,
                       "owner": r.owner or ""} for r in rows], "total": len(rows)}


async def assess_control(db: AsyncSession, tenant: str, control_id, status: str, *,
                         actor: str = "", reason: str = "") -> dict:
    allowed = ("PASS", "FAIL", "NOT_ASSESSED", "WAIVED")
    if status not in allowed:
        raise ValidationError(f"invalid status: {status!r}")
    service = await _service()
    row = await service.assess_control(db, str(control_id), status,
                                       actor=actor or None, tenant=tenant,
                                       reason=reason or None)
    if row is None:
        raise NotFoundError("control not found")
    return {"id": str(row.id), "control_id": row.control_id, "status": row.status}


def integrity_hash(source_system: str, source_ref: str, source_version: str = "") -> str:
    return hashlib.sha256(json.dumps(
        [source_system, source_ref, source_version], sort_keys=True).encode()).hexdigest()


async def collect_control_evidence(
    db: AsyncSession, tenant: str, control_id, *,
    source_system: str, source_ref: str, source_version: str = "",
    validity_days: int = EVIDENCE_VALIDITY_DAYS, actor: str = "",
) -> dict:
    """Record evidence as reference + hash. The source artifact itself is
    never copied into governance storage."""
    if not source_system or not source_ref:
        raise ValidationError("source_system and source_ref required")
    service = await _service()
    digest = integrity_hash(source_system, source_ref, source_version)
    row = await service.collect_evidence(
        db, str(control_id), tenant, "audit", source_system, hash=digest,
        valid_until=_utcnow() + timedelta(days=min(max(int(validity_days or 90), 1), 365)))
    try:
        from app.governance.plane_common import emit_event
        await emit_event("governance_evidence_collected",
                         {"control_id": str(control_id), "source": source_system}, tenant)
    except Exception:
        pass
    return {"id": str(row.id), "control_id": str(row.control_id),
            "source": row.source, "hash": row.hash,
            "valid_until": row.valid_until.isoformat() if row.valid_until else None}


async def control_package(db: AsyncSession, tenant: str, *, framework: str = "") -> dict:
    service = await _service()
    return await service.build_package(db, tenant, framework=framework or None)
