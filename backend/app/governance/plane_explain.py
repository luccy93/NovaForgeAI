"""Governance decision explanation — Volume 71 Commit 2.

Authorized, tenant-scoped explanations: why allowed/denied, which
policy/version/binding/rule, which exception and which approval
requirement. Policy content never crosses tenant boundaries.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.governance.plane_common import NotFoundError, ValidationError, _as_uuid
from app.governance.plane_evaluate import _serialize_decision
from app.governance.plane_models import (
    GovernancePlaneBinding,
    GovernancePlaneDecision,
    GovernancePlanePolicy,
    GovernancePlanePolicyVersion,
)


async def explain_decision(db: AsyncSession, tenant: str, decision_id) -> dict:
    if not tenant:
        raise ValidationError("tenant required")
    stmt = select(GovernancePlaneDecision).where(
        GovernancePlaneDecision.id == _as_uuid(decision_id),
        GovernancePlaneDecision.tenant == tenant,
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise NotFoundError("decision not found")

    explanation: dict = {
        "decision": row.decision,
        "reason": row.reason or "",
        "scope": {"scope_type": row.scope_type or "", "scope_value": row.scope_value or ""},
        "priority": row.priority,
        "obligations": row.obligations or [],
        "approval_id": row.approval_id or "",
        "actor": row.actor or "",
    }
    if row.policy_id:
        policy = (await db.execute(select(GovernancePlanePolicy).where(
            GovernancePlanePolicy.id == row.policy_id,
            GovernancePlanePolicy.tenant == tenant))).scalar_one_or_none()
        if policy is not None:
            explanation["policy"] = {"id": str(policy.id), "name": policy.name,
                                     "domain": policy.domain, "status": policy.status}
    if row.version_id:
        version = (await db.execute(select(GovernancePlanePolicyVersion).where(
            GovernancePlanePolicyVersion.id == row.version_id,
            GovernancePlanePolicyVersion.tenant == tenant))).scalar_one_or_none()
        if version is not None:
            explanation["version"] = {"id": str(version.id), "version": version.version,
                                      "status": version.status, "checksum": version.checksum}
            rules = version.rules or []
            if row.rule_index is not None and 0 <= row.rule_index < len(rules):
                rule = rules[row.rule_index]
                explanation["rule"] = {"index": row.rule_index, "name": rule.get("name"),
                                       "effect": rule.get("effect"),
                                       "priority": rule.get("priority"),
                                       "obligations": rule.get("obligations") or []}
    if row.binding_id:
        binding = (await db.execute(select(GovernancePlaneBinding).where(
            GovernancePlaneBinding.id == row.binding_id,
            GovernancePlaneBinding.tenant == tenant))).scalar_one_or_none()
        if binding is not None:
            explanation["binding"] = {"id": str(binding.id), "scope_type": binding.scope_type,
                                      "scope_value": binding.scope_value or "",
                                      "mandatory": binding.mandatory}
    if row.evaluation_id:
        explanation["evaluation_id"] = str(row.evaluation_id)
    if row.metadata_ and row.metadata_.get("exception_id"):
        explanation["exception_id"] = row.metadata_["exception_id"]
    if row.decision == "ALLOW":
        explanation["why"] = f"allowed by {explanation.get('rule', {}).get('name', 'default effect')}"
    elif row.decision == "DENY":
        explanation["why"] = f"denied: {row.reason or 'no allow rule matched'}"
    else:
        explanation["why"] = f"approval required: {row.reason or ''}"
    return {"id": str(row.id), "tenant": tenant, "explanation": explanation}
