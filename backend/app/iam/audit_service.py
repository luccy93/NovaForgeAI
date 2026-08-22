"""Audit service — comprehensive IAM audit trail with immutability."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional


class AuditService:
    def __init__(self):
        self._audit_logs: list[dict] = []

    def log(self, org_id: str, actor_id: str, actor_type: str, action: str, resource_type: str = "", resource_id: str = "", result: str = "success", details: Optional[dict] = None, ip_address: str = "", user_agent: str = "", request_id: str = "", tenant_id: str = "", risk_score: float = 0.0) -> dict:
        entry = {"id": str(uuid.uuid4()), "organization_id": org_id, "actor_id": actor_id, "actor_type": actor_type, "action": action, "resource_type": resource_type, "resource_id": resource_id, "result": result, "details": details or {}, "ip_address": ip_address, "user_agent": user_agent, "request_id": request_id, "tenant_id": tenant_id, "risk_score": risk_score, "immutable": True, "created_at": datetime.now(timezone.utc).isoformat()}
        self._audit_logs.append(entry)
        return entry

    def log_login(self, org_id: str, user_id: str, method: str = "password", success: bool = True, ip_address: str = "", user_agent: str = "", mfa_used: bool = False) -> dict:
        return self.log(org_id, user_id, "user", "login", "user", user_id, "success" if success else "failure", {"method": method, "mfa_used": mfa_used}, ip_address, user_agent)

    def log_logout(self, org_id: str, user_id: str, ip_address: str = "") -> dict:
        return self.log(org_id, user_id, "user", "logout", "user", user_id, "success", {}, ip_address)

    def log_role_change(self, org_id: str, actor_id: str, target_user_id: str, old_role: str, new_role: str, reason: str = "") -> dict:
        return self.log(org_id, actor_id, "user", "role_change", "membership", target_user_id, "success", {"old_role": old_role, "new_role": new_role, "reason": reason})

    def log_permission_change(self, org_id: str, actor_id: str, resource_type: str, resource_id: str, old_permissions: list, new_permissions: list) -> dict:
        return self.log(org_id, actor_id, "user", "permission_change", resource_type, resource_id, "success", {"old_permissions": old_permissions, "new_permissions": new_permissions})

    def log_api_key_create(self, org_id: str, user_id: str, key_name: str, key_id: str) -> dict:
        return self.log(org_id, user_id, "user", "api_key_create", "api_key", key_id, "success", {"name": key_name})

    def log_api_key_revoke(self, org_id: str, user_id: str, key_id: str, reason: str = "") -> dict:
        return self.log(org_id, user_id, "user", "api_key_revoke", "api_key", key_id, "success", {"reason": reason})

    def log_service_account_create(self, org_id: str, actor_id: str, sa_name: str, sa_id: str) -> dict:
        return self.log(org_id, actor_id, "user", "service_account_create", "service_account", sa_id, "success", {"name": sa_name})

    def log_policy_change(self, org_id: str, actor_id: str, policy_id: str, action: str, details: Optional[dict] = None) -> dict:
        return self.log(org_id, actor_id, "user", f"policy_{action}", "policy", policy_id, "success", details)

    def log_break_glass(self, org_id: str, user_id: str, reason: str, scope: list, session_id: str) -> dict:
        return self.log(org_id, user_id, "user", "break_glass_start", "break_glass", session_id, "success", {"reason": reason, "scope": scope}, risk_score=0.9)

    def log_access_denied(self, org_id: str, user_id: str, permission: str, resource_type: str = "", resource_id: str = "", reason: str = "") -> dict:
        return self.log(org_id, user_id, "user", "access_denied", resource_type, resource_id, "failure", {"permission": permission, "reason": reason}, risk_score=0.5)

    def log_data_export(self, org_id: str, user_id: str, export_type: str, details: Optional[dict] = None) -> dict:
        return self.log(org_id, user_id, "user", "data_export", "export", export_type, "success", details, risk_score=0.7)

    def log_member_add(self, org_id: str, actor_id: str, target_user_id: str, role: str) -> dict:
        return self.log(org_id, actor_id, "user", "member_add", "membership", target_user_id, "success", {"role": role})

    def log_member_remove(self, org_id: str, actor_id: str, target_user_id: str, reason: str = "") -> dict:
        return self.log(org_id, actor_id, "user", "member_remove", "membership", target_user_id, "success", {"reason": reason})

    def log_org_create(self, org_id: str, user_id: str, org_name: str) -> dict:
        return self.log(org_id, user_id, "user", "org_create", "organization", org_id, "success", {"name": org_name})

    def log_org_suspend(self, org_id: str, actor_id: str, reason: str = "") -> dict:
        return self.log(org_id, actor_id, "user", "org_suspend", "organization", org_id, "success", {"reason": reason})

    def log_org_delete(self, org_id: str, actor_id: str, reason: str = "") -> dict:
        return self.log(org_id, actor_id, "user", "org_delete", "organization", org_id, "success", {"reason": reason}, risk_score=0.9)

    def query(self, org_id: Optional[str] = None, user_id: Optional[str] = None, action: Optional[str] = None, resource_type: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None, limit: int = 100, offset: int = 0) -> list[dict]:
        logs = list(self._audit_logs)
        if org_id:
            logs = [l for l in logs if l["organization_id"] == org_id]
        if user_id:
            logs = [l for l in logs if l["actor_id"] == user_id]
        if action:
            logs = [l for l in logs if l["action"] == action]
        if resource_type:
            logs = [l for l in logs if l.get("resource_type") == resource_type]
        if start_date:
            logs = [l for l in logs if l["created_at"] >= start_date]
        if end_date:
            logs = [l for l in logs if l["created_at"] <= end_date]
        return logs[offset:offset + limit]

    def get_immutable_logs(self, org_id: str) -> list[dict]:
        return [l for l in self._audit_logs if l["organization_id"] == org_id and l.get("immutable")]

    def get_stats(self, org_id: Optional[str] = None) -> dict:
        logs = self._audit_logs
        if org_id:
            logs = [l for l in logs if l["organization_id"] == org_id]
        action_counts = {}
        for l in logs:
            action_counts[l["action"]] = action_counts.get(l["action"], 0) + 1
        return {"total_entries": len(logs), "action_counts": action_counts, "high_risk_events": sum(1 for l in logs if l.get("risk_score", 0) >= 0.7)}


audit_service = AuditService()
