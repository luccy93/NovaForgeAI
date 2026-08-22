"""IAM Pydantic schemas."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from app.iam.constants import IAMRole, IAMPermission, DATA_CLASSIFICATIONS, ENVIRONMENTS, RESOURCE_SCOPES


class OrganizationCreate(BaseModel):
    name: str = Field(..., max_length=255)
    slug: str = Field(..., max_length=100)
    description: Optional[str] = None
    plan: str = "free"
    settings: Optional[dict] = None


class OrganizationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    plan: Optional[str] = None
    settings: Optional[dict] = None
    is_active: Optional[bool] = None


class WorkspaceCreate(BaseModel):
    name: str = Field(..., max_length=255)
    slug: str = Field(..., max_length=100)
    description: Optional[str] = None
    settings: Optional[dict] = None


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    settings: Optional[dict] = None
    is_active: Optional[bool] = None


class ProjectCreate(BaseModel):
    name: str = Field(..., max_length=255)
    slug: str = Field(..., max_length=100)
    description: Optional[str] = None
    workspace_id: Optional[str] = None
    settings: Optional[dict] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    settings: Optional[dict] = None
    is_archived: Optional[bool] = None


class MemberInvite(BaseModel):
    email: str
    role: IAMRole = IAMRole.VIEWER
    team_ids: Optional[list[str]] = None
    message: Optional[str] = None


class MemberRoleUpdate(BaseModel):
    role: IAMRole
    reason: Optional[str] = None


class MemberRemove(BaseModel):
    reason: Optional[str] = None
    transfer_to: Optional[str] = None


class TeamCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    parent_team_id: Optional[str] = None


class TeamUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    parent_team_id: Optional[str] = None


class TeamMemberAdd(BaseModel):
    user_id: str
    role: IAMRole = IAMRole.MEMBER


class RoleCreate(BaseModel):
    name: str = Field(..., max_length=100)
    description: Optional[str] = None
    permissions: list[IAMPermission] = []
    inherits_from: Optional[list[str]] = None
    is_system: bool = False


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    permissions: Optional[list[IAMPermission]] = None
    inherits_from: Optional[list[str]] = None


class PolicyCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    effect: str = "allow"
    conditions: list[dict] = []
    resource_scope: str = "organization"
    priority: int = 0
    tags: list[str] = []


class PolicyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    effect: Optional[str] = None
    conditions: Optional[list[dict]] = None
    resource_scope: Optional[str] = None
    priority: Optional[int] = None
    tags: Optional[list[str]] = None
    is_active: Optional[bool] = None


class PolicyTest(BaseModel):
    identity: dict = {}
    resource: dict = {}
    action: str = ""
    context: dict = {}


class ServiceAccountCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    scopes: list[IAMPermission] = []
    expires_in_days: Optional[int] = None
    max_usage: Optional[int] = None


class ServiceAccountRotate(BaseModel):
    reason: Optional[str] = None


class APIKeyCreate(BaseModel):
    name: str = Field(..., max_length=255)
    scopes: list[IAMPermission] = []
    expires_in_days: Optional[int] = None


class APIKeyRotate(BaseModel):
    reason: Optional[str] = None


class SessionCreate(BaseModel):
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class IdentityProviderCreate(BaseModel):
    name: str
    protocol: str
    issuer: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    metadata_url: Optional[str] = None
    certificate: Optional[str] = None
    attribute_mapping: Optional[dict] = None
    group_mapping: Optional[dict] = None


class IdentityProviderUpdate(BaseModel):
    name: Optional[str] = None
    issuer: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    metadata_url: Optional[str] = None
    certificate: Optional[str] = None
    attribute_mapping: Optional[dict] = None
    group_mapping: Optional[dict] = None
    is_active: Optional[bool] = None


class DomainVerification(BaseModel):
    domain: str
    method: str = "dns"


class BreakGlassRequest(BaseModel):
    reason: str
    scope: list[IAMPermission] = []
    resource_id: Optional[str] = None
    resource_type: Optional[str] = None
    duration_hours: int = 1


class AccessRequestCreate(BaseModel):
    permission: IAMPermission
    resource_id: Optional[str] = None
    resource_type: Optional[str] = None
    justification: Optional[str] = None
    expires_at: Optional[datetime] = None


class AccessRequestReview(BaseModel):
    approved: bool
    reason: Optional[str] = None


class QuotaUpdate(BaseModel):
    quota_type: str
    limit: int
    period: str = "monthly"


class ResourceAuthorization(BaseModel):
    resource_id: str
    resource_type: str
    action: str
    tenant_id: Optional[str] = None
    project_id: Optional[str] = None
    workspace_id: Optional[str] = None
    context: Optional[dict] = None


class AuthorizationDecision(BaseModel):
    allowed: bool
    decision: str
    reason: str = ""
    matched_policies: list[str] = []
    requires_approval: bool = False
    risk_score: float = 0.0
    explanation: Optional[str] = None


class AuditQuery(BaseModel):
    organization_id: Optional[str] = None
    user_id: Optional[str] = None
    action: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    limit: int = 100
    offset: int = 0


class DataClassificationUpdate(BaseModel):
    resource_id: str
    resource_type: str
    classification: str
    reason: Optional[str] = None


class AccessReviewRequest(BaseModel):
    review_type: str = "periodic"
    scope: str = "all"
    notify_stale: bool = True
    auto_revoke_expired: bool = False
