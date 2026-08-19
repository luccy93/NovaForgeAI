"""Code Intelligence Engine — event emission and filtering.

Defines all domain events emitted by the indexing pipeline: repository
indexing lifecycle, file parsing, symbol discovery, graph updates,
embedding generation, index validation, activation, and staleness
detection.

Every event is idempotent: it carries a ``event_id`` (UUID4) that can be
used by consumers to deduplicate. Events are plain dataclasses with a
uniform shape (``event_id``, ``event_type``, ``repository_id``,
``timestamp``, ``payload``) so they serialise cleanly to JSON or
protobuf.

The ``EventEmitter`` facade exposes ``emit``, ``emit_to_log`` and an
abstract ``emit_to_bus`` hook that subclasses override to push events
to Redis, Kafka, SQS, etc. ``InMemoryEventBus`` is a TTL-capped,
thread-safe, in-memory bus suitable for unit tests.
"""

from __future__ import annotations

import abc
import logging
import time
import threading
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence, Type, Union

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Event type enum
# ---------------------------------------------------------------------------

class CodeEventType(str, Enum):
    """All code-intelligence event types."""

    REPOSITORY_INDEX_STARTED = "code_intelligence.repository_index.started"
    REPOSITORY_INDEX_PROGRESS = "code_intelligence.repository_index.progress"
    REPOSITORY_INDEX_COMPLETED = "code_intelligence.repository_index.completed"
    REPOSITORY_INDEX_FAILED = "code_intelligence.repository_index.failed"
    FILE_PARSED = "code_intelligence.file.parsed"
    SYMBOL_DISCOVERED = "code_intelligence.symbol.discovered"
    GRAPH_UPDATED = "code_intelligence.graph.updated"
    EMBEDDING_COMPLETED = "code_intelligence.embedding.completed"
    INDEX_VALIDATED = "code_intelligence.index.validated"
    INDEX_ACTIVATED = "code_intelligence.index.activated"
    INDEX_STALE = "code_intelligence.index.stale"


# ---------------------------------------------------------------------------
# Base event dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class CodeEvent:
    """Base class for all code-intelligence events.

    Attributes:
        event_id:     UUID4 string — unique per emission (idempotency key).
        event_type:   One of :class:`CodeEventType`.
        repository_id: UUID string identifying the repository.
        timestamp:    UTC-aware datetime of emission.
        payload:      Arbitrary JSON-safe dictionary with event-specific data.
    """

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: CodeEventType = CodeEventType.REPOSITORY_INDEX_STARTED
    repository_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "repository_id": self.repository_id,
            "timestamp": self.timestamp.isoformat(),
            "payload": dict(self.payload),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CodeEvent":
        ts = data.get("timestamp", "")
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts)
            except (ValueError, TypeError):
                ts = datetime.now(timezone.utc)
        elif not isinstance(ts, datetime):
            ts = datetime.now(timezone.utc)
        et_raw = data.get("event_type", "")
        try:
            et = CodeEventType(et_raw)
        except ValueError:
            et = CodeEventType.REPOSITORY_INDEX_STARTED
        return cls(
            event_id=data.get("event_id", str(uuid.uuid4())),
            event_type=et,
            repository_id=data.get("repository_id", ""),
            timestamp=ts,
            payload=data.get("payload", {}),
        )


# ---------------------------------------------------------------------------
# Typed event dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class RepositoryIndexStarted(CodeEvent):
    """Emitted when repository indexing begins."""

    event_type: CodeEventType = CodeEventType.REPOSITORY_INDEX_STARTED


@dataclass(frozen=True, slots=True)
class RepositoryIndexProgress(CodeEvent):
    """Periodic progress update during indexing.

    Payload keys: ``stage``, ``files_processed``, ``files_total``,
    ``symbols_extracted``, ``elapsed_seconds``.
    """

    event_type: CodeEventType = CodeEventType.REPOSITORY_INDEX_PROGRESS


@dataclass(frozen=True, slots=True)
class RepositoryIndexCompleted(CodeEvent):
    """Emitted when indexing finishes successfully.

    Payload keys: ``files_total``, ``symbols_extracted``,
    ``chunks_created``, ``duration_seconds``.
    """

    event_type: CodeEventType = CodeEventType.REPOSITORY_INDEX_COMPLETED


