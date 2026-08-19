"""Volume 43 — Knowledge & Retrieval (RAG) layer configuration.

Central, explicit configuration for the RAG pipeline: collection names,
fusion/rerank weights, context budgets, diversity and citation behaviour.
All values are overridable via constructor so tests can use small budgets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ContextBudget:
    """Token budget allocation for a single retrieval/context assembly.

    The total is the hard ceiling; individual slots are soft guidance that
    the assembler respects while never silently dropping critical evidence.
    """

    total: int = 8000
    system: int = 1500
    conversation: int = 2000
    retrieval: int = 3500
    code: int = 2000
    tools: int = 1000
    output: int = 2000

    def __post_init__(self) -> None:
        if self.total <= 0:
            raise ValueError("ContextBudget.total must be positive")


@dataclass
class FusionWeights:
    """Reciprocal Rank Fusion / weighted combination weights.

    Weights are normalised at use time, so they only need to be relative.
    """

    lexical: float = 0.30
    semantic: float = 0.35
    symbol: float = 0.15
    graph: float = 0.10
    metadata: float = 0.05
    recency: float = 0.05


@dataclass
class RerankWeights:
    """Multi-factor reranking weights (used by the ``weighted`` reranker)."""

    query_relevance: float = 0.35
    semantic_similarity: float = 0.25
    symbol_relevance: float = 0.10
    graph_relevance: float = 0.10
    source_quality: float = 0.10
    freshness: float = 0.05
    permission_validity: float = 0.05


@dataclass
class RagConfig:
    """Top level RAG configuration.

    Instances are cheap to construct; the production system passes the same
    config object down through the ingestion and retrieval stacks.
    """

    # Vector collection used for knowledge chunks.
    knowledge_collection: str = "knowledge_chunks"
    # Collection used for repository/code chunks (reused from code intelligence).
    code_collection: str = "repository_chunks"
    # Collection used for documentation chunks.
    doc_collection: str = "documentation_chunks"

    # Tenant isolation is always enforced; these are the payload keys.
    tenant_payload_keys: list[str] = field(
        default_factory=lambda: ["tenant_id", "organization_id", "repository_id"]
    )

    fusion: FusionWeights = field(default_factory=FusionWeights)
    rerank: RerankWeights = field(default_factory=RerankWeights)
    budget: ContextBudget = field(default_factory=ContextBudget)

    # Reranking strategy: "rrf" | "weighted" | "cross_encoder".
    rerank_strategy: str = "weighted"
    rrf_k: int = 60

    # Diversity: maximum cosine/overlap before a chunk is considered redundant.
    diversity_threshold: float = 0.92
    max_context_chunks: int = 40

    # Citation validation toggles.
    validate_citations: bool = True
    require_content_match: bool = True
    drop_invalid_citations: bool = True

    # Retrieval defaults.
    default_limit: int = 20
    default_top_k_context: int = 12

    # Lexical / BM25 parameters.
    bm25_k1: float = 1.5
    bm25_b: float = 0.75

    # Embedding retry/backoff.
    embed_max_retries: int = 3
    embed_batch_size: int = 32

    # Graph traversal limits.
    graph_max_depth: int = 3
    graph_max_nodes: int = 50

    # Cache.
    cache_ttl_seconds: int = 300
    cache_namespace: str = "rag"

    # Staleness.
    stale_after_days: int = 30

    # Recency half-life (days) used by freshness scoring.
    recency_half_life_days: int = 90

    def collection_for(self, source_type: str) -> str:
        """Return the Qdrant collection name for a knowledge source type."""
        st = (source_type or "").lower()
        if st in ("code", "repository", "repo"):
            return self.code_collection
        if st in ("doc", "documentation", "docx", "wiki", "readme"):
            return self.doc_collection
        return self.knowledge_collection


# A module-level default, overridable per-call.
DEFAULT_RAG_CONFIG = RagConfig()
