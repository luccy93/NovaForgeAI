"""Models package — import all models for Alembic autogenerate."""

from app.models.user import User, UserSession, ApiKey
from app.models.organization import Organization, Subscription, Project, user_organizations
from app.models.repository import Repository, Branch, Commit, RepositoryVersion
from app.models.conversation import Conversation, Message, MessageRole
from app.models.support import (
    AuditLog, AuditAction,
    Notification,
    NotificationChannel,
    FeatureFlag,
    AppSetting,
    AgentRun,
    AnalyticsEvent,
    UsageRecord,
    SecurityReport,
    Deployment,
)
from app.sre import models as sre_models  # noqa: F401  (Volume 35 SRE tables)

__all__ = [
    "User", "UserSession", "ApiKey",
    "Organization", "Subscription", "Project", "user_organizations",
    "Repository", "Branch", "Commit", "RepositoryVersion",
    "Conversation", "Message", "MessageRole",
    "AuditLog", "AuditAction",
    "Notification",
    "NotificationChannel",
    "FeatureFlag",
    "AppSetting",
    "AgentRun",
    "AnalyticsEvent",
    "UsageRecord",
    "SecurityReport",
    "Deployment",
]
