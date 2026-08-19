"""Volume 43 — RAG layer shared schemas (dataclasses).

These are the in-memory representations passed between ingestion, retrieval,
reranking, context assembly and citation validation. They are deliberately
framework-agnostic (no Pydantic) so they can be unit-tested without a running
web stack.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class SourceType(str, Enum):
    REPOSITORY = "repository"
    SOURCE_FILE = "source_file"
    DOCUMENTATION = "documentation"
    MARKDOWN = "markdown"
    PDF = "pdf"
    TICKET = "ticket"
    ISSUE = "issue"
    PR = "pr"
    WIKI = "wiki"
    API_SPEC = "api_spec"
    DATABASE = "database"
    UPLOAD = "upload"
    CONVERSATION = "conversation"
    EXTERNAL = "external"


class IngestionStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    INDEXED = "indexed"
    VALIDATED = "validated"
    FAILED = "failed"
    STALE = "stale"
    DELETED = "deleted"


class QueryIntent(str, Enum):
    CODE_SEARCH = "code_search"
    SYMBOL_LOOKUP = "symbol_lookup"
    ARCHITECTURE = "architecture"
    DOCUMENTATION = "documentation"
    BUG_INVESTIGATION = "bug_investigation"
    DEPENDENCY_ANALYSIS = "dependency_analysis"
    SECURITY = "security"
    NL_KNOWLEDGE = "nl_knowledge"


class Answerability(str, Enum):
    HIGH_CONFIDENCE = "HIGH_CONFIDENCE"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"


class RetrievalMethod(str, Enum):
    LEXICAL = "lexical"
    VECTOR = "vector"
    SYMBOL = "symbol"
    GRAPH = "graph"
    METADATA = "metadata"
    HYBRID = "hybrid"


@dataclass
class RetrievedChunk:
    """A single retrieved unit of knowledge with all provenance metadata."""

    chunk_id: str
    content: str
    source_type: str = SourceType.DOCUMENTATION.value
    repository_id: Optional[str] = None
    source_id: Optional[str] = None
    source_version_id: Optional[str] = None
    file_path: Optional[str] = None
    symbol: Optional[str] = None
    language: Optional[str] = None
    branch: Optional[str] = None
    commit: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    snippet: str = ""
    embedding_model: Optional[str] = None
    embedding_version: Optional[str] = None
    permissions: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    scores: dict = field(default_factory=dict)
    retrieval_method: str = RetrievalMethod.HYBRID.value
    created_at: Optional[datetime] = None

    @property
    def id(self) -> str:
        return self.chunk_id

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "content": self.content,
            "source_type": self.source_type,
            "repository_id": self.repository_id,
            "source_id": self.source_id,
            "source_version_id": self.source_version_id,
            "file_path": self.file_path,
            "symbol": self.symbol,
            "language": self.language,
            "branch": self.branch,
            "commit": self.commit,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "snippet": self.snippet,
            "embedding_model": self.embedding_model,
            "embedding_version": self.embedding_version,
            "permissions": self.permissions,
            "metadata": self.metadata,
            "scores": self.scores,
            "retrieval_method": self.retrieval_method,
        }


@dataclass
class Citation:
    """A validated citation attached to generated content."""

    source_id: str
    chunk_id: str
    file_path: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    symbol: Optional[str] = None
    commit: Optional[str] = None
    snippet: str = ""
    retrieval_method: str = ""
    confidence: float = 1.0

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "chunk_id": self.chunk_id,
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "symbol": self.symbol,
            "commit": self.commit,
            "snippet": self.snippet,
            "retrieval_method": self.retrieval_method,
            "confidence": self.confidence,
        }


@dataclass
class ContextSet:
    """Assembled, budget-aware model context with citations."""

    chunks: list[RetrievedChunk] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    context_text: str = ""
    token_count: int = 0
    budget: dict = field(default_factory=dict)
    answerability: str = Answerability.PARTIAL.value
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "chunks": [c.to_dict() for c in self.chunks],
            "citations": [c.to_dict() for c in self.citations],
            "context_text": self.context_text,
            "token_count": self.token_count,
            "budget": self.budget,
            "answerability": self.answerability,
            "notes": self.notes,
        }


@dataclass
class QueryClassification:
    intent: str = QueryIntent.NL_KNOWLEDGE.value
    confidence: float = 0.5
    strategies: list[str] = field(default_factory=list)
    filters: dict = field(default_factory=dict)
    expansion_terms: list[str] = field(default_factory=list)


@dataclass
class RetrievalPlan:
    """Produced by the query router: which strategies + weights + filters."""

    intent: str
    strategies: list[str]
    weights: dict
    filters: dict
    expansion_terms: list[str] = field(default_factory=list)


@dataclass
class EvaluationMetrics:
    recall_at_k: float = 0.0
    precision_at_k: float = 0.0
    mrr: float = 0.0
    ndcg: float = 0.0
    citation_accuracy: float = 0.0
    citation_coverage: float = 0.0
    groundedness: float = 0.0
    retrieval_latency_ms: float = 0.0
    notes: dict = field(default_factory=dict)


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
