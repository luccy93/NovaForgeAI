"""IAM API — organizations, workspaces, projects, members, teams, RBAC/ABAC,
sessions, API keys, service accounts, IdPs, SCIM, break-glass, quotas,
domain verification, audit, access reviews, privilege analysis, policy testing,
rate limiting, tenant isolation and notifications."""

from typing import Optional

from fastapi import APIRouter

router = APIRouter()


# ---------------------------------------------------------------------------
# Organizations (8)
# ---------------------------------------------------------------------------


@router.get("/organizations")
async def list_organizations(state: Optional[str] = None):
    import asyncio
    from app.iam.organization_service import org_service

    return await asyncio.to_thread(org_service.list_all, state=state)


@router.post("/organizations")
async def create_organization(data: dict):
    import asyncio
    from app.iam.organization_service import org_service
    from app.iam.membership_service import membership_service
    from app.iam.audit_service import audit_service
    from app.iam.quota_service import quota_service

    def _create():
        org = org_service.create(
            name=data["name"],
            slug=data["slug"],
            owner_id=data.get("owner_id", ""),
            description=data.get("description", ""),
            plan=data.get("plan", "free"),
            settings=data.get("settings"),
        )
        membership_service.add_member(org["id"], data.get("owner_id", ""), role="owner")
        quota_service.initialize_org_quotas(org["id"])
        audit_service.log_org_create(org["id"], data.get("owner_id", ""), org["name"])
        return org

    return await asyncio.to_thread(_create)


@router.get("/organizations/{org_id}")
async def get_organization(org_id: str):
    import asyncio
    from app.iam.organization_service import org_service

    org = await asyncio.to_thread(org_service.get, org_id)
    if not org:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Organization not found")
    return org


@router.put("/organizations/{org_id}")
async def update_organization(org_id: str, updates: dict):
    import asyncio
    from app.iam.organization_service import org_service
    from app.iam.audit_service import audit_service

    def _update():
        org = org_service.update(org_id, updates)
        if org:
            audit_service.log(
                org_id, updates.pop("actor_id", "system"), "user",
                "organization.updated", resource_type="organization", resource_id=org_id,
                details={"fields": sorted(updates.keys())},
            )
        return org

    org = await asyncio.to_thread(_update)
    if not org:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Organization not found")
    return org


@router.delete("/organizations/{org_id}")
async def delete_organization(org_id: str):
    import asyncio
    from app.iam.organization_service import org_service
    from app.iam.session_service import session_service
    from app.iam.audit_service import audit_service

    def _delete():
        deleted = org_service.delete(org_id)
        if deleted:
            session_service.revoke_all_for_org(org_id, reason="org_deleted")
            audit_service.log_org_delete(org_id, "system")
        return deleted

    deleted = await asyncio.to_thread(_delete)
    if not deleted:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Organization not found")
    return {"deleted": True}


@router.post("/organizations/{org_id}/suspend")
async def suspend_organization(org_id: str, data: Optional[dict] = None):
    import asyncio
    from app.iam.organization_service import org_service
    from app.iam.session_service import session_service
    from app.iam.audit_service import audit_service

    reason = (data or {}).get("reason", "")

    def _suspend():
        suspended = org_service.suspend(org_id, reason=reason)
        if suspended:
            session_service.revoke_all_for_org(org_id, reason="org_suspended")
            audit_service.log_org_suspend(org_id, "system", reason)
        return suspended

    suspended = await asyncio.to_thread(_suspend)
    if not suspended:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Organization not found or already suspended")
    return {"suspended": True}


@router.post("/organizations/{org_id}/reactivate")
async def reactivate_organization(org_id: str):
    import asyncio
    from app.iam.organization_service import org_service
    from app.iam.audit_service import audit_service

    def _reactivate():
        reactivated = org_service.reactivate(org_id)
        if reactivated:
            audit_service.log(org_id, "system", "system", "organization.reactivated")
        return reactivated

    reactivated = await asyncio.to_thread(_reactivate)
    if not reactivated:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Organization not found or not suspended")
    return {"reactivated": True}


@router.get("/organizations/{org_id}/stats")
async def get_organization_stats(org_id: str):
    import asyncio
    from app.iam.organization_service import org_service

    stats = await asyncio.to_thread(org_service.get_stats, org_id)
    if stats is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Organization not found")
    return stats


# ---------------------------------------------------------------------------
# Workspaces (5)
# ---------------------------------------------------------------------------


@router.get("/workspaces")
async def list_workspaces(org_id: str):
    import asyncio
    from app.iam.workspace_service import workspace_service

    return await asyncio.to_thread(workspace_service.list_for_org, org_id)


