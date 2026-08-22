"""IAM constants — roles, permissions, enums, and defaults."""
import enum


class IAMRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    DEVELOPER = "developer"
    VIEWER = "viewer"
    SECURITY = "security"
    AUDITOR = "auditor"
    BILLING = "billing"
    SRE = "sre"
    SERVICE_ACCOUNT = "service_account"


class IAMPermission(str, enum.Enum):
    ORG_READ = "organization:read"
    ORG_WRITE = "organization:write"
    WORKSPACE_READ = "workspace:read"
    WORKSPACE_WRITE = "workspace:write"
    PROJECT_READ = "project:read"
    PROJECT_WRITE = "project:write"
    REPOSITORY_READ = "repository:read"
    REPOSITORY_WRITE = "repository:write"
    REPOSITORY_ADMIN = "repository:admin"
    AGENT_EXECUTE = "agent:execute"
    TOOL_EXECUTE = "tool:execute"
    WORKFLOW_EXECUTE = "workflow:execute"
    ENVIRONMENT_READ = "environment:read"
    ENVIRONMENT_DEPLOY = "environment:deploy"
    SECURITY_READ = "security:read"
    SECURITY_ADMIN = "security:admin"
    BILLING_READ = "billing:read"
    BILLING_ADMIN = "billing:admin"
    AUDIT_READ = "audit:read"
    MEMBER_MANAGE = "member:manage"
    ROLE_MANAGE = "role:manage"
    POLICY_MANAGE = "policy:manage"
    SERVICE_ACCOUNT_MANAGE = "service_account:manage"
    API_KEY_MANAGE = "api_key:manage"
    SSO_MANAGE = "sso:manage"
    SCIM_MANAGE = "scim:manage"
    BREAK_GLASS_USE = "break_glass:use"
    DATA_EXPORT = "data:export"
    SETTINGS_ADMIN = "settings:admin"


ROLE_HIERARCHY: dict[IAMRole, list[IAMRole]] = {
    IAMRole.OWNER: [IAMRole.ADMIN, IAMRole.SRE, IAMRole.SECURITY, IAMRole.AUDITOR, IAMRole.BILLING, IAMRole.MEMBER, IAMRole.DEVELOPER, IAMRole.VIEWER],
    IAMRole.ADMIN: [IAMRole.MEMBER, IAMRole.DEVELOPER, IAMRole.VIEWER],
    IAMRole.SRE: [IAMRole.DEVELOPER, IAMRole.VIEWER],
    IAMRole.SECURITY: [IAMRole.VIEWER],
    IAMRole.AUDITOR: [IAMRole.VIEWER],
    IAMRole.BILLING: [IAMRole.VIEWER],
    IAMRole.MEMBER: [IAMRole.VIEWER],
    IAMRole.DEVELOPER: [IAMRole.VIEWER],
    IAMRole.VIEWER: [],
    IAMRole.SERVICE_ACCOUNT: [],
}

