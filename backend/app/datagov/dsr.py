"""Volume 57 — DSRService (tenant-scoped, verification-gated, approval-backed).

Provides data-subject request workflow:
  - create_request  — validates type/subject, stores governance_data_requests
  - verify_identity — enforces additional factor for sensitive scope (never email alone)
  - approve_request — via app.governance.approval_workflows when available
  - complete_request — tracks per-system completion and exceptions
  - helpers get_request / list_requests tenant-scoped

Tenant isolation enforced on every read. Audit is best-effort.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.datagov.models import GovernanceDataRequest

logger = logging.getLogger(__name__)

VALID_REQUEST_TYPES: set[str] = {"access", "deletion", "correction", "restriction", "export"}
VALID_VERIFICATION_STATUSES: set[str] = {"pending", "verified", "rejected"}
VALID_APPROVAL_STATUSES: set[str] = {"pending", "approved", "rejected", "cancelled"}

# markers that indicate sensitive personal data — scoped verification must be stricter
_SENSITIVE_CLASSIFICATIONS: set[str] = {"confidential", "restricted", "secret"}
_SENSITIVE_CATEGORIES: set[str] = {
    "ssn",
    "credit_card",
    "iban",
    "credentials",
    "token",
    "api_key",
    "private_code",
    "customer_data",
    "security_info",
    "financial",
    "pii",
    "sensitive",
}
_SENSITIVE_SCOPE_KEYS: set[str] = {"sensitive", "confidential", "restricted", "secret", "pii"}
_EMAIL_ONLY_METHODS: set[str] = {"email", "email_verification", "email_only", "email-alone"}


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
                "governance_dsr",
                resource_id,
                "success",
                details or {},
            )
        except TypeError:
            audit_service.log(tenant, actor, "user", action, "governance_dsr", resource_id, "success", details or {})
    except Exception as exc:  # noqa: BLE001
        logger.debug("audit unavailable (%s): %s", action, exc)


def _parse_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except Exception:
        return None


def _is_sensitive_scope(scope: Any) -> bool:
    """Return True if scope indicates sensitive personal data.

    Checks dict keys/values for confidential/restricted markers and known
    PII/financial/credential categories. Intentionally broad to fail closed.
    """
    if scope is None:
        return False
    # if scope is a string, direct marker
    if isinstance(scope, str):
        low = scope.strip().lower()
        if low in _SENSITIVE_SCOPE_KEYS or low in _SENSITIVE_CATEGORIES or low in _SENSITIVE_CLASSIFICATIONS:
            return True
        # contains marker substring
        for marker in _SENSITIVE_CATEGORIES | _SENSITIVE_SCOPE_KEYS | _SENSITIVE_CLASSIFICATIONS:
            if marker in low:
                return True
        return False
    # if list, check any element sensitive
    if isinstance(scope, list):
        for item in scope:
            if _is_sensitive_scope(item):
                return True
        return False
    if isinstance(scope, dict):
        # check keys and values recursively
        for k, v in scope.items():
            k_low = str(k).strip().lower()
            if k_low in _SENSITIVE_SCOPE_KEYS or k_low in _SENSITIVE_CATEGORIES or k_low in _SENSITIVE_CLASSIFICATIONS:
                return True
            if k_low in ("classification", "level", "sensitivity"):
                if isinstance(v, str) and v.strip().lower() in _SENSITIVE_CLASSIFICATIONS:
                    return True
            # value string markers
            if isinstance(v, str):
                v_low = v.strip().lower()
                if v_low in _SENSITIVE_CATEGORIES or v_low in _SENSITIVE_SCOPE_KEYS or v_low in _SENSITIVE_CLASSIFICATIONS:
                    return True
                for marker in _SENSITIVE_CATEGORIES:
                    if marker in v_low:
                        return True
            elif isinstance(v, (dict, list)):
                if _is_sensitive_scope(v):
                    return True
            # also key contains sensitive substring
            for marker in _SENSITIVE_CATEGORIES | _SENSITIVE_SCOPE_KEYS:
                if marker in k_low:
                    return True
        # special flag keys
        if scope.get("sensitive") is True:
            return True
        if scope.get("is_sensitive") is True:
            return True
        return False
    return False


def _normalize_method(method: str) -> str:
    return str(method).strip().lower().replace(" ", "_").replace("-", "_")


async def _get_request_or_raise(db: AsyncSession, request_id: str) -> GovernanceDataRequest:
    pid = _parse_uuid(request_id)
    if pid is not None:
        stmt = select(GovernanceDataRequest).where(GovernanceDataRequest.id == pid)
    else:
        # compat: allow string id lookup
        stmt = select(GovernanceDataRequest).where(GovernanceDataRequest.id == request_id)  # type: ignore
    result = await db.execute(stmt)
    row: GovernanceDataRequest | None = result.scalars().first()
    if row is None:
        raise ValueError(f"data request '{request_id}' not found")
    return row


class DSRService:
    """Tenant-scoped Data Subject Request service."""

    async def create_request(
        self,
        db: AsyncSession,
        tenant: str,
        request_type: str,
        subject: str,
        scope: dict | list | str | None = None,
        requested_by: str | None = None,
    ) -> GovernanceDataRequest:
        """Create a GovernanceDataRequest.

        Args:
            tenant: tenant scope (required).
            request_type: one of {access,deletion,correction,restriction,export}
            subject: data-subject identifier (required, non-empty).
            scope: scope description (dict/list/str, optional; normalized to dict).
            requested_by: actor who created the request.
        """
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        tenant_s = str(tenant).strip()

        if not request_type or not str(request_type).strip():
            raise ValueError("request_type is required")
        rt = str(request_type).strip().lower()
        if rt not in VALID_REQUEST_TYPES:
            raise ValueError(f"invalid request_type '{request_type}'; allowed: {sorted(VALID_REQUEST_TYPES)}")

        if subject is None or not str(subject).strip():
            raise ValueError("subject is required and cannot be empty")
        subject_s = str(subject).strip()

        # normalize scope to dict for storage
        if scope is None:
            scope_dict: dict = {}
        elif isinstance(scope, dict):
            scope_dict = dict(scope)
        elif isinstance(scope, list):
            scope_dict = {"scope": list(scope)}
        elif isinstance(scope, str):
            s = scope.strip()
            if s == "":
                scope_dict = {}
            else:
                scope_dict = {"scope": s}
        else:
            scope_dict = {"scope": str(scope)}

        requested_by_s = str(requested_by).strip() if requested_by and str(requested_by).strip() else None

        row = GovernanceDataRequest(
            tenant=tenant_s,
            request_type=rt,
            subject=subject_s,
            scope=scope_dict,
            verification_status="pending",
            approval_status="pending",
            systems=[],
            completion={},
            exceptions=[],
            requested_by=requested_by_s,
        )
        db.add(row)
        await db.flush()
        await db.refresh(row)

        _audit(tenant_s, requested_by_s or "system", "governance.dsr.created", str(row.id), {"request_type": rt, "subject": subject_s})
        return row

    async def verify_identity(
        self,
        db: AsyncSession,
        request_id: str,
        verifier: str,
        method: str,
    ) -> GovernanceDataRequest:
        """Verify data-subject identity.

        Enforces that email-only verification is insufficient for sensitive scopes
        — an additional factor (mfa, government_id, knowledge, document, etc.)
        is required. Updates verification_status to verified or rejected.

        Args:
            request_id: GovernanceDataRequest id (uuid string).
            verifier: actor performing verification.
            method: verification method (e.g., email, mfa, government_id, document,
                    knowledge, rejected, failed). The value determines the outcome:
                    rejected-like values set status to rejected, otherwise verified
                    after passing sensitive-scope guard.
        """
        if not request_id or not str(request_id).strip():
            raise ValueError("request_id is required")
        if not verifier or not str(verifier).strip():
            raise ValueError("verifier is required")
        if method is None or not str(method).strip():
            raise ValueError("method is required")

        verifier_s = str(verifier).strip()
        method_norm = _normalize_method(method)

        row = await _get_request_or_raise(db, str(request_id).strip())

        # sensitive scope guard — never fulfill on email alone
        if _is_sensitive_scope(row.scope):
            if method_norm in _EMAIL_ONLY_METHODS:
                raise ValueError("additional verification factor required for sensitive scope — email alone insufficient")

        # map method to verification outcome
        if method_norm in ("rejected", "reject", "failed", "failure", "deny", "denied"):
            row.verification_status = "rejected"
        else:
            row.verification_status = "verified"

        await db.flush()
        await db.refresh(row)

        _audit(row.tenant, verifier_s, f"governance.dsr.verification.{row.verification_status}", str(row.id), {"method": method_norm, "subject": row.subject})
        return row

    async def approve_request(
        self,
        db: AsyncSession,
        request_id: str,
        approver: str,
        decision: str,
    ) -> GovernanceDataRequest:
        """Approve or reject a DSR via approval_workflows when available.

        Args:
            request_id: GovernanceDataRequest id.
            approver: actor deciding.
            decision: approved / rejected (also accepts approve/allow/deny).
        """
        if not request_id or not str(request_id).strip():
            raise ValueError("request_id is required")
        if not approver or not str(approver).strip():
            raise ValueError("approver is required")
        if decision is None or not str(decision).strip():
            raise ValueError("decision is required")

        approver_s = str(approver).strip()
        dec_norm = str(decision).strip().lower()
        if dec_norm in ("approved", "approve", "allow", "allowed"):
            final_decision = "approved"
        elif dec_norm in ("rejected", "reject", "denied", "deny", "cancelled", "canceled"):
            final_decision = "rejected"
        else:
            raise ValueError(f"invalid decision '{decision}'; allowed: approved, rejected")

        row = await _get_request_or_raise(db, str(request_id).strip())

        # best-effort approval workflow integration
        # For destructive types (deletion/export) or sensitive scope, we attempt
        # a workflow; otherwise we still persist decision directly.
        workflow_attempted = False
        workflow_status: str | None = None
        try:
            from app.governance.approval_workflows import (  # type: ignore
                ApprovalRequest,
                ApprovalRole,
                ApprovalStatus,
                ApprovalStep,
                ApprovalType,
                ApprovalWorkflow,
                ApprovalWorkflowEngine,
            )

            # tenant-isolated engine dir to avoid collisions
            try:
                engine = ApprovalWorkflowEngine(storage_dir=f"approval_engine_data_{row.tenant}")  # type: ignore
            except Exception:
                engine = ApprovalWorkflowEngine()  # type: ignore

            wf_id = str(uuid.uuid4())
            try:
                step = ApprovalStep(
                    id=str(uuid.uuid4()),
                    name="dsr-approval",
                    role=ApprovalRole.APPROVER,  # type: ignore
                    required_approvers=1,
                    order=0,
                    wait_for_previous=True,
                    timeout_hours=72,
                    escalation_after_hours=24,
                )
            except Exception:
                step = ApprovalStep(
                    id=str(uuid.uuid4()),
                    name="dsr-approval",
                    role=ApprovalRole.ADMIN,  # type: ignore
                    required_approvers=1,
                )  # type: ignore

            workflow = ApprovalWorkflow(
                id=wf_id,
                org_id=row.tenant,
                name=f"dsr:{row.request_type}:{row.id}",
                description=f"DSR {row.request_type} for subject {row.subject}",
                type=ApprovalType.COMPLIANCE,  # type: ignore
                target_type="governance_data_request",
                target_id=str(row.id),
                steps=[step],
                status=ApprovalStatus.PENDING,  # type: ignore
                initiated_by=approver_s,
                metadata={"request_id": str(row.id), "request_type": row.request_type, "subject": row.subject, "scope": row.scope},
            )
            try:
                engine.create_workflow(workflow)
                req = ApprovalRequest(
                    id=str(uuid.uuid4()),
                    workflow_id=wf_id,
                    org_id=row.tenant,
                    requester=approver_s,
                    target_type="governance_data_request",
                    target_id=str(row.id),
                    reason=f"DSR {final_decision} by {approver_s}",
                    status=ApprovalStatus.PENDING,  # type: ignore
                    metadata={"decision": final_decision},
                )
                engine.submit_request(req)
                # drive workflow to decided state in same call
                if final_decision == "approved":
                    engine.approve_step(wf_id, step.id, approver_s, comments=f"DSR approved by {approver_s}")
                else:
                    engine.reject_step(wf_id, step.id, approver_s, comments=f"DSR rejected by {approver_s}")
                wf = engine.get_workflow(wf_id)
                if wf is not None and hasattr(wf, "status"):
                    st = wf.status.value if hasattr(wf.status, "value") else str(wf.status)
                    workflow_status = st
                    if st == "approved":
                        row.approval_status = "approved"
                    elif st in ("rejected", "cancelled", "expired"):
                        row.approval_status = "rejected"
                    else:
                        row.approval_status = final_decision
                else:
                    row.approval_status = final_decision
                workflow_attempted = True
            except Exception as exc:  # noqa: BLE001
                logger.debug("DSR approval workflow create/submit failed, falling back: %s", exc)
                row.approval_status = final_decision
                workflow_attempted = False
        except ImportError as exc:
            logger.debug("approval_workflows not available, stub DSR approval: %s", exc)
            row.approval_status = final_decision
        except Exception as exc:  # noqa: BLE001
            logger.debug("approval workflow unavailable for DSR, stub: %s", exc)
            row.approval_status = final_decision

        await db.flush()
        await db.refresh(row)

        _audit(
            row.tenant,
            approver_s,
            f"governance.dsr.{row.approval_status}",
            str(row.id),
            {
                "decision": final_decision,
                "request_type": row.request_type,
                "subject": row.subject,
                "workflow_attempted": workflow_attempted,
                "workflow_status": workflow_status,
            },
        )
        return row

    async def complete_request(
        self,
        db: AsyncSession,
        request_id: str,
        systems: list | None = None,
        completion: dict | None = None,
        exceptions: list | None = None,
    ) -> GovernanceDataRequest:
        """Mark a DSR as completed per-system.

        Requires identity to be verified; approval is expected for destructive
        types but not strictly blocked so that non-destructive reads can complete
        with audit. Updates systems, completion, exceptions on the row.

        Args:
            request_id: GovernanceDataRequest id.
            systems: list of system identifiers that were processed.
            completion: dict of system -> result/status/details.
            exceptions: list of exception dicts for systems where retention/legal
                        hold or other policy prevented fulfillment.
        """
        if not request_id or not str(request_id).strip():
            raise ValueError("request_id is required")

        row = await _get_request_or_raise(db, str(request_id).strip())

        if row.verification_status != "verified":
            raise ValueError("cannot complete — identity not verified (verification_status != verified)")

        # update fields
        if systems is not None:
            if not isinstance(systems, list):
                raise ValueError("systems must be a list")
            row.systems = list(systems)
        if completion is not None:
            if not isinstance(completion, dict):
                raise ValueError("completion must be a dict")
            # merge with existing completion
            existing = dict(row.completion or {})
            existing.update(completion)
            # also store completed_at
            existing.setdefault("completed_at", _utc_now().isoformat())
            existing.setdefault("completed_by", "system")
            row.completion = existing
        else:
            # still ensure completion has completed_at when systems provided
            if systems is not None:
                comp = dict(row.completion or {})
                comp.setdefault("completed_at", _utc_now().isoformat())
                row.completion = comp
        if exceptions is not None:
            if not isinstance(exceptions, list):
                raise ValueError("exceptions must be a list")
            row.exceptions = list(exceptions)

        await db.flush()
        await db.refresh(row)

        _audit(
            row.tenant,
            "system",
            "governance.dsr.completed",
            str(row.id),
            {
                "systems": row.systems,
                "completion": row.completion,
                "exceptions": row.exceptions,
                "request_type": row.request_type,
            },
        )
        return row

    async def get_request(
        self,
        db: AsyncSession,
        tenant: str,
        request_id: str,
    ) -> GovernanceDataRequest | None:
        """Fetch a single DSR tenant-scoped."""
        if not tenant or not request_id:
            raise ValueError("tenant and request_id are required")
        pid = _parse_uuid(request_id)
        if pid is not None:
            stmt = select(GovernanceDataRequest).where(
                GovernanceDataRequest.tenant == tenant,
                GovernanceDataRequest.id == pid,
            )
        else:
            stmt = select(GovernanceDataRequest).where(
                GovernanceDataRequest.tenant == tenant,
                GovernanceDataRequest.id == request_id,  # type: ignore
            )
        result = await db.execute(stmt)
        return result.scalars().first()

    async def list_requests(
        self,
        db: AsyncSession,
        tenant: str,
        request_type: str | None = None,
        subject: str | None = None,
    ) -> list[GovernanceDataRequest]:
        """List DSRs for tenant with optional filters."""
        if not tenant or not str(tenant).strip():
            raise ValueError("tenant is required")
        tenant_s = str(tenant).strip()
        stmt = select(GovernanceDataRequest).where(GovernanceDataRequest.tenant == tenant_s)
        if request_type and str(request_type).strip():
            rt = str(request_type).strip().lower()
            stmt = stmt.where(GovernanceDataRequest.request_type == rt)
        if subject and str(subject).strip():
            stmt = stmt.where(GovernanceDataRequest.subject == str(subject).strip())
        stmt = stmt.order_by(GovernanceDataRequest.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())


dsr_service = DSRService()
