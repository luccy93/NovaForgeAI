"""Volume 62 Commit 1 — Failover / Failback Service (control-plane records).

Commit 1 provides the metadata + decision records for failover and failback:
validates target region residency + health before recording, emits events.
Full automated orchestration (detect/assess/authorize/verify, split-brain
protection, stabilization) is implemented in Commit 2's orchestrator.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import Event, EventType, event_bus
from app.regions.models import (
    FO_COMPLETED,
    FO_FAILED,
    FO_STARTED,
    RegionFailoverRecord,
)
from app.regions.placement import PlacementService
from app.regions.registry import RegionService, is_region_critical_safe
from app.regions.routing import routing_service

logger = logging.getLogger(__name__)


class FailoverService:
    """Record + validate failover/failback decisions (control-plane)."""

    def __init__(self, region_service: RegionService | None = None, placement_service: PlacementService | None = None):
        self.region_service = region_service or RegionService()
        self.placement_service = placement_service or PlacementService(self.region_service)

    async def start_failover(
        self,
        db: AsyncSession,
        tenant: str,
        source_region: str,
        target_region: str,
        service: str | None = None,
        data_classification: str | None = None,
        authorized_by: str | None = None,
        failover_type: str = "failover",
        actor: str | None = None,
    ) -> RegionFailoverRecord:
        """Validate + record a failover/failback decision. Fail-closed."""
        # Target region must exist and be critical-safe (never FAILED/UNKNOWN)
        target = await self.region_service.get_region(db, target_region)
        if target is None:
            raise ValueError(f"target region {target_region} not registered")
        if not is_region_critical_safe(target.status):
            raise ValueError(f"target region {target_region} status {target.status} is not safe for failover")

        # Data residency check (never route restricted data outside allowed regions)
        residency_ok = True
        if data_classification and data_classification.upper() in ("RESTRICTED", "SECRET", "CONFIDENTIAL"):
            ev = await self.placement_service.evaluate(db, tenant, data_classification, target_region, actor=actor)
            residency_ok = ev.get("decision") == "ALLOW"
            if not residency_ok:
                raise ValueError(f"data residency denied failover to {target_region}: {ev.get('reason')}")

        # Routing policy must reference this target (or placement allows it)
        allowed = await self.placement_service.is_allowed(db, tenant, target_region)
        if not allowed and failover_type == "failover":
            # allow failover only to allowed regions (configured fallback)
            raise ValueError(f"target region {target_region} not in tenant allowed_regions")

        rec = RegionFailoverRecord(
            tenant=tenant,
            service=service,
            source_region=source_region,
            target_region=target_region,
            failover_type=failover_type,
            status=FO_STARTED,
            authorized_by=authorized_by or actor,
            data_residency_ok=residency_ok,
            health_verified=is_region_critical_safe(target.status),
            reason=f"{failover_type} initiated",
            started_at=datetime.now(timezone.utc),
        )
        db.add(rec)
        await db.flush()
        et = EventType.regional_failover_started if failover_type == "failover" else EventType.regional_failback_started
        await self._emit(et, {
            "id": rec.id, "tenant": tenant, "service": service,
            "source_region": source_region, "target_region": target_region,
            "data_residency_ok": residency_ok, "authorized_by": authorized_by, "actor": actor,
        })
        return rec

    async def complete(
        self, db: AsyncSession, record_id: int, health_verified: bool | None = None, actor: str | None = None
    ) -> RegionFailoverRecord:
        res = await db.execute(select(RegionFailoverRecord).where(RegionFailoverRecord.id == record_id))
        rec = res.scalar_one_or_none()
        if not rec:
            raise ValueError(f"failover record {record_id} not found")
        if rec.status not in (FO_STARTED,):
            raise ValueError(f"failover record {record_id} not in STARTED state")
        rec.health_verified = health_verified if health_verified is not None else rec.health_verified
        rec.status = FO_COMPLETED
        rec.completed_at = datetime.now(timezone.utc)
        await db.flush()
        et = EventType.regional_failover_completed if rec.failover_type == "failover" else EventType.regional_failback_completed
        await self._emit(et, {
            "id": rec.id, "tenant": rec.tenant, "service": rec.service,
            "source_region": rec.source_region, "target_region": rec.target_region,
            "health_verified": rec.health_verified, "actor": actor,
        })
        return rec

    async def fail(self, db: AsyncSession, record_id: int, reason: str | None = None, actor: str | None = None) -> RegionFailoverRecord:
        res = await db.execute(select(RegionFailoverRecord).where(RegionFailoverRecord.id == record_id))
        rec = res.scalar_one_or_none()
        if not rec:
            raise ValueError(f"failover record {record_id} not found")
        rec.status = FO_FAILED
        rec.reason = reason
        rec.completed_at = datetime.now(timezone.utc)
        await db.flush()
        return rec

    async def list_records(self, db: AsyncSession, tenant: str | None = None, failover_type: str | None = None) -> list[RegionFailoverRecord]:
        stmt = select(RegionFailoverRecord)
        if tenant:
            stmt = stmt.where(RegionFailoverRecord.tenant == tenant)
        if failover_type:
            stmt = stmt.where(RegionFailoverRecord.failover_type == failover_type)
        res = await db.execute(stmt.order_by(RegionFailoverRecord.id.desc()))
        return list(res.scalars().all())

    async def _emit(self, et: EventType, data: dict) -> None:
        try:
            await event_bus.publish_nowait(Event(et, data, source="regions"))
        except Exception as exc:  # noqa: BLE001
            logger.debug("failover event emit failed %s: %s", et, exc)


failover_service = FailoverService()
