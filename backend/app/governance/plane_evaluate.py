"""Policy evaluation and enforcement decisions — Volume 71 Commit 1.

`evaluate()` runs central policies bound to the request scope, applies
active exceptions, resolves conflicts deterministically and persists
evaluation + decision metadata (never secrets or raw bodies).
`decide()` adds the existing Zero Trust authorization as an additional
layer and routes approval obligations to existing JIT/workflow
approvals. Governance never replaces underlying authorization.
"""

from __future__ import annotations

import time
import uuid
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.governance.plane_bindings import resolve_chain
from app.governance.plane_common import (
    NotFoundError,
    ValidationError,
    _as_uuid,
    _ensure_aware,
    _utcnow,
    parse_time,
    request_hash,
    sanitize_context,
    sanitize_metadata,
)
from app.governance.plane_engine import match_condition, resolve_decision
from app.governance.plane_models import (
    GovernancePlaneDecision,
    GovernancePlaneEvaluation,
    GovernancePlanePolicyVersion,
)
from app.governance.plane_policies import get_active_version


def _serialize_decision(row: GovernancePlaneDecision, evaluation_id=None) -> dict:
    return {
        "id": str(row.id),
        "evaluation_id": str(row.evaluation_id or evaluation_id or ""),
        "tenant": row.tenant,
        "policy_id": str(row.policy_id) if row.policy_id else None,
        "version_id": str(row.version_id) if row.version_id else None,
        "binding_id": str(row.binding_id) if row.binding_id else None,
        "rule_index": row.rule_index,
        "decision": row.decision,
        "scope_type": row.scope_type or "",
        "scope_value": row.scope_value or "",
        "priority": row.priority,
        "reason": row.reason or "",
        "obligations": row.obligations or [],
        "approval_id": row.approval_id or "",
        "actor": row.actor or "",
    }


async def _active_exceptions(db: AsyncSession, tenant: str, policy_id, scope_type: str,
                             scope_value: str) -> list:
    from app.governance.plane_models import GovernancePlaneException

    now = _utcnow()
    rows = (await db.execute(select(GovernancePlaneException).where(
        GovernancePlaneException.tenant == tenant,
        GovernancePlaneException.policy_id == policy_id,
        GovernancePlaneException.status == "APPROVED",
        GovernancePlaneException.start_at <= now,
        GovernancePlaneException.end_at > now,
    ))).scalars().all()
    valid = []
    for row in rows:
        if row.scope_type and row.scope_type != scope_type:
            continue
        if row.scope_value and row.scope_value not in (scope_value, ""):
            continue
        valid.append(row)
    return valid


