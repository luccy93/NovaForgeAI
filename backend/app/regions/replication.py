"""Volume 62 Commit 1 — Replication Service (cross-region lag + status)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import Event, EventType, event_bus
from app.regions.models import (
    REPL_BROKEN,
    REPL_HEALTHY,
    REPL_LAGGING,
    REPL_PAUSED,
    REPL_STATES,
    REPL_UNKNOWN,
    RegionReplicationRecord,
)

logger = logging.getLogger(__name__)

# Lag threshold (seconds) beyond which replication is considered LAGGING
LAG_WARN_SECONDS = 30.0


class ReplicationService:
    """Track cross-region replication: source/dest/resource/lag/status/last_sync."""

    async def record_replication(
        self,
        db: AsyncSession,
        source_region: str,
        dest_region: str,
        resource: str,
        resource_type: str | None = None,
        tenant: str = "",
        lag_seconds: float = 0.0,
        status: str = REPL_HEALTHY,
        last_sync: datetime | None = None,
        actor: str | None = None,
    ) -> RegionReplicationRecord:
        if status not in REPL_STATES:
            raise ValueError(f"invalid replication status {status}")
        rec = RegionReplicationRecord(
            tenant=tenant,
            source_region=source_region,
            dest_region=dest_region,
            resource=resource,
            resource_type=resource_type,
            lag_seconds=float(lag_seconds),
            status=status,
            last_sync=last_sync or datetime.now(timezone.utc),
        )
        db.add(rec)
        await db.flush()
        await self._emit(EventType.replication_started, {
            "id": rec.id, "source_region": source_region, "dest_region": dest_region,
            "resource": resource, "status": status, "actor": actor,
        })
        if status == REPL_LAGGING:
            await self._emit(EventType.replication_lag_detected, {
                "id": rec.id, "source_region": source_region, "dest_region": dest_region,
                "resource": resource, "lag_seconds": lag_seconds,
            })
        return rec

    async def update_lag(
        self, db: AsyncSession, record_id: int, lag_seconds: float, status: str | None = None, last_sync: datetime | None = None
    ) -> RegionReplicationRecord:
        res = await db.execute(select(RegionReplicationRecord).where(RegionReplicationRecord.id == record_id))
        rec = res.scalar_one_or_none()
        if not rec:
            raise ValueError(f"replication record {record_id} not found")
        rec.lag_seconds = float(lag_seconds)
        if status:
            if status not in REPL_STATES:
                raise ValueError(f"invalid replication status {status}")
            rec.status = status
        if last_sync:
            rec.last_sync = last_sync
        else:
            rec.last_sync = datetime.now(timezone.utc)
        await db.flush()
        # Emit lag/health events based on transition
        if rec.status == REPL_LAGGING or rec.lag_seconds >= LAG_WARN_SECONDS:
            await self._emit(EventType.replication_lag_detected, {
                "id": rec.id, "source_region": rec.source_region, "dest_region": rec.dest_region,
                "resource": rec.resource, "lag_seconds": rec.lag_seconds,
            })
        elif rec.status == REPL_HEALTHY:
            await self._emit(EventType.replication_recovered, {
                "id": rec.id, "source_region": rec.source_region, "dest_region": rec.dest_region,
                "resource": rec.resource, "lag_seconds": rec.lag_seconds,
            })
        return rec

    async def list_replication(
        self, db: AsyncSession, tenant: str | None = None, source_region: str | None = None, dest_region: str | None = None
    ) -> list[RegionReplicationRecord]:
        stmt = select(RegionReplicationRecord)
        if tenant is not None:
            stmt = stmt.where(RegionReplicationRecord.tenant == tenant)
        if source_region:
            stmt = stmt.where(RegionReplicationRecord.source_region == source_region)
        if dest_region:
            stmt = stmt.where(RegionReplicationRecord.dest_region == dest_region)
        res = await db.execute(stmt.order_by(RegionReplicationRecord.id.desc()))
        return list(res.scalars().all())

    async def lag_for(self, db: AsyncSession, source_region: str, dest_region: str, resource: str | None = None) -> float | None:
        """Current replication lag (seconds) exposed to routing/recovery systems."""
        stmt = select(RegionReplicationRecord).where(
            RegionReplicationRecord.source_region == source_region,
            RegionReplicationRecord.dest_region == dest_region,
        )
        if resource:
            stmt = stmt.where(RegionReplicationRecord.resource == resource)
        stmt = stmt.order_by(RegionReplicationRecord.id.desc())
        res = await db.execute(stmt)
        rec = res.scalar_one_or_none()
        return rec.lag_seconds if rec else None

    async def _emit(self, et: EventType, data: dict) -> None:
        try:
            await event_bus.publish_nowait(Event(et, data, source="regions"))
        except Exception as exc:  # noqa: BLE001
            logger.debug("replication event emit failed %s: %s", et, exc)


replication_service = ReplicationService()
