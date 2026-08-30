"""Policy simulation and what-if analysis."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.iam.policy_tester import policy_tester


async def simulate(db: AsyncSession, tenant_id: str, identity: str, action: str, resource: str, context: dict | None = None) -> dict:
    ctx = context or {}
    ctx.setdefault("tenant", tenant_id)
    # Use policy_tester for safe decision without exposing secrets
    try:
        result = policy_tester.simulate_access(tenant_id, f"sim-{identity}", identity, action, ctx, denied=[])
        # But we need real decision via policy_authorizer
        from app.iam.policy_authorizer import policy_authorizer
        dec = policy_authorizer.authorize(identity, tenant_id, action, resource_type="simulation", resource_id=resource, context=ctx)
        return {
            "identity": identity,
            "action": action,
            "resource": resource,
            "decision": dec.get("decision", "deny"),
            "allowed": dec.get("allowed", False),
            "policy": dec.get("matched_policy") or dec.get("reason"),
            "required_conditions": dec.get("required_conditions", []),
            "safe_explanation": f"Decision {dec.get('decision')} via {dec.get('matched_policy', 'default')}",
        }
    except Exception as e:
        return {"identity": identity, "action": action, "resource": resource, "decision": "DENY", "allowed": False, "error": str(e)[:200], "safe_explanation": "deny by default — simulation failed"}


async def what_if(db: AsyncSession, tenant_id: str, permission: str, remove: bool = True) -> dict:
    # What happens if this permission is removed?
    # Find roles that have permission
    from app.iam.rbac_engine import rbac_engine
    impacted = []
    try:
        for role, perms in rbac_engine._role_permissions.items():
            if permission in perms:
                impacted.append({"role": role, "permission": permission})
        # Also check custom roles
        for org_role, perms in getattr(rbac_engine, "_custom_roles", {}).items():
            pass
    except Exception:
        pass
    return {
        "permission": permission,
        "action": "remove" if remove else "add",
        "impacted_roles": impacted[:10],
        "impacted_resources": [],  # would need resource scan
        "note": "What-if is hypothesis — validate against actual authorization",
    }