async def evaluate(
    db: AsyncSession, tenant: str, *,
    scope_type: str, scope_value: str = "", operation: str = "",
    context: Optional[dict] = None, actor: str = "",
    persist: bool = True,
) -> dict:
    """Evaluate central policies for a request. Deterministic; persists
    metadata unless persist=False (simulation path uses its own runner)."""
    from app.governance.plane_common import SCOPE_TYPES

    if not tenant:
        raise ValidationError("tenant required")
    if scope_type not in SCOPE_TYPES:
        raise ValidationError(f"invalid scope_type: {scope_type!r}")
    clean = sanitize_context(context)
    started = time.monotonic()

    chain = await resolve_chain(db, tenant, scope_type, scope_value or "")
    matched: list[dict] = []
    default_effect = "deny"
    for binding in chain:
        version = await get_active_version(db, tenant, binding["policy_id"])
        if version is None:
            continue
        default_effect = version.get("default_effect", "deny")
        for index, rule in enumerate(version.get("rules") or []):
            try:
                hit = match_condition(rule["condition"], clean)
            except ValidationError:
                continue
            if not hit:
                continue
            matched.append({
                "effect": rule["effect"], "priority": int(rule.get("priority", 0)),
                "depth": binding["depth"], "mandatory": bool(binding.get("mandatory")),
                "policy_id": binding["policy_id"], "version_id": version["id"],
                "binding_id": binding["id"], "rule_index": index,
                "rule_name": rule.get("name", f"rule-{index}"),
                "obligations": rule.get("obligations") or [],
            })

    resolution = resolve_decision(matched, default_effect=default_effect)
    latency_ms = int((time.monotonic() - started) * 1000)

    # Active approved exceptions soften non-mandatory denies within scope.
    exception_id = ""
    if resolution["decision"] == "DENY" and not any(m.get("mandatory") for m in resolution.get("matched", [])):
        winner = (resolution.get("matched") or [{}])[0]
        if winner.get("policy_id"):
            applicable = await _active_exceptions(
                db, tenant, uuid.UUID(str(winner["policy_id"])), scope_type, scope_value or "")
            if applicable:
                chosen = applicable[0]
                exception_id = str(chosen.id)
                resolution = {"decision": "ALLOW", "matched": [], "exception_id": exception_id,
                              "reason": f"governed exception {exception_id} applies"}

    obligations = list(resolution.get("obligations", []))
    winner = resolution.get("winner") or (resolution.get("matched") or [{}])[0] if resolution.get("matched") else {}
    decision_row = None
    evaluation_id = uuid.uuid4()
    if persist:
        evaluation = GovernancePlaneEvaluation(
            id=evaluation_id, tenant=tenant,
            request_hash=request_hash(tenant, scope_type, scope_value or "",
                                      operation or "", clean),
            scope_type=scope_type, scope_value=scope_value or "",
            operation=operation or "", decision=resolution["decision"],
            policy_id=uuid.UUID(str(winner.get("policy_id"))) if winner.get("policy_id") else None,
            version_id=uuid.UUID(str(winner.get("version_id"))) if winner.get("version_id") else None,
            latency_ms=latency_ms, simulated=False, metadata_={},
        )
        db.add(evaluation)
        await db.flush()
        decision_row = GovernancePlaneDecision(
            tenant=tenant, evaluation_id=evaluation.id,
            policy_id=uuid.UUID(str(winner.get("policy_id"))) if winner.get("policy_id") else None,
            version_id=uuid.UUID(str(winner.get("version_id"))) if winner.get("version_id") else None,
            binding_id=uuid.UUID(str(winner.get("binding_id"))) if winner.get("binding_id") else None,
            rule_index=winner.get("rule_index"), decision=resolution["decision"],
            scope_type=scope_type, scope_value=scope_value or "",
            priority=int(winner.get("priority", 0)), reason=resolution.get("reason", "")[:1024],
            obligations=obligations, approval_id="", actor=actor or "",
            metadata_={"exception_id": exception_id} if exception_id else {},
        )
        db.add(decision_row)
        await db.flush()
        if resolution["decision"] == "DENY":
            try:
                from app.governance.plane_common import emit_event
                await emit_event("governance_violation",
                                 {"operation": operation, "reason": resolution.get("reason", "")}, tenant)
            except Exception:
                pass

    result = {
        "decision": resolution["decision"],
        "reason": resolution.get("reason", ""),
        "policy_id": (winner.get("policy_id")),
        "version_id": (winner.get("version_id")),
        "binding_id": (winner.get("binding_id")),
        "rule_index": winner.get("rule_index"),
        "priority": int(winner.get("priority", 0)),
        "obligations": obligations,
        "exception_id": exception_id,
        "scope_type": scope_type,
        "scope_value": scope_value or "",
        "effective_at": _utcnow().isoformat(),
        "latency_ms": latency_ms,
    }
    if decision_row is not None:
        result["id"] = str(decision_row.id)
        result["evaluation_id"] = str(evaluation_id)
    return result


