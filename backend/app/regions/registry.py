"""Volume 62 Commit 1 — Region Service (global registry + capabilities + health).

Region discovery/metadata/capabilities/health. Provider/location are data, not
hard-coded assumptions. UNKNOWN status is never treated as healthy.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import Event, EventType, event_bus
from app.regions.models import (
    Region,
    RegionCapability,
    RegionHealthSnapshot,
    REGION_ACTIVE,
    REGION_DEGRADED,
    REGION_DRAINING,
    REGION_FAILED,
    REGION_UNKNOWN,
    REGION_STATUSES,
)

# Capability catalog
CAPABILITY_CATALOG = {
    "AI", "GPU", "RAG", "vector_search", "graph", "storage",
    "compute", "deployment", "billing", "marketplace",
}

# Statuses that are NOT safe for critical routing
_UNHEALTHY_FOR_CRITICAL = {REGION_FAILED, REGION_UNKNOWN}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def is_region_healthy(status: str | None) -> bool:
    """Fail-closed: only ACTIVE/DEGRADED are considered routable; UNKNOWN/Failed are not."""
    if status is None:
        return False
    return status in (REGION_ACTIVE, REGION_DEGRADED)


def is_region_critical_safe(status: str | None) -> bool:
    """For critical workloads, UNKNOWN and FAILED must never be used."""
    if status is None:
        return False
    return status not in _UNHEALTHY_FOR_CRITICAL


class RegionService:
    """Region registry: register, discover, capabilities, health."""

    async def register_region(
        self,
        db: AsyncSession,
        region_id: str,
        name: str,
        provider: str,
        location: str,
        environment: str = "production",
        data_residency: dict | None = None,
        capacity: dict | None = None,
        status: str = REGION_ACTIVE,
        capabilities: dict | None = None,
        actor: str | None = None,
    ) -> Region:
        if status not in REGION_STATUSES:
            raise ValueError(f"invalid region status {status}")
        existing = await self.get_region(db, region_id)
        if existing:
            raise ValueError(f"region {region_id} already registered")
        region = Region(
            region_id=region_id,
            name=name,
            provider=provider,
            location=location,
            environment=environment,
            data_residency=data_residency or {},
            capacity=capacity or {},
            status=status,
        )
        db.add(region)
        await db.flush()
        if capabilities:
            await self.set_capabilities(db, region_id, capabilities)
        # initial health snapshot
        await self.record_health(db, region_id, status, checks={"registered": True}, observed_at=_utcnow())
        await self._emit(EventType.region_registered, {
            "region_id": region_id, "name": name, "provider": provider,
            "location": location, "status": status, "actor": actor,
        })
        return region

    async def get_region(self, db: AsyncSession, region_id: str) -> Region | None:
        res = await db.execute(select(Region).where(Region.region_id == region_id))
        return res.scalar_one_or_none()

    async def discover_regions(self, db: AsyncSession, status: str | None = None) -> list[Region]:
        stmt = select(Region)
        if status:
            stmt = stmt.where(Region.status == status)
        res = await db.execute(stmt.order_by(Region.region_id))
        return list(res.scalars().all())

    async def update_status(
        self, db: AsyncSession, region_id: str, status: str, reason: str | None = None, actor: str | None = None
    ) -> Region:
        if status not in REGION_STATUSES:
            raise ValueError(f"invalid region status {status}")
        region = await self.get_region(db, region_id)
        if not region:
            raise ValueError(f"region {region_id} not found")
        old = region.status
        region.status = status
        await db.flush()
        await self.record_health(db, region_id, status, checks={"reason": reason}, observed_at=_utcnow())
        if old != status:
            await self._emit(EventType.region_health_changed, {
                "region_id": region_id, "old_status": old, "new_status": status,
                "reason": reason, "actor": actor,
            })
        return region

    async def update_region(
        self, db: AsyncSession, region_id: str, status: str | None = None, provider: str | None = None,
        location: str | None = None, metadata: dict | None = None, actor: str | None = None,
    ) -> Region:
        region = await self.get_region(db, region_id)
        if not region:
            raise ValueError(f"region {region_id} not found")
        if status is not None:
            if status not in REGION_STATUSES:
                raise ValueError(f"invalid region status {status}")
            old = region.status
            region.status = status
            if old != status:
                await self.record_health(db, region_id, status, observed_at=_utcnow())
                await self._emit(EventType.region_health_changed, {
                    "region_id": region_id, "old_status": old, "new_status": status, "actor": actor,
                })
        if provider is not None:
            region.provider = provider
        if location is not None:
            region.location = location
        if metadata is not None:
            region.metadata_json = {**(region.metadata_json or {}), **metadata}
        await db.flush()
        return region

    async def set_capabilities(self, db: AsyncSession, region_id: str, capabilities: dict[str, bool]) -> list[RegionCapability]:
        if not await self.get_region(db, region_id):
            raise ValueError(f"region {region_id} not found")
        out: list[RegionCapability] = []
        for svc, supported in capabilities.items():
            if svc not in CAPABILITY_CATALOG:
                raise ValueError(f"unknown capability {svc}")
            res = await db.execute(
                select(RegionCapability).where(
                    RegionCapability.region_id == region_id, RegionCapability.service == svc
                )
            )
            cap = res.scalar_one_or_none()
            if cap:
                cap.supported = bool(supported)
            else:
                cap = RegionCapability(region_id=region_id, service=svc, supported=bool(supported))
                db.add(cap)
            out.append(cap)
        await db.flush()
        return out

    async def get_capabilities(self, db: AsyncSession, region_id: str) -> dict[str, bool]:
        res = await db.execute(select(RegionCapability).where(RegionCapability.region_id == region_id))
        return {c.service: c.supported for c in res.scalars().all()}

    async def supported_services(self, db: AsyncSession, region_id: str) -> list[str]:
        caps = await self.get_capabilities(db, region_id)
        return [s for s, ok in caps.items() if ok]

    async def region_supports(self, db: AsyncSession, region_id: str, service: str) -> bool:
        caps = await self.get_capabilities(db, region_id)
        return bool(caps.get(service, False))

    async def record_health(
        self, db: AsyncSession, region_id: str, status: str, checks: dict | None = None, observed_at: datetime | None = None
    ) -> RegionHealthSnapshot:
        snap = RegionHealthSnapshot(
            region_id=region_id,
            status=status,
            checks=checks or {},
            observed_at=observed_at or _utcnow(),
        )
        db.add(snap)
        await db.flush()
        return snap

    async def latest_health(self, db: AsyncSession, region_id: str) -> RegionHealthSnapshot | None:
        res = await db.execute(
            select(RegionHealthSnapshot)
            .where(RegionHealthSnapshot.region_id == region_id)
            .order_by(RegionHealthSnapshot.id.desc())
        )
        return res.scalar_one_or_none()

    async def list_health(self, db: AsyncSession) -> list[dict]:
        res = await db.execute(select(Region).order_by(Region.region_id))
        regions = res.scalars().all()
        out = []
        for r in regions:
            snap = await self.latest_health(db, r.region_id)
            out.append({
                "region_id": r.region_id,
                "status": r.status,
                "healthy": is_region_healthy(r.status),
                "critical_safe": is_region_critical_safe(r.status),
                "last_observed": str(snap.observed_at) if snap else None,
            })
        return out

    async def _emit(self, et: EventType, data: dict) -> None:
        try:
            await event_bus.publish_nowait(Event(et, data, source="regions"))
        except Exception as exc:  # noqa: BLE001
            logger.debug("region event emit failed %s: %s", et, exc)


region_service = RegionService()
