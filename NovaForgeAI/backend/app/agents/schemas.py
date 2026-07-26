"""Agent-specific schemas, enums, and data classes."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class AgentStatus(str, Enum):
    idle = "idle"
    running = "running"
    completed = "completed"
    failed = "failed"
    blocked = "blocked"
    cancelled = "cancelled"


class AgentRole(str, Enum):
    planner = "planner"
    repository_intelligence = "repository_intelligence"
    architect = "architect"
    code_reviewer = "code_reviewer"
    refactorer = "refactorer"
    documenter = "documenter"
    tester = "tester"
    security = "security"
    devops = "devops"
    deployment = "deployment"
    analytics = "analytics"
    performance = "performance"
    database = "database"
    api_agent = "api_agent"
    frontend = "frontend"
    backend = "backend"
    bug_investigator = "bug_investigator"
    release_manager = "release_manager"
    compliance = "compliance"
    researcher = "researcher"


class RiskLevel(str, Enum):
    none = "none"
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class MemoryScope(str, Enum):
    short_term = "short_term"
    long_term = "long_term"
    repository = "repository"
    organization = "organization"
    decision = "decision"
    architecture = "architecture"


@dataclass
class ToolResult:
    success: bool
    output: str
    error: Optional[str] = None
    duration_ms: Optional[int] = None
    data: Optional[Any] = None


@dataclass
class AgentDecision:
    evidence: list[str] = field(default_factory=list)
    confidence: float = 0.0
    files_affected: list[str] = field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.none
    estimated_impact: str = ""
    suggested_validation: str = ""
    rollback_strategy: str = ""
    reasoning: str = ""


@dataclass
class AgentResult:
    agent_name: str
    status: AgentStatus
    output: str
    decision: Optional[AgentDecision] = None
    tool_calls: list[ToolResult] = field(default_factory=list)
    duration_ms: Optional[int] = None
    tokens_used: Optional[int] = None
    model_used: Optional[str] = None
    error: Optional[str] = None
    checkpoint: Optional[dict] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class RetryPolicy:
    max_retries: int = 3
    backoff_base: float = 2.0
    max_delay: float = 60.0
    retryable_exceptions: tuple = (TimeoutError, ConnectionError)


@dataclass
class AgentConfig:
    name: str
    role: AgentRole
    version: str = "1.0.0"
    description: str = ""
    goals: list[str] = field(default_factory=list)
    model: str = "gpt-4o"
    temperature: float = 0.3
    max_tokens: int = 4096
    timeout_seconds: int = 120
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    require_human_approval: bool = False
    permissions: list[str] = field(default_factory=lambda: ["read"])
    telemetry_enabled: bool = True
    max_tool_calls: int = 25
