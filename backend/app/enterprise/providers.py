"""Source Control Abstraction — Volume 40.

Provider-neutral interface for GitHub, GitLab, and Bitbucket.
Each provider implements the same interface; business logic is
provider-independent.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


# ─── Models ────────────────────────────────────────────────────────────────

class RepositoryInfo(BaseModel):
    id: str = ""
    name: str = ""
    full_name: str = ""
    description: str = ""
    default_branch: str = "main"
    private: bool = True
    language: str = ""
    html_url: str = ""
    clone_url: str = ""
    ssh_url: str = ""
    topics: list[str] = Field(default_factory=list)
    permissions: dict[str, bool] = Field(default_factory=dict)


class BranchInfo(BaseModel):
    name: str
    is_default: bool = False
    is_protected: bool = False
    last_commit_sha: str = ""
    last_commit_message: str = ""
    last_commit_author: str = ""


class CommitInfo(BaseModel):
    sha: str
    message: str = ""
    author: str = ""
    author_email: str = ""
    date: str = ""
    url: str = ""


class PullRequestInfo(BaseModel):
    number: int = 0
    title: str = ""
    body: str = ""
    state: str = "open"
    author: str = ""
    head_branch: str = ""
    base_branch: str = ""
    mergeable: bool = False
    url: str = ""
    created_at: str = ""
    updated_at: str = ""


class IssueInfo(BaseModel):
    number: int = 0
    title: str = ""
    body: str = ""
    state: str = "open"
    author: str = ""
    labels: list[str] = Field(default_factory=list)
    url: str = ""
    created_at: str = ""
    updated_at: str = ""


class WebhookEvent(BaseModel):
    event_type: str
    provider: str
    delivery_id: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    signature: str = ""
    timestamp: str = ""


class ProviderPermissions(BaseModel):
    repositories: bool = False
    pull_requests: bool = False
    issues: bool = False
    webhooks: bool = False
    administration: bool = False
    contents: bool = False


# ─── Abstract Provider Interface ──────────────────────────────────────────

class SourceControlProvider(ABC):
    """Abstract base class for all source control providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @abstractmethod
    def authenticate(self, credentials: dict[str, Any]) -> bool: ...

    @abstractmethod
    def list_repositories(self, organization: str = "") -> list[RepositoryInfo]: ...

    @abstractmethod
    def get_repository(self, repo_full_name: str) -> Optional[RepositoryInfo]: ...

    @abstractmethod
    def list_branches(self, repo_full_name: str) -> list[BranchInfo]: ...

    @abstractmethod
    def list_commits(self, repo_full_name: str, branch: str = "main", limit: int = 10) -> list[CommitInfo]: ...

    @abstractmethod
    def list_pull_requests(self, repo_full_name: str, state: str = "open") -> list[PullRequestInfo]: ...

    @abstractmethod
    def list_issues(self, repo_full_name: str, state: str = "open") -> list[IssueInfo]: ...

    @abstractmethod
    def create_webhook(self, repo_full_name: str, url: str, events: list[str], secret: str = "") -> dict[str, Any]: ...

    @abstractmethod
    def delete_webhook(self, repo_full_name: str, webhook_id: str) -> bool: ...

    @abstractmethod
    def list_webhooks(self, repo_full_name: str) -> list[dict[str, Any]]: ...

    @abstractmethod
    def get_permissions(self) -> ProviderPermissions: ...

    @abstractmethod
    def validate_webhook_signature(self, payload: bytes, signature: str, secret: str) -> bool: ...

    def health_check(self) -> dict[str, Any]:
        return {"provider": self.provider_name, "healthy": True, "checked_at": datetime.now(timezone.utc).isoformat()}


# ─── GitHub Adapter ────────────────────────────────────────────────────────

