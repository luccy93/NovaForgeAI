"""IAM configuration."""
from dataclasses import dataclass, field
from app.iam.constants import (
    SESSION_MAX_CONCURRENT, SESSION_IDLE_MINUTES, SESSION_ABSOLUTE_HOURS,
    API_KEY_MAX_PER_USER, SERVICE_ACCOUNT_MAX_PER_ORG, BREAK_GLASS_MAX_HOURS,
    RATE_LIMIT_REQUESTS_PER_MINUTE, QUOTA_DEFAULT_USERS, QUOTA_DEFAULT_REPOSITORIES,
    QUOTA_DEFAULT_STORAGE_GB, QUOTA_DEFAULT_AI_TOKENS, QUOTA_DEFAULT_AGENTS,
    QUOTA_DEFAULT_WORKFLOWS, QUOTA_DEFAULT_API_CALLS, QUOTA_DEFAULT_CI_JOBS,
    QUOTA_DEFAULT_DEPLOYMENTS,
)


@dataclass
class IAMConfig:
    session_max_concurrent: int = SESSION_MAX_CONCURRENT
    session_idle_minutes: int = SESSION_IDLE_MINUTES
    session_absolute_hours: int = SESSION_ABSOLUTE_HOURS
    api_key_max_per_user: int = API_KEY_MAX_PER_USER
    service_account_max_per_org: int = SERVICE_ACCOUNT_MAX_PER_ORG
    break_glass_max_hours: int = BREAK_GLASS_MAX_HOURS
    rate_limit_requests_per_minute: int = RATE_LIMIT_REQUESTS_PER_MINUTE
    default_quota_users: int = QUOTA_DEFAULT_USERS
    default_quota_repositories: int = QUOTA_DEFAULT_REPOSITORIES
    default_quota_storage_gb: int = QUOTA_DEFAULT_STORAGE_GB
    default_quota_ai_tokens: int = QUOTA_DEFAULT_AI_TOKENS
    default_quota_agents: int = QUOTA_DEFAULT_AGENTS
    default_quota_workflows: int = QUOTA_DEFAULT_WORKFLOWS
    default_quota_api_calls: int = QUOTA_DEFAULT_API_CALLS
    default_quota_ci_jobs: int = QUOTA_DEFAULT_CI_JOBS
    default_quota_deployments: int = QUOTA_DEFAULT_DEPLOYMENTS
    enforce_tenant_isolation: bool = True
    require_mfa_for_admins: bool = True
    require_mfa_for_production: bool = True
    require_mfa_for_billing: bool = True
    break_glass_requires_mfa: bool = True
    fail_closed: bool = True
    enable_access_reviews: bool = True
    access_review_interval_days: int = 90
    enable_privilege_analysis: bool = True
    enable_domain_verification: bool = True
    data_export_requires_approval: bool = True
    organization_deletion_requires_approval: bool = True
    admin_impersonation_requires_approval: bool = True
    max_api_key_expiry_days: int = 365
    max_service_account_expiry_days: int = 365
    scim_sync_interval_minutes: int = 30
    session_cleanup_interval_minutes: int = 15
    key_expiration_check_interval_minutes: int = 60


_iam_config: IAMConfig | None = None


def get_iam_config() -> IAMConfig:
    global _iam_config
    if _iam_config is None:
        _iam_config = IAMConfig()
    return _iam_config
