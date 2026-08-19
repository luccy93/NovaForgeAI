import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("TESTING", "true")

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"


import asyncio
import uuid

import pytest

from app.code_intelligence.events import (
    CodeEvent,
    CodeEventType,
    EventEmitter,
    EventFilter,
    InMemoryEventBus,
    build_event,
    create_emitter,
    validate_event,
)


def _make_event(repo_id, etype=CodeEventType.FILE_PARSED):
    return build_event(
        event_type=etype,
        repository_id=repo_id,
        payload={"file_path": "app/mod.py"},
    )


def test_build_event():
    repo_id = str(uuid.uuid4())
    ev = _make_event(repo_id)
    assert isinstance(ev, CodeEvent)
    assert ev.repository_id == repo_id
    assert ev.event_type == CodeEventType.FILE_PARSED
    assert ev.timestamp is not None


def test_validate_event_valid():
    repo_id = str(uuid.uuid4())
    ev = _make_event(repo_id)
    errors = validate_event(ev)
    assert errors == []


def test_validate_event_invalid():
    import dataclasses

    repo_id = str(uuid.uuid4())
    ev = _make_event(repo_id)
    ev = dataclasses.replace(ev, repository_id="")
    errors = validate_event(ev)
    assert len(errors) >= 1


def test_in_memory_bus_publish_and_recent():
    bus = InMemoryEventBus()
    repo_id = str(uuid.uuid4())
    bus.publish(_make_event(repo_id))
    recent = bus.get_recent(limit=10)
    assert len(recent) == 1
    assert bus.count() == 1
    assert bus.has_event_id(recent[0].event_id)


def test_in_memory_bus_filter_by_type():
    bus = InMemoryEventBus()
    repo_id = str(uuid.uuid4())
    bus.publish(_make_event(repo_id, CodeEventType.FILE_PARSED))
    bus.publish(_make_event(repo_id, CodeEventType.SYMBOL_DISCOVERED))
    recent = bus.get_recent(event_type=CodeEventType.FILE_PARSED, limit=10)
    assert len(recent) == 1
    assert recent[0].event_type == CodeEventType.FILE_PARSED


def test_event_filter_matches():
    f = EventFilter(event_types={CodeEventType.FILE_PARSED})
    repo_id = str(uuid.uuid4())
    ev = _make_event(repo_id, CodeEventType.FILE_PARSED)
    assert f.matches(ev) is True
    ev2 = _make_event(repo_id, CodeEventType.SYMBOL_DISCOVERED)
    assert f.matches(ev2) is False


def test_emitter_emit_and_recent():
    repo_id = str(uuid.uuid4())
    bus = InMemoryEventBus()
    emitter = EventEmitter(repository_id=repo_id, in_memory_bus=bus)
    emitter.emit(CodeEventType.FILE_PARSED, {"file_path": "app/mod.py"})
    events = emitter.get_recent_events(limit=10)
    assert len(events) == 1
    assert events[0].event_type == CodeEventType.FILE_PARSED


def test_create_emitter():
    repo_id = str(uuid.uuid4())
    bus = InMemoryEventBus()
    emitter = create_emitter(repository_id=repo_id, in_memory_bus=bus)
    assert isinstance(emitter, EventEmitter)
    emitter.emit(CodeEventType.REPOSITORY_INDEX_COMPLETED, {})
    assert bus.count() == 1


def test_bus_ttl_eviction():
    bus = InMemoryEventBus(ttl_seconds=-1)
    repo_id = str(uuid.uuid4())
    bus.publish(_make_event(repo_id))
    bus._prune_locked()
    assert bus.count() == 0
