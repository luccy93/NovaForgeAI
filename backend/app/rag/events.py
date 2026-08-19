"""Volume 43 — RAG domain events.

Reuses the existing ``InMemoryEventBus`` / ``EventEmitter`` plumbing from
code intelligence and adds the RAG lifecycle event types. All events carry a
stable ``event_id`` so consumers (cache invalidation, evaluation, security
review) can be idempotent.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from app.code_intelligence.events import EventEmitter, InMemoryEventBus

logger = logging.getLogger(__name__)


class RAGEventType(str, Enum):
    KNOWLEDGE_SOURCE_ADDED = "knowledge_source_added"
    KNOWLEDGE_SOURCE_UPDATED = "knowledge_source_updated"
    KNOWLEDGE_SOURCE_DELETED = "knowledge_source_deleted"
    RAG_INDEX_STARTED = "rag_index_started"
    RAG_INDEX_COMPLETED = "rag_index_completed"
    RAG_INDEX_FAILED = "rag_index_failed"
    RAG_INDEX_ACTIVATED = "rag_index_activated"
    EMBEDDING_UPDATED = "embedding_updated"
    KNOWLEDGE_STALE = "knowledge_stale"
    PERMISSION_CHANGED = "permission_changed"
    CITATION_VALIDATION_FAILED = "citation_validation_failed"
    RAG_EVALUATION_FAILED = "rag_evaluation_failed"


_RAG_EVENT_PAYLOAD_FIELDS = (
    "source_id", "source_version_id", "repository_id", "tenant_id",
    "chunk_count", "embedding_model", "detail",
)


@dataclass
class RAGEvent:
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = ""
    repository_id: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "repository_id": self.repository_id,
            "timestamp": self.timestamp.isoformat(),
            "payload": self.payload,
        }


def build_rag_event(event_type: RAGEventType | str, repository_id: Optional[str] = None, **kwargs) -> RAGEvent:
    payload = {k: v for k, v in kwargs.items() if k in _RAG_EVENT_PAYLOAD_FIELDS}
    return RAGEvent(event_type=str(event_type), repository_id=repository_id, payload=payload)


class RAGEventEmitter:
    """Thin facade over the code-intelligence EventEmitter for RAG events."""

    def __init__(
        self,
        repository_id: Optional[str] = None,
        bus: Optional[InMemoryEventBus] = None,
    ) -> None:
        self._repository_id = repository_id
        self._emitter = EventEmitter(repository_id=str(repository_id or "rag"), in_memory_bus=bus or InMemoryEventBus())

    def emit(self, event_type: RAGEventType | str, **kwargs) -> RAGEvent:
        ev = build_rag_event(event_type, self._repository_id, **kwargs)
        try:
            self._emitter.emit_to_log(str(event_type), payload=ev.payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning("rag event emit failed: %s", exc)
        return ev

    def emit_invalid_citation(self, repository_id: Optional[str], detail: str) -> RAGEvent:
        return self.emit(RAGEventType.CITATION_VALIDATION_FAILED, repository_id=repository_id, detail=detail)


# A shared in-process bus for subscribers (cache invalidation, etc.).
rag_event_bus = InMemoryEventBus()
