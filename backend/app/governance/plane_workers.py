"""Governance background workers — Volume 71 Commit 1.

Lease-guarded jobs reusing the platform lease-dict convention:
scheduled policy evaluation sweeps, expired-exception cleanup,
posture refresh, evidence refresh and policy drift detection.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.governance.plane_common import _utcnow

logger = logging.getLogger(__name__)

_leases: dict[str, dict] = {}


def _worker_id() -> str:
    return f"governance-worker-{uuid.uuid4().hex[:8]}"


async def acquire_lease(tenant: str, job_key: str, worker_id: str, ttl_seconds: int = 300) -> bool:
    from datetime import timedelta
    now = _utcnow()
    key = f"{tenant}:{job_key}"
    lease = _leases.get(key)
    if lease and lease["expires_at"] > now and lease["worker_id"] != worker_id:
        return False
    _leases[key] = {"worker_id": worker_id, "acquired_at": now,
                    "expires_at": now + timedelta(seconds=ttl_seconds)}
    return True


async def release_lease(tenant: str, job_key: str, worker_id: str) -> None:
    key = f"{tenant}:{job_key}"
    lease = _leases.get(key)
    if lease and lease["worker_id"] == worker_id:
        _leases.pop(key, None)


async def _guarded(tenant: str, job_key: str, worker_id: str, coro):
    if not await acquire_lease(tenant, job_key, worker_id):
        return {"status": "skipped", "reason": "lease held by another worker"}
    try:
        return await coro
    except Exception as exc:
        logger.warning("governance job %s failed: %s", job_key, exc)
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
    finally:
        await release_lease(tenant, job_key, worker_id)


async def run_evaluation_sweep(db: AsyncSession, tenant: str, *,
                               worker_id: Optional[str] = None, limit: int = 50,
                               actor: str = "worker") -> dict:
    """Re-evaluate a bounded sample of recent bindings to detect drift
    between stored posture and current decisions."""
    from app.governance.plane_evaluate import evaluate
    from app.governance.plane_models import GovernancePlaneBinding

    worker_id = worker_id or _worker_id()

    async def _run():
        rows = (await db.execute(select(GovernancePlaneBinding).where(
            GovernancePlaneBinding.tenant == tenant,
            GovernancePlaneBinding.enabled == True,  # noqa: E712
        ).limit(min(max(int(limit or 50), 1), 200)))).scalars().all()
        evaluated, denies = 0, 0
        for row in rows:
            result = await evaluate(
                db, tenant, scope_type=row.scope_type, scope_value=row.scope_value or "",
                operation="sweep", context={"sweep": True}, actor=actor)
            evaluated += 1
            if result["decision"] == "DENY":
                denies += 1
        return {"status": "completed", "evaluated": evaluated, "denies": denies}

    return await _guarded(tenant, "evaluation-sweep", worker_id, _run())


async def run_exception_cleanup(db: AsyncSession, tenant: str, *,
                                worker_id: Optional[str] = None) -> dict:
    from app.governance.plane_exceptions import expire_due_exceptions

    worker_id = worker_id or _worker_id()

    async def _run():
        result = await expire_due_exceptions(db, tenant)
        return {"status": "completed", **result}

    return await _guarded(tenant, "exception-cleanup", worker_id, _run())


async def run_posture_refresh(db: AsyncSession, tenant: str, *,
                              scope_type: str = "tenant", scope_value: str = "",
                              worker_id: Optional[str] = None) -> dict:
    worker_id = worker_id or _worker_id()

    async def _run():
        try:
            from app.governance.plane_posture import refresh_posture  # C2 module
        except ImportError:
            from app.governance.plane_workers import _refresh_posture_basic as refresh_posture
        result = await refresh_posture(db, tenant, scope_type=scope_type,
                                       scope_value=scope_value)
        return {"status": "completed", **result}

    return await _guarded(tenant, f"posture:{scope_type}", worker_id, _run())


async def _refresh_posture_basic(db: AsyncSession, tenant: str, *,
                                 scope_type: str = "tenant", scope_value: str = "") -> dict:
    """C1 posture refresh: counts from governed tables only (no invented
    percentages). C2 replaces the calculator, not the table."""
    from datetime import timedelta
    from sqlalchemy import func
    from app.governance.plane_models import (
        GovernancePlaneDecision,
        GovernancePlaneException,
        GovernancePlanePolicy,
        GovernancePlanePostureSnapshot,
    )

    total = (await db.execute(select(func.count()).select_from(GovernancePlanePolicy).where(
        GovernancePlanePolicy.tenant == tenant))).scalar() or 0
    active = (await db.execute(select(func.count()).select_from(GovernancePlanePolicy).where(
        GovernancePlanePolicy.tenant == tenant,
        GovernancePlanePolicy.status == "ACTIVE"))).scalar() or 0
    day_ago = _utcnow() - timedelta(hours=24)
    violations = (await db.execute(select(func.count()).select_from(GovernancePlaneDecision).where(
        GovernancePlaneDecision.tenant == tenant,
        GovernancePlaneDecision.decision == "DENY",
        GovernancePlaneDecision.created_at >= day_ago))).scalar() or 0
    open_exc = (await db.execute(select(func.count()).select_from(GovernancePlaneException).where(
        GovernancePlaneException.tenant == tenant,
        GovernancePlaneException.status == "APPROVED"))).scalar() or 0
    row = GovernancePlanePostureSnapshot(
        tenant=tenant, scope_type=scope_type, scope_value=scope_value or "",
        domain="general", total_policies=int(total), active_policies=int(active),
        violations_24h=int(violations), open_exceptions=int(open_exc),
        verified_controls=0, failing_controls=0, computed_at=_utcnow(), metadata_={},
    )
    db.add(row)
    await db.flush()
    return {"snapshot_id": str(row.id), "total_policies": int(total),
            "active_policies": int(active), "violations_24h": int(violations),
            "open_exceptions": int(open_exc)}


async def run_evidence_refresh(db: AsyncSession, tenant: str, *,
                               worker_id: Optional[str] = None, limit: int = 100) -> dict:
    worker_id = worker_id or _worker_id()

    async def _run():
        try:
            from app.governance.plane_evidence import refresh_evidence  # C2 module
            return {"status": "completed", **await refresh_evidence(db, tenant, limit=limit)}
        except ImportError:
            return {"status": "completed", "refreshed": 0, "note": "evidence plane lands in C2"}

    return await _guarded(tenant, "evidence-refresh", worker_id, _run())


async def run_drift_detection(db: AsyncSession, tenant: str, *,
                              worker_id: Optional[str] = None) -> dict:
    worker_id = worker_id or _worker_id()

    async def _run():
        try:
            from app.governance.plane_drift import detect_drift  # C2 module
            return {"status": "completed", **await detect_drift(db, tenant)}
        except ImportError:
            from app.governance.plane_models import GovernancePlanePolicyVersion
            from app.governance.plane_common import canonical_checksum
            rows = (await db.execute(select(GovernancePlanePolicyVersion).where(
                GovernancePlanePolicyVersion.tenant == tenant,
                GovernancePlanePolicyVersion.status == "ACTIVE"))).scalars().all()
            tampered = []
            for row in rows:
                expected = canonical_checksum({"rules": row.rules or [],
                                               "default_effect": row.default_effect})
                if expected != row.checksum:
                    tampered.append(str(row.id))
            try:
                from app.governance.plane_common import emit_event
                if tampered:
                    await emit_event("governance_drift_detected",
                                     {"tampered_versions": tampered}, tenant)
            except Exception:
                pass
            return {"status": "completed", "tampered_versions": tampered,
                    "checked": len(rows)}

    return await _guarded(tenant, "drift-detection", worker_id, _run())
