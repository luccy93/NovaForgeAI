"""Event model - standardized event envelope, categories, validation, versioning, idempotency."""
import json, uuid
from dataclasses import dataclass, field, asdict
from typing import Optional, Any
from datetime import datetime, timezone


class EventCategory:
    """Event categories used across the platform."""
    REPOSITORY = "repository"
    COMMIT = "commit"
    PULL_REQUEST = "pull_request"
    ISSUE = "issue"
    DEPLOYMENT = "deployment"
    BUILD = "build"
    SECURITY = "security"
    TEST = "test"
    AI_REQUEST = "ai_request"
    AI_RESPONSE = "ai_response"
    AGENT_EXECUTION = "agent_execution"
    RAG_SEARCH = "rag_search"
    EMBEDDING = "embedding"
    USER = "user"
    WORKSPACE = "workspace"
    BILLING = "billing"
    MARKETPLACE = "marketplace"
    INFRASTRUCTURE = "infrastructure"
    INCIDENT = "incident"
    WORKFLOW = "workflow"

    ALL = [
        REPOSITORY, COMMIT, PULL_REQUEST, ISSUE, DEPLOYMENT, BUILD, SECURITY,
        TEST, AI_REQUEST, AI_RESPONSE, AGENT_EXECUTION, RAG_SEARCH, EMBEDDING,
        USER, WORKSPACE, BILLING, MARKETPLACE, INFRASTRUCTURE, INCIDENT, WORKFLOW,
    ]


class EventType:
    """Valid event types grouped by category."""
    CATEGORY = {
        EventCategory.REPOSITORY: ["repository.created", "repository.updated", "repository.archived"],
        EventCategory.COMMIT: ["commit.pushed", "commit.amended"],
        EventCategory.PULL_REQUEST: ["pull_request.opened", "pull_request.merged", "pull_request.reviewed", "pull_request.closed"],
        EventCategory.ISSUE: ["issue.opened", "issue.closed", "issue.commented"],
        EventCategory.DEPLOYMENT: ["deployment.started", "deployment.succeeded", "deployment.failed", "deployment.rollback"],
        EventCategory.BUILD: ["build.started", "build.succeeded", "build.failed"],
        EventCategory.SECURITY: ["security.scan", "security.vulnerability", "security.secret_found", "security.incident"],
        EventCategory.TEST: ["test.execution", "test.suite_finished", "test.flaky_detected"],
        EventCategory.AI_REQUEST: ["ai.request_started", "ai.request_completed", "ai.request_failed"],
        EventCategory.AI_RESPONSE: ["ai.response_generated", "ai.response_streamed"],
        EventCategory.AGENT_EXECUTION: ["agent.execution_started", "agent.execution_completed", "agent.execution_failed", "agent.decision"],
        EventCategory.RAG_SEARCH: ["rag.search", "rag.retrieval", "rag.rerank", "rag.citation"],
        EventCategory.EMBEDDING: ["embedding.generated", "embedding.queried"],
        EventCategory.USER: ["user.login", "user.logout", "user.session", "user.preference_changed"],
        EventCategory.WORKSPACE: ["workspace.created", "workspace.updated", "workspace.member_added"],
        EventCategory.BILLING: ["billing.usage_recorded", "billing.invoice_created", "billing.payment_succeeded", "billing.payment_failed"],
        EventCategory.MARKETPLACE: ["marketplace.install", "marketplace.uninstall", "marketplace.usage"],
        EventCategory.INFRASTRUCTURE: ["infra.metric_sample", "infra.scaling_event", "infra.capacity_change"],
        EventCategory.INCIDENT: ["incident.created", "incident.updated", "incident.resolved"],
        EventCategory.WORKFLOW: ["workflow.started", "workflow.completed", "workflow.failed"],
    }

    @staticmethod
    def category_of(event_type: str) -> Optional[str]:
        for cat, types in EventType.CATEGORY.items():
            if event_type in types:
                return cat
        return None


REQUIRED_FIELDS = [
    "event_id", "event_type", "event_version", "timestamp", "organization_id",
    "source", "correlation_id", "trace_id", "payload",
]


@dataclass
class Event:
    """The standardized, versioned, idempotent event envelope."""
    event_id: str = ""
    event_type: str = ""
    event_version: int = 1
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    organization_id: str = ""
    workspace_id: str = ""
    project_id: str = ""
    repository_id: str = ""
    user_id: str = ""
    actor_type: str = "system"
    source: str = "lakehouse"
    correlation_id: str = ""
    trace_id: str = ""
    idempotency_key: str = ""
    payload: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.event_id:
            self.event_id = uuid.uuid4().hex
        if not self.correlation_id:
            self.correlation_id = self.event_id
        if not self.trace_id:
            self.trace_id = self.event_id
        if not self.idempotency_key:
            self.idempotency_key = f"{self.event_type}:{self.event_id}"

    @property
    def category(self) -> str:
        return EventType.category_of(self.event_type) or "unknown"

    def validate(self) -> list[str]:
        errors = []
        for f in REQUIRED_FIELDS:
            if getattr(self, f, None) is None:
                errors.append(f"missing required field: {f}")
        if self.event_version < 1:
            errors.append("event_version must be >= 1")
        if self.category == "unknown":
            errors.append(f"unknown event_type: {self.event_type}")
        return errors

    def is_valid(self) -> bool:
        return not self.validate()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Event":
        allowed = {f for f in REQUIRED_FIELDS}
        allowed = cls.__dataclass_fields__.keys() if hasattr(cls, "__dataclass_fields__") else allowed
        return cls(**{k: v for k, v in data.items() if k in allowed})


class EventStore:
    """Versioned, idempotent, replayable in-memory event store."""

    def __init__(self, max_events: int = 200000):
        self.events: list[dict] = []
        self._keys: set[str] = set()
        self.max_events = max_events
        self.duplicates_rejected = 0

    def append(self, event: Event) -> bool:
        if event.idempotency_key in self._keys:
            self.duplicates_rejected += 1
            return False
        record = event.to_dict()
        record["_offset"] = len(self.events)
        self.events.append(record)
        self._keys.add(event.idempotency_key)
        if len(self.events) > self.max_events:
            self.events.pop(0)
        return True

    def get(self, offset: int = 0, limit: Optional[int] = None) -> list[dict]:
        result = self.events[offset:]
        if limit is not None:
            result = result[:limit]
        return result

    def replay(self, from_offset: int = 0) -> list[dict]:
        return self.get(from_offset)

    def checkpoint(self) -> int:
        return len(self.events)

    def count(self) -> int:
        return len(self.events)

    def filter(self, **filters) -> list[dict]:
        result = []
        for e in self.events:
            match = True
            for k, v in filters.items():
                if e.get(k) != v:
                    match = False
                    break
            if match:
                result.append(e)
        return result

    def clear(self) -> None:
        self.events.clear()
        self._keys.clear()