ROLE_PERMISSIONS: dict[IAMRole, set[IAMPermission]] = {
    IAMRole.OWNER: set(IAMPermission),
    IAMRole.ADMIN: {
        IAMPermission.ORG_READ, IAMPermission.ORG_WRITE,
        IAMPermission.WORKSPACE_READ, IAMPermission.WORKSPACE_WRITE,
        IAMPermission.PROJECT_READ, IAMPermission.PROJECT_WRITE,
        IAMPermission.REPOSITORY_READ, IAMPermission.REPOSITORY_WRITE, IAMPermission.REPOSITORY_ADMIN,
        IAMPermission.AGENT_EXECUTE, IAMPermission.TOOL_EXECUTE, IAMPermission.WORKFLOW_EXECUTE,
        IAMPermission.ENVIRONMENT_READ, IAMPermission.ENVIRONMENT_DEPLOY,
        IAMPermission.MEMBER_MANAGE, IAMPermission.ROLE_MANAGE,
        IAMPermission.SETTINGS_ADMIN,
    },
    IAMRole.SRE: {
        IAMPermission.ORG_READ,
        IAMPermission.WORKSPACE_READ, IAMPermission.PROJECT_READ,
        IAMPermission.REPOSITORY_READ, IAMPermission.REPOSITORY_WRITE,
        IAMPermission.AGENT_EXECUTE, IAMPermission.TOOL_EXECUTE, IAMPermission.WORKFLOW_EXECUTE,
        IAMPermission.ENVIRONMENT_READ, IAMPermission.ENVIRONMENT_DEPLOY,
        IAMPermission.SECURITY_READ,
    },
    IAMRole.SECURITY: {
        IAMPermission.ORG_READ, IAMPermission.WORKSPACE_READ, IAMPermission.PROJECT_READ,
        IAMPermission.REPOSITORY_READ,
        IAMPermission.SECURITY_READ, IAMPermission.SECURITY_ADMIN,
        IAMPermission.AUDIT_READ,
    },
    IAMRole.AUDITOR: {
        IAMPermission.ORG_READ, IAMPermission.WORKSPACE_READ, IAMPermission.PROJECT_READ,
        IAMPermission.REPOSITORY_READ,
        IAMPermission.AUDIT_READ,
    },
    IAMRole.BILLING: {
        IAMPermission.ORG_READ, IAMPermission.WORKSPACE_READ,
        IAMPermission.BILLING_READ, IAMPermission.BILLING_ADMIN,
    },
    IAMRole.MEMBER: {
        IAMPermission.ORG_READ, IAMPermission.WORKSPACE_READ, IAMPermission.PROJECT_READ,
        IAMPermission.REPOSITORY_READ, IAMPermission.REPOSITORY_WRITE,
        IAMPermission.AGENT_EXECUTE, IAMPermission.WORKFLOW_EXECUTE,
        IAMPermission.ENVIRONMENT_READ,
    },
    IAMRole.DEVELOPER: {
        IAMPermission.ORG_READ, IAMPermission.WORKSPACE_READ, IAMPermission.PROJECT_READ,
        IAMPermission.REPOSITORY_READ, IAMPermission.REPOSITORY_WRITE,
        IAMPermission.AGENT_EXECUTE, IAMPermission.TOOL_EXECUTE, IAMPermission.WORKFLOW_EXECUTE,
        IAMPermission.ENVIRONMENT_READ,
    },
    IAMRole.VIEWER: {
        IAMPermission.ORG_READ, IAMPermission.WORKSPACE_READ, IAMPermission.PROJECT_READ,
        IAMPermission.REPOSITORY_READ, IAMPermission.ENVIRONMENT_READ,
    },
    IAMRole.SERVICE_ACCOUNT: set(),
}

RESOURCE_SCOPES = ("organization", "workspace", "project", "repository", "service", "environment")

DATA_CLASSIFICATIONS = ("PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED", "SECRET")

ENVIRONMENTS = ("development", "staging", "production")

SESSION_MAX_CONCURRENT = 10
SESSION_IDLE_MINUTES = 60
SESSION_ABSOLUTE_HOURS = 24
API_KEY_MAX_PER_USER = 10
SERVICE_ACCOUNT_MAX_PER_ORG = 50
BREAK_GLASS_MAX_HOURS = 4
RATE_LIMIT_REQUESTS_PER_MINUTE = 100
QUOTA_DEFAULT_USERS = 100
QUOTA_DEFAULT_REPOSITORIES = 50
QUOTA_DEFAULT_STORAGE_GB = 100
QUOTA_DEFAULT_AI_TOKENS = 1000000
QUOTA_DEFAULT_AGENTS = 10
QUOTA_DEFAULT_WORKFLOWS = 25
QUOTA_DEFAULT_API_CALLS = 10000
QUOTA_DEFAULT_CI_JOBS = 50
QUOTA_DEFAULT_DEPLOYMENTS = 25
