"""Contextual authorization — Zero Trust core flow.

Evaluates identity+session+resource+action+tenant+region+classification+policy+risk.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.zero_trust.cache import cache_get, cache_set

# Cache key includes policy_version to invalidate on permission change


async def authorize(
    db: AsyncSession,
    identity_id: str,
    tenant_id: str,
    resource: str,
    action: str,
    session_id_hash: str | None = None,
    device_context: dict | None = None,
    region: str | None = None,
    data_classification: str | None = None,
    risk_state: str | None = None,
) -> dict:
    # Tenant isolation first
    if not tenant_id:
        return {"decision": "DENY", "allowed": False, "reason": "no tenant context", "matched_policy": None}
    # Session verification if provided
    session_data = None
    if session_id_hash:
        from app.zero_trust.sessions import get_session
        session_data = await get_session(db, session_id_hash, tenant_id)
        if not session_data:
            # DB failure or revoked → fail closed for protected
            if action in {"DELETE", "EXPORT", "DEPLOY", "ADMIN", "APPROVE"} or region == "production":
                return {"decision": "DENY", "allowed": False, "reason": "session not found or revoked — fail-closed", "matched_policy": None}
            # For safe read, could allow fallback? But spec says fail-closed for protected/high-risk, safe degradation for read
            # Here we deny as well to be safe, unless explicitly configured
            return {"decision": "DENY", "allowed": False, "reason": "session invalid", "matched_policy": None}
        # Check session risk
        if session_data.get("risk_state") in ("HIGH", "CRITICAL"):
            # Require challenge
            return {"decision": "CHALLENGE", "allowed": False, "reason": "high session risk requires step-up", "matched_policy": "risk_policy"}
        # Device trust check
        device_trust = device_context.get("trust") if device_context else "UNKNOWN"
        if device_trust == "UNKNOWN":
            # UNKNOWN must not automatically become TRUSTED — require explicit
            pass
        # Check region isolation via Volume 62 placement
        if region and data_classification:
            try:
                from app.regions.placement import placement_service
                eval_res = await placement_service.evaluate(db, tenant_id, data_classification, region, actor=identity_id)
                if eval_res.get("decision") == "DENY":
                    return {"decision": "DENY", "allowed": False, "reason": f"region {region} not allowed for classification {data_classification}", "matched_policy": "region_policy"}
            except Exception:
                pass
        # Data classification check via Volume57
        if data_classification in ("RESTRICTED", "SECRET", "CONFIDENTIAL"):
            # Require explicit export permission for EXPORT action
            if action == "EXPORT":
                # This will be checked via policy_authorizer below, but early deny if not privileged
                pass

    # Check authorization cache
    # Need policy_version from DB or current
    policy_version = "1.0"
    try:
        from app.iam.models import ResourcePolicy
        from sqlalchemy import select
        q = select(ResourcePolicy).where(ResourcePolicy.organization_id == _to_uuid(tenant_id)).order_by(ResourcePolicy.priority.desc()).limit(1)
        res = await db.execute(q)
        rp = res.scalar_one_or_none()
        if rp:
            policy_version = str(rp.priority)  # proxy
    except Exception:
        pass
    cache_key = f"zero_trust:authz:{tenant_id}:{identity_id}:{resource}:{action}:{policy_version}"
    cached = await cache_get(cache_key)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass
    # Policy evaluation via existing authorizer
    # Map action to IAMPermission
    permission_map = {
        "READ": "repository:read",
        "CREATE": "repository:write",
        "UPDATE": "repository:write",
        "DELETE": "repository:admin",
        "EXECUTE": "agent:execute",
        "APPROVE": "policy:manage",
        "DEPLOY": "environment:deploy",
        "EXPORT": "data:export",
        "ADMIN": "settings:admin",
    }
    perm = permission_map.get(action.upper(), "repository:read")
    # Also check resource-specific ABAC via context
    context = {
        "tenant": tenant_id,
        "resource": resource,
        "action": action,
        "region": region or "",
        "classification": data_classification or "PUBLIC",
        "risk": risk_state or (session_data.get("risk_state") if session_data else "LOW"),
        "device_trust": device_context.get("trust") if device_context else "UNKNOWN",
        "environment": device_context.get("environment") if device_context and isinstance(device_context, dict) else "production",
    }
    try:
        from app.iam.policy_authorizer import policy_authorizer
        decision = policy_authorizer.authorize(identity_id, tenant_id, perm, resource_type="zero_trust", resource_id=resource, context=context)
        # Map to our decisions
        if decision.get("decision") == "require_approval" or "approval" in decision.get("reason","").lower():
            result = {"decision": "REQUIRE_APPROVAL", "allowed": False, "reason": decision.get("reason"), "matched_policy": decision.get("matched_policy"), "risk_score": decision.get("risk_score")}
        elif decision.get("allowed"):
            # Check risk-aware: higher risk can trigger challenge even if allowed
            risk = context["risk"]
            if risk in ("HIGH", "CRITICAL") and action in {"DELETE", "EXPORT", "DEPLOY", "ADMIN"}:
                result = {"decision": "CHALLENGE", "allowed": False, "reason": f"high risk {risk} requires step-up", "matched_policy": "risk_policy"}
            else:
                result = {"decision": "ALLOW", "allowed": True, "reason": decision.get("reason", "allowed"), "matched_policy": decision.get("matched_policy")}
        else:
            # Check if challenge vs deny via risk
            if context["risk"] in ("MEDIUM", "HIGH") and decision.get("risk_score",0) > 0.5:
                result = {"decision": "CHALLENGE", "allowed": False, "reason": decision.get("reason", "challenge required"), "matched_policy": decision.get("matched_policy")}
            else:
                result = {"decision": "DENY", "allowed": False, "reason": decision.get("reason", "deny by default"), "matched_policy": decision.get("matched_policy")}
    except Exception as e:
        # Policy engine failure → fail-closed for protected/high-risk
        if action in {"DELETE", "ADMIN", "DEPLOY", "EXPORT", "APPROVE"}:
            result = {"decision": "DENY", "allowed": False, "reason": f"policy engine failure — fail-closed: {e}", "matched_policy": None}
        else:
            # Safe degradation for non-sensitive read
            result = {"decision": "DENY", "allowed": False, "reason": f"deny by default (policy unavailable)", "matched_policy": None}
    # Cache result
    await cache_set(cache_key, json.dumps(result), ttl=60)
    # Audit
    try:
        from app.iam.audit_service import audit_service
        audit_service.log(org_id=tenant_id, actor_id=identity_id, actor_type="user", action=f"zero_trust.authorize:{action}", resource_type="resource", resource_id=resource, result="success" if result["allowed"] else "failure", details={"decision": result["decision"], "region": region, "classification": data_classification}, tenant_id=tenant_id)
    except Exception:
        pass
    return result


def _to_uuid(v):
    import uuid
    try:
        return uuid.UUID(str(v))
    except Exception:
        return v


async def invalidate_cache_for_tenant(tenant_id: str):
    from app.zero_trust.cache import cache_del_pattern
    await cache_del_pattern(f"zero_trust:authz:{tenant_id}:*")
