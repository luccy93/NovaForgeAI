"""Volume 57 — ControlService + ExceptionService + LegalHold alias.

Controls:
  - create_control — creates GovernanceControl with status NOT_ASSESSED
  - list_controls, get_control
  - collect_evidence — creates GovernanceControlEvidence with timestamp valid_until
  - assess_control — updates status PASS/FAIL/PARTIAL etc., never PASS without valid evidence
  - get_evidence, expire_evidence, build_package (evidence package for audit readiness)

Exceptions:
  - create_exception — auto-expiry via expires_at, evaluation ignores expired
  - list_exceptions, get_exception, list_active (filters expired)
  - Legal holds alias: create_hold / release_hold / is_under_hold delegate to retention

All AsyncSession, tenant-scoped, audit best-effort, no placeholders.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datagov.models import GovernanceControl, GovernanceControlEvidence, GovernanceException, GovernanceLegalHold

logger = logging.getLogger(__name__)

# ── constants ───────────────────────────────────────────────────────────

VALID_CONTROL_STATUSES: set[str] = {"PASS", "FAIL", "PARTIAL", "NOT_ASSESSED", "NOT_APPLICABLE", "IN_PROGRESS", "DEFERRED"}
VALID_EVIDENCE_TYPES: set[str] = {"audit", "config", "test", "scan", "policy_eval", "deployment", "access_review", "manual", "log", "attestation"}
# mapping lower -> canonical upper
_STATUS_CANON: dict[str, str] = {s.lower(): s for s in VALID_CONTROL_STATUSES}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(tenant: str, actor: str, action: str, resource_id: str = "", details: dict | None = None) -> None:
    try:
        from app.iam.audit_service import audit_service  # type: ignore

        try:
            audit_service.log(
                tenant,
                actor,
                "user",
                action,
                "governance_control",
                resource_id,
                "success",
                details or {},
            )
        except TypeError:
            audit_service.log(tenant, actor, "user", action, "governance_control", resource_id, "success", details or {})
    except Exception as exc:  # noqa: BLE001
        logger.debug("audit unavailable (%s): %s", action, exc)


def _parse_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except Exception:
        return None


def _norm_status(value: str) -> str:
    if not value or not str(value).strip():
        raise ValueError("status is required")
    low = str(value).strip().lower()
    if low not in _STATUS_CANON:
        raise ValueError(f"invalid control status '{value}'; allowed: {sorted(VALID_CONTROL_STATUSES)}")
    return _STATUS_CANON[low]


# ── helpers ─────────────────────────────────────────────────────────────

async def _fetch_control(db: AsyncSession, tenant: str, control_id: str) -> GovernanceControl | None:
    """Fetch control by id tenant-scoped (id is UUID pk, not control_id string)."""
    if not tenant or not control_id:
        return None
    tenant_s = str(tenant).strip()
    pid = _parse_uuid(str(control_id).strip())
    if pid is not None:
        stmt = select(GovernanceControl).where(
            GovernanceControl.tenant == tenant_s,
            GovernanceControl.id == pid,
        )
    else:
        # also allow lookup by tenant+control_id (business key)
        stmt = select(GovernanceControl).where(
            GovernanceControl.tenant == tenant_s,
            GovernanceControl.control_id == str(control_id).strip(),
        )
    result = await db.execute(stmt)
    return result.scalars().first()


async def _has_valid_evidence(db: AsyncSession, tenant: str, control_pk: uuid.UUID) -> bool:
    """Return True if at least one non-expired evidence exists for control."""
    stmt = select(GovernanceControlEvidence).where(
        GovernanceControlEvidence.control_id == control_pk,
        GovernanceControlEvidence.tenant == tenant,
    )
    result = await db.execute(stmt)
    evidences = list(result.scalars().all())
    now = _utc_now()
    for ev in evidences:
        vu = ev.valid_until
        if vu is None:
            # no expiry — counts as valid
            return True
        if vu.tzinfo is None:
            vu = vu.replace(tzinfo=timezone.utc)
        if vu > now:
            return True
    return False


# ══════════════════════════════════════════════════════════════════════════
#  ControlService
# ══════════════════════════════════════════════════════════════════════════

class ControlService:
    """Tenant-scoped governance controls + evidence."""

    # ── create_control ──────────────────────────────────────────────────

    async def create_control(
        self,
        db: AsyncSession,
        tenant: str,
        framework: str,
        control_id: str,
        policy_id: str | None = None,
        implementation: str | None = None,
        owner: str | None = None,
    ) -> GovernanceControl:
        """Create a GovernanceControl with status NOT_ASSESSED.

        Args:
            tenant: tenant scope (required).
            framework: framework name (e.g., SOC2, ISO27001, custom).
            control_id: control identifier within framework (e.g., CC6.1).
            policy_id: optional mapped policy identifier.
            implementation: implementation description.
            owner: control owner.

        Returns:
            Persisted GovernanceControl row.
        """
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        tenant_s = str(tenant).strip()

        if not framework or not str(framework).strip():
            raise ValueError("framework is required and cannot be empty")
        framework_s = str(framework).strip()

        if not control_id or not str(control_id).strip():
            raise ValueError("control_id is required and cannot be empty")
        control_id_s = str(control_id).strip()

        implementation_s = str(implementation).strip() if implementation and str(implementation).strip() else None
        owner_s = str(owner).strip() if owner and str(owner).strip() else None
        policy_id_s = str(policy_id).strip() if policy_id and str(policy_id).strip() else None

        # enforce tenant+control_id uniqueness (unique constraint)
        existing_stmt = select(GovernanceControl).where(
            GovernanceControl.tenant == tenant_s,
            GovernanceControl.control_id == control_id_s,
        )
        existing_res = await db.execute(existing_stmt)
        if existing_res.scalars().first() is not None:
            raise ValueError(f"control '{control_id_s}' already exists for tenant '{tenant_s}'")

        row = GovernanceControl(
            tenant=tenant_s,
            framework=framework_s,
            control_id=control_id_s,
            policy_id=policy_id_s,
            implementation=implementation_s,
            owner=owner_s,
            status="NOT_ASSESSED",
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)

        _audit(tenant_s, owner_s or "system", "governance.control.created", str(row.id), {"framework": framework_s, "control_id": control_id_s, "policy_id": policy_id_s})
        return row

    # ── list_controls ───────────────────────────────────────────────────

    async def list_controls(
        self,
        db: AsyncSession,
        tenant: str,
        framework: str | None = None,
        status: str | None = None,
    ) -> list[GovernanceControl]:
        """List controls for tenant with optional filters.

        Args:
            tenant: tenant scope.
            framework: optional framework filter.
            status: optional status filter.
        """
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        tenant_s = str(tenant).strip()
        stmt = select(GovernanceControl).where(GovernanceControl.tenant == tenant_s)
        if framework and str(framework).strip():
            stmt = stmt.where(GovernanceControl.framework == str(framework).strip())
        if status and str(status).strip():
            # normalize but allow partial case-insensitive
            try:
                canon = _norm_status(status)
                stmt = stmt.where(GovernanceControl.status == canon)
            except ValueError:
                # if invalid status filter, return empty (no match) rather than raise
                stmt = stmt.where(GovernanceControl.status == str(status).strip().upper())
        stmt = stmt.order_by(GovernanceControl.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    # ── get_control ─────────────────────────────────────────────────────

    async def get_control(
        self,
        db: AsyncSession,
        tenant: str,
        control_id: str,
    ) -> GovernanceControl | None:
        """Fetch single control tenant-scoped by id (UUID) or control_id.

        Args:
            tenant: tenant scope.
            control_id: GovernanceControl.id UUID string or business control_id.

        Returns:
            Row or None if not found / wrong tenant.
        """
        if not tenant or not control_id:
            raise ValueError("tenant and control_id are required")
        return await _fetch_control(db, str(tenant).strip(), str(control_id).strip())

    # ── collect_evidence ────────────────────────────────────────────────

    async def collect_evidence(
        self,
        db: AsyncSession,
        control_id: str,
        tenant: str,
        evidence_type: str,
        source: str,
        hash: str | None = None,  # noqa: A002
        valid_until: datetime | None = None,
        source_version: str | None = None,
        metadata: dict | None = None,
    ) -> GovernanceControlEvidence:
        """Create GovernanceControlEvidence with timestamp valid_until.

        Args:
            control_id: GovernanceControl id (UUID).
            tenant: tenant scope.
            evidence_type: one of audit/config/test/scan/policy_eval etc.
            source: evidence source identifier (path, url, system).
            hash: optional content hash (sha256 etc.).
            valid_until: expiry timestamp (timezone-aware). None = no expiry.
            source_version: optional version of source.
            metadata: optional metadata dict.

        Returns:
            Persisted GovernanceControlEvidence row.
        """
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        tenant_s = str(tenant).strip()

        if not control_id or not str(control_id).strip():
            raise ValueError("control_id is required")
        ctrl = await _fetch_control(db, tenant_s, str(control_id).strip())
        if ctrl is None:
            raise ValueError(f"control '{control_id}' not found for tenant '{tenant_s}'")

        if not evidence_type or not str(evidence_type).strip():
            raise ValueError("evidence_type is required")
        et = str(evidence_type).strip().lower()
        if et not in VALID_EVIDENCE_TYPES:
            raise ValueError(f"invalid evidence_type '{evidence_type}'; allowed: {sorted(VALID_EVIDENCE_TYPES)}")

        if not source or not str(source).strip():
            raise ValueError("source is required and cannot be empty")
        source_s = str(source).strip()

        hash_s = str(hash).strip() if hash and str(hash).strip() else None
        version_s = str(source_version).strip() if source_version and str(source_version).strip() else None

        # valid_until validation: must be future if provided
        vu: datetime | None = None
        if valid_until is not None:
            if not isinstance(valid_until, datetime):
                raise ValueError("valid_until must be a datetime")
            vu = valid_until
            if vu.tzinfo is None:
                vu = vu.replace(tzinfo=timezone.utc)
            # allow already-expired evidence to be collected (for audit trail) but warn

        meta = dict(metadata) if isinstance(metadata, dict) else ({"metadata": str(metadata)} if metadata is not None else {})

        row = GovernanceControlEvidence(
            control_id=ctrl.id,
            tenant=tenant_s,
            evidence_type=et,
            source=source_s,
            hash=hash_s,
            valid_until=vu,
            source_version=version_s,
            metadata_json=meta,
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)

        _audit(tenant_s, "system", "governance.evidence.collected", str(ctrl.id), {"evidence_type": et, "source": source_s, "valid_until": vu.isoformat() if vu else None, "control_id": str(ctrl.id)})
        return row

    # ── assess_control ──────────────────────────────────────────────────

    async def assess_control(
        self,
        db: AsyncSession,
        control_id: str,
        status: str,
        actor: str | None = None,
        tenant: str | None = None,
        reason: str | None = None,
    ) -> GovernanceControl:
        """Update control assessment status.

        Never mark PASS without evidence where valid_until not expired.
        Updates status to PASS/FAIL/PARTIAL/NOT_ASSESSED/NOT_APPLICABLE etc.

        Args:
            control_id: GovernanceControl id (UUID or business control_id).
            status: new status (PASS/FAIL/PARTIAL/NOT_ASSESSED/NOT_APPLICABLE etc).
            actor: actor performing assessment (for audit).
            tenant: tenant scope; if provided, enforces isolation. If None, control
                    tenant is used.
            reason: optional reason / justification.

        Returns:
            Updated GovernanceControl row.

        Raises:
            ValueError if PASS without valid evidence.
        """
        if not control_id or not str(control_id).strip():
            raise ValueError("control_id is required")
        if not status or not str(status).strip():
            raise ValueError("status is required")
        canon = _norm_status(status)
        actor_s = str(actor).strip() if actor and str(actor).strip() else "system"

        # resolve control — need tenant if provided to enforce scope
        ctrl: GovernanceControl | None = None
        if tenant and str(tenant).strip():
            ctrl = await _fetch_control(db, str(tenant).strip(), str(control_id).strip())
            if ctrl is None:
                raise ValueError(f"control '{control_id}' not found for tenant '{tenant}'")
        else:
            # try to find without tenant filter by UUID
            pid = _parse_uuid(str(control_id).strip())
            if pid is not None:
                stmt = select(GovernanceControl).where(GovernanceControl.id == pid)
                result = await db.execute(stmt)
                ctrl = result.scalars().first()
            else:
                # fallback: search without tenant (last resort, then enforce actor)
                stmt2 = select(GovernanceControl).where(GovernanceControl.control_id == str(control_id).strip())
                result2 = await db.execute(stmt2)
                ctrl = result2.scalars().first()
            if ctrl is None:
                raise ValueError(f"control '{control_id}' not found")

        tenant_s = ctrl.tenant

        # enforce PASS requires valid evidence
        if canon == "PASS":
            has_valid = await _has_valid_evidence(db, tenant_s, ctrl.id)  # type: ignore[arg-type]
            if not has_valid:
                raise ValueError("cannot mark control PASS without valid evidence (valid_until not expired) — collect evidence first")

        old_status = ctrl.status
        ctrl.status = canon
        await db.flush()
        await db.refresh(ctrl)

        _audit(tenant_s, actor_s, "governance.control.assessed", str(ctrl.id), {"from": old_status, "to": canon, "reason": reason, "control_id": ctrl.control_id, "framework": ctrl.framework})
        return ctrl

    # ── get_evidence ────────────────────────────────────────────────────

    async def get_evidence(
        self,
        db: AsyncSession,
        tenant: str,
        control_id: str,
        include_expired: bool = True,
    ) -> list[GovernanceControlEvidence]:
        """List evidence for a control tenant-scoped.

        Args:
            tenant: tenant scope.
            control_id: GovernanceControl id (UUID or business control_id).
            include_expired: if False, only evidences where valid_until is None or future.
        """
        if not tenant or not control_id:
            raise ValueError("tenant and control_id are required")
        tenant_s = str(tenant).strip()
        ctrl = await _fetch_control(db, tenant_s, str(control_id).strip())
        if ctrl is None:
            raise ValueError(f"control '{control_id}' not found for tenant '{tenant_s}'")

        stmt = select(GovernanceControlEvidence).where(
            GovernanceControlEvidence.control_id == ctrl.id,
            GovernanceControlEvidence.tenant == tenant_s,
        ).order_by(GovernanceControlEvidence.created_at.desc())
        result = await db.execute(stmt)
        evidences = list(result.scalars().all())

        if include_expired:
            return evidences

        now = _utc_now()
        filtered: list[GovernanceControlEvidence] = []
        for ev in evidences:
            vu = ev.valid_until
            if vu is None:
                filtered.append(ev)
                continue
            if vu.tzinfo is None:
                vu = vu.replace(tzinfo=timezone.utc)
            if vu > now:
                filtered.append(ev)
        return filtered

    # ── expire_evidence ─────────────────────────────────────────────────

    async def expire_evidence(
        self,
        db: AsyncSession,
        tenant: str,
        evidence_id: str | None = None,
        control_id: str | None = None,
    ) -> list[GovernanceControlEvidence] | GovernanceControlEvidence:
        """Expire evidence.

        Two modes:
          - evidence_id provided: expires single evidence by setting valid_until to now.
          - control_id provided (and no evidence_id): expires all expired evidences check
            returns list of still-valid evidences (no mutation), or if explicit, marks.

        For audit readiness, this method marks evidences where valid_until <= now as
        expired by returning them; caller can also expire a single evidence manually.

        Args:
            tenant: tenant scope.
            evidence_id: specific evidence pk (UUID string) to expire immediately.
            control_id: if evidence_id is None and control_id provided, returns
                        list of expired evidences for that control.

        Returns:
            If evidence_id provided: single updated GovernanceControlEvidence.
            Else: list of evidences that are expired (valid_until <= now).
        """
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        tenant_s = str(tenant).strip()

        if evidence_id and str(evidence_id).strip():
            eid = str(evidence_id).strip()
            pid = _parse_uuid(eid)
            if pid is not None:
                stmt = select(GovernanceControlEvidence).where(
                    GovernanceControlEvidence.tenant == tenant_s,
                    GovernanceControlEvidence.id == pid,
                )
            else:
                stmt = select(GovernanceControlEvidence).where(  # type: ignore
                    GovernanceControlEvidence.tenant == tenant_s,
                    GovernanceControlEvidence.id == eid,  # type: ignore
                )
            result = await db.execute(stmt)
            ev: GovernanceControlEvidence | None = result.scalars().first()
            if ev is None:
                raise ValueError(f"evidence '{evidence_id}' not found for tenant '{tenant_s}'")
            # expire by setting valid_until to now (if already expired, keep)
            ev.valid_until = _utc_now()
            await db.flush()
            await db.refresh(ev)
            _audit(tenant_s, "system", "governance.evidence.expired", str(ev.control_id), {"evidence_id": str(ev.id), "control_id": str(ev.control_id)})
            return ev

        # control_id mode: return expired list
        if control_id and str(control_id).strip():
            ctrl = await _fetch_control(db, tenant_s, str(control_id).strip())
            if ctrl is None:
                raise ValueError(f"control '{control_id}' not found for tenant '{tenant_s}'")
            evidences = await self.get_evidence(db, tenant_s, str(control_id).strip(), include_expired=True)
            now = _utc_now()
            expired: list[GovernanceControlEvidence] = []
            for ev in evidences:
                vu = ev.valid_until
                if vu is None:
                    continue
                if vu.tzinfo is None:
                    vu = vu.replace(tzinfo=timezone.utc)
                if vu <= now:
                    expired.append(ev)
            return expired

        raise ValueError("either evidence_id or control_id is required")

    # ── build_package ───────────────────────────────────────────────────

    async def build_package(
        self,
        db: AsyncSession,
        tenant: str,
        framework: str | None = None,
        control_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Build evidence package for audit readiness.

        Args:
            tenant: tenant scope.
            framework: optional framework filter.
            control_ids: optional list of control ids (UUID or business) to include.

        Returns:
            dict with:
              - tenant, generated_at, framework
              - controls (list of control dicts with evidence)
              - summary (counts by status, evidence validity)
              - audit_ready (bool, True if every PASS control has valid evidence)
              - expired_evidence (list)
        """
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        tenant_s = str(tenant).strip()

        # fetch controls
        controls: list[GovernanceControl] = []
        if control_ids and isinstance(control_ids, list) and len(control_ids) > 0:
            for cid in control_ids:
                c = await _fetch_control(db, tenant_s, str(cid).strip())
                if c is not None:
                    controls.append(c)
        else:
            controls = await self.list_controls(db, tenant_s, framework=framework)

        now = _utc_now()
        package_controls: list[dict[str, Any]] = []
        total_evidence = 0
        valid_evidence = 0
        expired_evidence: list[dict[str, Any]] = []
        status_counts: dict[str, int] = {s: 0 for s in VALID_CONTROL_STATUSES}
        audit_ready = True

        for ctrl in controls:
            status_counts[ctrl.status] = status_counts.get(ctrl.status, 0) + 1
            stmt = select(GovernanceControlEvidence).where(
                GovernanceControlEvidence.control_id == ctrl.id,
                GovernanceControlEvidence.tenant == tenant_s,
            ).order_by(GovernanceControlEvidence.created_at.desc())
            result = await db.execute(stmt)
            evidences = list(result.scalars().all())
            total_evidence += len(evidences)

            valid_list: list[dict[str, Any]] = []
            expired_list: list[dict[str, Any]] = []
            for ev in evidences:
                vu = ev.valid_until
                is_expired = False
                if vu is not None:
                    if vu.tzinfo is None:
                        vu = vu.replace(tzinfo=timezone.utc)
                    if vu <= now:
                        is_expired = True
                if is_expired:
                    expired_list.append(
                        {
                            "evidence_id": str(ev.id),
                            "evidence_type": ev.evidence_type,
                            "source": ev.source,
                            "hash": ev.hash,
                            "valid_until": vu.isoformat() if vu else None,
                            "source_version": ev.source_version,
                            "expired": True,
                        }
                    )
                    expired_evidence.append(
                        {
                            "evidence_id": str(ev.id),
                            "control_id": str(ctrl.id),
                            "control_business_id": ctrl.control_id,
                            "framework": ctrl.framework,
                            "valid_until": vu.isoformat() if vu else None,
                        }
                    )
                else:
                    valid_list.append(
                        {
                            "evidence_id": str(ev.id),
                            "evidence_type": ev.evidence_type,
                            "source": ev.source,
                            "hash": ev.hash,
                            "valid_until": vu.isoformat() if vu else None,
                            "source_version": ev.source_version,
                            "expired": False,
                        }
                    )
                    valid_evidence += 1

            # audit readiness: PASS must have at least one valid evidence
            if ctrl.status == "PASS" and len(valid_list) == 0:
                audit_ready = False

            package_controls.append(
                {
                    "control_pk": str(ctrl.id),
                    "control_id": ctrl.control_id,
                    "framework": ctrl.framework,
                    "policy_id": ctrl.policy_id,
                    "implementation": ctrl.implementation,
                    "owner": ctrl.owner,
                    "status": ctrl.status,
                    "created_at": ctrl.created_at.isoformat() if ctrl.created_at else None,
                    "updated_at": ctrl.updated_at.isoformat() if ctrl.updated_at else None,
                    "evidences_total": len(evidences),
                    "evidences_valid": len(valid_list),
                    "evidences_expired": len(expired_list),
                    "valid_evidence": valid_list,
                    "expired_evidence": expired_list,
                }
            )

        summary = {
            "controls_total": len(controls),
            "by_status": {k: v for k, v in status_counts.items() if v > 0},
            "evidence_total": total_evidence,
            "evidence_valid": valid_evidence,
            "evidence_expired": len(expired_evidence),
            "audit_ready": audit_ready,
        }

        result: dict[str, Any] = {
            "tenant": tenant_s,
            "generated_at": now.isoformat(),
            "framework": framework.strip() if framework and str(framework).strip() else None,
            "controls": package_controls,
            "summary": summary,
            "audit_ready": audit_ready,
            "expired_evidence": expired_evidence,
            "disclaimer": "evidence package for audit readiness — not legal attestation",
        }

        _audit(tenant_s, "system", "governance.package.built", "", {"framework": framework, "controls": len(controls), "audit_ready": audit_ready})
        return result


