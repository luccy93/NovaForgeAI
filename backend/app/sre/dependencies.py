"""External dependency monitoring (Volume 35).

Records dependency health snapshots from the health checker, tracks
outages, and exposes an outage classification used by the fallback /
degrade / queue decision pipeline.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sre.constants import (
    DEPENDENCY_KIND_EXTERNAL,
    DEPENDENCY_STATUS_DOWN,
    DEPENDENCY_STATUS_HEALTHY,
    DEPENDENCY_STATUS_UNKNOWN,
)
from app.sre.models import SREDeadLetterEntry, SREDependencyHealth
from app.sre.store import new_id, new_key

logger = logging.getLogger(__name__)

# Default external dependencies seeded into the dependency monitor so
# status maps and dashboards are complete on first boot.
DEFAULT_DEPENDENCIES: list[dict] = [
    {"dependency": "postgresql", "kind": "database"},
    {"dependency": "redis", "kind": "queue"},
    {"dependency": "qdrant", "kind": "database"},
    {"dependency": "neo4j", "kind": "database"},
    {"dependency": "object_storage", "kind": "storage"},
    {"dependency": "event-bus", "kind": "queue"},
    {"dependency": "model-gateway", "kind": "ai_provider"},
    {"dependency": "ai_provider_openai", "kind": "ai_provider"},
    {"dependency": "ai_provider_anthropic", "kind": "ai_provider"},
    {"dependency": "github", "kind": "external"},
    {"dependency": "stripe", "kind": "external"},
]


async def record_dependency_health(
    db: AsyncSession,
    *,
    dependency: str,
    kind: str = DEPENDENCY_KIND_EXTERNAL,
    status: str = DEPENDENCY_STATUS_UNKNOWN,
    latency_ms: float = 0.0,
    error_rate: float = 0.0,
    metadata_json: Optional[dict] = None,
) -> SREDependencyHealth:
    """Record one dependency health snapshot; returns the row."""
    snapshot = SREDependencyHealth(
        dependency=dependency,
        kind=kind,
        status=status,
        latency_ms=latency_ms,
        error_rate=error_rate,
        metadata_json=metadata_json or {},
        last_outage_at=datetime.now(timezone.utc) if status == DEPENDENCY_STATUS_DOWN else None,
    )
    db.add(snapshot)
    await db.flush()
    return snapshot


async def record_from_check_results(db: AsyncSession, results: list) -> None:
    """Persist health-checker results as dependency health snapshots."""
    kind_map = {
        "database": "database",
        "redis": "queue",
        "qdrant": "database",
        "neo4j": "database",
        "object_storage": "storage",
        "event_bus": "queue",
        "ai_provider": "ai_provider",
    }
    for result in results:
        await record_dependency_health(
            db,
            dependency=result.name,
            kind=kind_map.get(result.name, DEPENDENCY_KIND_EXTERNAL),
            status=result.status,
            latency_ms=result.latency_ms,
            metadata_json=result.metadata,
        )


async def latest_dependency_health(db: AsyncSession, dependency: Optional[str] = None) -> list[dict]:
    stmt = select(SREDependencyHealth)
    if dependency:
        stmt = stmt.where(SREDependencyHealth.dependency == dependency)
    stmt = stmt.order_by(SREDependencyHealth.measured_at.desc()).limit(200)
    rows = list((await db.execute(stmt)).scalars().all())
    latest: dict[str, dict] = {}
    for row in rows:
        latest.setdefault(row.dependency, row.to_dict())
    return [latest[key] for key in sorted(latest)]


async def dependency_health_summary(db: AsyncSession) -> dict:
    """Healthy/down counts per dependency kind (for dashboards)."""
    stmt = select(SREDependencyHealth.dependency, SREDependencyHealth.status, func.count())
    stmt = stmt.group_by(SREDependencyHealth.dependency, SREDependencyHealth.status)
    rows = list((await db.execute(stmt)).all())
    latest: dict[str, dict] = {}
    for dependency, status, count in rows:
        entry = latest.setdefault(dependency, {"healthy": 0, "down": 0, "degraded": 0, "unknown": 0})
        key = status if status in entry else DEPENDENCY_STATUS_UNKNOWN
        entry[key] = int(count or 0)
    return latest


class DependencyOutageMode:
    """Classification pipeline used when a dependency fails: detect,
    classify, fallback, queue, degrade, alert, communicate, recover."""

    STEPS = ("detect", "classify", "fallback", "queue", "degrade", "alert", "communicate", "recover")

    @staticmethod
    def classify(dependency: str, kind: str, status: str) -> str:
        if status == DEPENDENCY_STATUS_HEALTHY:
            return "operational"
        if status == DEPENDENCY_STATUS_DOWN:
            if kind == "ai_provider":
                return "fallback"  # Model Gateway selects an approved fallback provider
            if kind == "storage":
                return "queue"  # queue writes; do not fabricate success
            if kind == "queue":
                return "degrade"  # pipelines pause; retain data
            return "degrade"
        return "monitor"


def outage_plan(dependency: str, kind: str, status: str) -> dict:
    mode = DependencyOutageMode.classify(dependency, kind, status)
    return {
        "dependency": dependency,
        "kind": kind,
        "status": status,
        "mode": mode,
        "steps": DependencyOutageMode.STEPS,
        "note": (
            "controlled degradation: never fabricate successful results while "
            "a dependency is unavailable"
        ),
    }


class DependencyMonitor:
    """Singleton facade over dependency health snapshots.

    Provides the record / status_of / status_map / seed_defaults surface
    used by the API and AI reliability modules.
    """

    async def record(
        self,
        db: AsyncSession,
        *,
        dependency: str,
        status: str,
        kind: str = DEPENDENCY_KIND_EXTERNAL,
        latency_ms: float = 0.0,
        error_rate: float = 0.0,
        metadata: Optional[dict] = None,
        metadata_json: Optional[dict] = None,
    ) -> SREDependencyHealth:
        return await record_dependency_health(
            db,
            dependency=dependency,
            kind=kind,
            status=status,
            latency_ms=latency_ms,
            error_rate=error_rate,
            metadata_json=metadata if metadata is not None else metadata_json,
        )

    async def status_of(self, db: AsyncSession, dependency: str) -> Optional[dict]:
        stmt = (
            select(SREDependencyHealth)
            .where(SREDependencyHealth.dependency == dependency)
            .order_by(SREDependencyHealth.measured_at.desc())
            .limit(1)
        )
        row = (await db.execute(stmt)).scalar_one_or_none()
        return row.to_dict() if row else None

    async def status_map(self, db: AsyncSession) -> dict[str, dict]:
        stmt = select(SREDependencyHealth).order_by(SREDependencyHealth.measured_at.desc()).limit(2000)
        rows = list((await db.execute(stmt)).scalars().all())
        latest: dict[str, dict] = {}
        for row in rows:
            latest.setdefault(row.dependency, row.to_dict())
        return latest

    async def seed_defaults(self, db: AsyncSession) -> int:
        """Idempotently seed default external dependencies (unknown status)."""
        count = 0
        for spec in DEFAULT_DEPENDENCIES:
            existing = await self.status_of(db, spec["dependency"])
            if existing:
                continue
            await record_dependency_health(
                db,
                dependency=spec["dependency"],
                kind=spec["kind"],
                status=DEPENDENCY_STATUS_UNKNOWN,
            )
            count += 1
        await db.flush()
        return count


class DeadLetterRegistry:
    """Registry for dead-lettered events with replay support."""

    async def record(
        self,
        db: AsyncSession,
        *,
        queue: str,
        error: str = "",
        attempts: int = 0,
        event_id: str = "",
        source: str = "",
        payload_reference: str = "",
        correlation_id: str = "",
    ) -> SREDeadLetterEntry:
        entry = SREDeadLetterEntry(
            id=new_id(),
            entry_id=new_key("dlq"),
            event_id=event_id,
            source=source,
            queue=queue,
            error=error,
            attempts=attempts,
            payload_reference=payload_reference,
            correlation_id=correlation_id,
            status="open",
        )
        db.add(entry)
        await db.flush()
        return entry

    async def list_open(self, db: AsyncSession, *, queue: str = "", limit: int = 100) -> list[dict]:
        stmt = select(SREDeadLetterEntry).where(SREDeadLetterEntry.status == "open").order_by(SREDeadLetterEntry.created_at.desc()).limit(limit)
        if queue:
            stmt = stmt.where(SREDeadLetterEntry.queue == queue)
        rows = (await db.execute(stmt)).scalars().all()
        return [r.to_dict() for r in rows]

    async def replay(self, db: AsyncSession, entry_id: str) -> Optional[SREDeadLetterEntry]:
        entry = (await db.execute(select(SREDeadLetterEntry).where(SREDeadLetterEntry.entry_id == entry_id))).scalar_one_or_none()
        if entry is None:
            return None
        if entry.status == "open":
            entry.status = "replayed"
            entry.attempts = entry.attempts + 1
            await db.flush()
        return entry


dependency_monitor = DependencyMonitor()
dead_letter_registry = DeadLetterRegistry()