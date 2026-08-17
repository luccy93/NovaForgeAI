"""Typed data models for the NovaForge SDK."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class User:
    id: str
    email: str
    username: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None


@dataclass
class Organization:
    id: str
    name: str
    slug: str
    description: Optional[str] = None
    plan: str = "free"
    is_active: bool = True
    member_count: int = 0
    created_at: Optional[datetime] = None


@dataclass
class Repository:
    id: str
    name: str
    full_name: str
    description: Optional[str] = None
    private: bool = True
    language: Optional[str] = None
    default_branch: str = "main"
    created_at: Optional[datetime] = None


@dataclass
class Conversation:
    id: str
    title: str
    message_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class Message:
    id: str
    role: str
    content: str
    created_at: Optional[datetime] = None


@dataclass
class Agent:
    name: str
    role: str
    description: str = ""
    version: str = "1.0.0"
    goals: list[str] = field(default_factory=list)


@dataclass
class AgentRun:
    id: str
    agent: str
    output: str = ""
    status: str = "pending"
    duration_ms: Optional[int] = None
    tokens_used: Optional[int] = None
    error: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class PipelineResult:
    workflow_id: str
    status: str
    steps: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class Notification:
    id: str
    title: str
    body: str
    notification_type: str = "system"
    is_read: bool = False
    created_at: Optional[datetime] = None


@dataclass
class BillingPlan:
    id: str
    name: str
    description: str = ""
    price_monthly: int = 0
    features: list[str] = field(default_factory=list)


@dataclass
class Subscription:
    id: str
    plan_id: str
    status: str = "active"
    current_period_end: Optional[datetime] = None


@dataclass
class FeatureFlag:
    name: str
    enabled: bool = False
    config: dict[str, Any] = field(default_factory=dict)


# ─── DevTools models ─────────────────────────────────────────────────


@dataclass
class DevSession:
    session_id: str
    client_type: str
    client_version: str = "1.0.0"
    organization_id: Optional[str] = None
    repository_id: Optional[str] = None
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    capabilities: list[str] = field(default_factory=list)


@dataclass
class ContextResult:
    context_id: str
    file_context: Optional[dict] = None
    symbols: list[dict] = field(default_factory=list)
    rag_results: list[dict] = field(default_factory=list)
    graph_context: list[dict] = field(default_factory=list)
    total_tokens_estimate: int = 0


@dataclass
class CodeActionResult:
    action_id: str
    action: str
    file_path: str
    original_code: str
    proposed_code: str
    explanation: str = ""
    diff: str = ""
    confidence: float = 0.0
    citations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ReviewResult:
    review_id: str
    summary: str
    findings: list[dict] = field(default_factory=list)
    score: float = 0.0
    files_reviewed: int = 0
    lines_reviewed: int = 0


@dataclass
class SearchResultItem:
    id: str
    score: float
    file_path: str
    line: int
    content: str
    symbol_type: str = ""
    symbol_name: str = ""
    repository: str = ""
