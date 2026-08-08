"""Formats RAG pipeline results into structured citations."""

import logging
from typing import Any

from app.schemas import Citation, CitationResponse

logger = logging.getLogger(__name__)


class CitationEngine:
    """Transforms raw RAG sources into numbered citations with formatted references."""

    def format_response(self, answer: str, sources: list[dict], confidence: float, model_used: str) -> CitationResponse:
        """Take raw RAG output and return a citation-grounded response."""
        citations = []
        for i, src in enumerate(sources, 1):
            text = (src.get("text") or src.get("content") or "")[:300]
            source_name = src.get("source", "unknown")
            source_type = src.get("type", "vector")
            score = src.get("score", 0.0)

            citations.append(
                Citation(
                    id=i,
                    text=text,
                    source=source_name,
                    source_type=source_type,
                    relevance_score=round(score, 4),
                )
            )

        annotated_answer = self._annotate_answer(answer, citations)
        return CitationResponse(
            answer=annotated_answer,
            citations=citations,
            confidence=round(confidence, 4),
            model_used=model_used,
        )

    def _annotate_answer(self, answer: str, citations: list[Citation]) -> str:
        """Add inline citation markers to the answer text."""
        if not citations:
            return answer

        citation_text = "\n\n---\n**Sources:**\n"
        for c in citations:
            tag = f"[{c.source_type.upper()}]" if c.source_type != "web" else "[WEB]"
            citation_text += f"\n[{c.id}] {tag} {c.source} (confidence: {c.relevance_score})"

        return answer + citation_text

    def empty_response(self, reason: str = "No relevant context found.") -> CitationResponse:
        return CitationResponse(
            answer=reason,
            citations=[],
            confidence=0.0,
            model_used="",
        )
