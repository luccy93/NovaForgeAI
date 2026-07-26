"""Event System — repository, deployment, issue, security, pipeline, agent, billing, analytics, plugin, workflow events with routing, filtering, and persistence."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


EVENT_CATEGORIES = [
    "repository", "deployment", "issue", "security", "pipeline",
    "agent", "billing", "analytics", "plugin", "workflow",
]


@dataclass
class IntegrationEvent:
    id: str
    category: str
    event_type: str
    source: str
    source_id: str = ""
    correlation_id: str = ""
    payload: Any = None
    severity: str = "info"
    version: str = "1.0"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "IntegrationEvent": return cls(**data)


@dataclass
class EventRule:
    id: str
    name: str
    event_category: str
    event_type_filter: str = ""
    condition: dict = field(default_factory=dict)
    actions: list = field(default_factory=list)
    is_active: bool = True
    priority: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "EventRule": return cls(**data)


class EventSystem:
    def __init__(self, storage_dir: str = "integration_data/events"):
        self.storage_dir = storage_dir
        self._events: dict[str, IntegrationEvent] = {}
        self._rules: dict[str, EventRule] = {}
        self._handlers: dict[str, list] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _evt_path(self) -> str: return os.path.join(self.storage_dir, "events.json")
    def _rule_path(self) -> str: return os.path.join(self.storage_dir, "rules.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._evt_path(), self._events, IntegrationEvent),
            (self._rule_path(), self._rules, EventRule),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Failed to load event data: %s", e)

    def _save(self) -> None:
        try:
            with open(self._evt_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._events.items()}, f, indent=2, default=str)
            with open(self._rule_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._rules.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save event data: %s", e)

    def emit(self, category: str, event_type: str, source: str, payload: Any = None, source_id: str = "", severity: str = "info") -> IntegrationEvent:
        event = IntegrationEvent(id=str(uuid.uuid4()), category=category, event_type=event_type, source=source, source_id=source_id, correlation_id=str(uuid.uuid4()), payload=payload, severity=severity)
        self._events[event.id] = event
        self._telemetry["events_emitted"] = self._telemetry.get("events_emitted", 0) + 1
        self._save()
        self._route(event)
        return event

    def add_rule(self, name: str, event_category: str, event_type_filter: str = "", condition: dict = None, actions: list = None, priority: int = 0) -> EventRule:
        rule = EventRule(id=str(uuid.uuid4()), name=name, event_category=event_category, event_type_filter=event_type_filter, condition=condition or {}, actions=actions or [], priority=priority)
        self._rules[rule.id] = rule
        self._save()
        return rule

    def register_handler(self, event_type: str, handler) -> None:
        if event_type not in self._handlers: self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def _route(self, event: IntegrationEvent) -> None:
        handlers = self._handlers.get(event.event_type, [])
        for h in handlers:
            try: h(event)
            except Exception as e: logger.error("Handler error for %s: %s", event.event_type, e)

    def get_events(self, category: str = "", event_type: str = "", limit: int = 100) -> list[IntegrationEvent]:
        results = list(self._events.values())
        if category: results = [e for e in results if e.category == category]
        if event_type: results = [e for e in results if e.event_type == event_type]
        return sorted(results, key=lambda e: e.created_at, reverse=True)[:limit]

    def get_event_categories(self) -> list[str]: return EVENT_CATEGORIES

    def get_telemetry(self) -> dict: return dict(self._telemetry)
