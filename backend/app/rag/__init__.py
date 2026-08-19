"""Volume 43 — Knowledge & Retrieval (RAG) layer.

Combines code, documents, repositories, architecture graphs, conversations
and enterprise knowledge into accurate, permission-aware, version-aware AI
context. Builds on the existing embedding / Qdrant / Neo4j / Redis / event
infrastructure and Volume 42 code intelligence.
"""

from app.rag.config import DEFAULT_RAG_CONFIG, RagConfig
from app.rag.exceptions import (
    CitationValidationError,
    IndexNotReadyError,
    InsufficientEvidenceError,
    PermissionDeniedError,
    RagError,
    SourceNotFoundError,
    StaleKnowledgeError,
)
from app.rag.ingestion import (
    Chunker,
    DocumentParser,
    Indexer,
    KnowledgeSourceRegistry,
    StaleDetector,
)
from app.rag.retrieval import RAGService
from app.rag.schemas import (
    Answerability,
    Citation,
    ContextSet,
    QueryClassification,
    QueryIntent,
    RetrievalMethod,
    RetrievalPlan,
    RetrievedChunk,
    SourceType,
    IngestionStatus,
)
from app.rag.models import (
    KnowledgeSource,
    KnowledgeSourceVersion,
    RagChunk,
    RagCitationRecord,
    RagContextSet,
    RagEvaluationRun,
    RagIngestionJob,
    RagQualityMetric,
    RagRetrievalLog,
)

__all__ = [
    "RagConfig",
    "DEFAULT_RAG_CONFIG",
    "RagError",
    "PermissionDeniedError",
    "SourceNotFoundError",
    "IndexNotReadyError",
    "StaleKnowledgeError",
    "InsufficientEvidenceError",
    "CitationValidationError",
    "Answerability",
    "Citation",
    "ContextSet",
    "QueryClassification",
    "QueryIntent",
    "RetrievalMethod",
    "RetrievalPlan",
    "RetrievedChunk",
    "SourceType",
    "IngestionStatus",
    "KnowledgeSource",
    "KnowledgeSourceVersion",
    "RagChunk",
    "RagIngestionJob",
    "RagRetrievalLog",
    "RagContextSet",
    "RagCitationRecord",
    "RagEvaluationRun",
    "RagQualityMetric",
]
