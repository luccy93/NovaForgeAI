"""Tenant isolation service — enforce tenant boundaries at every layer."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional


class TenantIsolation:
    def __init__(self):
        self._tenant_scopes: dict[str, dict] = {}
        self._isolation_violations: list[dict] = []

    def set_tenant_scope(self, tenant_id: str, scope_type: str, scope_id: str) -> dict:
        key = f"{scope_type}:{scope_id}"
        self._tenant_scopes[key] = {"tenant_id": tenant_id, "scope_type": scope_type, "scope_id": scope_id, "set_at": datetime.now(timezone.utc).isoformat()}
        return self._tenant_scopes[key]

    def validate_tenant_access(self, tenant_id: str, resource_type: str, resource_id: str) -> dict:
        key = f"{resource_type}:{resource_id}"
        scope = self._tenant_scopes.get(key)
        if not scope:
            return {"valid": True, "reason": "No tenant scope registered for resource, allowing by default"}
        if scope["tenant_id"] == tenant_id:
            return {"valid": True, "reason": "Tenant scope matches"}
        self._isolation_violations.append({"tenant_id": tenant_id, "resource_type": resource_type, "resource_id": resource_id, "expected_tenant": scope["tenant_id"], "time": datetime.now(timezone.utc).isoformat()})
        return {"valid": False, "reason": f"Tenant mismatch: resource belongs to tenant '{scope['tenant_id']}'"}

    def create_cache_key(self, tenant_id: str, key: str) -> str:
        return f"tenant:{tenant_id}:{key}"

    def validate_cache_access(self, tenant_id: str, cache_key: str) -> bool:
        return cache_key.startswith(f"tenant:{tenant_id}:")

    def create_vector_filter(self, tenant_id: str, additional_filters: Optional[dict] = None) -> dict:
        filter_dict = {"tenant_id": tenant_id}
        if additional_filters:
            filter_dict.update(additional_filters)
        return filter_dict

    def create_graph_filter(self, tenant_id: str) -> dict:
        return {"tenant_id": tenant_id}

    def create_storage_path(self, tenant_id: str, path: str) -> str:
        return f"tenants/{tenant_id}/{path}"

    def validate_path(self, tenant_id: str, path: str) -> bool:
        return path.startswith(f"tenants/{tenant_id}/") or not path.startswith("tenants/")

    def create_job_context(self, tenant_id: str, actor_id: str, permissions: Optional[list[str]] = None) -> dict:
        return {"tenant_id": tenant_id, "actor_id": actor_id, "permissions": permissions or [], "created_at": datetime.now(timezone.utc).isoformat()}

    def validate_job_context(self, job_context: dict, required_tenant: str) -> bool:
        return job_context.get("tenant_id") == required_tenant

    def create_agent_permissions(self, tenant_id: str, project_id: str, repository_id: str, tools: Optional[list[str]] = None, data_permissions: Optional[list[str]] = None) -> dict:
        return {"tenant_id": tenant_id, "project_id": project_id, "repository_id": repository_id, "tools": tools or [], "data_permissions": data_permissions or [], "is_admin": False, "created_at": datetime.now(timezone.utc).isoformat()}

    def validate_agent_permission(self, agent_perms: dict, required_tenant: str, required_action: str) -> bool:
        if agent_perms.get("tenant_id") != required_tenant:
            return False
        if agent_perms.get("is_admin"):
            return True
        return required_action in agent_perms.get("data_permissions", []) or required_action in agent_perms.get("tools", [])

    def get_isolation_violations(self, tenant_id: Optional[str] = None) -> list[dict]:
        violations = self._isolation_violations
        if tenant_id:
            violations = [v for v in violations if v.get("tenant_id") == tenant_id]
        return violations

    def get_stats(self) -> dict:
        return {"total_scopes": len(self._tenant_scopes), "total_violations": len(self._isolation_violations)}


tenant_isolation = TenantIsolation()
