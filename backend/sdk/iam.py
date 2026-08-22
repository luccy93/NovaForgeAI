"""IAM SDK mixin — enterprise identity, multi-tenancy, authorization & zero-trust access control."""
from __future__ import annotations


class IAMMixin:
    def iam_list_organizations(self, state=None):
        params = {"state": state} if state else {}
        return self._get("/iam/organizations", params=params)

    def iam_create_organization(self, name, slug, owner_id="", description="", plan="free"):
        return self._post("/iam/organizations", json={"name": name, "slug": slug, "owner_id": owner_id, "description": description, "plan": plan})

    def iam_get_organization(self, org_id):
        return self._get(f"/iam/organizations/{org_id}")

    def iam_update_organization(self, org_id, **kwargs):
        return self._put(f"/iam/organizations/{org_id}", json=kwargs)

    def iam_delete_organization(self, org_id, reason=""):
        return self._delete(f"/iam/organizations/{org_id}", params={"reason": reason})

    def iam_suspend_organization(self, org_id, reason=""):
        return self._post(f"/iam/organizations/{org_id}/suspend", json={"reason": reason})

    def iam_reactivate_organization(self, org_id):
        return self._post(f"/iam/organizations/{org_id}/reactivate")

    def iam_get_organization_stats(self, org_id):
        return self._get(f"/iam/organizations/{org_id}/stats")

    def iam_list_workspaces(self, org_id):
        return self._get(f"/iam/organizations/{org_id}/workspaces")

    def iam_create_workspace(self, org_id, name, slug, description="", created_by=""):
        return self._post(f"/iam/organizations/{org_id}/workspaces", json={"name": name, "slug": slug, "description": description, "created_by": created_by})

    def iam_get_workspace(self, workspace_id):
        return self._get(f"/iam/workspaces/{workspace_id}")

    def iam_update_workspace(self, workspace_id, **kwargs):
        return self._put(f"/iam/workspaces/{workspace_id}", json=kwargs)

    def iam_delete_workspace(self, workspace_id):
        return self._delete(f"/iam/workspaces/{workspace_id}")

    def iam_list_projects(self, workspace_id):
        return self._get(f"/iam/workspaces/{workspace_id}/projects")

    def iam_create_project(self, workspace_id, name, slug, org_id="", description="", created_by=""):
        return self._post(f"/iam/workspaces/{workspace_id}/projects", json={"name": name, "slug": slug, "org_id": org_id, "description": description, "created_by": created_by})

    def iam_get_project(self, project_id):
        return self._get(f"/iam/projects/{project_id}")

    def iam_update_project(self, project_id, **kwargs):
        return self._put(f"/iam/projects/{project_id}", json=kwargs)

    def iam_delete_project(self, project_id):
        return self._delete(f"/iam/projects/{project_id}")

    def iam_list_members(self, org_id):
        return self._get(f"/iam/organizations/{org_id}/members")

    def iam_invite_member(self, org_id, email, role="viewer", invited_by="", team_ids=None, message=""):
        return self._post(f"/iam/organizations/{org_id}/members/invite", json={"email": email, "role": role, "invited_by": invited_by, "team_ids": team_ids, "message": message})

    def iam_accept_invitation(self, org_id, invitation_id, user_id):
        return self._post(f"/iam/organizations/{org_id}/members/accept", json={"invitation_id": invitation_id, "user_id": user_id})

    def iam_update_member_role(self, org_id, user_id, role, reason="", actor_id=""):
        return self._put(f"/iam/organizations/{org_id}/members/{user_id}/role", json={"role": role, "reason": reason, "actor_id": actor_id})

    def iam_remove_member(self, org_id, user_id, reason="", transfer_to="", actor_id=""):
        return self._delete(f"/iam/organizations/{org_id}/members/{user_id}", json={"reason": reason, "transfer_to": transfer_to, "actor_id": actor_id})

    def iam_suspend_member(self, org_id, user_id, reason=""):
        return self._post(f"/iam/organizations/{org_id}/members/{user_id}/suspend", json={"reason": reason})

    def iam_get_membership_stats(self, org_id):
        return self._get(f"/iam/organizations/{org_id}/memberships/stats")

    def iam_list_teams(self, org_id):
        return self._get(f"/iam/organizations/{org_id}/teams")

    def iam_create_team(self, org_id, name, description="", parent_team_id=None):
        return self._post(f"/iam/organizations/{org_id}/teams", json={"name": name, "description": description, "parent_team_id": parent_team_id})

    def iam_update_team(self, team_id, **kwargs):
        return self._put(f"/iam/teams/{team_id}", json=kwargs)

    def iam_delete_team(self, team_id):
        return self._delete(f"/iam/teams/{team_id}")

    def iam_add_team_member(self, team_id, user_id, role="member"):
        return self._post(f"/iam/teams/{team_id}/members", json={"user_id": user_id, "role": role})

    def iam_remove_team_member(self, team_id, user_id):
        return self._delete(f"/iam/teams/{team_id}/members/{user_id}")

    def iam_list_team_members(self, team_id):
        return self._get(f"/iam/teams/{team_id}/members")

    def iam_list_roles(self, org_id):
        return self._get(f"/iam/organizations/{org_id}/roles")

    def iam_create_role(self, org_id, name, permissions=None, inherits_from=None, description="", is_system=False):
        return self._post(f"/iam/organizations/{org_id}/roles", json={"name": name, "permissions": permissions or [], "inherits_from": inherits_from, "description": description, "is_system": is_system})

    def iam_update_role(self, role_id, **kwargs):
        return self._put(f"/iam/roles/{role_id}", json=kwargs)

    def iam_delete_role(self, role_id):
        return self._delete(f"/iam/roles/{role_id}")

    def iam_get_role_hierarchy(self, role):
        return self._get(f"/iam/roles/hierarchy/{role}")

    def iam_create_resource_policy(self, org_id, name, effect="allow", resource_scope="organization", conditions=None, principals=None, actions=None, priority=0, description=""):
        return self._post(f"/iam/organizations/{org_id}/resource-policies", json={"name": name, "effect": effect, "resource_scope": resource_scope, "conditions": conditions or [], "principals": principals or [], "actions": actions or [], "priority": priority, "description": description})

    def iam_list_resource_policies(self, org_id, resource_scope=None):
        params = {"resource_scope": resource_scope} if resource_scope else {}
        return self._get(f"/iam/organizations/{org_id}/resource-policies", params=params)

    def iam_update_resource_policy(self, policy_id, **kwargs):
        return self._put(f"/iam/resource-policies/{policy_id}", json=kwargs)

    def iam_delete_resource_policy(self, policy_id):
        return self._delete(f"/iam/resource-policies/{policy_id}")

    def iam_authorize(self, user_id, org_id, permission, resource_type="", resource_id="", context=None):
        return self._post("/iam/authorize", json={"user_id": user_id, "org_id": org_id, "permission": permission, "resource_type": resource_type, "resource_id": resource_id, "context": context})

    def iam_explain_authorization(self, user_id, org_id, permission, context=None):
        return self._post("/iam/authorize/explain", json={"user_id": user_id, "org_id": org_id, "permission": permission, "context": context})

    def iam_create_session(self, org_id, user_id, ip_address="", user_agent="", auth_method="password"):
        return self._post(f"/iam/organizations/{org_id}/sessions", json={"user_id": user_id, "ip_address": ip_address, "user_agent": user_agent, "auth_method": auth_method})

    def iam_list_sessions(self, org_id):
        return self._get(f"/iam/organizations/{org_id}/sessions")

    def iam_revoke_session(self, session_id, reason="user_request"):
        return self._post(f"/iam/sessions/{session_id}/revoke", json={"reason": reason})

    def iam_refresh_session(self, session_id):
        return self._post(f"/iam/sessions/{session_id}/refresh")

    def iam_create_api_key(self, org_id, user_id, name, scopes=None, expires_in_days=None):
        return self._post(f"/iam/organizations/{org_id}/api-keys", json={"user_id": user_id, "name": name, "scopes": scopes, "expires_in_days": expires_in_days})

    def iam_list_api_keys(self, org_id):
        return self._get(f"/iam/organizations/{org_id}/api-keys")

    def iam_revoke_api_key(self, key_id, reason="user_request", actor_id=""):
        return self._post(f"/iam/api-keys/{key_id}/revoke", json={"reason": reason, "actor_id": actor_id})

    def iam_rotate_api_key(self, key_id, reason="rotation"):
        return self._post(f"/iam/api-keys/{key_id}/rotate", json={"reason": reason})

    def iam_create_service_account(self, org_id, name, description="", scopes=None, expires_in_days=None, created_by="", max_usage=None):
        return self._post(f"/iam/organizations/{org_id}/service-accounts", json={"name": name, "description": description, "scopes": scopes, "expires_in_days": expires_in_days, "created_by": created_by, "max_usage": max_usage})

    def iam_list_service_accounts(self, org_id):
        return self._get(f"/iam/organizations/{org_id}/service-accounts")

    def iam_rotate_service_account(self, sa_id, reason="rotation"):
        return self._post(f"/iam/service-accounts/{sa_id}/rotate", json={"reason": reason})

    def iam_disable_service_account(self, sa_id):
        return self._post(f"/iam/service-accounts/{sa_id}/disable")

    def iam_list_identity_providers(self, org_id):
        return self._get(f"/iam/organizations/{org_id}/identity-providers")

    def iam_create_identity_provider(self, org_id, name, protocol, issuer="", client_id="", client_secret="", metadata_url="", certificate="", attribute_mapping=None, group_mapping=None):
        return self._post(f"/iam/organizations/{org_id}/identity-providers", json={"name": name, "protocol": protocol, "issuer": issuer, "client_id": client_id, "client_secret": client_secret, "metadata_url": metadata_url, "certificate": certificate, "attribute_mapping": attribute_mapping, "group_mapping": group_mapping})

    def iam_validate_identity_provider(self, idp_id):
        return self._post(f"/iam/identity-providers/{idp_id}/validate")

    def iam_list_scim_directories(self, org_id):
        return self._get(f"/iam/organizations/{org_id}/scim/directories")

    def iam_create_scim_directory(self, org_id, name, provider, config=None):
        return self._post(f"/iam/organizations/{org_id}/scim/directories", json={"name": name, "provider": provider, "config": config})

    def iam_sync_scim_directory(self, dir_id):
        return self._post(f"/iam/scim/directories/{dir_id}/sync")

    def iam_request_break_glass(self, org_id, user_id, reason, scope=None, resource_id="", resource_type="", duration_hours=1, mfa_verified=False, approved_by=""):
        return self._post(f"/iam/organizations/{org_id}/break-glass", json={"user_id": user_id, "reason": reason, "scope": scope or [], "resource_id": resource_id, "resource_type": resource_type, "duration_hours": duration_hours, "mfa_verified": mfa_verified, "approved_by": approved_by})

    def iam_list_break_glass_sessions(self, org_id):
        return self._get(f"/iam/organizations/{org_id}/break-glass")

    def iam_end_break_glass(self, session_id, reason="voluntary"):
        return self._post(f"/iam/break-glass/{session_id}/end", json={"reason": reason})

    def iam_list_quotas(self, org_id):
        return self._get(f"/iam/organizations/{org_id}/quotas")

    def iam_update_quota(self, org_id, quota_type, limit, period="monthly"):
        return self._put(f"/iam/organizations/{org_id}/quotas", json={"quota_type": quota_type, "limit": limit, "period": period})

    def iam_get_quota_summary(self, org_id):
        return self._get(f"/iam/organizations/{org_id}/quotas/summary")

    def iam_check_quota(self, org_id, quota_type, amount=1):
        return self._post(f"/iam/organizations/{org_id}/quotas/check", json={"quota_type": quota_type, "amount": amount})

    def iam_query_audit_logs(self, org_id, action=None, resource_type=None, user_id=None, limit=100, offset=0):
        params = {"limit": limit, "offset": offset}
        if action:
            params["action"] = action
        if resource_type:
            params["resource_type"] = resource_type
        if user_id:
            params["user_id"] = user_id
        return self._get(f"/iam/organizations/{org_id}/audit", params=params)

    def iam_get_audit_stats(self, org_id):
        return self._get(f"/iam/organizations/{org_id}/audit/stats")

    def iam_create_access_review(self, org_id, review_type="periodic", scope="all", initiated_by=""):
        return self._post(f"/iam/organizations/{org_id}/access-reviews", json={"review_type": review_type, "scope": scope, "initiated_by": initiated_by})

    def iam_list_access_reviews(self, org_id, status=None):
        params = {"status": status} if status else {}
        return self._get(f"/iam/organizations/{org_id}/access-reviews", params=params)

    def iam_complete_access_review(self, review_id, results=None, stale_items=None, actions_taken=None):
        return self._put(f"/iam/access-reviews/{review_id}/complete", json={"results": results or {}, "stale_items": stale_items or [], "actions_taken": actions_taken or []})

    def iam_run_privilege_analysis(self, org_id):
        return self._post(f"/iam/organizations/{org_id}/privilege-analysis/run")

    def iam_list_privilege_analyses(self, org_id, limit=10):
        return self._get(f"/iam/organizations/{org_id}/privilege-analysis", params={"limit": limit})

    def iam_test_rbac(self, role, permission, denied_permissions=None, inherited_roles=None):
        return self._post("/iam/policy-test/rbac", json={"role": role, "permission": permission, "denied_permissions": denied_permissions, "inherited_roles": inherited_roles})

    def iam_test_abac(self, resource_type, action, context):
        return self._post("/iam/policy-test/abac", json={"resource_type": resource_type, "action": action, "context": context})

    def iam_batch_policy_test(self, tests):
        return self._post("/iam/policy-test/batch", json={"tests": tests})

    def iam_get_rate_limit_usage(self):
        return self._get("/iam/rate-limiter/stats")

    def iam_get_tenant_violations(self, tenant_id=None):
        params = {"tenant_id": tenant_id} if tenant_id else {}
        return self._get("/iam/tenant-isolation/violations", params=params)

    def iam_get_tenant_isolation_stats(self):
        return self._get("/iam/tenant-isolation/stats")

    def iam_list_notifications(self, user_id, unread_only=False):
        return self._get(f"/iam/notifications/{user_id}", params={"unread_only": unread_only})

    def iam_mark_notification_read(self, notification_id):
        return self._post(f"/iam/notifications/{notification_id}/read")


