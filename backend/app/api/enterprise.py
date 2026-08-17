"""Enterprise Integrations API — Volume 40.

Endpoints for integration registry, SSO (OIDC/SAML), SCIM provisioning,
source control, communication, project management, session management,
service accounts, group mapping, and health monitoring.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field
from typing import Optional, Any

from app.api.auth import _get_current_user

router = APIRouter(tags=["Enterprise Integrations"])


# ─── Request Models ────────────────────────────────────────────────────────

class IntegrationCreateRequest(BaseModel):
    name: str
    provider: str
    category: str = ""
    description: str = ""
    scopes_requested: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)


class ConnectionActivateRequest(BaseModel):
    access_token: str = ""
    refresh_token: str = ""
    scopes: list[str] = Field(default_factory=list)
    provider_user_id: str = ""
    provider_username: str = ""
    provider_email: str = ""
    expires_in_seconds: int = 0


class SSOCreateRequest(BaseModel):
    protocol: str
    provider_name: str
    is_enforced: bool = False
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_scopes: list[str] = Field(default_factory=lambda: ["openid", "email", "profile"])
    saml_entity_id: str = ""
    saml_sso_url: str = ""
    saml_certificate: str = ""
    saml_attribute_mapping: dict[str, str] = Field(default_factory=dict)
    default_role: str = "member"


class SCIMDirectoryRequest(BaseModel):
    provider: str
    base_url: str
    config: dict[str, Any] = Field(default_factory=dict)


class SCIMUserProvisionRequest(BaseModel):
    external_id: str
    username: str
    email: str = ""
    display_name: str = ""
    active: bool = True
    groups: list[str] = Field(default_factory=list)


class SCIMGroupProvisionRequest(BaseModel):
    external_id: str
    display_name: str
    members: list[str] = Field(default_factory=list)
    mapped_role: str = ""


class GroupMappingRequest(BaseModel):
    external_group_name: str
    mapped_role: str = ""
    mapped_workspace_ids: list[str] = Field(default_factory=list)
    mapped_project_ids: list[str] = Field(default_factory=list)
    mapped_policies: list[str] = Field(default_factory=list)


class ServiceAccountRequest(BaseModel):
    name: str
    description: str = ""
    scopes: list[str] = Field(default_factory=list)
    expires_in_days: int = 0


class WebhookValidateRequest(BaseModel):
    payload: str
    signature: str
    secret: str
    provider: str = "github"


# ─── Integration Registry Endpoints ───────────────────────────────────────

@router.post("/integrations", status_code=201)
async def create_integration(
    req: IntegrationCreateRequest,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.integration_service import IntegrationRegistryService
    svc = IntegrationRegistryService()
    org_id = getattr(current_user, "organization_id", "default")
    record = svc.create_integration(
        organization_id=org_id,
        name=req.name,
        provider=req.provider,
        category=req.category,
        description=req.description,
        owner_id=getattr(current_user, "id", ""),
        scopes_requested=req.scopes_requested,
        config=req.config,
    )
    return record.model_dump()


@router.get("/integrations")
async def list_integrations(
    provider: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.integration_service import IntegrationRegistryService
    svc = IntegrationRegistryService()
    org_id = getattr(current_user, "organization_id", "default")
    integrations = svc.list_integrations(organization_id=org_id, provider=provider, category=category)
    return {"integrations": [i.model_dump() for i in integrations], "total": len(integrations)}


@router.get("/integrations/{integration_id}")
async def get_integration(
    integration_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.integration_service import IntegrationRegistryService
    svc = IntegrationRegistryService()
    record = svc.get_integration(integration_id)
    if not record:
        raise HTTPException(status_code=404, detail="Integration not found")
    return record.model_dump()


@router.delete("/integrations/{integration_id}")
async def delete_integration(
    integration_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.integration_service import IntegrationRegistryService
    svc = IntegrationRegistryService()
    success = svc.delete_integration(integration_id)
    if not success:
        raise HTTPException(status_code=404, detail="Integration not found")
    return {"deleted": True, "integration_id": integration_id}


@router.get("/integrations/metrics/overview")
async def integration_metrics(
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.integration_service import IntegrationRegistryService
    svc = IntegrationRegistryService()
    org_id = getattr(current_user, "organization_id", "default")
    return svc.get_metrics(org_id)


# ─── Connection Endpoints ─────────────────────────────────────────────────

@router.post("/integrations/{integration_id}/connections", status_code=201)
async def create_connection(
    integration_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.integration_service import IntegrationRegistryService
    svc = IntegrationRegistryService()
    org_id = getattr(current_user, "organization_id", "default")
    integration = svc.get_integration(integration_id)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    conn = svc.create_connection(integration_id, org_id, integration.provider)
    if not conn:
        raise HTTPException(status_code=400, detail="Failed to create connection")
    return conn.model_dump()


@router.post("/integrations/connections/{connection_id}/activate")
async def activate_connection(
    connection_id: str,
    req: ConnectionActivateRequest,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.integration_service import IntegrationRegistryService
    svc = IntegrationRegistryService()
    conn = svc.activate_connection(
        connection_id,
        access_token=req.access_token,
        refresh_token=req.refresh_token,
        scopes=req.scopes,
        provider_user_id=req.provider_user_id,
        provider_username=req.provider_username,
        provider_email=req.provider_email,
        expires_in_seconds=req.expires_in_seconds,
    )
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    return conn.model_dump()


@router.get("/integrations/connections")
async def list_connections(
    integration_id: Optional[str] = Query(None),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.integration_service import IntegrationRegistryService
    svc = IntegrationRegistryService()
    org_id = getattr(current_user, "organization_id", "default")
    conns = svc.list_connections(integration_id=integration_id, organization_id=org_id)
    return {"connections": [c.model_dump() for c in conns], "total": len(conns)}


@router.post("/integrations/connections/{connection_id}/revoke")
async def revoke_connection(
    connection_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.integration_service import IntegrationRegistryService
    svc = IntegrationRegistryService()
    conn = svc.revoke_connection(connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    return conn.model_dump()


# ─── SSO Endpoints ────────────────────────────────────────────────────────

@router.post("/sso", status_code=201)
async def create_sso_connection(
    req: SSOCreateRequest,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.sso_service import SSOService
    svc = SSOService()
    org_id = getattr(current_user, "organization_id", "default")
    conn = svc.create_sso_connection(
        organization_id=org_id,
        protocol=req.protocol,
        provider_name=req.provider_name,
        is_enforced=req.is_enforced,
        oidc_issuer=req.oidc_issuer,
        oidc_client_id=req.oidc_client_id,
        oidc_scopes=req.oidc_scopes,
        saml_entity_id=req.saml_entity_id,
        saml_sso_url=req.saml_sso_url,
        default_role=req.default_role,
    )
    return conn.model_dump()


@router.get("/sso")
async def list_sso_connections(
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.sso_service import SSOService
    svc = SSOService()
    org_id = getattr(current_user, "organization_id", "default")
    conns = svc.list_sso_connections(org_id)
    return {"connections": [c.model_dump() for c in conns], "total": len(conns)}


@router.get("/sso/{connection_id}")
async def get_sso_connection(
    connection_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.sso_service import SSOService
    svc = SSOService()
    conn = svc.get_sso_connection(connection_id)
    if not conn:
        raise HTTPException(status_code=404, detail="SSO connection not found")
    return conn.model_dump()


@router.post("/sso/{connection_id}/enforce")
async def enforce_sso(
    connection_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.sso_service import SSOService
    svc = SSOService()
    conn = svc.update_sso_connection(connection_id, is_enforced=True)
    if not conn:
        raise HTTPException(status_code=404, detail="SSO connection not found")
    return {"enforced": True, "connection_id": connection_id}


@router.get("/sso/oidc/authorize")
async def oidc_authorize(
    connection_id: str = Query(...),
    redirect_uri: str = Query(...),
    state: str = Query(...),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.sso_service import SSOService
    svc = SSOService()
    url = svc.build_oidc_authorization_url(connection_id, redirect_uri, state)
    if not url:
        raise HTTPException(status_code=400, detail="Invalid OIDC connection")
    return {"authorization_url": url}


@router.post("/sso/saml/validate")
async def validate_saml_assertion(
    connection_id: str = Body(...),
    assertion_data: dict[str, Any] = Body(...),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.sso_service import SSOService
    svc = SSOService()
    result = svc.process_saml_assertion(connection_id, assertion_data)
    if not result:
        raise HTTPException(status_code=400, detail="Invalid SAML assertion")
    return result


# ─── Session Management Endpoints ─────────────────────────────────────────

@router.get("/sessions")
async def list_sessions(
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.sso_service import SSOService
    svc = SSOService()
    user_id = getattr(current_user, "id", "default")
    sessions = svc.list_sessions(user_id=user_id)
    return {"sessions": [s.model_dump() for s in sessions], "total": len(sessions)}


@router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.sso_service import SSOService
    svc = SSOService()
    session = svc.revoke_session(session_id, reason="user_revoke")
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"revoked": True, "session_id": session_id}


@router.delete("/sessions")
async def revoke_all_sessions(
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.sso_service import SSOService
    svc = SSOService()
    user_id = getattr(current_user, "id", "default")
    count = svc.revoke_all_user_sessions(user_id)
    return {"revoked_count": count}


@router.get("/sessions/suspicious")
async def detect_suspicious(
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.sso_service import SSOService
    svc = SSOService()
    user_id = getattr(current_user, "id", "default")
    suspicious = svc.detect_suspicious_sessions(user_id)
    return {"suspicious": [s.model_dump() for s in suspicious], "count": len(suspicious)}


# ─── Service Account Endpoints ────────────────────────────────────────────

@router.post("/service-accounts", status_code=201)
async def create_service_account(
    req: ServiceAccountRequest,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.sso_service import SSOService
    svc = SSOService()
    org_id = getattr(current_user, "organization_id", "default")
    sa = svc.create_service_account(
        organization_id=org_id,
        name=req.name,
        description=req.description,
        owner_id=getattr(current_user, "id", ""),
        scopes=req.scopes,
    )
    return sa.model_dump()


@router.get("/service-accounts")
async def list_service_accounts(
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.sso_service import SSOService
    svc = SSOService()
    org_id = getattr(current_user, "organization_id", "default")
    accounts = svc.list_service_accounts(org_id)
    return {"service_accounts": [a.model_dump() for a in accounts], "total": len(accounts)}


@router.post("/service-accounts/{sa_id}/rotate")
async def rotate_service_account(
    sa_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.sso_service import SSOService
    svc = SSOService()
    result = svc.rotate_service_account(sa_id)
    if not result:
        raise HTTPException(status_code=404, detail="Service account not found or inactive")
    return result


@router.post("/service-accounts/{sa_id}/revoke")
async def revoke_service_account(
    sa_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.sso_service import SSOService
    svc = SSOService()
    sa = svc.revoke_service_account(sa_id)
    if not sa:
        raise HTTPException(status_code=404, detail="Service account not found")
    return {"revoked": True, "service_account_id": sa_id}


# ─── Group Mapping Endpoints ──────────────────────────────────────────────

@router.post("/group-mappings", status_code=201)
async def create_group_mapping(
    req: GroupMappingRequest,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.sso_service import SSOService
    svc = SSOService()
    org_id = getattr(current_user, "organization_id", "default")
    mapping = svc.create_group_mapping(
        organization_id=org_id,
        external_group_name=req.external_group_name,
        mapped_role=req.mapped_role,
        mapped_workspace_ids=req.mapped_workspace_ids,
        mapped_project_ids=req.mapped_project_ids,
        mapped_policies=req.mapped_policies,
    )
    return mapping.model_dump()


@router.get("/group-mappings")
async def list_group_mappings(
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.sso_service import SSOService
    svc = SSOService()
    org_id = getattr(current_user, "organization_id", "default")
    mappings = svc.list_group_mappings(org_id)
    return {"mappings": [m.model_dump() for m in mappings], "total": len(mappings)}


@router.post("/group-mappings/resolve")
async def resolve_group_roles(
    groups: list[str] = Body(...),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.sso_service import SSOService
    svc = SSOService()
    org_id = getattr(current_user, "organization_id", "default")
    return svc.resolve_group_roles(org_id, groups)


@router.delete("/group-mappings/{mapping_id}")
async def delete_group_mapping(
    mapping_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.sso_service import SSOService
    svc = SSOService()
    success = svc.delete_group_mapping(mapping_id)
    if not success:
        raise HTTPException(status_code=404, detail="Mapping not found")
    return {"deleted": True, "mapping_id": mapping_id}


# ─── SCIM Endpoints ───────────────────────────────────────────────────────

@router.post("/scim/directories", status_code=201)
async def create_scim_directory(
    req: SCIMDirectoryRequest,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.scim_service import SCIMService
    svc = SCIMService()
    org_id = getattr(current_user, "organization_id", "default")
    d = svc.create_directory(org_id, req.provider, req.base_url, req.config)
    return d.model_dump()


@router.get("/scim/directories")
async def list_scim_directories(
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.scim_service import SCIMService
    svc = SCIMService()
    org_id = getattr(current_user, "organization_id", "default")
    dirs = svc.list_directories(org_id)
    return {"directories": [d.model_dump() for d in dirs], "total": len(dirs)}


@router.post("/scim/directories/{directory_id}/users", status_code=201)
async def provision_scim_user(
    directory_id: str,
    req: SCIMUserProvisionRequest,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.scim_service import SCIMService
    svc = SCIMService()
    d = svc.get_directory(directory_id)
    if not d:
        raise HTTPException(status_code=404, detail="Directory not found")
    user = svc.provision_user(
        directory_id=directory_id,
        organization_id=d.organization_id,
        external_id=req.external_id,
        username=req.username,
        email=req.email,
        display_name=req.display_name,
        active=req.active,
        groups=req.groups,
    )
    return user.model_dump()


@router.get("/scim/directories/{directory_id}/users")
async def list_scim_users(
    directory_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.scim_service import SCIMService
    svc = SCIMService()
    users = svc.list_users(directory_id=directory_id)
    return {"users": [u.model_dump() for u in users], "total": len(users)}


@router.post("/scim/directories/{directory_id}/groups", status_code=201)
async def provision_scim_group(
    directory_id: str,
    req: SCIMGroupProvisionRequest,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.scim_service import SCIMService
    svc = SCIMService()
    d = svc.get_directory(directory_id)
    if not d:
        raise HTTPException(status_code=404, detail="Directory not found")
    group = svc.provision_group(
        directory_id=directory_id,
        organization_id=d.organization_id,
        external_id=req.external_id,
        display_name=req.display_name,
        members=req.members,
        mapped_role=req.mapped_role,
    )
    return group.model_dump()


@router.get("/scim/directories/{directory_id}/groups")
async def list_scim_groups(
    directory_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.scim_service import SCIMService
    svc = SCIMService()
    groups = svc.list_groups(directory_id=directory_id)
    return {"groups": [g.model_dump() for g in groups], "total": len(groups)}


@router.post("/scim/directories/{directory_id}/sync")
async def sync_scim_directory(
    directory_id: str,
    groups_data: list[dict[str, Any]] = Body(...),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.scim_service import SCIMService
    svc = SCIMService()
    result = svc.sync_groups_from_directory(directory_id, groups_data)
    return result.model_dump()


@router.post("/scim/users/{user_id}/deactivate")
async def deactivate_scim_user(
    user_id: str,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.scim_service import SCIMService
    svc = SCIMService()
    user = svc.deprovision_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"deactivated": True, "user_id": user_id}


# ─── Source Control Endpoints ─────────────────────────────────────────────

@router.get("/source-control/providers")
async def list_source_control_providers(
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.providers import SourceControlFactory
    return {"providers": SourceControlFactory.available_providers()}


@router.post("/source-control/{provider}/repositories")
async def list_sc_repositories(
    provider: str,
    organization: str = Body("", embed=True),
    access_token: str = Body("", embed=True),
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.providers import SourceControlFactory
    sc = SourceControlFactory.create(provider, access_token=access_token)
    if not sc:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")
    repos = sc.list_repositories(organization)
    return {"repositories": [r.model_dump() for r in repos], "total": len(repos)}


@router.post("/source-control/{provider}/webhook/validate")
async def validate_webhook(
    provider: str,
    req: WebhookValidateRequest,
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.providers import SourceControlFactory
    sc = SourceControlFactory.create(provider)
    if not sc:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")
    valid = sc.validate_webhook_signature(req.payload.encode(), req.signature, req.secret)
    return {"valid": valid, "provider": provider}


# ─── Communication Endpoints ──────────────────────────────────────────────

@router.get("/communication/providers")
async def list_communication_providers(
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.providers import CommunicationFactory
    return {"providers": CommunicationFactory.available_providers()}


# ─── Project Management Endpoints ─────────────────────────────────────────

@router.get("/project-management/providers")
async def list_pm_providers(
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.providers import ProjectManagementFactory
    return {"providers": ProjectManagementFactory.available_providers()}


# ─── Health & Sync Endpoints ──────────────────────────────────────────────

@router.get("/health")
async def enterprise_health(
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.integration_service import IntegrationRegistryService
    from app.enterprise.sso_service import SSOService
    from app.enterprise.scim_service import SCIMService
    return {
        "status": "healthy",
        "version": "40.0",
        "services": {
            "integration_registry": True,
            "sso": True,
            "scim": True,
            "source_control": True,
            "communication": True,
            "project_management": True,
        },
    }


@router.get("/health/integrations")
async def integration_health_summary(
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.integration_service import IntegrationRegistryService
    svc = IntegrationRegistryService()
    org_id = getattr(current_user, "organization_id", "default")
    return svc.get_metrics(org_id)


@router.get("/health/sso")
async def sso_health_summary(
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.sso_service import SSOService
    svc = SSOService()
    org_id = getattr(current_user, "organization_id", "default")
    return svc.get_metrics(org_id)


@router.get("/health/scim")
async def scim_health_summary(
    current_user: Any = Depends(_get_current_user),
) -> dict:
    from app.enterprise.scim_service import SCIMService
    svc = SCIMService()
    org_id = getattr(current_user, "organization_id", "default")
    return svc.get_metrics(org_id)