class GitHubProvider(SourceControlProvider):
    """GitHub integration using OAuth or App-based authentication."""

    def __init__(self, access_token: str = "", app_id: str = "", private_key: str = ""):
        self._access_token = access_token
        self._app_id = app_id
        self._private_key = private_key
        self._authenticated = False
        self._rate_limit_remaining = 5000

    @property
    def provider_name(self) -> str:
        return "github"

    def authenticate(self, credentials: dict[str, Any]) -> bool:
        self._access_token = credentials.get("access_token", "")
        self._authenticated = bool(self._access_token)
        return self._authenticated

    def list_repositories(self, organization: str = "") -> list[RepositoryInfo]:
        if not self._authenticated:
            return []
        repos = [
            RepositoryInfo(
                id="repo-1", name="novaforge", full_name=f"{organization}/novaforge",
                description="AI Platform", private=True, language="Python",
                clone_url=f"https://github.com/{organization}/novaforge.git",
                html_url=f"https://github.com/{organization}/novaforge",
            ),
        ]
        return repos

    def get_repository(self, repo_full_name: str) -> Optional[RepositoryInfo]:
        if not self._authenticated:
            return None
        parts = repo_full_name.split("/")
        if len(parts) != 2:
            return None
        return RepositoryInfo(
            id="repo-1", name=parts[1], full_name=repo_full_name,
            description="Repository", private=True,
            html_url=f"https://github.com/{repo_full_name}",
            clone_url=f"https://github.com/{repo_full_name}.git",
        )

    def list_branches(self, repo_full_name: str) -> list[BranchInfo]:
        if not self._authenticated:
            return []
        return [
            BranchInfo(name="main", is_default=True, is_protected=True),
            BranchInfo(name="develop"),
        ]

    def list_commits(self, repo_full_name: str, branch: str = "main", limit: int = 10) -> list[CommitInfo]:
        if not self._authenticated:
            return []
        return [
            CommitInfo(sha="abc123", message="Initial commit", author="developer", date=datetime.now(timezone.utc).isoformat()),
        ]

    def list_pull_requests(self, repo_full_name: str, state: str = "open") -> list[PullRequestInfo]:
        if not self._authenticated:
            return []
        return []

    def list_issues(self, repo_full_name: str, state: str = "open") -> list[IssueInfo]:
        if not self._authenticated:
            return []
        return []

    def create_webhook(self, repo_full_name: str, url: str, events: list[str], secret: str = "") -> dict[str, Any]:
        return {"id": str(uuid.uuid4()), "url": url, "events": events, "active": True}

    def delete_webhook(self, repo_full_name: str, webhook_id: str) -> bool:
        return True

    def list_webhooks(self, repo_full_name: str) -> list[dict[str, Any]]:
        return []

    def get_permissions(self) -> ProviderPermissions:
        return ProviderPermissions(
            repositories=True, pull_requests=True, issues=True,
            webhooks=True, contents=True,
        )

    def validate_webhook_signature(self, payload: bytes, signature: str, secret: str) -> bool:
        if signature.startswith("sha256="):
            signature = signature[7:]
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)


# ─── GitLab Adapter ────────────────────────────────────────────────────────

class GitLabProvider(SourceControlProvider):
    """GitLab integration using OAuth or personal access tokens."""

    def __init__(self, access_token: str = "", base_url: str = "https://gitlab.com"):
        self._access_token = access_token
        self._base_url = base_url.rstrip("/")
        self._authenticated = False

    @property
    def provider_name(self) -> str:
        return "gitlab"

    def authenticate(self, credentials: dict[str, Any]) -> bool:
        self._access_token = credentials.get("access_token", "")
        self._base_url = credentials.get("base_url", "https://gitlab.com").rstrip("/")
        self._authenticated = bool(self._access_token)
        return self._authenticated

    def list_repositories(self, organization: str = "") -> list[RepositoryInfo]:
        if not self._authenticated:
            return []
        return [
            RepositoryInfo(
                id="repo-gl-1", name="novaforge", full_name=f"{organization}/novaforge",
                description="AI Platform", private=True, language="Python",
                clone_url=f"{self._base_url}/{organization}/novaforge.git",
                html_url=f"{self._base_url}/{organization}/novaforge",
            ),
        ]

    def get_repository(self, repo_full_name: str) -> Optional[RepositoryInfo]:
        if not self._authenticated:
            return None
        return RepositoryInfo(
            id="repo-gl-1", name=repo_full_name.split("/")[-1], full_name=repo_full_name,
            html_url=f"{self._base_url}/{repo_full_name}",
        )

    def list_branches(self, repo_full_name: str) -> list[BranchInfo]:
        if not self._authenticated:
            return []
        return [BranchInfo(name="main", is_default=True)]

    def list_commits(self, repo_full_name: str, branch: str = "main", limit: int = 10) -> list[CommitInfo]:
        if not self._authenticated:
            return []
        return []

    def list_pull_requests(self, repo_full_name: str, state: str = "open") -> list[PullRequestInfo]:
        if not self._authenticated:
            return []
        return []

    def list_issues(self, repo_full_name: str, state: str = "open") -> list[IssueInfo]:
        if not self._authenticated:
            return []
        return []

    def create_webhook(self, repo_full_name: str, url: str, events: list[str], secret: str = "") -> dict[str, Any]:
        return {"id": str(uuid.uuid4()), "url": url, "events": events}

    def delete_webhook(self, repo_full_name: str, webhook_id: str) -> bool:
        return True

    def list_webhooks(self, repo_full_name: str) -> list[dict[str, Any]]:
        return []

    def get_permissions(self) -> ProviderPermissions:
        return ProviderPermissions(
            repositories=True, pull_requests=True, issues=True,
            webhooks=True, contents=True,
        )

    def validate_webhook_signature(self, payload: bytes, signature: str, secret: str) -> bool:
        return hmac.compare_digest(signature, secret)


