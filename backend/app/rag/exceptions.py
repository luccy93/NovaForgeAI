"""Volume 43 — RAG layer exceptions.

Explicit, typed failures so the system fails loudly (never silently) when
evidence is insufficient, permissions are missing, or an index is not ready.
"""

from __future__ import annotations


class RagError(Exception):
    """Base class for all RAG-layer errors."""


class PermissionDeniedError(RagError):
    """The caller is not allowed to access the requested source/result."""


class SourceNotFoundError(RagError):
    """A referenced knowledge source or chunk does not exist."""


class IndexNotReadyError(RagError):
    """Requested index version is not validated/activated."""


class StaleKnowledgeError(RagError):
    """The only available knowledge is stale and disallowed by policy."""


class InsufficientEvidenceError(RagError):
    """Retrieval could not gather enough supporting evidence.

    Carries an :class:`Answerability` so agents can decide whether to request
    additional retrieval rather than hallucinate.
    """

    def __init__(
        self,
        message: str,
        answerability: str = "INSUFFICIENT",
        evidence: list | None = None,
    ) -> None:
        super().__init__(message)
        self.answerability = answerability
        self.evidence = evidence or []


class CitationValidationError(RagError):
    """A citation failed validation (missing source, bad lines, no match)."""

    def __init__(
        self,
        message: str,
        invalid_citations: list | None = None,
    ) -> None:
        super().__init__(message)
        self.invalid_citations = invalid_citations or []
