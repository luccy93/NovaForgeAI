from __future__ import annotations

import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)


def build_citation(document, source=None) -> dict:
    """Construct a citation dict from a KnowledgeDocument record and optional KnowledgeSource."""
    try:
        citation = {
            "source_name": getattr(source, "name", None) if source else None,
            "doc_type": getattr(document, "doc_type", None),
            "title": getattr(document, "title", None),
            "version": getattr(document, "version", None),
            "external_id": getattr(document, "external_id", None),
            "url": getattr(document, "url", None),
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "classification": getattr(document, "classification", "INTERNAL"),
        }
        return citation
    except Exception:
        log.warning("Failed to build citation from document %s", getattr(document, "id", "?"), exc_info=True)
        return {
            "source_name": None,
            "doc_type": None,
            "title": None,
            "version": None,
            "external_id": None,
            "url": None,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "classification": "INTERNAL",
        }


def format_citation_text(citation: dict) -> str:
    """Format citation as a human-readable string like '[source_name] title (version)'."""
    try:
        parts: list[str] = []
        source_name = citation.get("source_name")
        title = citation.get("title")
        version = citation.get("version")

        if source_name:
            parts.append(f"[{source_name}]")
        if title:
            parts.append(title)
        if version:
            parts.append(f"({version})")

        return " ".join(parts) if parts else "[unknown source]"
    except Exception:
        return "[unknown source]"


def validate_citations(citations: list[dict]) -> list[dict]:
    """Filter out citations missing required fields (source_name, title)."""
    validated: list[dict] = []
    for c in citations:
        try:
            if c.get("source_name") and c.get("title"):
                validated.append(c)
        except Exception:
            continue
    return validated