@router.post("/workspaces")
async def create_workspace(data: dict):
    import asyncio
    from app.iam.workspace_service import workspace_service
    from app.iam.audit_service import audit_service

    def _create():
        ws = workspace_service.create(
            org_id=data["org_id"],
            name=data["name"],
            slug=data["slug"],
            created_by=data.get("created_by", ""),
            description=data.get("description", ""),
            settings=data.get("settings"),
        )
        audit_service.log(data["org_id"], data.get("created_by", ""), "user", "workspace.created",
                          resource_type="workspace", resource_id=ws["id"], details={"name": ws["name"]})
        return ws

    return await asyncio.to_thread(_create)


@router.get("/workspaces/{workspace_id}")
async def get_workspace(workspace_id: str):
    import asyncio
    from app.iam.workspace_service import workspace_service

    ws = await asyncio.to_thread(workspace_service.get, workspace_id)
    if not ws:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Workspace not found")
    return ws


@router.put("/workspaces/{workspace_id}")
async def update_workspace(workspace_id: str, updates: dict):
    import asyncio
    from app.iam.workspace_service import workspace_service

    ws = await asyncio.to_thread(workspace_service.update, workspace_id, updates)
    if not ws:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Workspace not found")
    return ws


@router.delete("/workspaces/{workspace_id}")
async def delete_workspace(workspace_id: str):
    import asyncio
    from app.iam.workspace_service import workspace_service

    deleted = await asyncio.to_thread(workspace_service.delete, workspace_id)
    if not deleted:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Workspace not found")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Projects (5)
# ---------------------------------------------------------------------------


@router.get("/projects")
async def list_projects(workspace_id: str):
    import asyncio
    from app.iam.project_service import project_service

    return await asyncio.to_thread(project_service.list_for_workspace, workspace_id)


@router.post("/projects")
async def create_project(data: dict):
    import asyncio
    from app.iam.project_service import project_service
    from app.iam.audit_service import audit_service

    def _create():
        project = project_service.create(
            org_id=data["org_id"],
            workspace_id=data["workspace_id"],
            name=data["name"],
            slug=data["slug"],
            created_by=data.get("created_by", ""),
            description=data.get("description", ""),
            settings=data.get("settings"),
        )
        audit_service.log(data["org_id"], data.get("created_by", ""), "user", "project.created",
                          resource_type="project", resource_id=project["id"], details={"name": project["name"]})
        return project

    return await asyncio.to_thread(_create)


@router.get("/projects/{project_id}")
async def get_project(project_id: str):
    import asyncio
    from app.iam.project_service import project_service

    project = await asyncio.to_thread(project_service.get, project_id)
    if not project:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.put("/projects/{project_id}")
async def update_project(project_id: str, updates: dict):
    import asyncio
    from app.iam.project_service import project_service

    project = await asyncio.to_thread(project_service.update, project_id, updates)
    if not project:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    import asyncio
    from app.iam.project_service import project_service

    deleted = await asyncio.to_thread(project_service.delete, project_id)
    if not deleted:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Project not found")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Members (7)
# ---------------------------------------------------------------------------


@router.get("/organizations/{org_id}/members")
async def list_members(org_id: str, active_only: bool = True):
    import asyncio
    from app.iam.membership_service import membership_service

    return await asyncio.to_thread(membership_service.list_members, org_id, active_only=active_only)


@router.post("/organizations/{org_id}/members/invite")
async def invite_member(org_id: str, data: dict):
    import asyncio
    from app.iam.membership_service import membership_service
    from app.iam.notification_service import notification_service
    from app.iam.audit_service import audit_service

    def _invite():
        invitation = membership_service.invite(
            org_id,
            email=data["email"],
            role=data.get("role", "viewer"),
            invited_by=data.get("invited_by", ""),
            team_ids=data.get("team_ids"),
            message=data.get("message", ""),
        )
        audit_service.log_member_add(org_id, data.get("invited_by", ""), data["email"], data.get("role", "viewer"))
        return invitation

    return await asyncio.to_thread(_invite)


@router.post("/organizations/{org_id}/members/accept")
async def accept_invitation(org_id: str, data: dict):
    import asyncio
    from app.iam.membership_service import membership_service
    from app.iam.notification_service import notification_service

    def _accept():
        result = membership_service.accept_invitation(data["invitation_id"], data["user_id"])
        notification_service.send_member_added(org_id, data["user_id"], result.get("role", "viewer"))
        return result

    return await asyncio.to_thread(_accept)


@router.put("/organizations/{org_id}/members/{user_id}/role")
async def update_member_role(org_id: str, user_id: str, data: dict):
    import asyncio
    from fastapi import HTTPException
    from app.iam.membership_service import membership_service
    from app.iam.notification_service import notification_service
    from app.iam.audit_service import audit_service

    def _update():
        old_role = membership_service.get_user_role(org_id, user_id)
        updated = membership_service.update_role(
            org_id, user_id, data["new_role"], reason=data.get("reason", "")
        )
        if updated:
            notification_service.send_role_changed(org_id, user_id, old_role or "", data["new_role"])
            audit_service.log_role_change(
                org_id, data.get("actor_id", "system"), user_id, old_role or "", data["new_role"],
                data.get("reason", ""),
            )
        return updated

    updated = await asyncio.to_thread(_update)
    if not updated:
        raise HTTPException(status_code=404, detail="Membership not found")
    return updated


