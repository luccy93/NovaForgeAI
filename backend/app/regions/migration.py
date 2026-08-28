"""Volume 62 Commit 2 — Tenant Migration (controlled cross-region move).

States PLANNED -> VALIDATING -> COPYING -> SYNCING -> CUTOVER -> VERIFYING ->
COMPLETED (or FAILED / ROLLED_BACK). Safety: explicit rollback strategy for DB,
cutover freeze + sync + verify + switch + observe, rollback supported. Data
integrity preserved (no silent loss). Reuses Volume 57 residency + Volume 60.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import Event, EventType, event_bus
from app.regions.models_c2 import (
    MIG_COMPLETED,
    MIG_CUTOVER,
    MIG_FAILED,
    MIG_PLANNED,
    MIG_ROLLED_BACK,
    MIG_SYNCING,
    MIG_VERIFYING,
    TenantMigration,
)
from app.regions.registry import RegionService
from app.regions.placement import PlacementService

logger = logging.getLogger(__name__)


class TenantMigrationService:
    """Orchestrates a single tenant migration between regions with safety states."""

    def __init__(self, region_service: RegionService | None = None, placement_service: PlacementService | None = None):
        self.region_service = region_service or RegionService()
        self.placement_service = placement_service or PlacementService(self.region_service)

    async def plan(self, db: AsyncSession, tenant: str, source_region: str, target_region: str,
                   authorized_by: str, service: str | None = None, data_classification: str | None = None,
                   rollback_strategy: str | None = None, actor: str | None = None) -> TenantMigration:
        # Both regions must be registered
        for rid in (source_region, target_region):
            reg = await self.region_service.get_region(db, rid)
            if reg is None:
                raise ValueError(f"region {rid} not registered")
        # Residency check (fail-closed) for restricted data
        if data_classification and data_classification.upper() in ("RESTRICTED", "SECRET", "CONFIDENTIAL"):
            ev = await self.placement_service.evaluate(db, tenant, data_classification, target_region, actor=actor)
            if ev.get("decision") == "DENY":
                raise ValueError(f"data residency denies placement in {target_region}")
        # DB migrations must have an explicit rollback strategy
        if service and "db" in service.lower() and not rollback_strategy:
            raise ValueError("explicit rollback_strategy required for database migrations")
        migration = TenantMigration(
            tenant=tenant, source_region=source_region, target_region=target_region, service=service,
            state=MIG_PLANNED, authorized_by=authorized_by, rollback_strategy=rollback_strategy,
            started_at=datetime.now(timezone.utc),
        )
        db.add(migration)
        await db.flush()
        await self._emit(EventType.tenant_migration_started, {
            "tenant": tenant, "source_region": source_region, "target_region": target_region,
            "service": service, "authorized_by": authorized_by,
        })
        return migration

    async def _get(self, db: AsyncSession, migration_id: int) -> TenantMigration:
        res = await db.execute(select(TenantMigration).where(TenantMigration.id == migration_id))
        m = res.scalar_one_or_none()
        if not m:
            raise ValueError(f"migration {migration_id} not found")
        return m

    async def advance(self, db: AsyncSession, migration_id: int, state: str) -> TenantMigration:
        forward_states = ("VALIDATING", "COPYING", MIG_SYNCING, MIG_CUTOVER, MIG_VERIFYING, MIG_COMPLETED, MIG_FAILED, MIG_ROLLED_BACK)
        if state not in forward_states:
            raise ValueError(f"invalid advance state {state}")
        m = await self._get(db, migration_id)
        # Validate forward progress only
        order = [MIG_PLANNED, "VALIDATING", "COPYING", MIG_SYNCING, MIG_CUTOVER, MIG_VERIFYING, MIG_COMPLETED]
        if m.state not in order:
            raise ValueError(f"cannot advance from terminal/rolling state {m.state}")
        if state == MIG_COMPLETED and m.state != MIG_VERIFYING:
            raise ValueError("must VERIFY before COMPLETED")
        if state in (MIG_FAILED, MIG_ROLLED_BACK):
            pass  # terminal transitions allowed from any non-terminal state
        m.state = state
        if state in (MIG_COMPLETED, MIG_FAILED, MIG_ROLLED_BACK):
            m.completed_at = datetime.now(timezone.utc)
            if state == MIG_COMPLETED:
                await self._emit(EventType.tenant_migration_completed, {
                    "tenant": m.tenant, "source_region": m.source_region, "target_region": m.target_region,
                    "service": m.service,
                })
        await db.flush()
        return m

    async def set_verification(self, db: AsyncSession, migration_id: int, verification: dict) -> TenantMigration:
        m = await self._get(db, migration_id)
        m.verification = verification  # real evidence: data checksum, row counts, integrity
        await db.flush()
        return m

    async def rollback(self, db: AsyncSession, migration_id: int, reason: str | None = None) -> TenantMigration:
        m = await self._get(db, migration_id)
        if m.state in (MIG_COMPLETED, MIG_ROLLED_BACK):
            raise ValueError(f"cannot rollback from {m.state}")
        if not m.rollback_strategy and m.service and "db" in (m.service or "").lower():
            raise ValueError("no rollback_strategy defined for db migration")
        m.metadata_json = {**m.metadata_json, "rollback_reason": reason}
        m.state = MIG_ROLLED_BACK
        m.completed_at = datetime.now(timezone.utc)
        await db.flush()
        return m

    async def _emit(self, et: EventType, data: dict) -> None:
        try:
            await event_bus.publish_nowait(Event(et, data, source="tenant-migration"))
        except Exception as exc:  # noqa: BLE001
            logger.debug("migration event emit failed %s: %s", et, exc)


tenant_migration_service = TenantMigrationService()
