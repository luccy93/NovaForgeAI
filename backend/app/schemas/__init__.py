"""Centralized Pydantic schemas for NovaForge API."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


# ─── Pagination ───────────────────────────────────────────────────────────

class PaginationMeta(BaseModel):
    offset: int = 0
    limit: int = 20
    total: int = 0


class PaginatedResponse(BaseModel):
    data: list[Any]
    meta: PaginationMeta


# ─── Error ────────────────────────────────────────────────────────────────

class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = {}


class ErrorResponse(BaseModel):
    error: ErrorDetail


# ─── Health ───────────────────────────────────────────────────────────────

class HealthCheck(BaseModel):
    status: str
    version: str


class ReadinessCheck(BaseModel):
    status: str
    checks: dict[str, bool]


# ─── User ─────────────────────────────────────────────────────────────────

class UserOut(BaseModel):
    id: str
    email: str
    username: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: bool
    created_at: datetime


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None


# ─── Auth ─────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str = Field(..., max_length=255)
    username: str = Field(..., min_length=2, max_length=100, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(..., min_length=8, max_length=128)
    full_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int


class GitHubAuthUrl(BaseModel):
    url: str


class GitHubAuthResponse(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int
    is_new_user: bool = False


class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    scopes: list[str] = []


class ApiKeyOut(BaseModel):
    id: str
    name: str
    key_prefix: str
    scopes: list[str]
    is_active: bool
    last_used_at: Optional[datetime]
    expires_at: Optional[datetime]
    created_at: datetime


class ApiKeyCreated(BaseModel):
    id: str
    name: str
    key_prefix: str
    full_key: str
    scopes: list[str]
    created_at: datetime


# ─── Repository ───────────────────────────────────────────────────────────

class RepositoryCreate(BaseModel):
    name: str = Field(..., max_length=255)
    full_name: str = Field(..., max_length=500)
    description: Optional[str] = None
    private: bool = True
    git_url: Optional[str] = None
    default_branch: str = "main"
    language: Optional[str] = None
    organization_id: Optional[str] = None


class RepositoryOut(BaseModel):
    id: str
    name: str
    full_name: str
    description: Optional[str]
    private: bool
    git_url: Optional[str]
    default_branch: str
    language: Optional[str]
    size: Optional[int]
    last_indexed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


# ─── Chat ─────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=10000)
    conversation_id: Optional[str] = None
    repo_id: Optional[str] = None
    stream: bool = False


class ChatSource(BaseModel):
    text: str
    source: str
    score: float
    type: str  # vector | graph | web


class ChatResponse(BaseModel):
    answer: str
    conversation_id: str
    confidence: float
    model_used: str
    sources: list[ChatSource]


class ConversationSummary(BaseModel):
    id: str
    title: str
    message_count: int
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime


class ConversationDetail(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[MessageOut]


# ─── Code Analysis ────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    content: str = Field(..., max_length=500000)
    language: str = Field(..., pattern=r"^(python|typescript|javascript|go|rust|java)$")


class AnalyzeResponse(BaseModel):
    language: str
    size_bytes: int
    line_count: int
    functions: list[dict]
    classes: list[dict]
    complexity: int
    dependencies: list[str]
    has_syntax_tree: bool


# ─── Agents ───────────────────────────────────────────────────────────────

class AgentInfo(BaseModel):
    name: str
    description: str
    capabilities: list[str]


class AgentRunRequest(BaseModel):
    input: str
    config: Optional[dict[str, Any]] = None


class AgentRunResponse(BaseModel):
    agent: str
    output: str
    status: str


class PipelineRequest(BaseModel):
    agents: list[str] = Field(..., min_length=1)
    input: str


class PipelineResponse(BaseModel):
    results: list[AgentRunResponse]
    final_output: str


class ParallelRequest(BaseModel):
    agents: list[str] = Field(..., min_length=1)
    input: str


class ParallelResponse(BaseModel):
    results: list[AgentRunResponse]


# ─── Organization ─────────────────────────────────────────────────────────

class OrganizationCreate(BaseModel):
    name: str = Field(..., max_length=255)
    slug: str = Field(..., min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    description: Optional[str] = None


class OrganizationOut(BaseModel):
    id: str
    name: str
    slug: str
    description: Optional[str]
    plan: str = "free"
    is_active: bool = True
    created_at: datetime
    member_count: int = 0
    repository_count: int = 0


# ─── Organization Members ─────────────────────────────────────────────────

class OrganizationMemberOut(BaseModel):
    user_id: str
    email: str
    username: str
    role: str
    joined_at: datetime


class InviteRequest(BaseModel):
    email: str = Field(..., max_length=255)
    role: str = Field(default="member", pattern=r"^(admin|member|viewer|manager|developer|reviewer)$")


class InviteOut(BaseModel):
    id: str
    email: str
    role: str
    token: str
    expires_at: datetime
    created_at: datetime


# ─── Billing ──────────────────────────────────────────────────────────────

class PlanOut(BaseModel):
    id: str
    name: str
    description: str
    price_monthly: int
    price_yearly: int
    features: list[str]
    limits: dict[str, Any]


class SubscriptionOut(BaseModel):
    id: str
    plan_id: str
    status: str
    current_period_start: datetime
    current_period_end: datetime
    canceled_at: Optional[datetime]
    trial_end: Optional[datetime]


class CheckoutSessionRequest(BaseModel):
    plan_id: str = Field(..., pattern=r"^(pro|team|business|enterprise)$")
    success_url: str
    cancel_url: str


class CheckoutSessionResponse(BaseModel):
    url: str
    session_id: str


class BillingPortalResponse(BaseModel):
    url: str


class UsageSummary(BaseModel):
    metric: str
    current: float
    limit: float
    percentage: float


class UsageSummaryResponse(BaseModel):
    organization_id: str
    plan: str
    usage: list[UsageSummary]


# ─── Feature Flag ─────────────────────────────────────────────────────────

class FeatureFlagOut(BaseModel):
    id: str
    name: str
    enabled: bool
    config: dict[str, Any]
    organization_id: Optional[str]


class FeatureFlagUpdate(BaseModel):
    enabled: bool
    config: Optional[dict[str, Any]] = None


# ─── Admin ────────────────────────────────────────────────────────────────

class AdminOverview(BaseModel):
    total_organizations: int
    total_users: int
    total_repositories: int
    active_subscriptions: int
    mrr_cents: int
    total_agent_runs: int


class AdminOrganizationOut(BaseModel):
    id: str
    name: str
    slug: str
    plan: str
    is_active: bool
    member_count: int
    repository_count: int
    created_at: datetime


# ─── Citation ─────────────────────────────────────────────────────────────

class Citation(BaseModel):
    id: int
    text: str
    source: str
    source_type: str
    relevance_score: float
    url: Optional[str] = None


class CitationResponse(BaseModel):
    answer: str
    citations: list[Citation]
    confidence: float
    model_used: str


# ─── Notifications ──────────────────────────────────────────────────────────

class NotificationEventType(str, Enum):
    deployment_complete = "deployment_complete"
    deployment_failed = "deployment_failed"
    security_alert = "security_alert"
    security_scan_complete = "security_scan_complete"
    member_joined = "member_joined"
    member_invite = "member_invite"
    subscription_change = "subscription_change"
    usage_threshold = "usage_threshold"
    ai_call_complete = "ai_call_complete"
    pipeline_complete = "pipeline_complete"
    agent_error = "agent_error"
    repository_imported = "repository_imported"
    system_announcement = "system_announcement"


class NotificationChannelType(str, Enum):
    email = "email"
    slack = "slack"
    discord = "discord"
    webhook = "webhook"
    in_app = "in_app"


class NotificationOut(BaseModel):
    id: str
    title: str
    body: str
    notification_type: str
    is_read: bool
    read_at: Optional[datetime]
    action_url: Optional[str]
    created_at: datetime


class NotificationChannelCreate(BaseModel):
    channel_type: NotificationChannelType
    name: str = Field(..., max_length=100)
    config: dict[str, Any] = {}


class NotificationChannelUpdate(BaseModel):
    name: Optional[str] = None
    config: Optional[dict[str, Any]] = None
    is_active: Optional[bool] = None


class NotificationChannelOut(BaseModel):
    id: str
    channel_type: str
    name: str
    is_active: bool
    verified_at: Optional[datetime]
    created_at: datetime


class NotificationPreferenceItem(BaseModel):
    event_type: NotificationEventType
    channels: list[NotificationChannelType]
    enabled: bool = True


class NotificationPreferencesOut(BaseModel):
    preferences: list[NotificationPreferenceItem]