@dataclass(frozen=True, slots=True)
class RepositoryIndexFailed(CodeEvent):
    """Emitted when indexing fails.

    Payload keys: ``error``, ``stage``, ``traceback``.
    """

    event_type: CodeEventType = CodeEventType.REPOSITORY_INDEX_FAILED


@dataclass(frozen=True, slots=True)
class FileParsed(CodeEvent):
    """Emitted when a file is successfully parsed.

    Payload keys: ``file_path``, ``language``, ``line_count``,
    ``symbol_count``, ``parse_time_ms``.
    """

    event_type: CodeEventType = CodeEventType.FILE_PARSED


@dataclass(frozen=True, slots=True)
class SymbolDiscovered(CodeEvent):
    """Emitted when a new symbol is extracted.

    Payload keys: ``symbol_id``, ``name``, ``qualified_name``,
    ``symbol_type``, ``file_path``, ``start_line``, ``end_line``.
    """

    event_type: CodeEventType = CodeEventType.SYMBOL_DISCOVERED


@dataclass(frozen=True, slots=True)
class GraphUpdated(CodeEvent):
    """Emitted when the dependency/call graph is updated.

    Payload keys: ``edges_added``, ``nodes_added``,
    ``graph_type`` (call/import/dependency/inheritance).
    """

    event_type: CodeEventType = CodeEventType.GRAPH_UPDATED


@dataclass(frozen=True, slots=True)
class EmbeddingCompleted(CodeEvent):
    """Emitted when embeddings are generated for chunks.

    Payload keys: ``chunks_embedded``, ``model``, ``dimension``,
    ``duration_seconds``.
    """

    event_type: CodeEventType = CodeEventType.EMBEDDING_COMPLETED


@dataclass(frozen=True, slots=True)
class IndexValidated(CodeEvent):
    """Emitted when consistency validation passes.

    Payload keys: ``valid``, ``issues``, ``total_files``,
    ``total_chunks``, ``total_symbols``.
    """

    event_type: CodeEventType = CodeEventType.INDEX_VALIDATED


@dataclass(frozen=True, slots=True)
class IndexActivated(CodeEvent):
    """Emitted when a new index version is made active.

    Payload keys: ``version_number``, ``previous_index_id``,
    ``commit_sha``.
    """

    event_type: CodeEventType = CodeEventType.INDEX_ACTIVATED


@dataclass(frozen=True, slots=True)
class IndexStale(CodeEvent):
    """Emitted when an index is detected as stale.

    Payload keys: ``previous_index_id``, ``reason``,
    ``superseded_by``.
    """

    event_type: CodeEventType = CodeEventType.INDEX_STALE


# ---------------------------------------------------------------------------
# Registry: maps CodeEventType → concrete dataclass
# ---------------------------------------------------------------------------

_EVENT_REGISTRY: Dict[CodeEventType, Type[CodeEvent]] = {
    CodeEventType.REPOSITORY_INDEX_STARTED: RepositoryIndexStarted,
    CodeEventType.REPOSITORY_INDEX_PROGRESS: RepositoryIndexProgress,
    CodeEventType.REPOSITORY_INDEX_COMPLETED: RepositoryIndexCompleted,
    CodeEventType.REPOSITORY_INDEX_FAILED: RepositoryIndexFailed,
    CodeEventType.FILE_PARSED: FileParsed,
    CodeEventType.SYMBOL_DISCOVERED: SymbolDiscovered,
    CodeEventType.GRAPH_UPDATED: GraphUpdated,
    CodeEventType.EMBEDDING_COMPLETED: EmbeddingCompleted,
    CodeEventType.INDEX_VALIDATED: IndexValidated,
    CodeEventType.INDEX_ACTIVATED: IndexActivated,
    CodeEventType.INDEX_STALE: IndexStale,
}


