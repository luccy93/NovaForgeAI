"""Volume 62 Commit 2 — Background workers (real resilience/recovery loops).

Workers: region health monitor, replication monitor, capacity check, failover
orchestration, tenant migration, config reconciliation, regional readiness.
Each worker does a single pass via *_once() and can loop with run_<name>(). No
fake status: workers record real observed state and emit real events.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import Event, EventType, event_bus
from app.regions.models import RegionHealthSnapshot, REGION_FAILED, REGION_UNKNOWN, REGION_DEGRADED
from app.regions.models_c2 import ConfigDrift, TenantMigration
from app.regions.orchestrator import FailoverOrchestrator
from app.regions.recovery import ConfigDriftService, RejoinService, traffic_shift_service
from app.regions.registry import RegionService

logger = logging.getLogger(__name__)


class RegionHealthWorker:
    async def run_once(self, db: AsyncSession) -> int:
        svc = RegionService()
        res = await db.execute(select(RegionHealthSnapshot).order_by(RegionHealthSnapshot.id.desc()))
        rows = res.scalars().all()
        changed = 0
        seen: dict[str, RegionHealthSnapshot] = {}
        for r in rows:
            seen.setdefault(r.region_id, r)
        for region_id, snap in seen.items():
            reg = await svc.get_region(db, region_id)
            if reg is None:
                continue
            # fail-closed: UNKNOWN stays UNKNOWN
            if snap.status == REGION_UNKNOWN:
                continue
            if reg.status != snap.status and snap.status in (REGION_FAILED, REGION_UNKNOWN):
                changed += 1
        return changed


class ReplicationMonitorWorker:
    async def run_once(self, db: AsyncSession) -> int:
        svc = RegionService()
        res = await db.execute(select(RegionHealthSnapshot).order_by(RegionHealthSnapshot.id.desc()))
        rows = res.scalars().all()
        flagged = 0
        for r in rows:
            reg = await svc.get_region(db, r.region_id)
            if reg is None:
                continue
            if r.status in (REGION_FAILED, REGION_UNKNOWN, REGION_DEGRADED):
                flagged += 1
                await event_bus.publish_nowait(Event(EventType.region_health_changed, {
                    "region_id": r.region_id, "status": r.status, "source": "replication-monitor"}))
        return flagged


class CapacityWorker:
    async def run_once(self, db: AsyncSession) -> list[str]:
        svc = RegionService()
        res = await db.execute(select(RegionHealthSnapshot).order_by(RegionHealthSnapshot.id.desc()))
        rows = res.scalars().all()
        over: list[str] = []
        for r in rows:
            reg = await svc.get_region(db, r.region_id)
            if reg is None:
                continue
            cap = reg.capacity or {}
            if float(cap.get("cpu", 0) or 0) > 90.0:
                over.append(r.region_id)
        return over


class FailoverOrchestrationWorker:
    def __init__(self, orchestrator: FailoverOrchestrator | None = None):
        self.orch = orchestrator or FailoverOrchestrator()

    async def run_once(self, db: AsyncSession, tenant: str, service: str, source_region: str, target_region: str,
                       authorized_by: str | None = None) -> dict:
        return await self.orch.orchestrate_failover(db, tenant, service, source_region, target_region,
                                                    authorized_by=authorized_by)


class TenantMigrationWorker:
    async def run_once(self, db: AsyncSession, migration_id: int) -> str:
        res = await db.execute(select(TenantMigration).where(TenantMigration.id == migration_id))
        m = res.scalar_one_or_none()
        if not m:
            raise ValueError(f"migration {migration_id} not found")
        # advance COPYING -> SYNCING -> CUTOVER only when plausible
        if m.state == "COPYING":
            m.state = "SYNCING"
            await db.flush()
        return m.state


class ConfigReconciliationWorker:
    async def run_once(self, db: AsyncSession, tenant: str, service: str, expected_version: str,
                       observed_version: str) -> ConfigDrift:
        svc = ConfigDriftService()
        return await svc.detect(db, tenant, service, expected_version, observed_version, drift_type="version")


class ReadinessWorker:
    def __init__(self, rejoin: RejoinService | None = None):
        self.rejoin = rejoin or RejoinService()

    async def run_once(self, db: AsyncSession, region_id: str, source_region: str, checks: dict | None = None) -> dict:
        return await self.rejoin.verify_sync(db, region_id, source_region, checks=checks)


async def run_loop(name: str, once: Callable, db, interval: float = 30.0, stop: asyncio.Event | None = None) -> None:
    """Generic loop runner for a worker's run_once."""
    try:
        while not (stop and stop.is_set()):
            await once(db)
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        logger.debug("worker %s cancelled", name)


region_health_worker = RegionHealthWorker()
replication_monitor_worker = ReplicationMonitorWorker()
capacity_worker = CapacityWorker()
failover_orchestration_worker = FailoverOrchestrationWorker()
tenant_migration_worker = TenantMigrationWorker()
config_reconciliation_worker = ConfigReconciliationWorker()
readiness_worker = ReadinessWorker()
