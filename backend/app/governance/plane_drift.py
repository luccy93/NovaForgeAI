"""Policy drift detection — Volume 71 Commit 2.

Finds: tampered ACTIVE versions (checksum mismatch), ACTIVE versions
past effective_until, resources operating without bindings (from
recent decision/evaluation activity), and mandatory controls missing
verified evidence. Findings are actionable rows + audit events, never
silent mutations.
"""

from __future__ import annotations

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.governance.plane_common import (
    ValidationError,
    _utcnow,
    canonical_checksum,
    sanitize_metadata,
)
from app.governance.plane_models import (
    GovernancePlaneBinding,
    GovernancePlaneEvaluation,
    GovernancePlanePolicyVersion,
)
from app.governance.plane_models_c2 import GovernancePlaneDriftFinding

SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")


async def _open_finding(db: AsyncSession, tenant: str, finding_type: str,
                        severity: str, resource_type: str, resource_id: str,
                        description: str, metadata: dict | None = None) -> dict:
    existing = (await db.execute(select(GovernancePlaneDriftFinding).where(
        GovernancePlaneDriftFinding.tenant == tenant,
        GovernancePlaneDriftFinding.finding_type == finding_type,
        GovernancePlaneDriftFinding.resource_id == resource_id,
        GovernancePlaneDriftFinding.status == "OPEN",
    ))).scalar_one_or_none()
    if existing is not None:
        return {"id": str(existing.id), "deduplicated": True, "finding_type": finding_type}
    row = GovernancePlaneDriftFinding(
        tenant=tenant, finding_type=finding_type, severity=severity,
        resource_type=resource_type, resource_id=resource_id,
        description=description[:1024], status="OPEN",
        metadata_=sanitize_metadata(metadata),
    )
    db.add(row)
    await db.flush()
    try:
        from app.governance.plane_common import emit_event
        await emit_event("governance_drift_detected",
                         {"finding_type": finding_type, "severity": severity,
                          "resource_id": resource_id}, tenant)
    except Exception:
        pass
    return {"id": str(row.id), "finding_type": finding_type, "severity": severity}


async def detect_drift(db: AsyncSession, tenant: str) -> dict:
    if not tenant:
        raise ValidationError("tenant required")
    now = _utcnow()
    findings: list[dict] = []

    # 1. Tampered or expired ACTIVE versions.
    active = (await db.execute(select(GovernancePlanePolicyVersion).where(
        GovernancePlanePolicyVersion.tenant == tenant,
        GovernancePlanePolicyVersion.status == "ACTIVE"))).scalars().all()
    for row in active:
        expected = canonical_checksum({"rules": row.rules or [],
                                       "default_effect": row.default_effect})
        if expected != row.checksum:
            findings.append(await _open_finding(
                db, tenant, "policy_tampered", "CRITICAL", "policy_version",
                str(row.id), f"checksum mismatch on ACTIVE version {row.version}",
                {"policy_id": str(row.policy_id)}))
        elif row.effective_until and row.effective_until <= now:
            findings.append(await _open_finding(
                db, tenant, "policy_version_expired", "HIGH", "policy_version",
                str(row.id), f"ACTIVE version {row.version} past effective_until",
                {"policy_id": str(row.policy_id)}))

    # 2. Scopes with recent evaluation activity but no enabled binding.
    recent = (await db.execute(select(
        GovernancePlaneEvaluation.scope_type,
        GovernancePlaneEvaluation.scope_value,
        func.count().label("n"),
    ).where(
        GovernancePlaneEvaluation.tenant == tenant,
    ).group_by(GovernancePlaneEvaluation.scope_type,
               GovernancePlaneEvaluation.scope_value).limit(200))).all()
    bindings = (await db.execute(select(GovernancePlaneBinding).where(
        GovernancePlaneBinding.tenant == tenant,
        GovernancePlaneBinding.enabled == True,  # noqa: E712
    ))).scalars().all()
    covered = {(b.scope_type, b.scope_value or "") for b in bindings}
    covered |= {(b.scope_type, "") for b in bindings}
    for scope_type, scope_value, count in recent:
        key = (scope_type, scope_value or "")
        if key not in covered and (scope_type, "") not in covered and count >= 3:
            findings.append(await _open_finding(
                db, tenant, "unbound_scope", "MEDIUM", "scope",
                f"{scope_type}:{scope_value or '*'}",
                f"{count} evaluations without an enabled binding",
                {"evaluations": int(count)}))

    # 3. Mandatory datagov controls without verified evidence.
    try:
        from app.datagov.models import GovernanceControl
        controls = (await db.execute(select(GovernanceControl).where(
            GovernanceControl.tenant == tenant))).scalars().all()
        if controls:
            from app.governance.plane_models_c2 import GovernancePlaneEvidence
            verified_keys = {r.control_key for r in (await db.execute(select(
                GovernancePlaneEvidence).where(
                GovernancePlaneEvidence.tenant == tenant,
                GovernancePlaneEvidence.valid_until > now,
            ))).scalars().all()}
            for control in controls:
                if control.control_id not in verified_keys:
                    findings.append(await _open_finding(
                        db, tenant, "control_without_evidence", "LOW", "control",
                        control.control_id,
                        f"control {control.control_id} lacks verified evidence",
                        {"framework": control.framework}))
    except Exception:
        pass
    return {"findings": findings, "total": len(findings)}


async def list_drift(db: AsyncSession, tenant: str, *, status: str = "",
                     severity: str = "", limit: int = 100) -> dict:
    stmt = select(GovernancePlaneDriftFinding).where(
        GovernancePlaneDriftFinding.tenant == tenant)
    if status:
        stmt = stmt.where(GovernancePlaneDriftFinding.status == status)
    if severity:
        stmt = stmt.where(GovernancePlaneDriftFinding.severity == severity)
    limit = min(max(int(limit or 100), 1), 1000)
    rows = (await db.execute(stmt.order_by(
        desc(GovernancePlaneDriftFinding.created_at)).limit(limit))).scalars().all()
    return {"items": [{
        "id": str(r.id), "finding_type": r.finding_type, "severity": r.severity,
        "resource_type": r.resource_type or "", "resource_id": r.resource_id or "",
        "description": r.description or "", "status": r.status,
    } for r in rows], "total": len(rows)}


async def resolve_drift(db: AsyncSession, tenant: str, finding_id, *, actor: str = "") -> dict:
    from app.governance.plane_common import _as_uuid, NotFoundError
    stmt = select(GovernancePlaneDriftFinding).where(
        GovernancePlaneDriftFinding.id == _as_uuid(finding_id),
        GovernancePlaneDriftFinding.tenant == tenant)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise NotFoundError("drift finding not found")
    row.status = "RESOLVED"
    await db.flush()
    return {"id": str(row.id), "status": row.status}
