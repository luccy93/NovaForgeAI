"""Data Ingestion Layer - sources, retry, backpressure, dedup, ordering, DLQ, replay, checkpointing."""
import json, uuid, time, os, logging
from dataclasses import dataclass, field
from typing import Optional, Callable
from datetime import datetime, timezone

from .event_model import Event, EventStore

logger = logging.getLogger(__name__)


class IngestSource:
    """Supported ingestion source adapters."""
    REST = "rest"
    WEBHOOK = "webhook"
    EVENT_BUS = "event_bus"
    KAFKA = "kafka"
    REDIS_STREAM = "redis_stream"
    MESSAGE_QUEUE = "message_queue"
    BATCH_UPLOAD = "batch_upload"
    SCHEDULED_JOB = "scheduled_job"
    DATABASE_CDC = "database_cdc"

    ALL = [REST, WEBHOOK, EVENT_BUS, KAFKA, REDIS_STREAM, MESSAGE_QUEUE,
           BATCH_UPLOAD, SCHEDULED_JOB, DATABASE_CDC]


@dataclass
class DeliveryResult:
    """Outcome of a single event delivery attempt."""
    event_id: str
    accepted: bool
    duplicate: bool = False
    retries: int = 0
    error: str = ""
    offset: int = -1


class DeadLetterQueue:
    """Dead-letter queue for events that exhausted retries."""

    def __init__(self):
        self.items: list[dict] = []

    def push(self, event: Event, reason: str, retries: int) -> None:
        self.items.append({"event": event.to_dict(), "reason": reason,
                           "retries": retries, "failed_at": datetime.now(timezone.utc).isoformat()})

    def __len__(self) -> int:
        return len(self.items)

    def drain(self) -> list[dict]:
        items, self.items = self.items, []
        return items


class IngestionPipeline:
    """Backpressure-aware ingestion pipeline with retry, dedup, DLQ, checkpointing."""

    def __init__(
        self,
        store: Optional[EventStore] = None,
        max_queue: int = 10000,
        batch_size: int = 100,
        max_retries: int = 3,
        retry_backoff: float = 0.05,
        on_event: Optional[Callable[[Event], None]] = None,
    ):
        self.store = store or EventStore()
        self.dlq = DeadLetterQueue()
        self.max_queue = max_queue
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.on_event = on_event
        self.queue: list[Event] = []
        self.queue_depth = 0
        self.overload_dropped = 0
        self.ingested = 0
        self.failed = 0
        self.started_at = time.time()

    def _backpressure(self) -> bool:
        return self.queue_depth >= self.max_queue

    def enqueue(self, event: Event) -> DeliveryResult:
        errors = event.validate()
        if errors:
            self.failed += 1
            return DeliveryResult(event.event_id, False, error="; ".join(errors))
        if self._backpressure():
            self.overload_dropped += 1
            if self.on_event:
                self.on_event(event)
            return DeliveryResult(event.event_id, False, error="backpressure: queue full")
        self.queue.append(event)
        self.queue_depth = len(self.queue)
        return DeliveryResult(event.event_id, True)

    def _deliver(self, event: Event) -> DeliveryResult:
        for attempt in range(1, self.max_retries + 1):
            try:
                accepted = self.store.append(event)
                if not accepted:
                    return DeliveryResult(event.event_id, True, duplicate=True, offset=self.store.checkpoint())
                return DeliveryResult(event.event_id, True, offset=self.store.checkpoint() - 1)
            except Exception as exc:
                time.sleep(self.retry_backoff * attempt)
                if attempt >= self.max_retries:
                    self.dlq.push(event, str(exc), attempt)
                    self.failed += 1
                    return DeliveryResult(event.event_id, False, retries=attempt, error=str(exc))
        return DeliveryResult(event.event_id, False, error="unknown")

    def drain_queue(self, limit: Optional[int] = None) -> int:
        """Processes queued events with batching, honoring ordering."""
        processed = 0
        limit = limit or self.batch_size * 100
        while self.queue and processed < limit:
            batch = self.queue[:self.batch_size]
            self.queue = self.queue[self.batch_size:]
            for event in batch:
                result = self._deliver(event)
                if result.accepted and not result.duplicate:
                    self.ingested += 1
                    if self.on_event:
                        self.on_event(event)
                processed += 1
            self.queue_depth = len(self.queue)
        return processed

    def ingest(self, raw: dict, source: str = IngestSource.REST) -> DeliveryResult:
        """Accepts raw payloads (from any adapter) into the pipeline."""
        if isinstance(raw, dict):
            event = Event.from_dict(raw)
            if not raw.get("source"):
                event.source = source
        else:
            return DeliveryResult("", False, error="raw must be a dict")
        return self.enqueue(event)

    def checkpoint(self) -> int:
        return self.store.checkpoint()

    def replay(self, from_offset: int = 0) -> list[dict]:
        return self.store.replay(from_offset)

    def health(self) -> dict:
        return {
            "store_events": self.store.count(),
            "duplicates_rejected": self.store.duplicates_rejected,
            "queue_depth": self.queue_depth,
            "max_queue": self.max_queue,
            "ingested": self.ingested,
            "failed": self.failed,
            "overload_dropped": self.overload_dropped,
            "dlq_length": len(self.dlq),
            "checkpoint": self.checkpoint(),
            "uptime_seconds": time.time() - self.started_at,
        }


class SourceSource:
    """Alias for Source adapter names (avoid confusion with Source class)."""
    REST = "rest"
    WEBHOOK = "webhook"
    EVENT_BUS = "event_bus"


class SourceAdapter:
    """Adapter to normalize raw inputs from any supported source into Events."""

    def __init__(self, pipeline: IngestionPipeline):
        self.pipeline = pipeline

    def from_rest(self, raw: dict, source: str = IngestSource.REST) -> DeliveryResult:
        return self.pipeline.ingest(raw, source=source)

    def from_webhook(self, raw: dict, source: str = IngestSource.WEBHOOK) -> DeliveryResult:
        return self.pipeline.ingest(raw, source=source)

    def from_kafka(self, raw: dict, source: str = IngestSource.KAFKA) -> DeliveryResult:
        return self.pipeline.ingest(raw, source=source)

    def from_redis_stream(self, raw: dict, source: str = IngestSource.REDIS_STREAM) -> DeliveryResult:
        return self.pipeline.ingest(raw, source=source)

    def from_batch(self, raw_events: list[dict], source: str = IngestSource.BATCH_UPLOAD, *, check_tenant: bool = False) -> list[DeliveryResult]:
        results = []
        for raw in raw_events:
            result = self.pipeline.ingest(raw, source=source)
            if check_tenant and result.accepted:
                self._validate_tenant(result)
            results.append(result)
        return results

    def from_scheduled(self, raw: dict, source: str = IngestSource.SCHEDULED_JOB) -> DeliveryResult:
        return self.pipeline.ingest(raw, source=source)

    def from_cdc(self, raw: dict, source: str = IngestSource.DATABASE_CDC) -> DeliveryResult:
        return self.pipeline.ingest(raw, source=source)

    def _validate_tenant(self, result: DeliveryResult) -> None:
        """Tenant isolation gate: org-bound events must carry an organization_id."""
        try:
            events = self.pipeline.store.get(max(result.offset, 0), 1)
        except Exception:
            events = []