@router.delete("/organizations/{org_id}/members/{user_id}")
async def remove_member(org_id: str, user_id: str, data: Optional[dict] = None):
    import asyncio
    from fastapi import HTTPException
    from app.iam.membership_service import membership_service
    from app.iam.session_service import session_service
    from app.iam.api_key_service import api_key_service
    from app.iam.notification_service import notification_service
    from app.iam.audit_service import audit_service

    reason = (data or {}).get("reason", "")

    def _remove():
        removed = membership_service.remove_member(org_id, user_id, reason=reason)
        if removed:
            session_service.revoke_all_for_user(user_id, reason="removed_from_org")
            api_key_service.revoke_all_for_user(user_id, reason="removed_from_org")
            notification_service.send_member_removed(org_id, user_id)
            audit_service.log_member_remove(org_id, (data or {}).get("actor_id", "system"), user_id, reason)
        return removed

    removed = await asyncio.to_thread(_remove)
    if not removed:
        raise HTTPException(status_code=404, detail="Member not found")
    return {"removed": True}


@router.post("/organizations/{org_id}/members/{user_id}/suspend")
async def suspend_member(org_id: str, user_id: str, data: Optional[dict] = None):
    import asyncio
    from fastapi import HTTPException
    from app.iam.membership_service import membership_service
    from app.iam.session_service import session_service

    reason = (data or {}).get("reason", "")

    def _suspend():
        suspended = membership_service.suspend_member(org_id, user_id, reason=reason)
        if suspended:
            session_service.terminate_on_suspension(user_id)
        return suspended

    suspended = await asyncio.to_thread(_suspend)
    if not suspended:
        raise HTTPException(status_code=404, detail="Member not found")
    return {"suspended": True}


@router.get("/organizations/{org_id}/members/stats")
async def member_stats(org_id: str):
    import asyncio
    from app.iam.membership_service import membership_service

    return await asyncio.to_thread(membership_service.get_stats, org_id)


# ---------------------------------------------------------------------------
# Teams (6)
# ---------------------------------------------------------------------------


@router.get("/teams")
async def list_teams(org_id: str):
    import asyncio
    from app.iam.team_service import team_service

    return await asyncio.to_thread(team_service.list_for_org, org_id)


@router.post("/teams")
async def create_team(data: dict):
    import asyncio
    from app.iam.team_service import team_service
    from app.iam.audit_service import audit_service

    def _create():
        team = team_service.create(
            org_id=data["org_id"],
            name=data["name"],
            description=data.get("description", ""),
            parent_team_id=data.get("parent_team_id"),
        )
        audit_service.log(data["org_id"], data.get("created_by", "system"), "user", "team.created",
                          resource_type="team", resource_id=team["id"], details={"name": team["name"]})
        return team

    return await asyncio.to_thread(_create)


@router.put("/teams/{team_id}")
async def update_team(team_id: str, updates: dict):
    import asyncio
    from app.iam.team_service import team_service

    team = await asyncio.to_thread(team_service.update, team_id, updates)
    if not team:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Team not found")
    return team


@router.delete("/teams/{team_id}")
async def delete_team(team_id: str):
    import asyncio
    from app.iam.team_service import team_service

    deleted = await asyncio.to_thread(team_service.delete, team_id)
    if not deleted:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Team not found")
    return {"deleted": True}


@router.post("/teams/{team_id}/members")
async def add_team_member(team_id: str, data: dict):
    import asyncio
    from app.iam.team_service import team_service

    return await asyncio.to_thread(
        team_service.add_member, team_id, data["user_id"], role=data.get("role", "member")
    )


@router.delete("/teams/{team_id}/members/{user_id}")
async def remove_team_member(team_id: str, user_id: str):
    import asyncio
    from app.iam.team_service import team_service

    removed = await asyncio.to_thread(team_service.remove_member, team_id, user_id)
    if not removed:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Team member not found")
    return {"removed": True}


# ---------------------------------------------------------------------------
# Roles (4)
# ---------------------------------------------------------------------------


@router.get("/roles")
async def list_roles(org_id: Optional[str] = None):
    import asyncio
    from app.iam.rbac_engine import rbac_engine

    return await asyncio.to_thread(rbac_engine.list_roles, org_id)


