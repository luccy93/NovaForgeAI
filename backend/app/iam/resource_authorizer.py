"""Resource authorizer — resource-level access control with tenant/project/workspace scoping."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional
from app.iam.constants import IAMPermission
from app.iam.policy_authorizer import policy_authorizer


class ResourceAuthorizer:
    def __init__(self):
        self._resource_policies: dict[str, dict] = {}
        self._resource_owners: dict[str, dict] = {}
        self._evaluation_log: list[dict] = []

    def set_resource_owner(self, resource_id: str, resource_type: str, owner_id: str, org_id: str, workspace_id: str = "", project_id: str = "") -> dict:
        entry = {"resource_id": resource_id, "resource_type": resource_type, "owner_id": owner_id, "organization_id": org_id, "workspace_id": workspace_id, "project_id": project_id, "set_at": datetime.now(timezone.utc).isoformat()}
        self._resource_owners[resource_id] = entry
        return entry

    def get_resource_owner(self, resource_id: str) -> Optional[dict]:
        return self._resource_owners.get(resource_id)

    def grant_access(self, resource_id: str, resource_type: str, user_id: str, permissions: list[str], org_id: str, granted_by: str = "", expires_at: Optional[str] = None) -> dict:
        grant_id = str(uuid.uuid4())
        grant = {"id": grant_id, "resource_id": resource_id, "resource_type": resource_type, "user_id": user_id, "permissions": permissions, "organization_id": org_id, "granted_by": granted_by, "expires_at": expires_at, "is_active": True, "created_at": datetime.now(timezone.utc).isoformat()}
        self._resource_policies[grant_id] = grant
        return grant

    def revoke_access(self, grant_id: str, reason: str = "revoked") -> bool:
        grant = self._resource_policies.get(grant_id)
        if not grant:
            return False
        grant["is_active"] = False
        grant["revoked_at"] = datetime.now(timezone.utc).isoformat()
        grant["revocation_reason"] = reason
        return True

    def check_resource_access(self, user_id: str, resource_id: str, resource_type: str, action: str, org_id: str, context: Optional[dict] = None) -> dict:
        owner = self._resource_owners.get(resource_id)
        if owner and owner["owner_id"] == user_id:
            return {"allowed": True, "decision": "allow", "reason": "User is resource owner", "risk_score": 0.0}
        user_grants = [g for g in self._resource_policies.values() if g["user_id"] == user_id and g["resource_id"] == resource_id and g["is_active"]]
        for grant in user_grants:
            if action in grant["permissions"] or "admin:all" in grant["permissions"]:
                now = datetime.now(timezone.utc)
                if grant.get("expires_at"):
                    expires = datetime.fromisoformat(grant["expires_at"])
                    if expires.tzinfo is None:
                        expires = expires.replace(tzinfo=timezone.utc)
                    if now > expires:
                        continue
                self._evaluation_log.append({"user_id": user_id, "resource_id": resource_id, "action": action, "decision": "allow", "reason": "resource_grant", "time": now.isoformat()})
                return {"allowed": True, "decision": "allow", "reason": f"Direct resource grant matched", "grant_id": grant["id"], "risk_score": 0.1}
        ctx = context or {}
        ctx["resource_type"] = resource_type
        ctx["resource_id"] = resource_id
        result = policy_authorizer.authorize(user_id, org_id, action, resource_type, resource_id, ctx)
        self._evaluation_log.append({"user_id": user_id, "resource_id": resource_id, "action": action, "decision": result["decision"], "time": datetime.now(timezone.utc).isoformat()})
        return result

    def list_grants_for_resource(self, resource_id: str) -> list[dict]:
        return [g for g in self._resource_policies.values() if g["resource_id"] == resource_id and g["is_active"]]

    def list_grants_for_user(self, user_id: str, org_id: Optional[str] = None) -> list[dict]:
        grants = [g for g in self._resource_policies.values() if g["user_id"] == user_id and g["is_active"]]
        if org_id:
            grants = [g for g in grants if g["organization_id"] == org_id]
        return grants

    def get_evaluation_log(self, limit: int = 100) -> list[dict]:
        return self._evaluation_log[-limit:]

    def get_stats(self) -> dict:
        return {"total_grants": len(self._resource_policies), "active_grants": sum(1 for g in self._resource_policies.values() if g["is_active"]), "total_resource_owners": len(self._resource_owners), "evaluations": len(self._evaluation_log)}


resource_authorizer = ResourceAuthorizer()
