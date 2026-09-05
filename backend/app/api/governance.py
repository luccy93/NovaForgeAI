"""Central governance plane API — Volume 71 Commit 1.

Tenant-authorized policy CRUD/versioning, bindings, evaluation,
simulation, exceptions, decisions and posture. Authorization reuses
organization:read / settings:admin with the superuser convention;
explicit deny overrides are honored. All ranges and pages bounded.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db as _get_db_session
from app.governance.plane_common import ADMIN_PERMISSION, READ_PERMISSION

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/governance", tags=["Governance"])


async def _get_db():
    from app.core.database import async_session
    async with async_session() as session:
        yield session


async def _resolve_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(_get_db_session),
):
    try:
        from app.api.auth import _get_current_user
        return await _get_current_user(authorization, db)
    except HTTPException:
        raise
    except Exception:
        class _Anon:
            id = ""
            organization_id = ""
            role = "anonymous"
        return _Anon()


def _tenant(user) -> str:
    oid = getattr(user, "organization_id", None) or getattr(user, "id", None)
    if not oid:
        raise HTTPException(status_code=403, detail="No tenant context")
    return str(oid)


def _iam_check(user, tenant: str, perm: str) -> None:
    if getattr(user, "is_superuser", False):
        return
    try:
        from app.iam.policy_authorizer import policy_authorizer
        result = policy_authorizer.authorize(
            str(getattr(user, "id", "")), tenant, perm,
            context={"role": getattr(user, "role", "user")},
        )
        if isinstance(result, dict) and not result.get("allowed", True):
            raise HTTPException(status_code=403, detail="forbidden")
    except HTTPException:
        raise
    except Exception:
        pass


def _err(exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=f"{type(exc).__name__}: {exc}")
    from app.governance.plane_common import ValidationError as _ValidationError
    if isinstance(exc, _ValidationError):
        return HTTPException(status_code=422, detail=f"{type(exc).__name__}: {exc}")
    msg = f"{type(exc).__name__}: {exc}"
    lowered = str(exc).lower()
    if "not found" in lowered:
        return HTTPException(status_code=404, detail=msg)
    if "already exists" in lowered or "duplicate" in lowered:
        return HTTPException(status_code=409, detail=msg)
    return HTTPException(status_code=500, detail=msg)


def _user_id(user) -> str:
    return str(getattr(user, "id", "") or "")


async def _limit(tenant: str, endpoint: str, limit: int = 120) -> None:
    try:
        from app.core.redis import rate_limit_check
        allowed, _ = await rate_limit_check(f"governance:{tenant}:{endpoint}", limit, 60)
        if not allowed:
            raise HTTPException(status_code=429, detail="rate limit exceeded")
    except HTTPException:
        raise
    except Exception:
        pass


# ─── Schemas ─────────────────────────────────────────────────────────────────


class PolicyIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    domain: str = "general"
    description: str = ""
    owner: str = ""


class VersionIn(BaseModel):
    rules: list
    default_effect: str = "deny"
    effective_from: Optional[str] = None
    effective_until: Optional[str] = None
    reason: str = ""


class VersionStatusIn(BaseModel):
    status: str
    reason: str = ""


class BindingIn(BaseModel):
    policy_id: str
    version_id: str
    scope_type: str
    scope_value: str = ""
    mandatory: bool = False


class EvaluateIn(BaseModel):
    scope_type: str
    scope_value: str = ""
    operation: str = ""
    context: Optional[dict] = None
    actor: str = ""
    identity: str = ""
    enforce: bool = False


class SimulateIn(BaseModel):
    requests: Optional[list] = None
    scope_type: str = "tenant"
    scope_value: str = ""
    operation: str = ""
    context: Optional[dict] = None
    proposed: Optional[dict] = None


class ExceptionIn(BaseModel):
    policy_id: str
    scope_type: str = ""
    scope_value: str = ""
    justification: str = Field(..., min_length=1)
    requester: str = ""
    duration_hours: int = 24
    high_risk: bool = False


class ExceptionDecisionIn(BaseModel):
    approver: str = Field(..., min_length=1)
    approval_id: str = ""
    approval_type: str = "jit"


# ─── Policies ────────────────────────────────────────────────────────────────


@router.get("/policies")
async def list_policies(
    status: Optional[str] = None, domain: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.governance.plane_policies import list_policies as _list
        return await _list(db, tenant, status=status or "", domain=domain or "", limit=limit)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/policies", status_code=201)
async def create_policy(
    payload: PolicyIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.governance.plane_policies import create_policy as _create
        result = await _create(db, tenant, payload.name, **{
            k: v for k, v in payload.model_dump().items() if k != "name"
        }, actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/policies/{policy_id}")
async def get_policy(
    policy_id: str,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.governance.plane_policies import get_policy as _get
        return await _get(db, tenant, policy_id)
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/policies/{policy_id}/versions")
async def get_versions(
    policy_id: str,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.governance.plane_policies import list_versions as _list
        return await _list(db, tenant, policy_id)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/policies/{policy_id}/versions", status_code=201)
async def create_version(
    policy_id: str, payload: VersionIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.governance.plane_policies import create_version as _create
        result = await _create(db, tenant, policy_id, payload.rules, **{
            k: v for k, v in payload.model_dump().items() if k != "rules"
        }, actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/versions/{version_id}/status")
async def set_version_status(
    version_id: str, payload: VersionStatusIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.governance.plane_policies import set_version_status as _set
        result = await _set(db, tenant, version_id, payload.status,
                            actor=_user_id(current_user), reason=payload.reason)
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


# ─── Bindings ────────────────────────────────────────────────────────────────


@router.get("/bindings")
async def get_bindings(
    policy_id: Optional[str] = None, scope_type: Optional[str] = None,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.governance.plane_bindings import list_bindings as _list
        return await _list(db, tenant, policy_id=policy_id, scope_type=scope_type or "")
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/bindings", status_code=201)
async def create_binding(
    payload: BindingIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.governance.plane_bindings import create_binding as _create
        result = await _create(db, tenant, payload.policy_id, payload.version_id, **{
            k: v for k, v in payload.model_dump().items()
            if k not in ("policy_id", "version_id")
        }, actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.delete("/bindings/{binding_id}")
async def delete_binding(
    binding_id: str,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.governance.plane_bindings import delete_binding as _delete
        result = await _delete(db, tenant, binding_id, actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


# ─── Evaluation & simulation ─────────────────────────────────────────────────


@router.post("/evaluate")
async def evaluate_request(
    payload: EvaluateIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        await _limit(tenant, "evaluate")
        if payload.enforce:
            from app.governance.plane_evaluate import decide as _decide
            result = await _decide(
                db, tenant, scope_type=payload.scope_type, scope_value=payload.scope_value,
                operation=payload.operation, context=payload.context,
                actor=payload.actor or _user_id(current_user),
                identity=payload.identity or _user_id(current_user))
        else:
            from app.governance.plane_evaluate import evaluate as _evaluate
            result = await _evaluate(
                db, tenant, scope_type=payload.scope_type, scope_value=payload.scope_value,
                operation=payload.operation, context=payload.context,
                actor=payload.actor or _user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/simulate")
async def simulate_request(
    payload: SimulateIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        await _limit(tenant, "simulate")
        from app.governance.plane_simulate import compare_versions, simulate_batch, simulate_one
        if payload.requests is not None:
            if payload.proposed:
                return await compare_versions(db, tenant, payload.requests, proposed=payload.proposed)
            return await simulate_batch(db, tenant, payload.requests, proposed=payload.proposed)
        return await simulate_one(
            db, tenant, scope_type=payload.scope_type, scope_value=payload.scope_value,
            operation=payload.operation, context=payload.context, proposed=payload.proposed)
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/decisions")
async def get_decisions(
    decision: Optional[str] = None, operation: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.governance.plane_evaluate import list_decisions as _list
        return await _list(db, tenant, decision=decision or "", operation=operation or "", limit=limit)
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/decisions/{decision_id}")
async def get_decision(
    decision_id: str,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.governance.plane_evaluate import get_decision as _get
        return await _get(db, tenant, decision_id)
    except Exception as exc:
        raise _err(exc) from exc


# ─── Exceptions ──────────────────────────────────────────────────────────────


@router.get("/policy-exceptions")
async def get_exceptions(
    status: Optional[str] = None,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.governance.plane_exceptions import list_exceptions as _list
        return await _list(db, tenant, status=status or "")
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/policy-exceptions", status_code=201)
async def create_exception(
    payload: ExceptionIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.governance.plane_exceptions import request_exception as _create
        result = await _create(db, tenant, payload.policy_id, **{
            k: v for k, v in payload.model_dump().items() if k != "policy_id"
        })
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/policy-exceptions/{exception_id}/approve")
async def approve_exception(
    exception_id: str, payload: ExceptionDecisionIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.governance.plane_exceptions import approve_exception as _approve
        result = await _approve(db, tenant, exception_id, approver=payload.approver,
                                approval_id=payload.approval_id,
                                approval_type=payload.approval_type)
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/policy-exceptions/{exception_id}/deny")
async def deny_exception(
    exception_id: str, payload: ExceptionDecisionIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.governance.plane_exceptions import deny_exception as _deny
        result = await _deny(db, tenant, exception_id, approver=payload.approver)
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/policy-exceptions/{exception_id}/revoke")
async def revoke_exception(
    exception_id: str,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.governance.plane_exceptions import revoke_exception as _revoke
        result = await _revoke(db, tenant, exception_id, actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


# ─── Posture ─────────────────────────────────────────────────────────────────


@router.get("/posture")
async def get_posture(
    scope_type: str = "tenant", scope_value: str = "", domain: str = "general",
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.governance.plane_workers import run_posture_refresh
        result = await run_posture_refresh(db, tenant, scope_type=scope_type,
                                           scope_value=scope_value)
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/posture/history")
async def get_posture_history(
    scope_type: str = "tenant", scope_value: str = "", domain: str = "general",
    limit: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.governance.plane_posture import latest_posture as _history
        return await _history(db, tenant, scope_type=scope_type,
                              scope_value=scope_value, domain=domain, limit=limit)
    except Exception as exc:
        raise _err(exc) from exc


# ─── Evidence registry (C2) ──────────────────────────────────────────────────
#
# NOTE: control lifecycle (/controls, /controls/{id}/assess,
# /controls/{id}/evidence, /controls/package) is owned by the existing
# Data Governance router, which is registered first and stays
# authoritative. This router only adds the central evidence registry
# and coverage views, which have no pre-existing equivalents.


class EvidenceIn(BaseModel):
    control_key: str = Field(..., min_length=1, max_length=128)
    source_system: str = Field(..., min_length=1, max_length=64)
    source_ref: str = Field(..., min_length=1, max_length=256)
    source_version: str = ""
    result: str = "PASS"
    validity_days: int = 90
    metadata: Optional[dict] = None


@router.post("/evidence/register", status_code=201)
async def register_evidence(
    payload: EvidenceIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.governance.plane_evidence import register_evidence as _register
        result = await _register(db, tenant, payload.control_key, **{
            k: v for k, v in payload.model_dump().items() if k != "control_key"
        })
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/evidence")
async def get_evidence(
    control_key: Optional[str] = None, expired_only: bool = False,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.governance.plane_evidence import list_evidence as _list
        return await _list(db, tenant, control_key=control_key or "",
                           expired_only=expired_only)
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/evidence/coverage")
async def get_evidence_coverage(
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.governance.plane_evidence import evidence_coverage as _coverage
        return await _coverage(db, tenant)
    except Exception as exc:
        raise _err(exc) from exc


# ─── Drift ───────────────────────────────────────────────────────────────────


@router.get("/drift")
async def get_drift(
    status: Optional[str] = None, severity: Optional[str] = None,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.governance.plane_drift import list_drift as _list
        return await _list(db, tenant, status=status or "", severity=severity or "")
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/drift/detect")
async def detect_drift(
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.governance.plane_drift import detect_drift as _detect
        result = await _detect(db, tenant)
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/drift/{finding_id}/resolve")
async def resolve_drift(
    finding_id: str,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, ADMIN_PERMISSION)
        from app.governance.plane_drift import resolve_drift as _resolve
        result = await _resolve(db, tenant, finding_id, actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


# ─── Reports & trends ────────────────────────────────────────────────────────


class ReportIn(BaseModel):
    report_type: str = "posture"
    scope_type: str = "tenant"
    scope_value: str = ""
    days: int = 30


@router.post("/reports", status_code=201)
async def create_report(
    payload: ReportIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.governance.plane_reports import generate_report as _generate
        result = await _generate(db, tenant, payload.report_type, **{
            k: v for k, v in payload.model_dump().items() if k != "report_type"
        }, actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/reports")
async def get_reports(
    report_type: Optional[str] = None,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.governance.plane_reports import list_reports as _list
        return await _list(db, tenant, report_type=report_type or "")
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/reports/trends")
async def get_trends(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.governance.plane_reports import trends as _trends
        return await _trends(db, tenant, days=days)
    except Exception as exc:
        raise _err(exc) from exc


# ─── Explanation ─────────────────────────────────────────────────────────────


@router.get("/decisions/{decision_id}/explain")
async def explain_decision(
    decision_id: str,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.governance.plane_explain import explain_decision as _explain
        return await _explain(db, tenant, decision_id)
    except Exception as exc:
        raise _err(exc) from exc


# ─── Domain governance ───────────────────────────────────────────────────────


class GovernAIIn(BaseModel):
    model: str = ""
    provider: str = ""
    use_case: str = ""
    action_class: str = ""
    classification: str = "INTERNAL"
    input_tokens: int = 0
    estimated_cents: int = 0
    operation: str = "ai.invoke"


class GovernDataIn(BaseModel):
    dataset: str = ""
    project: str = ""
    workspace: str = ""
    classification: str = "INTERNAL"
    region: str = ""
    destination: str = ""
    operation: str = "data.access"


class GovernSecurityIn(BaseModel):
    action: str = ""
    resource: str = ""
    classification: str = "INTERNAL"
    auth_strength: str = ""
    device_posture: str = ""
    identity: str = ""


class GovernSpendIn(BaseModel):
    operation: str = "spend"
    model: str = ""
    provider: str = ""
    workspace: str = ""
    project: str = ""
    estimated_cents: int = 0
    budget_id: Optional[str] = None


class GovernIntegrationIn(BaseModel):
    connection_id: str = ""
    operation: str = "integration.use"
    destination: str = ""
    classification: str = "INTERNAL"
    region: str = ""
    scopes: Optional[list] = None
    estimated_cents: int = 0


class GovernWorkflowIn(BaseModel):
    workflow_id: str = ""
    run_id: str = ""
    executor: str = ""
    environment: str = ""
    classification: str = "INTERNAL"
    fan_out: int = 1
    max_fan_out: int = 5


class GovernAgentIn(BaseModel):
    agent: str = ""
    tool: str = ""
    step_number: int = 0
    max_steps: int = 25
    classification: str = "INTERNAL"


@router.post("/govern/ai")
async def govern_ai(
    payload: GovernAIIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.governance.plane_ai import govern_ai_request as _govern
        result = await _govern(db, tenant, **payload.model_dump(), actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/govern/data")
async def govern_data(
    payload: GovernDataIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.governance.plane_data import govern_data_access as _govern
        result = await _govern(db, tenant, **payload.model_dump(), actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/govern/security")
async def govern_security(
    payload: GovernSecurityIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.governance.plane_security import govern_security_action as _govern
        result = await _govern(db, tenant, **payload.model_dump(), actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/govern/spend")
async def govern_spend(
    payload: GovernSpendIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.governance.plane_finops import govern_spend as _govern
        result = await _govern(db, tenant, **payload.model_dump(), actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/govern/integration")
async def govern_integration(
    payload: GovernIntegrationIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.governance.plane_integrations import govern_integration_use as _govern
        result = await _govern(db, tenant, **payload.model_dump(), actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/govern/workflow")
async def govern_workflow(
    payload: GovernWorkflowIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.governance.plane_workflow import govern_workflow_run as _govern
        result = await _govern(db, tenant, **payload.model_dump(), actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/govern/agent")
async def govern_agent(
    payload: GovernAgentIn,
    db: AsyncSession = Depends(_get_db), current_user=Depends(_resolve_user),
):
    try:
        tenant = _tenant(current_user)
        _iam_check(current_user, tenant, READ_PERMISSION)
        from app.governance.plane_workflow import govern_agent_step as _govern
        result = await _govern(db, tenant, **payload.model_dump(), actor=_user_id(current_user))
        await db.commit()
        return result
    except Exception as exc:
        raise _err(exc) from exc
