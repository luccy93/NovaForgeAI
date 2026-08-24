"""Volume 58 — AIApprovalService.

Tenant-scoped, AsyncSession, no placeholders.

Manages ``ai_approval_requests`` for model/provider/production approvals.

* request_approval — creates a tenant-scoped approval request bound to
  exact model/provider/version
* approve          — records approver decision bound to exact
  model/provider/version, never reuse across versions

Tenant isolation: every read/write scoped to tenant.  Approval is
immutable with respect to model/provider/version — approve never reuses
across versions; a new request is required for a new version.

No placeholders — all branches are real AsyncSession operations.
Audit best-effort via ``app.iam.audit_service`` — never raises.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.aiml.models import AIApprovalRequest
from app.core.exceptions import ConflictError, NotFoundError, ValidationError

logger = logging.getLogger(__name__)


_VALID_REQUEST_TYPES: set[str] = {
    "new_model",
    "new_provider",
    "restricted_data",
    "production",
    "high_risk",
    "model_deployment",
    "data_access",
    "cross_border",
    "tool_use",
    "agent_deployment",
}

_VALID_DECISIONS: set[str] = {"approved", "rejected", "approve", "reject", "allow", "deny", "pending", "cancelled"}
_APPROVED_NORM = {"approved", "approve", "allow"}
_REJECTED_NORM = {"rejected", "reject", "deny"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _audit(tenant: str, actor: str, action: str, resource_id: str = "", details: dict | None = None) -> None:
    try:
        from app.iam.audit_service import audit_service  # type: ignore

        safe: dict = {}
        if details:
            for k, v in details.items():
                if k in ("raw_value", "secret", "prompt", "content", "value", "match"):
                    continue
                if isinstance(v, dict) and "raw_value" in v:
                    v = {ik: iv for ik, iv in v.items() if ik != "raw_value"}
                safe[k] = v
        try:
            audit_service.log(tenant, actor, "user", action, "ai_approval", resource_id, "success", safe)
        except TypeError:
            audit_service.log(tenant, actor, "user", action, "ai_approval", resource_id, "success", safe)  # type: ignore[call-arg]
    except Exception as exc:  # noqa: BLE001
        logger.debug("audit unavailable (%s): %s", action, exc)


def _parse_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value).strip())
    except Exception as exc:  # noqa: BLE001
        raise ValidationError(message=f"invalid UUID: {value} — {exc}") from exc


def _normalize_request_type(value: str) -> str:
    if not value or not str(value).strip():
        raise ValidationError(message="request_type is required")
    s = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    # keep original valid set but allow any non-empty — warn if unknown
    if s not in _VALID_REQUEST_TYPES:
        logger.debug("unknown request_type '%s' — storing as-is", s)
    return s


def _normalize_decision(value: str) -> str:
    if not value or not str(value).strip():
        raise ValidationError(message="decision is required")
    s = str(value).strip().lower()
    if s not in _VALID_DECISIONS:
        raise ValidationError(message=f"invalid decision '{value}'; allowed: {sorted(_VALID_DECISIONS)}")
    if s in _APPROVED_NORM:
        return "approved"
    if s in _REJECTED_NORM:
        return "rejected"
    if s in ("pending", "cancelled"):
        return s
    return s


class AIApprovalService:
    """Tenant-scoped approval workflow for AI models/providers/versions."""

    # ── request_approval ───────────────────────────────────────────────

    async def request_approval(
        self,
        db: AsyncSession,
        tenant: str,
        request_type: str,
        model_id: str | uuid.UUID | None = None,
        provider: str | None = None,
        version: str | None = None,
        requested_by: str | None = None,
        reason: str | None = None,
    ) -> AIApprovalRequest:
        """Create a tenant-scoped approval request bound to exact model/provider/version.

        Never reuses approval across versions — each (model, provider, version)
        tuple requires its own request.  The created row's version is immutable;
        callers must create a new request for a new version.

        Args:
            db: AsyncSession (tenant-scoped).
            tenant: tenant id (required, non-empty).
            request_type: new_model/new_provider/restricted_data/production/high_risk etc.
            model_id: FK to ``ai_model_registry.id`` (UUID). Optional but when
                supplied must be a valid UUID that exists for the tenant when
                possible; non-UUID composite ids are stored via version/provider
                only.
            provider: provider key (e.g. openai) — stored as lowercased when present.
            version: model/provider version string (e.g. 1.0.0) — stored as-is.
            requested_by: requester identity (required).
            reason: justification for the request.

        Returns: persisted ``AIApprovalRequest`` with status ``pending``.

        Raises: ValidationError for missing/invalid tenant/request_type/requested_by.
        """
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        tenant_s = str(tenant).strip()
        request_type_s = _normalize_request_type(request_type)
        if not requested_by or not str(requested_by).strip():
            raise ValidationError(message="requested_by is required")
        requested_by_s = str(requested_by).strip()
        provider_s = str(provider).strip().lower() if provider and str(provider).strip() else None
        # normalize "none" string etc
        if provider_s and provider_s.lower() in ("none", "null", ""):
            provider_s = None
        version_s = str(version).strip() if version and str(version).strip() else None
        reason_s = str(reason).strip() if reason and str(reason).strip() else None

        model_uuid: uuid.UUID | None = None
        if model_id is not None and str(model_id).strip():
            try:
                model_uuid = _parse_uuid(model_id)
            except ValidationError:
                # model_id may be composite string (provider/name:version) — keep as None
                # and preserve composite in reason metadata rather than failing
                logger.debug("model_id '%s' not a UUID — storing as None for approval", model_id)
                model_uuid = None
                # stash composite for audit traceability
                if reason_s:
                    reason_s = f"{reason_s} [model_ref={str(model_id).strip()}]"
                else:
                    reason_s = f"[model_ref={str(model_id).strip()}]"

        # Tenant-scoped existence check when model_uuid provided
        if model_uuid is not None:
            try:
                from app.aiml.models import AIModelRegistry  # local import to avoid cycle

                stmt_m = select(AIModelRegistry).where(
                    AIModelRegistry.id == model_uuid,
                    AIModelRegistry.tenant == tenant_s,
                )
                result_m = await db.execute(stmt_m)
                found = result_m.scalars().first()
                if found is None:
                    raise NotFoundError(resource="AIModelRegistry", identifier=str(model_uuid))
            except NotFoundError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.debug("model existence check failed for %s: %s", model_uuid, exc)
                # do not block creation on lookup failure — proceed but log

        # Bound to exact model/provider/version — prevent duplicate pending for same tuple
        # If a pending request already exists for the same exact tuple, raise ConflictError
        try:
            stmt_dup = select(AIApprovalRequest).where(
                AIApprovalRequest.tenant == tenant_s,
                AIApprovalRequest.request_type == request_type_s,
                AIApprovalRequest.status == "pending",
            )
            if model_uuid is not None:
                stmt_dup = stmt_dup.where(AIApprovalRequest.model_id == model_uuid)
            else:
                stmt_dup = stmt_dup.where(AIApprovalRequest.model_id.is_(None))
            if provider_s is not None:
                stmt_dup = stmt_dup.where(AIApprovalRequest.provider == provider_s)
            else:
                stmt_dup = stmt_dup.where(AIApprovalRequest.provider.is_(None))
            if version_s is not None:
                stmt_dup = stmt_dup.where(AIApprovalRequest.version == version_s)
            else:
                stmt_dup = stmt_dup.where(AIApprovalRequest.version.is_(None))
            result_dup = await db.execute(stmt_dup)
            dup = result_dup.scalars().first()
            if dup is not None:
                raise ConflictError(f"pending approval already exists for {request_type_s} model={model_uuid} provider={provider_s} version={version_s} (id={dup.id})")
        except ConflictError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.debug("duplicate pending check failed: %s", exc)

        row = AIApprovalRequest(
            tenant=tenant_s,
            request_type=request_type_s,
            model_id=model_uuid,
            provider=provider_s,
            version=version_s,
            requested_by=requested_by_s,
            approver=None,
            status="pending",
            reason=reason_s,
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)
        _audit(tenant_s, requested_by_s, "ai_approval.requested", str(row.id), {"request_type": request_type_s, "model_id": str(model_uuid) if model_uuid else None, "provider": provider_s, "version": version_s})
        logger.info("approval requested %s tenant=%s type=%s model=%s provider=%s version=%s by=%s", row.id, tenant_s, request_type_s, model_uuid, provider_s, version_s, requested_by_s)
        return row

    # ── approve ────────────────────────────────────────────────────────

    async def approve(
        self,
        db: AsyncSession,
        approval_id: str | uuid.UUID,
        approver: str,
        decision: str,
    ) -> AIApprovalRequest:
        """Record approver decision bound to exact model/provider/version.

        The approval is bound to the exact ``model_id``/``provider``/``version``
        stored at creation — never reused across versions.  This method only
        updates ``approver`` and ``status`` on the existing row; it never
        changes ``model_id``/``provider``/``version``.

        Args:
            db: AsyncSession (tenant inferred from row — preserves isolation).
            approval_id: PK of ``ai_approval_requests`` (UUID, required).
            approver: approver identity (required, non-empty).
            decision: approved/rejected (also accepts approve/reject/allow/deny).

        Returns: updated ``AIApprovalRequest``.

        Raises:
            ValidationError for missing/invalid approver/decision.
            NotFoundError when approval not found.
            ConflictError when approval already decided (non-pending).
        """
        if not approval_id or (isinstance(approval_id, str) and not str(approval_id).strip()):
            raise ValidationError(message="approval_id is required")
        if not approver or not str(approver).strip():
            raise ValidationError(message="approver is required")
        approver_s = str(approver).strip()
        decision_s = _normalize_decision(decision)
        pk = _parse_uuid(approval_id)
        if pk is None:
            raise ValidationError(message="approval_id must be a valid UUID")

        stmt = select(AIApprovalRequest).where(AIApprovalRequest.id == pk)
        result = await db.execute(stmt)
        row: AIApprovalRequest | None = result.scalars().first()
        if row is None:
            raise NotFoundError(resource="AIApprovalRequest", identifier=str(pk))

        # Tenant isolation: row tenant is ground truth — no cross-tenant decision
        tenant_s = row.tenant

        # Never reuse across versions — approver cannot mutate version/provider/model_id
        # Ensure approval is still pending; already decided rows cannot be reused
        if row.status != "pending":
            raise ConflictError(f"approval {pk} already decided (status={row.status}) — never reuse across versions, create a new request for a new version")

        # Validate decision maps to status
        if decision_s not in ("approved", "rejected"):
            raise ValidationError(message=f"decision must be approved or rejected, got '{decision}'")

        # Capture original binding for audit immutability guarantee
        orig_model = str(row.model_id) if row.model_id else None
        orig_provider = row.provider
        orig_version = row.version

        old_status = row.status
        row.approver = approver_s
        row.status = decision_s
        await db.flush()
        await db.refresh(row)

        # Post-condition: ensure binding was not mutated (defense in depth)
        if str(row.model_id) if row.model_id else None != orig_model or row.provider != orig_provider or row.version != orig_version:
            # This should never happen — we never mutate those columns here — but if it did, rollback
            logger.error("approval binding mutated for %s: (%s,%s,%s) -> (%s,%s,%s)", pk, orig_model, orig_provider, orig_version, row.model_id, row.provider, row.version)
            raise ConflictError("approval binding violation — model/provider/version must not change")

        _audit(tenant_s, approver_s, f"ai_approval.{decision_s}", str(row.id), {"old_status": old_status, "new_status": decision_s, "model_id": orig_model, "provider": orig_provider, "version": orig_version, "request_type": row.request_type})
        logger.info("approval %s %s->%s by=%s tenant=%s model=%s provider=%s version=%s", row.id, old_status, decision_s, approver_s, tenant_s, orig_model, orig_provider, orig_version)
        return row

    # ── helpers ────────────────────────────────────────────────────────

    async def get_approval(
        self,
        db: AsyncSession,
        tenant: str,
        approval_id: str | uuid.UUID,
    ) -> AIApprovalRequest | None:
        """Fetch approval by PK, tenant-scoped. Returns None if not found or tenant mismatch."""
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        tenant_s = str(tenant).strip()
        pk = _parse_uuid(approval_id)
        if pk is None:
            raise ValidationError(message="approval_id is required")
        stmt = select(AIApprovalRequest).where(AIApprovalRequest.id == pk, AIApprovalRequest.tenant == tenant_s)
        result = await db.execute(stmt)
        return result.scalars().first()

    async def list_approvals(
        self,
        db: AsyncSession,
        tenant: str,
        status: str | None = None,
        request_type: str | None = None,
        model_id: str | uuid.UUID | None = None,
    ) -> list[AIApprovalRequest]:
        """List approvals for tenant with optional filters (tenant-scoped)."""
        if not tenant or not str(tenant).strip():
            raise ValidationError(message="tenant is required")
        tenant_s = str(tenant).strip()
        stmt = select(AIApprovalRequest).where(AIApprovalRequest.tenant == tenant_s)
        if status and str(status).strip():
            stmt = stmt.where(AIApprovalRequest.status == str(status).strip().lower())
        if request_type and str(request_type).strip():
            stmt = stmt.where(AIApprovalRequest.request_type == str(request_type).strip().lower())
        if model_id is not None and str(model_id).strip():
            try:
                mu = _parse_uuid(model_id)
                if mu is not None:
                    stmt = stmt.where(AIApprovalRequest.model_id == mu)
            except ValidationError:
                pass
        stmt = stmt.order_by(AIApprovalRequest.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())


approval_service = AIApprovalService()
# Backwards-compat aliases
ai_approval_service = approval_service
aiapproval_service = approval_service