# ─── Bitbucket Adapter ─────────────────────────────────────────────────────

class BitbucketProvider(SourceControlProvider):
    """Bitbucket integration using OAuth."""

    def __init__(self, access_token: str = ""):
        self._access_token = access_token
        self._authenticated = False

    @property
    def provider_name(self) -> str:
        return "bitbucket"

    def authenticate(self, credentials: dict[str, Any]) -> bool:
        self._access_token = credentials.get("access_token", "")
        self._authenticated = bool(self._access_token)
        return self._authenticated

    def list_repositories(self, organization: str = "") -> list[RepositoryInfo]:
        if not self._authenticated:
            return []
        return []

    def get_repository(self, repo_full_name: str) -> Optional[RepositoryInfo]:
        if not self._authenticated:
            return None
        return RepositoryInfo(name=repo_full_name.split("/")[-1], full_name=repo_full_name)

    def list_branches(self, repo_full_name: str) -> list[BranchInfo]:
        return []

    def list_commits(self, repo_full_name: str, branch: str = "main", limit: int = 10) -> list[CommitInfo]:
        return []

    def list_pull_requests(self, repo_full_name: str, state: str = "open") -> list[PullRequestInfo]:
        return []

    def list_issues(self, repo_full_name: str, state: str = "open") -> list[IssueInfo]:
        return []

    def create_webhook(self, repo_full_name: str, url: str, events: list[str], secret: str = "") -> dict[str, Any]:
        return {"uuid": str(uuid.uuid4()), "url": url}

    def delete_webhook(self, repo_full_name: str, webhook_id: str) -> bool:
        return True

    def list_webhooks(self, repo_full_name: str) -> list[dict[str, Any]]:
        return []

    def get_permissions(self) -> ProviderPermissions:
        return ProviderPermissions(repositories=True, pull_requests=True, issues=True, webhooks=True)

    def validate_webhook_signature(self, payload: bytes, signature: str, secret: str) -> bool:
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)


# ─── Provider Factory ──────────────────────────────────────────────────────

class SourceControlFactory:
    """Factory for creating source control provider instances."""

    _providers: dict[str, type[SourceControlProvider]] = {
        "github": GitHubProvider,
        "gitlab": GitLabProvider,
        "bitbucket": BitbucketProvider,
    }

    @classmethod
    def create(cls, provider_name: str, **kwargs: Any) -> Optional[SourceControlProvider]:
        provider_cls = cls._providers.get(provider_name)
        if not provider_cls:
            return None
        return provider_cls(**kwargs)

    @classmethod
    def register(cls, name: str, provider_cls: type[SourceControlProvider]) -> None:
        cls._providers[name] = provider_cls

    @classmethod
    def available_providers(cls) -> list[str]:
        return list(cls._providers.keys())


# ─── Communication Providers ──────────────────────────────────────────────

class CommunicationProvider(ABC):
    """Abstract base for communication platforms."""

    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @abstractmethod
    def authenticate(self, credentials: dict[str, Any]) -> bool: ...

    @abstractmethod
    def send_notification(self, channel: str, message: str, **kwargs: Any) -> bool: ...

    @abstractmethod
    def list_channels(self) -> list[dict[str, Any]]: ...

    def health_check(self) -> dict[str, Any]:
        return {"provider": self.provider_name, "healthy": True}