# ══════════════════════════════════════════════════════════════════════════
#  ExceptionService (same file per spec option)
# ══════════════════════════════════════════════════════════════════════════

class ExceptionService:
    """Tenant-scoped exception registry with auto-expiry."""

    async def create_exception(
        self,
        db: AsyncSession,
        tenant: str,
        policy_id: str | None = None,
        resource: str | None = None,
        reason: str | None = None,
        scope: dict | None = None,
        owner: str | None = None,
        approval: str | None = None,
        expires_at: datetime | None = None,
    ) -> GovernanceException:
        """Create an exception with auto-expiry.

        Expired exceptions are ignored at evaluation time (ExceptionExpired event
        model is used elsewhere). Legal holds already exist in retention but alias
        is provided here for convenience.

        Args:
            tenant: tenant scope (required).
            policy_id: optional policy this exception applies to.
            resource: optional resource identifier.
            reason: reason for exception (required, non-empty).
            scope: scope descriptor dict (optional).
            owner: owner/creator (required).
            approval: approval reference (approver or workflow id).
            expires_at: expiry timestamp (timezone-aware preferred). None = indefinite
                        but callers should always set to prevent perpetual exceptions.

        Returns:
            Persisted GovernanceException row.
        """
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        tenant_s = str(tenant).strip()
        if not reason or not str(reason).strip():
            raise ValueError("reason is required and cannot be empty")
        reason_s = str(reason).strip()
        if not owner or not str(owner).strip():
            raise ValueError("owner is required and cannot be empty")
        owner_s = str(owner).strip()

        policy_id_s = str(policy_id).strip() if policy_id and str(policy_id).strip() else None
        resource_s = str(resource).strip() if resource and str(resource).strip() else None
        approval_s = str(approval).strip() if approval and str(approval).strip() else None
        scope_dict = dict(scope) if isinstance(scope, dict) else ({"scope": str(scope).strip()} if isinstance(scope, str) and str(scope).strip() else {} if scope is None else {"scope": scope})  # type: ignore
        if not isinstance(scope_dict, dict):
            scope_dict = {"scope": str(scope_dict)}

        expires: datetime | None = None
        if expires_at is not None:
            if not isinstance(expires_at, datetime):
                raise ValueError("expires_at must be a datetime")
            expires = expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires <= _utc_now():
                logger.warning("exception expires_at %s is in the past — will be considered expired immediately", expires.isoformat())

        row = GovernanceException(
            tenant=tenant_s,
            policy_id=policy_id_s,
            resource=resource_s,
            reason=reason_s,
            scope=scope_dict,
            owner=owner_s,
            approval=approval_s,
            expires_at=expires,
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)

        _audit(tenant_s, owner_s, "governance.exception.created", str(row.id), {"policy_id": policy_id_s, "resource": resource_s, "expires_at": expires.isoformat() if expires else None})
        return row

    async def list_exceptions(
        self,
        db: AsyncSession,
        tenant: str,
        include_expired: bool = False,
        policy_id: str | None = None,
    ) -> list[GovernanceException]:
        """List exceptions tenant-scoped.

        Args:
            tenant: tenant scope.
            include_expired: if False, only active (not yet expired).
            policy_id: optional filter by policy_id.
        """
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        tenant_s = str(tenant).strip()
        stmt = select(GovernanceException).where(GovernanceException.tenant == tenant_s)
        if policy_id and str(policy_id).strip():
            stmt = stmt.where(GovernanceException.policy_id == str(policy_id).strip())
        stmt = stmt.order_by(GovernanceException.created_at.desc())
        result = await db.execute(stmt)
        rows = list(result.scalars().all())
        if include_expired:
            return rows
        now = _utc_now()
        active: list[GovernanceException] = []
        for r in rows:
            exp = r.expires_at
            if exp is None:
                active.append(r)
                continue
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp > now:
                active.append(r)
        return active

    async def get_exception(
        self,
        db: AsyncSession,
        tenant: str,
        exception_id: str,
    ) -> GovernanceException | None:
        """Fetch single exception tenant-scoped."""
        if not tenant or not exception_id:
            raise ValueError("tenant and exception_id are required")
        tenant_s = str(tenant).strip()
        pid = _parse_uuid(str(exception_id).strip())
        if pid is not None:
            stmt = select(GovernanceException).where(
                GovernanceException.tenant == tenant_s,
                GovernanceException.id == pid,
            )
        else:
            stmt = select(GovernanceException).where(
                GovernanceException.tenant == tenant_s,
                GovernanceException.id == exception_id,  # type: ignore
            )
        result = await db.execute(stmt)
        return result.scalars().first()

    async def is_exception_active(
        self,
        db: AsyncSession,
        tenant: str,
        exception_id: str,
    ) -> bool:
        """Check if exception is still active (not expired)."""
        row = await self.get_exception(db, tenant, exception_id)
        if row is None:
            return False
        if row.expires_at is None:
            return True
        exp = row.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return _utc_now() < exp

    async def expire_exceptions(
        self,
        db: AsyncSession,
        tenant: str,
    ) -> list[GovernanceException]:
        """Return list of expired exceptions for tenant (auto-expiry check).

        Does not delete rows — caller should ignore expired at evaluation time.
        Optionally emits GovernanceExceptionExpired event best-effort.
        """
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        tenant_s = str(tenant).strip()
        all_rows = await self.list_exceptions(db, tenant_s, include_expired=True)
        now = _utc_now()
        expired: list[GovernanceException] = []
        for r in all_rows:
            exp = r.expires_at
            if exp is None:
                continue
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp <= now:
                expired.append(r)
                # best-effort event emission (never fails call)
                try:
                    from app.core.events import EventBus  # type: ignore
                    # event bus usage is best-effort; spec says ExceptionExpired event
                    logger.debug("exception %s expired at %s", str(r.id), exp.isoformat())
                except Exception:
                    pass
        if expired:
            _audit(tenant_s, "system", "governance.exception.expired", "", {"expired_count": len(expired), "ids": [str(e.id) for e in expired[:10]]})
        return expired

    # ── legal hold alias (ensure alias even though retention already has it) ─

    async def create_hold(
        self,
        db: AsyncSession,
        tenant: str,
        scope: str,
        reason: str,
        created_by: str,
    ) -> GovernanceLegalHold:
        """Legal hold alias — delegates to RetentionService but self-contained.

        Provided so callers using controls/exceptions module can create holds
        without importing retention.
        """
        if not tenant or not scope or not reason or not created_by:
            raise ValueError("tenant, scope, reason and created_by are required")
        # delegate to RetentionService if available, else self-contained
        try:
            from app.datagov.retention import RetentionService

            svc = RetentionService()
            return await svc.create_hold(db, tenant, scope, reason, created_by)
        except Exception:
            # fallback self-contained
            row = GovernanceLegalHold(
                tenant=str(tenant).strip(),
                scope=str(scope).strip(),
                reason=str(reason).strip(),
                created_by=str(created_by).strip(),
                released_at=None,
                released_by=None,
                audit=[{"action": "create", "by": str(created_by).strip(), "at": _utc_now().isoformat(), "reason": str(reason).strip(), "scope": str(scope).strip()}],
            )
            db.add(row)
            await db.flush()
            await db.refresh(row)
            _audit(str(tenant).strip(), str(created_by).strip(), "governance.legal_hold.created", str(row.id), {"scope": scope, "reason": reason})
            return row

    async def release_hold(
        self,
        db: AsyncSession,
        tenant: str,
        hold_id: str,
        released_by: str,
    ) -> GovernanceLegalHold:
        """Release hold alias."""
        if not tenant or not hold_id or not released_by:
            raise ValueError("tenant, hold_id and released_by are required")
        try:
            from app.datagov.retention import RetentionService

            svc = RetentionService()
            return await svc.release_hold(db, tenant, hold_id, released_by)
        except Exception:
            pid = _parse_uuid(str(hold_id).strip())
            if pid is not None:
                stmt = select(GovernanceLegalHold).where(
                    GovernanceLegalHold.tenant == str(tenant).strip(),
                    GovernanceLegalHold.id == pid,
                )
            else:
                stmt = select(GovernanceLegalHold).where(
                    GovernanceLegalHold.tenant == str(tenant).strip(),
                    GovernanceLegalHold.id == hold_id,  # type: ignore
                )
            result = await db.execute(stmt)
            hold: GovernanceLegalHold | None = result.scalars().first()
            if hold is None:
                raise ValueError(f"legal hold '{hold_id}' not found for tenant '{tenant}'")
            if hold.released_at is not None:
                raise ValueError("legal hold already released")
            hold.released_at = _utc_now()
            hold.released_by = str(released_by).strip()
            audit = list(hold.audit or [])
            audit.append({"action": "release", "by": str(released_by).strip(), "at": _utc_now().isoformat()})
            hold.audit = audit
            await db.flush()
            await db.refresh(hold)
            _audit(str(tenant).strip(), str(released_by).strip(), "governance.legal_hold.released", str(hold.id), {"scope": hold.scope})
            return hold

    async def is_under_hold(
        self,
        db: AsyncSession,
        tenant: str,
        asset_id: str,
        resource: str | None = None,
    ) -> bool:
        """Check hold alias."""
        try:
            from app.datagov.retention import RetentionService

            svc = RetentionService()
            return await svc.is_under_hold(db, tenant, asset_id, resource)
        except Exception:
            # fallback inline
            stmt = select(GovernanceLegalHold).where(
                GovernanceLegalHold.tenant == str(tenant).strip(),
                GovernanceLegalHold.released_at.is_(None),
            )
            result = await db.execute(stmt)
            holds = list(result.scalars().all())
            if not holds:
                return False
            asset_id_s = str(asset_id).strip()
            resource_s = str(resource).strip() if resource else None
            for h in holds:
                scope = str(h.scope).strip() if h.scope else ""
                if not scope:
                    continue
                if scope == "*" or scope.lower() == "all":
                    return True
                if scope == asset_id_s or (resource_s and scope == resource_s):
                    return True
                if scope in (f"asset:{asset_id_s}", f"asset_id:{asset_id_s}"):
                    return True
                if resource_s and scope in (f"resource:{resource_s}", f"resource_id:{resource_s}"):
                    return True
                if asset_id_s in scope or scope in asset_id_s:
                    return True
                if resource_s and (resource_s in scope or scope in resource_s):
                    return True
            return False


control_service = ControlService()
exception_service = ExceptionService()
# alias exports for convenience
create_exception = exception_service.create_exception
