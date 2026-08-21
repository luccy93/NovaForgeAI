"""Unified Analytics Platform -- Event Normalization (Volume 50)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import uuid4


class NormalizationService:
    """Normalize, deduplicate, and validate analytics events."""

    def __init__(self, late_event_hours: int = 48, dedup_window_seconds: int = 300):
        self._events: dict[str, dict[str, Any]] = {}
        self._fingerprints: set[str] = set()
        self._late_event_hours = late_event_hours
        self._dedup_window = dedup_window_seconds
        self._stats: dict[str, int] = {"total": 0, "processed": 0, "duplicates": 0, "late": 0, "invalid": 0}

    def ingest(self, event: dict) -> dict[str, Any]:
        self._stats["total"] += 1
        valid, errors = self.validate_event(event)
        if not valid:
            self._stats["invalid"] += 1
            return {"status": "invalid", "errors": errors}

        event_id = event.get("event_id", "")
        if not event_id:
            event_id = self._generate_event_id(event)

        event["event_id"] = event_id

        fp = self._compute_fingerprint(event)
        if fp in self._fingerprints:
            self._stats["duplicates"] += 1
            return {"status": "duplicate", "event_id": event_id, "fingerprint": fp}

        ts_str = event.get("event_timestamp", "")
        is_late = False
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str)
                now = datetime.now(timezone.utc)
                if tzinfo := ts.tzinfo:
                    age = (now - ts).total_seconds() / 3600
                else:
                    age = (now - ts.replace(tzinfo=timezone.utc)).total_seconds() / 3600
                if age > self._late_event_hours:
                    is_late = True
                    self._stats["late"] += 1
            except (ValueError, TypeError):
                pass

        normalized = {
            "event_id": event_id,
            "tenant": event.get("tenant", "default"),
            "workspace": event.get("workspace", ""),
            "project": event.get("project", ""),
            "actor": event.get("actor", ""),
            "source": event.get("source", "platform"),
            "event_type": event.get("event_type", ""),
            "resource_type": event.get("resource_type", ""),
            "resource_id": event.get("resource_id", ""),
            "cost_usd": float(event.get("cost_usd", 0.0)),
            "duration_ms": float(event.get("duration_ms", 0.0)),
            "metadata_extra": event.get("metadata_extra", {}),
            "schema_version": event.get("schema_version", 1),
            "event_timestamp": ts_str or datetime.now(timezone.utc).isoformat(),
            "processed": False,
            "is_late": is_late,
            "fingerprint": fp,
            "normalized_at": datetime.now(timezone.utc).isoformat(),
        }

        self._events[event_id] = normalized
        self._fingerprints.add(fp)
        self._stats["processed"] += 1
        return normalized

    def ingest_batch(self, events: list[dict]) -> list[dict]:
        return [self.ingest(e) for e in events]

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        return self._events.get(event_id)

    def list_events(self, tenant: str = "", event_type: str = "", source: str = "",
                    start_time: str = "", end_time: str = "", limit: int = 100) -> list[dict]:
        results = []
        for ev in self._events.values():
            if tenant and ev.get("tenant") != tenant:
                continue
            if event_type and ev.get("event_type") != event_type:
                continue
            if source and ev.get("source") != source:
                continue
            if start_time and ev.get("event_timestamp", "") < start_time:
                continue
            if end_time and ev.get("event_timestamp", "") > end_time:
                continue
            results.append(ev)
        results.sort(key=lambda e: e.get("event_timestamp", ""), reverse=True)
        return results[:limit]

    def get_stats(self, tenant: str = "") -> dict[str, int]:
        if tenant:
            count = sum(1 for e in self._events.values() if e.get("tenant") == tenant)
            return {**self._stats, "tenant_events": count}
        return dict(self._stats)

    def validate_event(self, event: dict) -> tuple[bool, list[str]]:
        errors = []
        if not event.get("tenant"):
            errors.append("missing tenant")
        if not event.get("source"):
            errors.append("missing source")
        if not event.get("event_type"):
            errors.append("missing event_type")
        ts = event.get("event_timestamp", "")
        if ts:
            try:
                datetime.fromisoformat(ts)
            except (ValueError, TypeError):
                errors.append(f"invalid timestamp: {ts}")
        cost = event.get("cost_usd", 0)
        if isinstance(cost, (int, float)) and cost < 0:
            errors.append("negative cost_usd")
        duration = event.get("duration_ms", 0)
        if isinstance(duration, (int, float)) and duration < 0:
            errors.append("negative duration_ms")
        meta = event.get("metadata_extra", {})
        if isinstance(meta, dict):
            for k in ("password", "secret", "api_key", "token", "private_key"):
                if k in meta:
                    errors.append(f"secret in metadata: {k}")
        return (len(errors) == 0, errors)

    def mark_processed(self, event_id: str) -> bool:
        if event_id in self._events:
            self._events[event_id]["processed"] = True
            return True
        return False

    def detect_duplicates(self, events: list[dict]) -> list[str]:
        seen: set[str] = set()
        dupes: list[str] = []
        for e in events:
            fp = self._compute_fingerprint(e)
            eid = e.get("event_id", "")
            if fp in seen and eid:
                dupes.append(eid)
            seen.add(fp)
        return dupes

    def _generate_event_id(self, event: dict) -> str:
        parts = [event.get("tenant", ""), event.get("source", ""),
                 event.get("event_type", ""), event.get("event_timestamp", ""),
                 str(uuid4())]
        return hashlib.sha256(":".join(parts).encode()).hexdigest()[:32]

    def _compute_fingerprint(self, event: dict) -> str:
        ts = event.get("event_timestamp", "")
        if ts:
            try:
                dt = datetime.fromisoformat(ts)
                ts = dt.replace(second=0, microsecond=0).isoformat()
            except (ValueError, TypeError):
                pass
        parts = [event.get("tenant", ""), event.get("source", ""),
                 event.get("event_type", ""), event.get("resource_id", ""), ts]
        return hashlib.sha256(":".join(parts).encode()).hexdigest()[:24]


normalization_service = NormalizationService()