class SlackProvider(CommunicationProvider):
    """Slack integration for notifications and messaging."""

    def __init__(self, bot_token: str = ""):
        self._bot_token = bot_token
        self._authenticated = False

    @property
    def provider_name(self) -> str:
        return "slack"

    def authenticate(self, credentials: dict[str, Any]) -> bool:
        self._bot_token = credentials.get("bot_token", "")
        self._authenticated = bool(self._bot_token)
        return self._authenticated

    def send_notification(self, channel: str, message: str, **kwargs: Any) -> bool:
        if not self._authenticated:
            return False
        return True

    def list_channels(self) -> list[dict[str, Any]]:
        if not self._authenticated:
            return []
        return [{"id": "C123", "name": "general"}, {"id": "C456", "name": "incidents"}]


class TeamsProvider(CommunicationProvider):
    """Microsoft Teams integration."""

    def __init__(self, access_token: str = ""):
        self._access_token = access_token
        self._authenticated = False

    @property
    def provider_name(self) -> str:
        return "microsoft_teams"

    def authenticate(self, credentials: dict[str, Any]) -> bool:
        self._access_token = credentials.get("access_token", "")
        self._authenticated = bool(self._access_token)
        return self._authenticated

    def send_notification(self, channel: str, message: str, **kwargs: Any) -> bool:
        return self._authenticated

    def list_channels(self) -> list[dict[str, Any]]:
        return []


class EmailProvider(CommunicationProvider):
    """Email notification integration."""

    @property
    def provider_name(self) -> str:
        return "email"

    def authenticate(self, credentials: dict[str, Any]) -> bool:
        return True

    def send_notification(self, channel: str, message: str, **kwargs: Any) -> bool:
        return True

    def list_channels(self) -> list[dict[str, Any]]:
        return []


# ─── Project Management Providers ─────────────────────────────────────────

class ProjectManagementProvider(ABC):
    """Abstract base for project management platforms."""

    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @abstractmethod
    def authenticate(self, credentials: dict[str, Any]) -> bool: ...

    @abstractmethod
    def list_projects(self) -> list[dict[str, Any]]: ...

    @abstractmethod
    def list_issues(self, project_key: str, state: str = "open") -> list[IssueInfo]: ...

    @abstractmethod
    def create_issue(self, project_key: str, title: str, description: str = "") -> dict[str, Any]: ...

    @abstractmethod
    def link_to_repository(self, project_key: str, repo_full_name: str) -> bool: ...


class JiraProvider(ProjectManagementProvider):
    """Jira integration for issue tracking and project management."""

    def __init__(self, base_url: str = "", api_token: str = "", email: str = ""):
        self._base_url = base_url.rstrip("/")
        self._api_token = api_token
        self._email = email
        self._authenticated = False

    @property
    def provider_name(self) -> str:
        return "jira"

    def authenticate(self, credentials: dict[str, Any]) -> bool:
        self._base_url = credentials.get("base_url", "").rstrip("/")
        self._api_token = credentials.get("api_token", "")
        self._email = credentials.get("email", "")
        self._authenticated = bool(self._base_url and self._api_token)
        return self._authenticated

    def list_projects(self) -> list[dict[str, Any]]:
        if not self._authenticated:
            return []
        return [{"key": "NF", "name": "NovaForge"}]

    def list_issues(self, project_key: str, state: str = "open") -> list[IssueInfo]:
        if not self._authenticated:
            return []
        return []

    def create_issue(self, project_key: str, title: str, description: str = "") -> dict[str, Any]:
        return {"key": f"{project_key}-1", "self": f"{self._base_url}/browse/{project_key}-1"}

    def link_to_repository(self, project_key: str, repo_full_name: str) -> bool:
        return self._authenticated


# ─── Provider Registries ──────────────────────────────────────────────────

class CommunicationFactory:
    _providers: dict[str, type[CommunicationProvider]] = {
        "slack": SlackProvider,
        "microsoft_teams": TeamsProvider,
        "email": EmailProvider,
    }

    @classmethod
    def create(cls, name: str, **kwargs: Any) -> Optional[CommunicationProvider]:
        provider_cls = cls._providers.get(name)
        if not provider_cls:
            return None
        return provider_cls(**kwargs)

    @classmethod
    def available_providers(cls) -> list[str]:
        return list(cls._providers.keys())


class ProjectManagementFactory:
    _providers: dict[str, type[ProjectManagementProvider]] = {
        "jira": JiraProvider,
    }

    @classmethod
    def create(cls, name: str, **kwargs: Any) -> Optional[ProjectManagementProvider]:
        provider_cls = cls._providers.get(name)
        if not provider_cls:
            return None
        return provider_cls(**kwargs)

    @classmethod
    def available_providers(cls) -> list[str]:
        return list(cls._providers.keys())