@router.post("/roles")
async def create_role(data: dict):
    import asyncio
    from app.iam.rbac_engine import rbac_engine
    from app.iam.audit_service import audit_service

    def _create():
        role = rbac_engine.create_custom_role(
            org_id=data["org_id"],
            name=data["name"],
            permissions=data["permissions"],
            inherits_from=data.get("inherits_from"),
            description=data.get("description", ""),
            is_system=data.get("is_system", False),
        )
        audit_service.log_policy_change(
            data["org_id"], data.get("actor_id", "system"), role["id"],
            "role.created", details={"name": role["name"]},
        )
        return role

    return await asyncio.to_thread(_create)


@router.put("/roles/{role_id}")
async def update_role(role_id: str, updates: dict):
    import asyncio
    from app.iam.rbac_engine import rbac_engine

    role = await asyncio.to_thread(rbac_engine.update_custom_role, role_id, updates)
    if not role:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Role not found")
    return role


@router.delete("/roles/{role_id}")
async def delete_role(role_id: str):
    import asyncio
    from app.iam.rbac_engine import rbac_engine

    deleted = await asyncio.to_thread(rbac_engine.delete_custom_role, role_id)
    if not deleted:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Role not found")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Resource Policies (4)
# ---------------------------------------------------------------------------


@router.post("/policies/resource")
async def create_resource_policy(data: dict):
    import asyncio
    from app.iam.policy_authorizer import policy_authorizer
    from app.iam.audit_service import audit_service

    def _create():
        policy = policy_authorizer.create_resource_policy(
            org_id=data["org_id"],
            name=data["name"],
            effect=data.get("effect", "allow"),
            resource_scope=data.get("resource_scope", "organization"),
            conditions=data.get("conditions"),
            principals=data.get("principals"),
            actions=data.get("actions"),
            priority=data.get("priority", 0),
            description=data.get("description", ""),
        )
        audit_service.log_policy_change(
            data["org_id"], data.get("actor_id", "system"), policy["id"], "policy.created"
        )
        return policy

    return await asyncio.to_thread(_create)


@router.get("/policies/resource")
async def list_resource_policies(org_id: str, resource_scope: Optional[str] = None):
    import asyncio
    from app.iam.policy_authorizer import policy_authorizer

    return await asyncio.to_thread(
        policy_authorizer.list_resource_policies, org_id, resource_scope=resource_scope
    )


@router.put("/policies/resource/{policy_id}")
async def update_resource_policy(policy_id: str, updates: dict):
    import asyncio
    from app.iam.policy_authorizer import policy_authorizer

    policy = await asyncio.to_thread(policy_authorizer.update_resource_policy, policy_id, updates)
    if not policy:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Resource policy not found")
    return policy


@router.delete("/policies/resource/{policy_id}")
async def delete_resource_policy(policy_id: str):
    import asyncio
    from app.iam.policy_authorizer import policy_authorizer

    deleted = await asyncio.to_thread(policy_authorizer.delete_resource_policy, policy_id)
    if not deleted:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Resource policy not found")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Authorization (2)
# ---------------------------------------------------------------------------


@router.post("/authorization/authorize")
async def authorize(data: dict):
    import asyncio
    from app.iam.policy_authorizer import policy_authorizer
    from app.iam.resource_authorizer import resource_authorizer

    context = data.get("context")

    def _authorize():
        decision = policy_authorizer.authorize(
            user_id=data["user_id"],
            org_id=data["org_id"],
            permission=data["permission"],
            resource_type=data.get("resource_type", ""),
            resource_id=data.get("resource_id", ""),
            context=context,
        )
        if decision.get("allowed") and data.get("resource_id"):
            resource_decision = resource_authorizer.check_resource_access(
                user_id=data["user_id"],
                resource_id=data["resource_id"],
                resource_type=data.get("resource_type", ""),
                action=data["permission"],
                org_id=data["org_id"],
                context=context,
            )
            decision["resource_decision"] = resource_decision
            decision["allowed"] = resource_decision.get("allowed", False)
        return decision

    return await asyncio.to_thread(_authorize)


@router.post("/authorization/explain")
async def explain_authorization(data: dict):
    import asyncio
    from app.iam.policy_authorizer import policy_authorizer

    return await asyncio.to_thread(
        policy_authorizer.explain,
        data["user_id"],
        data["org_id"],
        data["permission"],
        context=data.get("context"),
    )


# ---------------------------------------------------------------------------
# Sessions (4)
# ---------------------------------------------------------------------------


@router.post("/sessions")
async def create_session(data: dict):
    import asyncio
    from app.iam.session_service import session_service
    from app.iam.audit_service import audit_service

    def _create():
        session = session_service.create(
            user_id=data["user_id"],
            organization_id=data.get("organization_id"),
            ip_address=data.get("ip_address", ""),
            user_agent=data.get("user_agent", ""),
            auth_method=data.get("auth_method", "password"),
            device_fingerprint=data.get("device_fingerprint", ""),
        )
        if data.get("organization_id"):
            audit_service.log_login(
                data["organization_id"], data["user_id"],
                method=data.get("auth_method", "password"),
                success=True, ip_address=data.get("ip_address", ""),
                user_agent=data.get("user_agent", ""), mfa_used=data.get("mfa_used", False),
            )
        return session

    return await asyncio.to_thread(_create)


