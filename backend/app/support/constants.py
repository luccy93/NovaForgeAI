"""Support & ITSM constants — Volume 54."""

from __future__ import annotations

import enum


class TicketStatus(str, enum.Enum):
    NEW = "new"
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    WAITING_CUSTOMER = "waiting_customer"
    WAITING_INTERNAL = "waiting_internal"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    CLOSED = "closed"
    REOPENED = "reopened"


class TicketPriority(str, enum.Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"
    CRITICAL = "critical"


class TicketSeverity(str, enum.Enum):
    S1 = "s1"
    S2 = "s2"
    S3 = "s3"
    S4 = "s4"


class TicketCategory(str, enum.Enum):
    QUESTION = "question"
    BUG = "bug"
    FEATURE_REQUEST = "feature_request"
    BILLING = "billing"
    SECURITY = "security"
    ACCOUNT = "account"
    DEPLOYMENT = "deployment"
    PERFORMANCE = "performance"
    INCIDENT = "incident"
    INTEGRATION = "integration"
    DOCUMENTATION = "documentation"
    ACCESS = "access"


class TicketSource(str, enum.Enum):
    WEB = "web"
    EMAIL = "email"
    API = "api"
    CLI = "cli"
    CHAT = "chat"
    WEBHOOK = "webhook"
    MESSAGING = "messaging"


class ArticleStatus(str, enum.Enum):
    DRAFT = "draft"
    REVIEW = "review"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class SLAState(str, enum.Enum):
    ON_TRACK = "on_track"
    AT_RISK = "at_risk"
    BREACHED = "breached"
    PAUSED = "paused"


class SentimentLevel(str, enum.Enum):
    VERY_NEGATIVE = "very_negative"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    POSITIVE = "positive"
    VERY_POSITIVE = "very_positive"


class EscalationType(str, enum.Enum):
    TIME_BASED = "time_based"
    SEVERITY_BASED = "severity_based"
    CUSTOMER_REQUESTED = "customer_requested"
    AI_RECOMMENDED = "ai_recommended"
    INCIDENT_BASED = "incident_based"


class MessageVisibility(str, enum.Enum):
    CUSTOMER = "customer"
    INTERNAL = "internal"
    SYSTEM = "system"


class SenderType(str, enum.Enum):
    CUSTOMER = "customer"
    AGENT = "agent"
    AI = "ai"
    SYSTEM = "system"


class TicketLinkType(str, enum.Enum):
    INCIDENT = "incident"
    ISSUE = "issue"
    PR = "pr"
    COMMIT = "commit"
    DEPLOYMENT = "deployment"
    SECURITY_FINDING = "security_finding"
    SERVICE = "service"
    REPOSITORY = "repository"
    DOCUMENTATION = "documentation"
    BILLING_INVOICE = "billing_invoice"
    SUBSCRIPTION = "subscription"


class AutomationAction(str, enum.Enum):
    AUTO_CLASSIFY = "auto_classify"
    AUTO_ROUTE = "auto_route"
    SUGGEST_ANSWER = "suggest_answer"
    SEND_APPROVED_ANSWER = "send_approved_answer"
    CREATE_ISSUE = "create_issue"
    LINK_INCIDENT = "link_incident"
    UPDATE_TICKET = "update_ticket"
    CLOSE_AFTER_CONFIRMATION = "close_after_confirmation"
    ESCALATE = "escalate"
    REQUEST_HUMAN = "request_human"


class FeedbackType(str, enum.Enum):
    CSAT = "csat"
    AI_RATING = "ai_rating"
    RESOLUTION = "resolution"
    RESPONSE = "response"


# ─── State transitions ────────────────────────────────────────────────
TICKET_TRANSITIONS: dict[TicketStatus, list[TicketStatus]] = {
    TicketStatus.NEW: [TicketStatus.OPEN],
    TicketStatus.OPEN: [TicketStatus.IN_PROGRESS, TicketStatus.WAITING_CUSTOMER,
                        TicketStatus.WAITING_INTERNAL, TicketStatus.ESCALATED,
                        TicketStatus.RESOLVED, TicketStatus.CLOSED],
    TicketStatus.IN_PROGRESS: [TicketStatus.WAITING_CUSTOMER, TicketStatus.WAITING_INTERNAL,
                               TicketStatus.ESCALATED, TicketStatus.RESOLVED, TicketStatus.CLOSED],
    TicketStatus.WAITING_CUSTOMER: [TicketStatus.OPEN, TicketStatus.IN_PROGRESS,
                                    TicketStatus.ESCALATED, TicketStatus.RESOLVED, TicketStatus.CLOSED],
    TicketStatus.WAITING_INTERNAL: [TicketStatus.OPEN, TicketStatus.IN_PROGRESS,
                                    TicketStatus.ESCALATED, TicketStatus.RESOLVED, TicketStatus.CLOSED],
    TicketStatus.ESCALATED: [TicketStatus.IN_PROGRESS, TicketStatus.WAITING_CUSTOMER,
                             TicketStatus.WAITING_INTERNAL, TicketStatus.RESOLVED, TicketStatus.CLOSED],
    TicketStatus.RESOLVED: [TicketStatus.CLOSED, TicketStatus.REOPENED],
    TicketStatus.CLOSED: [TicketStatus.REOPENED],
    TicketStatus.REOPENED: [TicketStatus.OPEN, TicketStatus.IN_PROGRESS, TicketStatus.ESCALATED],
}

TICKET_ACTIVE_STATUSES = {
    TicketStatus.NEW, TicketStatus.OPEN, TicketStatus.IN_PROGRESS,
    TicketStatus.WAITING_CUSTOMER, TicketStatus.WAITING_INTERNAL,
    TicketStatus.ESCALATED, TicketStatus.REOPENED,
}

# ─── Article state transitions ────────────────────────────────────────
ARTICLE_TRANSITIONS: dict[ArticleStatus, list[ArticleStatus]] = {
    ArticleStatus.DRAFT: [ArticleStatus.REVIEW, ArticleStatus.ARCHIVED],
    ArticleStatus.REVIEW: [ArticleStatus.PUBLISHED, ArticleStatus.DRAFT, ArticleStatus.ARCHIVED],
    ArticleStatus.PUBLISHED: [ArticleStatus.DRAFT, ArticleStatus.ARCHIVED],
    ArticleStatus.ARCHIVED: [ArticleStatus.DRAFT],
}

# ─── Default SLA policies (first_response_minutes, resolution_minutes) ─
DEFAULT_SLA_POLICIES: dict[TicketPriority, tuple[int, int]] = {
    TicketPriority.LOW: (2880, 10080),       # 2 days / 7 days
    TicketPriority.NORMAL: (1440, 4320),     # 1 day / 3 days
    TicketPriority.HIGH: (480, 1440),        # 8 hours / 1 day
    TicketPriority.URGENT: (120, 480),       # 2 hours / 8 hours
    TicketPriority.CRITICAL: (30, 240),      # 30 min / 4 hours
}

# ─── Priority is configurable per plan tier ───────────────────────────
PLAN_SLA_MULTIPLIER: dict[str, float] = {
    "free": 2.0,
    "starter": 1.5,
    "professional": 1.0,
    "team": 0.75,
    "business": 0.5,
    "enterprise": 0.25,
}

# ─── Reopen policy ────────────────────────────────────────────────────
REOPEN_WINDOW_DAYS = 30

# ─── Duplicate detection ──────────────────────────────────────────────
DUPLICATE_SIMILARITY_THRESHOLD = 0.6

# ─── AI classification confidence ─────────────────────────────────────
AI_CONFIDENCE_HUMAN_REVIEW_THRESHOLD = 0.6

# ─── Attachment limits ────────────────────────────────────────────────
MAX_ATTACHMENT_SIZE_MB = 25
ALLOWED_ATTACHMENT_TYPES = {
    "image/png", "image/jpeg", "image/gif", "image/webp",
    "application/pdf", "text/plain", "text/csv", "text/markdown",
    "application/json", "application/zip",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

# ─── Knowledge article source types ───────────────────────────────────
class KnowledgeSource(str, enum.Enum):
    OFFICIAL_DOCS = "official_docs"
    RUNBOOK = "runbook"
    FAQ = "faq"
    RESOLVED_TICKET = "resolved_ticket"
    POSTMORTEM = "postmortem"
    RELEASE_NOTES = "release_notes"
    PRODUCT_DOCS = "product_docs"
