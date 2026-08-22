"""RBAC engine — role-based access control with inheritance and deny-override."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional
from app.iam.constants import IAMRole, IAMPermission, ROLE_PERMISSIONS, ROLE_HIERARCHY


class RBACEngine:
    def __init__(self):
        self._custom_roles: dict[str, dict] = {}
        self._role_permissions: dict[str, set[IAMPermission]] = {}
        self._membership_cache: dict[tuple[str, str], str] = {}
        self._evaluation_log: list[dict] = []

    def resolve_role_permissions(self, role: str, inherited_roles: Optional[list[str]] = None) -> set[IAMPermission]:
        perms: set[IAMPermission] = set()
        try:
            enum_role = IAMRole(role)
            perms |= ROLE_PERMISSIONS.get(enum_role, set())
        except ValueError:
            if role in self._role_permissions:
                perms |= self._role_permissions[role]

        if inherited_roles:
            for inh_role in inherited_roles:
                try:
                    enum_role = IAMRole(inh_role)
                    perms |= ROLE_PERMISSIONS.get(enum_role, set())
                except ValueError:
                    if inh_role in self._role_permissions:
                        perms |= self._role_permissions[inh_role]
        return perms

    def check_permission(self, role: str, permission: IAMPermission, denied_permissions: Optional[set[IAMPermission]] = None) -> bool:
        if denied_permissions and permission in denied_permissions:
            return False
        perms = self.resolve_role_permissions(role)
        return permission in perms

    def evaluate_access(self, user_role: str, permission: str, denied_permissions: Optional[list[str]] = None, inherited_roles: Optional[list[str]] = None) -> dict:
        perm = IAMPermission(permission)
        denied = {IAMPermission(p) for p in (denied_permissions or [])}
        allowed = self.check_permission(user_role, perm, denied, )
        inherited = inherited_roles or []
        inherited_perms = self.resolve_role_permissions(user_role, inherited)
        effective_perms = inherited_perms - denied
        result = {
            "allowed": allowed,
            "role": user_role,
            "permission": permission,
            "effective_permissions": [p.value for p in effective_perms],
            "denied_permissions": [p for p in (denied_permissions or [])],
            "evaluation_time": datetime.now(timezone.utc).isoformat(),
        }
        self._evaluation_log.append(result)
        return result

    def create_custom_role(self, org_id: str, name: str, permissions: list[str], inherits_from: Optional[list[str]] = None, description: str = "", is_system: bool = False) -> dict:
        role_id = str(uuid.uuid4())
        role_data = {
            "id": role_id,
            "organization_id": org_id,
            "name": name,
            "description": description,
            "permissions": permissions,
            "inherits_from": inherits_from or [],
            "is_system": is_system,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._custom_roles[role_id] = role_data
        perms = set()
        for p in permissions:
            try:
                perms.add(IAMPermission(p))
            except ValueError:
                pass
        self._role_permissions[name] = perms
        return role_data

    def update_custom_role(self, role_id: str, updates: dict) -> Optional[dict]:
        role = self._custom_roles.get(role_id)
        if not role:
            return None
        for key, value in updates.items():
            if key in ("permissions", "inherits_from", "name", "description"):
                role[key] = value
        if "permissions" in updates:
            perms = set()
            for p in updates["permissions"]:
                try:
                    perms.add(IAMPermission(p))
                except ValueError:
                    pass
            self._role_permissions[role["name"]] = perms
        return role

    def delete_custom_role(self, role_id: str) -> bool:
        if role_id in self._custom_roles:
            role = self._custom_roles.pop(role_id)
            self._role_permissions.pop(role["name"], None)
            return True
        return False

    def get_role(self, role_id: str) -> Optional[dict]:
        return self._custom_roles.get(role_id)

    def list_roles(self, org_id: Optional[str] = None) -> list[dict]:
        roles = list(self._custom_roles.values())
        if org_id:
            roles = [r for r in roles if r["organization_id"] == org_id]
        return roles

    def get_role_hierarchy(self, role: str) -> list[str]:
        try:
            enum_role = IAMRole(role)
            children = ROLE_HIERARCHY.get(enum_role, [])
            return [r.value for r in children]
        except ValueError:
            return []

    def get_evaluation_log(self, limit: int = 100) -> list[dict]:
        return self._evaluation_log[-limit:]

    def get_stats(self) -> dict:
        return {
            "custom_roles": len(self._custom_roles),
            "total_evaluations": len(self._evaluation_log),
            "role_permissions_count": {name: len(perms) for name, perms in self._role_permissions.items()},
        }


rbac_engine = RBACEngine()