def build_event(
    event_type: CodeEventType,
    repository_id: str,
    payload: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> CodeEvent:
    """Factory that returns the correct typed dataclass for *event_type*."""
    cls = _EVENT_REGISTRY.get(event_type, CodeEvent)
    return cls(
        event_type=event_type,
        repository_id=repository_id,
        payload=payload or {},
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Event validation
# ---------------------------------------------------------------------------

_REQUIRED_EVENT_FIELDS = frozenset({"event_id", "event_type", "repository_id", "timestamp", "payload"})


def validate_event(event: CodeEvent) -> List[str]:
    """Return a list of validation error strings; empty means valid."""
    errors: List[str] = []

    if not event.event_id:
        errors.append("event_id is required")
    else:
        try:
            uuid.UUID(event.event_id)
        except ValueError:
            errors.append(f"event_id is not a valid UUID: {event.event_id!r}")

    if not isinstance(event.event_type, CodeEventType):
        errors.append(f"event_type must be a CodeEventType, got {type(event.event_type).__name__}")

    if not event.repository_id:
        errors.append("repository_id is required")

    if not isinstance(event.timestamp, datetime):
        errors.append("timestamp must be a datetime")
    elif event.timestamp.tzinfo is None:
        errors.append("timestamp must be timezone-aware (UTC)")

    if not isinstance(event.payload, dict):
        errors.append("payload must be a dict")

    return errors


def validate_event_dict(data: Dict[str, Any]) -> List[str]:
    """Validate a raw dictionary before constructing a :class:`CodeEvent`."""
    errors: List[str] = []
    missing = _REQUIRED_EVENT_FIELDS - set(data.keys())
    if missing:
        errors.append(f"missing required fields: {sorted(missing)}")
    return errors


# ---------------------------------------------------------------------------
# Abstract event bus
# ---------------------------------------------------------------------------

EventCallback = Callable[[CodeEvent], Any]


class AbstractEventBus(abc.ABC):
    """Abstract base for event buses (Redis, Kafka, SQS, etc.)."""

    @abc.abstractmethod
    async def publish(self, event: CodeEvent) -> None:
        """Publish *event* to the bus."""

    @abc.abstractmethod
    async def subscribe(self, event_type: CodeEventType, callback: EventCallback) -> None:
        """Register *callback* for *event_type*."""

    @abc.abstractmethod
    async def unsubscribe(self, event_type: CodeEventType, callback: EventCallback) -> None:
        """Remove *callback* from *event_type*."""

    @abc.abstractmethod
    async def get_recent(
        self,
        event_type: Optional[CodeEventType] = None,
        limit: int = 50,
    ) -> List[CodeEvent]:
        """Return the most recent events, optionally filtered by type."""


# ---------------------------------------------------------------------------
# In-memory event bus (for tests / lightweight usage)
# ---------------------------------------------------------------------------

class InMemoryEventBus:
    """Thread-safe, TTL-capped, in-memory event bus.

    Designed for unit tests and local development.  Events older than
    ``ttl_seconds`` are pruned on every write.  A ``max_size`` hard cap
    prevents unbounded growth.
    """

    def __init__(self, ttl_seconds: int = 3600, max_size: int = 10_000) -> None:
        self._lock = threading.Lock()
        self._events: List[CodeEvent] = []
        self._subscribers: Dict[CodeEventType, List[EventCallback]] = {}
        self._global_subscribers: List[EventCallback] = []
        self._ttl = timedelta(seconds=ttl_seconds)
        self._max_size = max_size

    def publish(self, event: CodeEvent) -> None:
        """Synchronous publish — suitable for tests."""
        with self._lock:
            self._prune_locked()
            self._events.append(event)
            if len(self._events) > self._max_size:
                self._events = self._events[-self._max_size:]

        self._dispatch(event)

    async def publish_async(self, event: CodeEvent) -> None:
        """Async-compatible publish (delegates to sync path)."""
        self.publish(event)

    def subscribe(self, event_type: CodeEventType, callback: EventCallback) -> None:
        with self._lock:
            self._subscribers.setdefault(event_type, []).append(callback)

    def subscribe_all(self, callback: EventCallback) -> None:
        """Subscribe to every event type."""
        with self._lock:
            self._global_subscribers.append(callback)

    def unsubscribe(self, event_type: CodeEventType, callback: EventCallback) -> None:
        with self._lock:
            cbs = self._subscribers.get(event_type)
            if cbs:
                self._subscribers[event_type] = [c for c in cbs if c is not callback]

    def unsubscribe_all(self, callback: EventCallback) -> None:
        with self._lock:
            self._global_subscribers = [c for c in self._global_subscribers if c is not callback]

    def get_recent(
        self,
        event_type: Optional[CodeEventType] = None,
        limit: int = 50,
    ) -> List[CodeEvent]:
        """Return up to *limit* most-recent events, newest first."""
        with self._lock:
            self._prune_locked()
            if event_type is not None:
                filtered = [e for e in self._events if e.event_type == event_type]
            else:
                filtered = list(self._events)
        return list(reversed(filtered[-limit:]))

    def get_all(self) -> List[CodeEvent]:
        with self._lock:
            self._prune_locked()
            return list(self._events)

    def count(self, event_type: Optional[CodeEventType] = None) -> int:
        with self._lock:
            self._prune_locked()
            if event_type is not None:
                return sum(1 for e in self._events if e.event_type == event_type)
            return len(self._events)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()

    def has_event_id(self, event_id: str) -> bool:
        """Check whether an event with this *event_id* has already been seen."""
        with self._lock:
            return any(e.event_id == event_id for e in self._events)

    # -- internal helpers ---------------------------------------------------

    def _dispatch(self, event: CodeEvent) -> None:
        callbacks: List[EventCallback] = []
        with self._lock:
            callbacks.extend(self._subscribers.get(event.event_type, []))
            callbacks.extend(self._global_subscribers)
        for cb in callbacks:
            try:
                cb(event)
            except Exception:
                logger.exception("Event callback failed for %s", event.event_type.value)

    def _prune_locked(self) -> None:
        """Remove expired events (called while holding _lock)."""
        if not self._events:
            return
        cutoff = datetime.now(timezone.utc) - self._ttl
        idx = 0
        while idx < len(self._events) and self._events[idx].timestamp < cutoff:
            idx += 1
        if idx:
            del self._events[:idx]


# ---------------------------------------------------------------------------
# Event filter
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class EventFilter:
    """Composable filter for querying events.

    All fields are optional; omitted fields are not applied.

    Attributes:
        event_types:    Restrict to these :class:`CodeEventType` values.
        repository_id:  Restrict to this repository UUID.
        after:          Only events after this datetime (inclusive).
        before:         Only events before this datetime (inclusive).
        event_ids:      Restrict to these specific event IDs.
        payload_key:    Require this key to exist in the payload.
        payload_value:  Require the key to have this exact value.
    """

    event_types: Optional[List[CodeEventType]] = None
    repository_id: Optional[str] = None
    after: Optional[datetime] = None
    before: Optional[datetime] = None
    event_ids: Optional[List[str]] = None
    payload_key: Optional[str] = None
    payload_value: Optional[Any] = None

    def matches(self, event: CodeEvent) -> bool:
        """Return ``True`` if *event* passes every configured criterion."""
        if self.event_types and event.event_type not in self.event_types:
            return False
        if self.repository_id and event.repository_id != self.repository_id:
            return False
        if self.after and event.timestamp < self.after:
            return False
        if self.before and event.timestamp > self.before:
            return False
        if self.event_ids and event.event_id not in self.event_ids:
            return False
        if self.payload_key is not None:
            if self.payload_key not in event.payload:
                return False
            if self.payload_value is not None and event.payload[self.payload_key] != self.payload_value:
                return False
        return True

    def apply(self, events: Sequence[CodeEvent]) -> List[CodeEvent]:
        """Return a filtered copy of *events*."""
        return [e for e in events if self.matches(e)]


# ---------------------------------------------------------------------------
# EventEmitter — main facade
# ---------------------------------------------------------------------------

class EventEmitter:
    """High-level event emitter used by pipeline stages.

    Usage::

        emitter = EventEmitter(repository_id="repo-uuid")
        emitter.emit(CodeEventType.FILE_PARSED, {"file_path": "src/main.py"})
        emitter.emit_to_log(CodeEventType.SYMBOL_DISCOVERED, {"name": "Foo"})

    ``emit_to_bus`` delegates to an injected :class:`AbstractEventBus`
    (or ``None`` for no-op).  ``get_recent_events`` queries the bus
    for recent events, optionally through an :class:`EventFilter`.
    """

    def __init__(
        self,
        repository_id: str,
        event_bus: Optional[AbstractEventBus] = None,
        in_memory_bus: Optional[InMemoryEventBus] = None,
    ) -> None:
        self._repository_id = repository_id
        self._event_bus = event_bus
        self._in_memory_bus = in_memory_bus
        self._recent: List[CodeEvent] = []
        self._lock = threading.Lock()

    @property
    def repository_id(self) -> str:
        return self._repository_id

    # -- emission -----------------------------------------------------------

    def emit(
        self,
        event_type: CodeEventType,
        payload: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> CodeEvent:
        """Build and emit an event.

        Dispatches to the in-memory log, the optional external bus, and
        the in-memory bus (if configured).  Returns the constructed
        :class:`CodeEvent` for inspection or testing.
        """
        event = build_event(
            event_type=event_type,
            repository_id=self._repository_id,
            payload=payload,
            **kwargs,
        )
        errors = validate_event(event)
        if errors:
            logger.warning("invalid event %s: %s", event_type.value, errors)
            return event

        self._store_recent(event)
        self._dispatch_to_buses(event)
        return event

    def emit_to_log(
        self,
        event_type: CodeEventType,
        payload: Optional[Dict[str, Any]] = None,
        level: int = logging.INFO,
        **kwargs: Any,
    ) -> CodeEvent:
        """Emit an event and log it at the specified *level*."""
        event = build_event(
            event_type=event_type,
            repository_id=self._repository_id,
            payload=payload,
            **kwargs,
        )
        self._store_recent(event)

        logger.log(
            level,
            "[%s] repo=%s event_id=%s payload=%s",
            event_type.value,
            self._repository_id,
            event.event_id,
            event.payload,
        )
        return event

    def emit_to_bus(self, event: CodeEvent) -> None:
        """Push *event* to the external :class:`AbstractEventBus`.

        Subclasses may override this for custom dispatch logic.  The
        default implementation is a no-op if no bus is configured.
        """
        if self._event_bus is None:
            return
        try:
            # The external bus may be async; callers that need async
            # dispatch should override this method.
            import asyncio
            loop = asyncio.get_running_loop()
            loop.create_task(self._event_bus.publish(event))
        except RuntimeError:
            # No running event loop — synchronous fallback.
            logger.debug("no event loop, skipping external bus publish")

    # -- querying -----------------------------------------------------------

    def get_recent_events(
        self,
        event_type: Optional[CodeEventType] = None,
        limit: int = 50,
        event_filter: Optional[EventFilter] = None,
    ) -> List[CodeEvent]:
        """Return recent events emitted by this emitter.

        Sources are merged from the local log and the in-memory bus.
        Results are deduplicated by ``event_id`` and sorted newest-first.
        """
        candidates: List[CodeEvent] = []

        with self._lock:
            if event_type is not None:
                candidates.extend(
                    e for e in self._recent if e.event_type == event_type
                )
            else:
                candidates.extend(self._recent)

        if self._in_memory_bus is not None:
            candidates.extend(
                self._in_memory_bus.get_recent(event_type=event_type, limit=limit * 2)
            )

        seen: set[str] = set()
        deduped: List[CodeEvent] = []
        for e in candidates:
            if e.event_id not in seen:
                seen.add(e.event_id)
                deduped.append(e)

        if event_filter is not None:
            deduped = event_filter.apply(deduped)

        deduped.sort(key=lambda e: e.timestamp, reverse=True)
        return deduped[:limit]

    # -- internal -----------------------------------------------------------

    def _store_recent(self, event: CodeEvent) -> None:
        with self._lock:
            self._recent.append(event)
            if len(self._recent) > 500:
                self._recent = self._recent[-500:]

    def _dispatch_to_buses(self, event: CodeEvent) -> None:
        if self._in_memory_bus is not None:
            try:
                self._in_memory_bus.publish(event)
            except Exception:
                logger.exception("in-memory bus publish failed for %s", event.event_type.value)
        self.emit_to_bus(event)


# ---------------------------------------------------------------------------
# Convenience factory for pipeline integration
# ---------------------------------------------------------------------------

def create_emitter(
    repository_id: str,
    event_bus: Optional[AbstractEventBus] = None,
    in_memory_bus: Optional[InMemoryEventBus] = None,
) -> EventEmitter:
    """Create an :class:`EventEmitter` wired to the given bus(es)."""
    return EventEmitter(
        repository_id=repository_id,
        event_bus=event_bus,
        in_memory_bus=in_memory_bus,
    )
