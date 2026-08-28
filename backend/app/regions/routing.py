"""Volume 62 Commit 1 — Routing Service (region-aware request routing).

Resolves primary -> preferred secondary -> emergency fallback. Health-aware
(skips FAILED/UNKNOWN for critical), capacity-aware (avoids overloaded where
policy permits), residency-aware (never routes outside allowed regions). Traffic
draining stops new requests to DRAINING regions.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import Event, EventType, event_bus
from app.regions.models import (
    REGION_DRAINING,
    REGION_FAILED,
    REGION_UNKNOWN,
    RegionRoutingPolicy,
    TenantRegionPlacement,
)
from app.regions.registry import RegionService, is_region_critical_safe, is_region_healthy
from app.regions.placement import PlacementService

logger = logging.getLogger(__name__)

# Capacity threshold (percent) above which a region is considered overloaded
OVERLOAD_CPU_PCT = 90.0


class RoutingService:
    """Resolve region for a (tenant, service, classification) request."""

    def __init__(self, region_service: RegionService | None = None, placement_service: PlacementService | None = None):
        self.region_service = region_service or RegionService()
        self.placement_service = placement_service or PlacementService(self.region_service)

    async def set_policy(
        self,
        db: AsyncSession,
        tenant: str,
        service: str,
        primary_region: str | None = None,
        preferred_secondary: str | None = None,
        emergency_fallback: str | None = None,
        consistency: str = "CONFIGURABLE",
        metadata: dict | None = None,
        publisher: str | None = None,
    ) -> RegionRoutingPolicy:
        if consistency not in ("STRONG", "EVENTUAL", "CONFIGURABLE"):
            raise ValueError(f"invalid consistency {consistency}")
        res = await db.execute(
            select(RegionRoutingPolicy).where(
                RegionRoutingPolicy.tenant == tenant, RegionRoutingPolicy.service == service
            )
        )
        pol = res.scalar_one_or_none()
        if pol:
            pol.primary_region = primary_region
            pol.preferred_secondary = preferred_secondary
            pol.emergency_fallback = emergency_fallback
            pol.consistency = consistency
            pol.metadata_json = metadata or pol.metadata_json
        else:
            pol = RegionRoutingPolicy(
                tenant=tenant,
                service=service,
                primary_region=primary_region,
                preferred_secondary=preferred_secondary,
                emergency_fallback=emergency_fallback,
                consistency=consistency,
                metadata_json=metadata or {},
            )
            db.add(pol)
        await db.flush()
        return pol

    async def get_policy(self, db: AsyncSession, tenant: str, service: str) -> RegionRoutingPolicy | None:
        res = await db.execute(
            select(RegionRoutingPolicy).where(
                RegionRoutingPolicy.tenant == tenant, RegionRoutingPolicy.service == service
            )
        )
        return res.scalar_one_or_none()

    def _overloaded(self, region) -> bool:
        cap = getattr(region, "capacity", None) or {}
        cpu = float(cap.get("cpu", 0) or 0)
        return cpu >= OVERLOAD_CPU_PCT

    async def _region_ok(self, db: AsyncSession, region_id: str, critical: bool, capacity_aware: bool) -> tuple[bool, str]:
        reg = await self.region_service.get_region(db, region_id)
        if reg is None:
            return False, "region not registered"
        if reg.status == REGION_DRAINING:
            return False, "region is DRAINING (stopping new requests)"
        if critical and not is_region_critical_safe(reg.status):
            return False, f"region status {reg.status} unsafe for critical workload"
        if capacity_aware and self._overloaded(reg):
            return False, "region overloaded (cpu >= threshold)"
        return True, "ok"

    async def route(
        self,
        db: AsyncSession,
        tenant: str,
        service: str,
        data_classification: str | None = None,
        preferred_region: str | None = None,
        criticality: str = "HIGH",
        capacity_aware: bool = True,
        actor: str | None = None,
    ) -> dict[str, Any]:
        """Resolve a target region with fallback chain.

        Order: preferred_region (if given and allowed) -> policy.primary ->
        policy.preferred_secondary -> policy.emergency_fallback. Each candidate
        must pass health + capacity + residency checks. Returns dict with
        region, tier (primary/secondary/emergency), reason, consistency.
        """
        critical = criticality in ("HIGH", "CRITICAL")
        pol = await self.get_policy(db, tenant, service)
        placement = await self.placement_service.get_placement(db, tenant)

        # Build ordered candidate chain
        candidates: list[tuple[str, str]] = []
        if preferred_region:
            candidates.append((preferred_region, "preferred"))
        if pol:
            if pol.primary_region:
                candidates.append((pol.primary_region, "primary"))
            if pol.preferred_secondary:
                candidates.append((pol.preferred_secondary, "secondary"))
            if pol.emergency_fallback:
                candidates.append((pol.emergency_fallback, "emergency"))
        # Fall back to placement primary/secondary if no policy
        if not candidates and placement:
            if placement.primary_region:
                candidates.append((placement.primary_region, "primary"))
            if placement.secondary_region:
                candidates.append((placement.secondary_region, "secondary"))

        if not candidates:
            return {
                "region": None,
                "tier": None,
                "reason": "no routing policy or placement configured for tenant/service",
                "decision": "NO_ROUTE",
                "consistency": pol.consistency if pol else "CONFIGURABLE",
            }

        last_reason = "no candidate passed checks"
        for region_id, tier in candidates:
            # Residency check (never route outside allowed regions)
            allowed = await self.placement_service.is_allowed(db, tenant, region_id) if placement else True
            if not allowed:
                last_reason = f"region {region_id} not in tenant allowed_regions"
                continue
            # Policy bridge residency evaluation for restricted data
            if data_classification and data_classification.upper() in ("RESTRICTED", "SECRET", "CONFIDENTIAL"):
                ev = await self.placement_service.evaluate(
                    db, tenant, data_classification, region_id, actor=actor
                )
                if ev.get("decision") == "DENY":
                    last_reason = f"residency policy denied {region_id}: {ev.get('reason')}"
                    continue
            ok, reason = await self._region_ok(db, region_id, critical, capacity_aware)
            if not ok:
                last_reason = reason
                continue
            return {
                "region": region_id,
                "tier": tier,
                "reason": f"routed to {tier} region",
                "decision": "ROUTED",
                "consistency": pol.consistency if pol else "CONFIGURABLE",
            }
        return {
            "region": None,
            "tier": None,
            "reason": last_reason,
            "decision": "NO_ROUTE",
            "consistency": pol.consistency if pol else "CONFIGURABLE",
        }

    async def mark_draining(self, db: AsyncSession, region_id: str, reason: str | None = None, actor: str | None = None) -> dict:
        region = await self.region_service.update_status(db, region_id, REGION_DRAINING, reason=reason, actor=actor)
        await self._emit(EventType.region_draining_started, {"region_id": region_id, "reason": reason, "actor": actor})
        return {"region_id": region_id, "status": region.status}

    async def complete_draining(self, db: AsyncSession, region_id: str, actor: str | None = None) -> dict:
        region = await self.region_service.get_region(db, region_id)
        if not region:
            raise ValueError(f"region {region_id} not found")
        # Draining complete -> return to DEGRADED (operator decides ACTIVE separately)
        region = await self.region_service.update_status(db, region_id, "DEGRADED", reason="drain completed", actor=actor)
        await self._emit(EventType.region_draining_completed, {"region_id": region_id, "actor": actor})
        return {"region_id": region_id, "status": region.status}

    async def _emit(self, et: EventType, data: dict) -> None:
        try:
            await event_bus.publish_nowait(Event(et, data, source="regions"))
        except Exception as exc:  # noqa: BLE001
            logger.debug("routing event emit failed %s: %s", et, exc)


routing_service = RoutingService()
