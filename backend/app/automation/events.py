"""Automation event bus (Volume 33).

Typed events emitted by the platform (workflow started/finished, approvals
created, artifacts produced). The bus is an in-process pub/sub with
per-topic listeners and persistent event log (tenant-scoped JSON).
"""
import logging, threading, time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ..common.storage import JsonFileStorage

logger = logging.getLogger(__name__)


@dataclass
class AutomationEvent:
    topic: str
    payload: dict = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: _new_id())
    created_at: str = field(default_factory=lambda: time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    organization_id: str = ""

    def to_dict(self) -> dict:
        return {"event_id": self.event_id, "topic": self.topic,
                "payload": self.payload, "created_at": self.created_at,
                "organization_id": self.organization_id}


def _new_id() -> str:
    import uuid
    return f"evt_{uuid.uuid4().hex[:10]}"


class EventBus:
    """Synchronous in-process bus with optional persistent log."""

    def __init__(self, storage: Optional[JsonFileStorage] = None):
        self._listeners: dict[str, list[Callable[[AutomationEvent], None]]] = {}
        self._storage = storage
        self._lock = threading.RLock()
        self.emitted = 0

    def subscribe(self, topic: str, listener: Callable) -> None:
        with self._lock:
            self._listeners.setdefault(topic, []).append(listener)

    def unsubscribe(self, topic: str, listener: Callable) -> None:
        with self._lock:
            listeners = self._listeners.get(topic, [])
            self._listeners[topic] = [l for l in listeners if l is not listener]

    def emit(self, topic: str, payload: dict | None = None,
             organization_id: str = "") -> AutomationEvent:
        event = AutomationEvent(topic=topic, payload=payload or {},
                                organization_id=organization_id)
        with self._lock:
            self.emitted += 1
            if self._storage is not None:
                self._storage.set(event.event_id, event.to_dict())
            listeners = list(self._listeners.get(topic, []))
        for listener in listeners:
            try:
                listener(event)
            except Exception as exc:
                logger.warning("listener on %s failed: %s", topic, exc)
        return event

    def recent(self, topic: str = "", limit: int = 50) -> list[dict]:
        if self._storage is None:
            return []
        rows = self._storage.get_all()
        events = [v for k, v in rows.items()
                  if not topic or v.get("topic") == topic]
        events.sort(key=lambda e: e.get("created_at", ""), reverse=True)
        return events[:limit]

    def count(self) -> int:
        return self.emitted

    # ---------------------------------------------------------- defaults
    WORKFLOW_STARTED = "automation.workflow.started"
    WORKFLOW_COMPLETED = "automation.workflow.completed"
    WORKFLOW_FAILED = "automation.workflow.failed"
    STEP_STARTED = "automation.step.started"
    STEP_COMPLETED = "automation.step.completed"
    STEP_FAILED = "automation.step.failed"
    APPROVAL_CREATED = "automation.approval.created"
    APPROVAL_DECIDED = "automation.approval.decided"
    ARTIFACT_PRODUCED = "automation.artifact.produced"
    SCHEDULE_TICK = "automation.schedule.tick"


def build_workflow_event(topic: str, execution_id: str, workflow_id: str,
                         organization_id: str = "",
                         **extra: Any) -> AutomationEvent:
    return AutomationEvent(topic=topic,
                           payload={"execution_id": execution_id,
                                    "workflow_id": workflow_id, **extra},
                           organization_id=organization_id)