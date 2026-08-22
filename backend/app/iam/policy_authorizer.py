"""Policy authorizer — evaluates RBAC + ABAC + resource policies for access decisions."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional
from app.iam.constants import IAMPermission, ROLE_PERMISSIONS, IAMRole
from app.iam.rbac_engine import rbac_engine
from app.iam.abac_engine import abac_engine


class PolicyAuthorizer:
    def __init__(self):
        self._resource_policies: dict[str, dict] = {}
        self._evaluation_log: list[dict] = []
        self._deny_overrides: dict[str, set[str]] = {}

    def create_resource_policy(self, org_id: str, name: str, effect: str = "allow", resource_scope: str = "organization", conditions: Optional[list[dict]] = None, principals: Optional[list[dict]] = None, actions: Optional[list[str]] = None, priority: int = 0, description: str = "") -> dict:
        policy_id = str(uuid.uuid4())
        policy = {"id": policy_id, "organization_id": org_id, "name": name, "description": description, "effect": effect, "resource_scope": resource_scope, "conditions": conditions or [], "principals": principals or [], "actions": actions or [], "priority": priority, "is_active": True, "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()}
        self._resource_policies[policy_id] = policy
        return policy

    def get_resource_policy(self, policy_id: str) -> Optional[dict]:
        return self._resource_policies.get(policy_id)

    def list_resource_policies(self, org_id: str, resource_scope: Optional[str] = None) -> list[dict]:
        policies = [p for p in self._resource_policies.values() if p["organization_id"] == org_id]
        if resource_scope:
            policies = [p for p in policies if p["resource_scope"] == resource_scope]
        return policies

    def update_resource_policy(self, policy_id: str, updates: dict) -> Optional[dict]:
        policy = self._resource_policies.get(policy_id)
        if not policy:
            return None
        for key in ("name", "description", "effect", "conditions", "principals", "actions", "priority", "is_active", "resource_scope"):
            if key in updates:
                policy[key] = updates[key]
        policy["updated_at"] = datetime.now(timezone.utc).isoformat()
        return policy

    def delete_resource_policy(self, policy_id: str) -> bool:
        return self._resource_policies.pop(policy_id, None) is not None

    def set_deny_override(self, org_id: str, permission: str) -> dict:
        self._deny_overrides.setdefault(org_id, set()).add(permission)
        return {"org_id": org_id, "permission": permission, "set": True}

    def clear_deny_override(self, org_id: str, permission: str) -> dict:
        if org_id in self._deny_overrides:
            self._deny_overrides[org_id].discard(permission)
        return {"org_id": org_id, "permission": permission, "cleared": True}

    def authorize(self, user_id: str, org_id: str, permission: str, resource_type: str = "", resource_id: str = "", context: Optional[dict] = None) -> dict:
        eval_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        user_role = context.get("role", "viewer") if context else "viewer"
        denied = self._deny_overrides.get(org_id, set())
        if permission in denied:
            decision = {"allowed": False, "decision": "deny", "reason": "Explicit deny override active", "permission": permission, "org_id": org_id, "evaluation_id": eval_id, "timestamp": now, "risk_score": 0.8}
            self._evaluation_log.append({"user_id": user_id, "org_id": org_id, "permission": permission, "decision": "deny", "reason": "deny_override", "time": now})
            return decision
        rbac_result = rbac_engine.evaluate_access(user_role, permission, list(denied))
        if not rbac_result["allowed"]:
            decision = {"allowed": False, "decision": "deny", "reason": f"RBAC check failed: role '{user_role}' lacks permission '{permission}'", "permission": permission, "org_id": org_id, "evaluation_id": eval_id, "timestamp": now, "risk_score": 0.6}
            self._evaluation_log.append({"user_id": user_id, "org_id": org_id, "permission": permission, "decision": "deny", "reason": "rbac_failed", "time": now})
            return decision
        abac_decision = "allow"
        if resource_type and context:
            abac_result = abac_engine.evaluate(resource_type, permission, context)
            abac_decision = abac_result.get("decision", "allow")
            if abac_decision == "denied":
                decision = {"allowed": False, "decision": "deny", "reason": "ABAC policy denied", "permission": permission, "org_id": org_id, "evaluation_id": eval_id, "timestamp": now, "risk_score": 0.7, "abac_details": abac_result}
                self._evaluation_log.append({"user_id": user_id, "org_id": org_id, "permission": permission, "decision": "deny", "reason": "abac_denied", "time": now})
                return decision
            if abac_decision == "require_approval":
                decision = {"allowed": False, "decision": "require_approval", "reason": "ABAC policy requires approval", "permission": permission, "org_id": org_id, "evaluation_id": eval_id, "timestamp": now, "risk_score": 0.4, "abac_details": abac_result}
                self._evaluation_log.append({"user_id": user_id, "org_id": org_id, "permission": permission, "decision": "require_approval", "reason": "abac_approval", "time": now})
                return decision
        risk_score = 0.1
        if "production" in str(context or {}):
            risk_score += 0.3
        if "admin" in permission or "security" in permission:
            risk_score += 0.2
        decision = {"allowed": True, "decision": "allow", "reason": "RBAC + ABAC authorization passed", "permission": permission, "org_id": org_id, "evaluation_id": eval_id, "timestamp": now, "risk_score": min(risk_score, 1.0)}
        self._evaluation_log.append({"user_id": user_id, "org_id": org_id, "permission": permission, "decision": "allow", "time": now})
        return decision

    def explain(self, user_id: str, org_id: str, permission: str, context: Optional[dict] = None) -> dict:
        user_role = context.get("role", "viewer") if context else "viewer"
        denied = self._deny_overrides.get(org_id, set())
        perms = rbac_engine.resolve_role_permissions(user_role)
        has_rbac = IAMPermission(permission) in perms if permission in [p.value for p in IAMPermission] else False
        is_denied = permission in denied
        abac_applicable = False
        abac_details = None
        resource_type = context.get("resource_type", "") if context else ""
        if resource_type:
            abac_result = abac_engine.evaluate(resource_type, permission, context or {})
            abac_applicable = abac_result.get("policies_evaluated", 0) > 0
            abac_details = abac_result
        return {"user_id": user_id, "org_id": org_id, "permission": permission, "role": user_role, "rbac_has_permission": has_rbac, "is_denied_by_override": is_denied, "abac_applicable": abac_applicable, "abac_details": abac_details, "effective_permissions": [p.value for p in perms], "evaluation_time": datetime.now(timezone.utc).isoformat()}

    def get_evaluation_log(self, limit: int = 100) -> list[dict]:
        return self._evaluation_log[-limit:]

    def get_stats(self, org_id: Optional[str] = None) -> dict:
        logs = self._evaluation_log
        if org_id:
            logs = [l for l in logs if l.get("org_id") == org_id]
        allowed = sum(1 for l in logs if l["decision"] == "allow")
        denied = sum(1 for l in logs if l["decision"] == "deny")
        return {"total_evaluations": len(logs), "allowed": allowed, "denied": denied, "resource_policies": len(self._resource_policies), "deny_overrides": sum(len(v) for v in self._deny_overrides.values())}


policy_authorizer = PolicyAuthorizer()
