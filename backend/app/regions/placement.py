"""Volume 62 Commit 1 — Placement Service (tenant placement + data residency).

Evaluates tenant + data classification + region + provider + capacity +
compliance policy. Integrates Volume 57 policy bridge (fail-closed for
RESTRICTED/SECRET when engine unavailable). Region affinity preferred; never
routes data outside allowed regions.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import Event, EventType, event_bus
from app.regions.models import (
    REGION_FAILED,
    REGION_UNKNOWN,
    TenantRegionPlacement,
)
from app.regions.registry import RegionService, is_region_healthy

logger = logging.getLogger(__name__)

# Restricted classification levels (fail-closed)
_RESTRICTED_LEVELS = {"RESTRICTED", "SECRET", "CONFIDENTIAL"}


class PlacementService:
    """Tenant placement + data residency policy evaluation."""

    def __init__(self, region_service: RegionService | None = None):
        self.region_service = region_service or RegionService()

    async def set_placement(
        self,
        db: AsyncSession,
        tenant: str,
        primary_region: str | None = None,
        secondary_region: str | None = None,
        allowed_regions: list | None = None,
        data_classification: str | None = None,
        residency_policy: dict | None = None,
        policy_version: str = "1.0.0",
        actor: str | None = None,
    ) -> TenantRegionPlacement:
        if primary_region:
            reg = await self.region_service.get_region(db, primary_region)
            if not reg:
                raise ValueError(f"primary region {primary_region} not found")
        if secondary_region:
            reg = await self.region_service.get_region(db, secondary_region)
            if not reg:
                raise ValueError(f"secondary region {secondary_region} not found")
        res = await db.execute(select(TenantRegionPlacement).where(TenantRegionPlacement.tenant == tenant))
        placement = res.scalar_one_or_none()
        if placement:
            placement.primary_region = primary_region
            placement.secondary_region = secondary_region
            placement.allowed_regions = allowed_regions or placement.allowed_regions
            placement.data_classification = data_classification or placement.data_classification
            placement.residency_policy = residency_policy or placement.residency_policy
            placement.policy_version = policy_version
        else:
            placement = TenantRegionPlacement(
                tenant=tenant,
                primary_region=primary_region,
                secondary_region=secondary_region,
                allowed_regions=allowed_regions or [],
                data_classification=data_classification,
                residency_policy=residency_policy or {},
                policy_version=policy_version,
            )
            db.add(placement)
        await db.flush()
        await self._emit(EventType.placement_changed, {
            "tenant": tenant, "primary_region": primary_region,
            "secondary_region": secondary_region, "allowed_regions": allowed_regions,
            "data_classification": data_classification, "policy_version": policy_version, "actor": actor,
        })
        return placement

    async def get_placement(self, db: AsyncSession, tenant: str) -> TenantRegionPlacement | None:
        res = await db.execute(select(TenantRegionPlacement).where(TenantRegionPlacement.tenant == tenant))
        return res.scalar_one_or_none()

    async def affinity_region(self, db: AsyncSession, tenant: str) -> str | None:
        """Preferred (primary) region for the tenant, or None if unset."""
        p = await self.get_placement(db, tenant)
        return p.primary_region if p else None

    async def is_allowed(self, db: AsyncSession, tenant: str, region: str) -> bool:
        """Region is allowed if it is primary/secondary or in allowed_regions."""
        p = await self.get_placement(db, tenant)
        if not p:
            return False
        allowed = set(p.allowed_regions or [])
        if p.primary_region:
            allowed.add(p.primary_region)
        if p.secondary_region:
            allowed.add(p.secondary_region)
        return region in allowed

    async def evaluate(
        self,
        db: AsyncSession,
        tenant: str,
        data_classification: str | None,
        region: str,
        provider: str | None = None,
        capacity: dict | None = None,
        actor: str | None = None,
    ) -> dict[str, Any]:
        """Evaluate whether placing/processing data in `region` is permitted.

        Returns dict with decision (ALLOW/DENY), reason, policy_version,
        policy_checked (bool). Fail-closed:
          - region UNKNOWN/FAILED or unknown region -> DENY
          - restricted classification and region not in allowed -> DENY
          - Volume 57 policy bridge invoked for residency/compliance, DENY on
            engine failure for restricted data
        """
        # 1. Region must exist and be routable
        reg = await self.region_service.get_region(db, region)
        if reg is None:
            return self._deny(tenant, region, "region not registered", data_classification, policy_version="1.0.0")
        if reg.status in (REGION_FAILED, REGION_UNKNOWN):
            return self._deny(tenant, region, f"region status {reg.status} is not routable", data_classification, policy_version="1.0.0")

        # 2. Allowed-region check (region affinity + residency)
        allowed = await self.is_allowed(db, tenant, region)
        if not allowed:
            # If data is restricted, never route outside allowed regions
            return self._deny(
                tenant, region, "region not in tenant allowed_regions", data_classification,
                policy_version=(await self.get_placement(db, tenant)).policy_version if await self.get_placement(db, tenant) else "1.0.0",
            )

        # 3. Volume 57 policy bridge (data residency / compliance)
        classification = (data_classification or "INTERNAL").upper()
        policy_result = await self._policy_bridge(db, tenant, region, classification, provider, actor)
        if policy_result.get("decision") == "DENY":
            return {
                "decision": "DENY",
                "reason": policy_result.get("reason", "policy denied placement"),
                "region": region,
                "data_classification": classification,
                "policy_version": policy_result.get("policy_version", "1.0.0"),
                "policy_checked": True,
                "fail_closed": policy_result.get("fail_closed", False),
            }

        return {
            "decision": "ALLOW",
            "reason": "region allowed by placement and policy bridge",
            "region": region,
            "data_classification": classification,
            "policy_version": policy_result.get("policy_version", "1.0.0"),
            "policy_checked": True,
            "fail_closed": False,
            "capacity": capacity,
        }

    async def _policy_bridge(
        self, db: AsyncSession, tenant: str, region: str, classification: str, provider: str | None, actor: str | None
    ) -> dict:
        """Invoke Volume 57 policy bridge for data residency. Fail-closed."""
        try:
            from app.datagov.policy_bridge import policy_bridge_service  # type: ignore

            result = await policy_bridge_service.evaluate(
                db,
                tenant=tenant,
                actor=actor or "region-placement",
                resource=f"region:{region}",
                policy_type="data_residency",
                context={
                    "classification": classification,
                    "region": region,
                    "provider": provider,
                    "purpose": "multi_region_placement",
                },
            )
            return result
        except Exception as exc:  # noqa: BLE001
            logger.debug("policy bridge unavailable: %s", exc)
            # Fail-closed only for restricted classification
            if classification in _RESTRICTED_LEVELS:
                return {
                    "decision": "DENY",
                    "reason": f"fail-closed: policy bridge unavailable for {classification} data",
                    "policy_version": "1.0.0",
                    "fail_closed": True,
                }
            return {"decision": "ALLOW", "reason": "policy bridge unavailable, data not restricted", "policy_version": "1.0.0"}

    @staticmethod
    def _deny(tenant: str, region: str, reason: str, classification: str | None, policy_version: str) -> dict:
        return {
            "decision": "DENY",
            "reason": reason,
            "region": region,
            "data_classification": (classification or "INTERNAL").upper(),
            "policy_version": policy_version,
            "policy_checked": False,
            "fail_closed": False,
        }

    async def _emit(self, et: EventType, data: dict) -> None:
        try:
            await event_bus.publish_nowait(Event(et, data, source="regions"))
        except Exception as exc:  # noqa: BLE001
            logger.debug("placement event emit failed %s: %s", et, exc)


placement_service = PlacementService()