async def decide(
    db: AsyncSession, tenant: str, *,
    scope_type: str, scope_value: str = "", operation: str = "",
    context: Optional[dict] = None, actor: str = "",
    identity: str = "", session_id_hash: Optional[str] = None,
) -> dict:
    """Enforcement entry point: central policy decision first, then the
    existing Zero Trust authorization as an additional layer. Either side
    can deny; approvals route to existing JIT controls."""
    result = await evaluate(db, tenant, scope_type=scope_type, scope_value=scope_value,
                            operation=operation, context=context, actor=actor)
    if result["decision"] == "DENY":
        return {**result, "allowed": False}

    # Additional layer: existing Zero Trust authorization (session-bound).
    try:
        from app.zero_trust.authorization import authorize as _zt_authorize
        zt = await _zt_authorize(
            db, identity or actor or "unknown", tenant,
            resource=f"governance:{scope_type}:{scope_value or '*'}",
            action=(operation or "access").upper(),
            session_id_hash=session_id_hash,
        )
        result["zero_trust"] = {"decision": zt.get("decision"), "allowed": bool(zt.get("allowed")),
                                "reason": zt.get("reason", "")}
        if not zt.get("allowed"):
            if zt.get("decision") == "REQUIRE_APPROVAL":
                approval_id = await _request_approval(
                    db, tenant, identity or actor or "unknown", operation or "access",
                    result.get("reason", ""), actor=actor)
                return {**result, "decision": "REQUIRE_APPROVAL", "allowed": False,
                        "approval_id": approval_id,
                        "reason": f"zero trust requires approval: {zt.get('reason', '')}"}
            return {**result, "decision": "DENY", "allowed": False,
                    "reason": f"zero trust denied: {zt.get('reason', '')}"}
    except Exception as exc:
        # Zero Trust unavailable: fail-safe on the central decision only if
        # it was an explicit allow; never upgrade a deny.
        result["zero_trust"] = {"decision": "UNKNOWN", "allowed": True,
                                "reason": f"zero trust unavailable: {type(exc).__name__}"}

    if result["decision"] == "REQUIRE_APPROVAL" or "require_approval" in result.get("obligations", []):
        approval_id = await _request_approval(
            db, tenant, identity or actor or "unknown", operation or "access",
            result.get("reason", ""), actor=actor)
        return {**result, "allowed": False, "approval_id": approval_id}
    return {**result, "allowed": result["decision"] == "ALLOW"}


async def _request_approval(db: AsyncSession, tenant: str, identity: str,
                            operation: str, reason: str, actor: str = "") -> str:
    from app.zero_trust.jit import request_access
    rec = await request_access(
        db, tenant, identity, f"governance:operation:{operation}", operation,
        reason or f"Governance requires approval for {operation}",
        duration_seconds=3600, scope={"governance": True},
        privilege_level="MEDIUM", requested_by=actor or identity)
    return str(rec.id)


async def get_decision(db: AsyncSession, tenant: str, decision_id) -> dict:
    from app.governance.plane_common import _as_uuid
    from app.governance.plane_models import GovernancePlaneDecision as _Decision

    stmt = select(_Decision).where(_Decision.id == _as_uuid(decision_id),
                                  _Decision.tenant == tenant)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        from app.governance.plane_common import NotFoundError as _NotFound
        raise _NotFound("decision not found")
    return _serialize_decision(row)


def _serialize_decision(row) -> dict:
    return {
        "id": str(row.id),
        "evaluation_id": str(row.evaluation_id) if row.evaluation_id else "",
        "tenant": row.tenant,
        "policy_id": str(row.policy_id) if row.policy_id else None,
        "version_id": str(row.version_id) if row.version_id else None,
        "binding_id": str(row.binding_id) if row.binding_id else None,
        "rule_index": row.rule_index,
        "decision": row.decision,
        "scope_type": row.scope_type or "",
        "scope_value": row.scope_value or "",
        "priority": row.priority,
        "reason": row.reason or "",
        "obligations": row.obligations or [],
        "approval_id": row.approval_id or "",
        "actor": row.actor or "",
    }


async def list_decisions(db: AsyncSession, tenant: str, *, decision: str = "",
                         operation: str = "", limit: int = 100) -> dict:
    from sqlalchemy import desc as _desc
    from app.governance.plane_common import _as_uuid  # noqa: F401
    from app.governance.plane_models import GovernancePlaneDecision as _Decision
    from app.governance.plane_models import GovernancePlaneEvaluation as _Evaluation

    stmt = select(_Decision).where(_Decision.tenant == tenant)
    if decision:
        stmt = stmt.where(_Decision.decision == decision)
    rows = (await db.execute(stmt.order_by(_desc(_Decision.created_at)).limit(
        min(max(int(limit or 100), 1), 1000)))).scalars().all()
    items = [_serialize_decision(r) for r in rows]
    if operation:
        items = [i for i in items if (await _evaluation_operation(db, tenant, i["evaluation_id"])) == operation]
    return {"items": items, "total": len(items)}


async def _evaluation_operation(db: AsyncSession, tenant: str, evaluation_id: str) -> str:
    from app.governance.plane_common import _as_uuid
    from app.governance.plane_models import GovernancePlaneEvaluation as _Evaluation

    if not evaluation_id:
        return ""
    try:
        stmt = select(_Evaluation).where(_Evaluation.id == _as_uuid(evaluation_id),
                                        _Evaluation.tenant == tenant)
        row = (await db.execute(stmt)).scalar_one_or_none()
        return row.operation if row else ""
    except Exception:
        return ""