class AsyncIAMMixin:
    async def iam_list_organizations(self, state=None):
        params = {"state": state} if state else {}
        return await self._get("/iam/organizations", params=params)

    async def iam_create_organization(self, name, slug, owner_id="", description="", plan="free"):
        return await self._post("/iam/organizations", json={"name": name, "slug": slug, "owner_id": owner_id, "description": description, "plan": plan})

    async def iam_get_organization(self, org_id):
        return await self._get(f"/iam/organizations/{org_id}")

    async def iam_update_organization(self, org_id, **kwargs):
        return await self._put(f"/iam/organizations/{org_id}", json=kwargs)

    async def iam_delete_organization(self, org_id, reason=""):
        return await self._delete(f"/iam/organizations/{org_id}", params={"reason": reason})

    async def iam_suspend_organization(self, org_id, reason=""):
        return await self._post(f"/iam/organizations/{org_id}/suspend", json={"reason": reason})

    async def iam_list_members(self, org_id):
        return await self._get(f"/iam/organizations/{org_id}/members")

    async def iam_invite_member(self, org_id, email, role="viewer"):
        return await self._post(f"/iam/organizations/{org_id}/members/invite", json={"email": email, "role": role})

    async def iam_authorize(self, user_id, org_id, permission, resource_type="", resource_id="", context=None):
        return await self._post("/iam/authorize", json={"user_id": user_id, "org_id": org_id, "permission": permission, "resource_type": resource_type, "resource_id": resource_id, "context": context})

    async def iam_create_session(self, org_id, user_id, ip_address="", user_agent="", auth_method="password"):
        return await self._post(f"/iam/organizations/{org_id}/sessions", json={"user_id": user_id, "ip_address": ip_address, "user_agent": user_agent, "auth_method": auth_method})

    async def iam_revoke_session(self, session_id, reason="user_request"):
        return await self._post(f"/iam/sessions/{session_id}/revoke", json={"reason": reason})

    async def iam_create_api_key(self, org_id, user_id, name, scopes=None):
        return await self._post(f"/iam/organizations/{org_id}/api-keys", json={"user_id": user_id, "name": name, "scopes": scopes})

    async def iam_request_break_glass(self, org_id, user_id, reason, scope=None, duration_hours=1, mfa_verified=False):
        return await self._post(f"/iam/organizations/{org_id}/break-glass", json={"user_id": user_id, "reason": reason, "scope": scope or [], "duration_hours": duration_hours, "mfa_verified": mfa_verified})

    async def iam_test_rbac(self, role, permission):
        return await self._post("/iam/policy-test/rbac", json={"role": role, "permission": permission})