@router.get("/sessions")
async def list_sessions(user_id: str, active_only: bool = True):
    import asyncio
    from app.iam.session_service import session_service

    return await asyncio.to_thread(session_service.list_for_user, user_id, active_only=active_only)


@router.post("/sessions/revoke")
async def revoke_session(data: dict):
    import asyncio
    from app.iam.session_service import session_service

    if data.get("session_id"):
        revoked = await asyncio.to_thread(
            session_service.revoke, data["session_id"], reason=data.get("reason", "user_request")
        )
    else:
        count = await asyncio.to_thread(
            session_service.revoke_all_for_user, data["user_id"], reason=data.get("reason", "global_revoke")
        )
        revoked = count > 0
    return {"revoked": revoked}


@router.post("/sessions/refresh")
async def refresh_session(data: dict):
    import asyncio
    from fastapi import HTTPException
    from app.iam.session_service import session_service

    session = await asyncio.to_thread(session_service.refresh, data["session_id"])
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    return session


# ---------------------------------------------------------------------------
# API Keys (4)
# ---------------------------------------------------------------------------


@router.post("/api-keys")
async def create_api_key(data: dict):
    import asyncio
    from app.iam.api_key_service import api_key_service
    from app.iam.audit_service import audit_service

    def _create():
        key = api_key_service.create(
            org_id=data["org_id"],
            user_id=data["user_id"],
            name=data["name"],
            scopes=data.get("scopes"),
            expires_in_days=data.get("expires_in_days"),
        )
        audit_service.log_api_key_create(data["org_id"], data["user_id"], data["name"], key["key_id"])
        return key

    return await asyncio.to_thread(_create)


@router.get("/api-keys")
async def list_api_keys(org_id: Optional[str] = None, user_id: Optional[str] = None):
    import asyncio
    from app.iam.api_key_service import api_key_service

    if user_id:
        return await asyncio.to_thread(api_key_service.list_for_user, user_id)
    if org_id:
        return await asyncio.to_thread(api_key_service.list_for_org, org_id)
    from fastapi import HTTPException

    raise HTTPException(status_code=400, detail="Provide org_id or user_id")


@router.post("/api-keys/{key_id}/revoke")
async def revoke_api_key(key_id: str, data: Optional[dict] = None):
    import asyncio
    from app.iam.api_key_service import api_key_service

    payload = data or {}
    revoked = await asyncio.to_thread(
        api_key_service.revoke, key_id, reason=payload.get("reason", "user_request")
    )
    if not revoked:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="API key not found")
    return {"revoked": True}


@router.post("/api-keys/{key_id}/rotate")
async def rotate_api_key(key_id: str, data: Optional[dict] = None):
    import asyncio
    from fastapi import HTTPException
    from app.iam.api_key_service import api_key_service

    payload = data or {}
    key = await asyncio.to_thread(api_key_service.rotate, key_id, reason=payload.get("reason", "rotation"))
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    return key


# ---------------------------------------------------------------------------
# Service Accounts (4)
# ---------------------------------------------------------------------------


@router.post("/service-accounts")
async def create_service_account(data: dict):
    import asyncio
    from app.iam.service_account_service import service_account_service
    from app.iam.audit_service import audit_service

    def _create():
        sa = service_account_service.create(
            org_id=data["org_id"],
            name=data["name"],
            description=data.get("description", ""),
            scopes=data.get("scopes"),
            expires_in_days=data.get("expires_in_days"),
            created_by=data.get("created_by", ""),
            max_usage=data.get("max_usage"),
        )
        audit_service.log_service_account_create(data["org_id"], data.get("created_by", "system"), data["name"], sa["sa_id"])
        return sa

    return await asyncio.to_thread(_create)


@router.get("/service-accounts")
async def list_service_accounts(org_id: str, active_only: bool = True):
    import asyncio
    from app.iam.service_account_service import service_account_service

    return await asyncio.to_thread(service_account_service.list_for_org, org_id, active_only=active_only)


@router.post("/service-accounts/{sa_id}/rotate")
async def rotate_service_account(sa_id: str, data: Optional[dict] = None):
    import asyncio
    from fastapi import HTTPException
    from app.iam.service_account_service import service_account_service

    payload = data or {}
    sa = await asyncio.to_thread(service_account_service.rotate, sa_id, reason=payload.get("reason", "rotation"))
    if not sa:
        raise HTTPException(status_code=404, detail="Service account not found")
    return sa


@router.post("/service-accounts/{sa_id}/disable")
async def disable_service_account(sa_id: str, data: Optional[dict] = None):
    import asyncio
    from fastapi import HTTPException
    from app.iam.service_account_service import service_account_service

    payload = data or {}
    disabled = await asyncio.to_thread(service_account_service.disable, sa_id, reason=payload.get("reason", "disabled"))
    if not disabled:
        raise HTTPException(status_code=404, detail="Service account not found")
    return {"disabled": True}


# ---------------------------------------------------------------------------
# Identity Providers (4)
# ---------------------------------------------------------------------------


@router.get("/identity-providers")
async def list_identity_providers(org_id: str):
    import asyncio
    from app.iam.identity_provider_service import identity_provider_service

    return await asyncio.to_thread(identity_provider_service.list_for_org, org_id)


@router.post("/identity-providers")
async def create_identity_provider(data: dict):
    import asyncio
    from app.iam.identity_provider_service import identity_provider_service

    provider = await asyncio.to_thread(
        identity_provider_service.create,
        data["org_id"],
        data["name"],
        data["protocol"],
        issuer=data.get("issuer", ""),
        client_id=data.get("client_id", ""),
        client_secret=data.get("client_secret", ""),
        metadata_url=data.get("metadata_url", ""),
        certificate=data.get("certificate", ""),
        attribute_mapping=data.get("attribute_mapping"),
        group_mapping=data.get("group_mapping"),
    )
    return provider


@router.post("/identity-providers/{provider_id}/validate")
async def validate_identity_provider(provider_id: str):
    import asyncio
    from fastapi import HTTPException
    from app.iam.identity_provider_service import identity_provider_service

    result = await asyncio.to_thread(identity_provider_service.validate_config, provider_id)
    if not result:
        raise HTTPException(status_code=404, detail="Identity provider not found")
    return result


@router.post("/identity-providers/{provider_id}/saml")
async def saml_assertion(provider_id: str, data: dict):
    import asyncio
    from fastapi import HTTPException
    from app.iam.identity_provider_service import identity_provider_service

    def _handle():
        result = identity_provider_service.validate_saml_assertion(provider_id, data)
        if result.get("valid") and data.get("user_id"):
            link = identity_provider_service.link_external_identity(
                provider_id,
                data["user_id"],
                data.get("external_id", data.get("name_id", "")),
                data.get("email", ""),
                display_name=data.get("display_name", ""),
                groups=data.get("groups"),
            )
            result["identity_link"] = link
        return result

    result = await asyncio.to_thread(_handle)
    if not result:
        raise HTTPException(status_code=404, detail="Identity provider not found")
    return result


# ---------------------------------------------------------------------------
# SCIM (5)
# ---------------------------------------------------------------------------


@router.get("/scim/directories")
async def list_scim_directories(org_id: str):
    import asyncio
    from app.iam.scim_service import scim_service

    return await asyncio.to_thread(scim_service.list_directories, org_id)


@router.post("/scim/directories")
async def create_scim_directory(data: dict):
    import asyncio
    from app.iam.scim_service import scim_service

    directory = await asyncio.to_thread(
        scim_service.create_directory,
        data["org_id"],
        data["name"],
        data["provider"],
        config=data.get("config"),
    )
    return directory


@router.post("/scim/directories/{dir_id}/sync")
async def sync_scim_directory(dir_id: str):
    import asyncio
    from app.iam.scim_service import scim_service

    return await asyncio.to_thread(scim_service.sync_directory, dir_id)


@router.post("/scim/users")
async def provision_scim_user(data: dict):
    import asyncio
    from app.iam.scim_service import scim_service

    user = await asyncio.to_thread(
        scim_service.provision_user,
        data["dir_id"],
        data["external_id"],
        data["email"],
        display_name=data.get("display_name", ""),
        groups=data.get("groups"),
        attributes=data.get("attributes"),
    )
    return user


@router.post("/scim/users/{user_id}/deactivate")
async def deactivate_scim_user(user_id: str):
    import asyncio
    from app.iam.scim_service import scim_service

    deactivated = await asyncio.to_thread(scim_service.deactivate_user, user_id)
    if not deactivated:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="SCIM user not found")
    return {"deactivated": True}


# ---------------------------------------------------------------------------
# Break-Glass (3)
# ---------------------------------------------------------------------------


@router.post("/break-glass")
async def request_break_glass(data: dict):
    import asyncio
    from app.iam.break_glass_service import break_glass_service
    from app.iam.audit_service import audit_service
    from app.iam.notification_service import notification_service

    def _request():
        session = break_glass_service.request(
            org_id=data["org_id"],
            user_id=data["user_id"],
            reason=data["reason"],
            scope=data.get("scope"),
            resource_id=data.get("resource_id", ""),
            resource_type=data.get("resource_type", ""),
            duration_hours=data.get("duration_hours", 1),
            mfa_verified=data.get("mfa_verified", False),
            approved_by=data.get("approved_by", ""),
        )
        audit_service.log_break_glass(data["org_id"], data["user_id"], data["reason"], data.get("scope", []), session["session_id"])
        notification_service.send_break_glass_activated(data["org_id"], data["user_id"], data["reason"])
        return session

    return await asyncio.to_thread(_request)


@router.get("/break-glass")
async def list_break_glass(org_id: Optional[str] = None):
    import asyncio
    from app.iam.break_glass_service import break_glass_service

    return await asyncio.to_thread(break_glass_service.list_active, org_id)


@router.post("/break-glass/{session_id}/end")
async def end_break_glass(session_id: str, data: Optional[dict] = None):
    import asyncio
    from fastapi import HTTPException
    from app.iam.break_glass_service import break_glass_service

    reason = (data or {}).get("reason", "voluntary")
    ended = await asyncio.to_thread(break_glass_service.end, session_id, reason=reason)
    if not ended:
        raise HTTPException(status_code=404, detail="Break-glass session not found or already ended")
    return {"ended": True}


# ---------------------------------------------------------------------------
# Quotas (4)
# ---------------------------------------------------------------------------


@router.get("/quotas")
async def list_quotas(org_id: str):
    import asyncio
    from app.iam.quota_service import quota_service

    return await asyncio.to_thread(quota_service.get_all_quotas, org_id)


@router.put("/quotas")
async def update_quota(data: dict):
    import asyncio
    from fastapi import HTTPException
    from app.iam.quota_service import quota_service

    quota = await asyncio.to_thread(
        quota_service.update_quota,
        data["org_id"],
        data["quota_type"],
        data["limit"],
        period=data.get("period", "monthly"),
    )
    if not quota:
        raise HTTPException(status_code=404, detail="Quota not found")
    return quota


@router.get("/quotas/summary")
async def quota_summary(org_id: str):
    import asyncio
    from app.iam.quota_service import quota_service

    return await asyncio.to_thread(quota_service.get_usage_summary, org_id)


@router.post("/quotas/check")
async def check_quota(data: dict):
    import asyncio
    from app.iam.quota_service import quota_service
    from app.iam.notification_service import notification_service

    def _check():
        result = quota_service.check_quota(
            data["org_id"], data["quota_type"], amount=data.get("amount", 1)
        )
        if not result.get("allowed"):
            notification_service.send_quota_exceeded(
                data["org_id"], data.get("user_id", ""), data["quota_type"], result.get("limit", 0)
            )
        return result

    return await asyncio.to_thread(_check)


# ---------------------------------------------------------------------------
# Domain Verification (3)
# ---------------------------------------------------------------------------


@router.get("/domains")
async def list_domains(org_id: str):
    import asyncio
    from app.iam.domain_verification_service import domain_verification_service

    return await asyncio.to_thread(domain_verification_service.list_for_org, org_id)


@router.post("/domains")
async def create_domain_verification(data: dict):
    import asyncio
    from app.iam.domain_verification_service import domain_verification_service

    verification = await asyncio.to_thread(
        domain_verification_service.create_verification,
        data["org_id"],
        data["domain"],
        method=data.get("method", "dns"),
    )
    return verification


@router.post("/domains/{verification_id}/verify")
async def verify_domain(verification_id: str, proof: str = ""):
    import asyncio
    from app.iam.domain_verification_service import domain_verification_service

    return await asyncio.to_thread(domain_verification_service.verify, verification_id, proof)


# ---------------------------------------------------------------------------
# Audit (2)
# ---------------------------------------------------------------------------


@router.get("/audit/logs")
async def query_audit_logs(
    org_id: Optional[str] = None,
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    import asyncio
    from app.iam.audit_service import audit_service

    return await asyncio.to_thread(
        audit_service.query,
        org_id=org_id,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )


@router.get("/audit/stats")
async def audit_stats(org_id: Optional[str] = None):
    import asyncio
    from app.iam.audit_service import audit_service

    return await asyncio.to_thread(audit_service.get_stats, org_id)


# ---------------------------------------------------------------------------
# Access Reviews (3)
# ---------------------------------------------------------------------------


@router.post("/access-reviews")
async def create_access_review(data: dict):
    import asyncio
    from app.iam.access_review_service import access_review_service
    from app.iam.notification_service import notification_service

    def _create():
        review = access_review_service.create_review(
            org_id=data["org_id"],
            review_type=data.get("review_type", "periodic"),
            scope=data.get("scope", "all"),
            initiated_by=data.get("initiated_by", ""),
        )
        notification_service.send_access_review_due(data["org_id"], data.get("initiated_by", ""), review.get("review_type", "periodic"))
        return review

    return await asyncio.to_thread(_create)


@router.get("/access-reviews")
async def list_access_reviews(org_id: Optional[str] = None, status: Optional[str] = None):
    import asyncio
    from app.iam.access_review_service import access_review_service

    return await asyncio.to_thread(access_review_service.list_reviews, org_id, status=status)


@router.put("/access-reviews/{review_id}/complete")
async def complete_access_review(review_id: str, data: dict):
    import asyncio
    from fastapi import HTTPException
    from app.iam.access_review_service import access_review_service

    review = await asyncio.to_thread(
        access_review_service.complete_review,
        review_id,
        results=data.get("results", {}),
        stale_items=data.get("stale_items"),
        actions_taken=data.get("actions_taken"),
    )
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return review


# ---------------------------------------------------------------------------
# Privilege Analysis (2)
# ---------------------------------------------------------------------------


@router.post("/privilege-analysis/run")
async def run_privilege_analysis(data: dict):
    import asyncio
    from app.iam.privilege_analysis_service import privilege_analysis_service
    from app.iam.membership_service import membership_service
    from app.iam.service_account_service import service_account_service
    from app.iam.api_key_service import api_key_service
    from app.iam.policy_authorizer import policy_authorizer
    from app.iam.notification_service import notification_service

    def _run():
        org_id = data["org_id"]
        memberships = membership_service.list_members(org_id, active_only=False)
        accounts = service_account_service.list_for_org(org_id, active_only=False)
        keys = api_key_service.list_for_org(org_id)
        policies = policy_authorizer.list_resource_policies(org_id)
        analysis = privilege_analysis_service.run_full_analysis(
            org_id,
            memberships,
            accounts,
            keys,
            policies,
            active_users=data.get("active_users"),
            activity_data=data.get("activity_data"),
        )
        findings_count = len(analysis.get("findings", []))
        notification_service.send_privilege_analysis_complete(org_id, data.get("initiated_by", ""), findings_count)
        return analysis

    return await asyncio.to_thread(_run)


@router.get("/privilege-analysis")
async def list_privilege_analyses(org_id: Optional[str] = None, limit: int = 10):
    import asyncio
    from app.iam.privilege_analysis_service import privilege_analysis_service

    return await asyncio.to_thread(privilege_analysis_service.get_analyses, org_id, limit=limit)


# ---------------------------------------------------------------------------
# Policy Testing (3)
# ---------------------------------------------------------------------------


@router.post("/policy-tests/rbac")
async def test_rbac(data: dict):
    import asyncio
    from app.iam.policy_tester import policy_tester

    return await asyncio.to_thread(
        policy_tester.test_rbac,
        data["role"],
        data["permission"],
        denied_permissions=data.get("denied_permissions"),
        inherited_roles=data.get("inherited_roles"),
    )


@router.post("/policy-tests/abac")
async def test_abac(data: dict):
    import asyncio
    from app.iam.policy_tester import policy_tester

    return await asyncio.to_thread(
        policy_tester.test_abac,
        data["resource_type"],
        data["action"],
        data["context"],
    )


@router.post("/policy-tests/batch")
async def batch_policy_test(data: dict):
    import asyncio
    from app.iam.policy_tester import policy_tester

    return await asyncio.to_thread(policy_tester.batch_test, data["tests"])


# ---------------------------------------------------------------------------
# Rate Limiting (1)
# ---------------------------------------------------------------------------


@router.get("/rate-limits/stats")
async def rate_limit_stats():
    import asyncio
    from app.iam.rate_limiter import rate_limiter

    return await asyncio.to_thread(rate_limiter.get_stats)


# ---------------------------------------------------------------------------
# Tenant Isolation (2)
# ---------------------------------------------------------------------------


@router.get("/tenant-isolation/violations")
async def isolation_violations(tenant_id: Optional[str] = None):
    import asyncio
    from app.iam.tenant_isolation import tenant_isolation

    return await asyncio.to_thread(tenant_isolation.get_isolation_violations, tenant_id)


@router.get("/tenant-isolation/stats")
async def isolation_stats():
    import asyncio
    from app.iam.tenant_isolation import tenant_isolation

    return await asyncio.to_thread(tenant_isolation.get_stats)


# ---------------------------------------------------------------------------
# Notifications (2)
# ---------------------------------------------------------------------------


@router.get("/notifications")
async def list_notifications(user_id: str, unread_only: bool = False):
    import asyncio
    from app.iam.notification_service import notification_service

    return await asyncio.to_thread(notification_service.list_for_user, user_id, unread_only=unread_only)


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str):
    import asyncio
    from app.iam.notification_service import notification_service

    marked = await asyncio.to_thread(notification_service.mark_read, notification_id)
    if not marked:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Notification not found")
    return {"marked": True}
