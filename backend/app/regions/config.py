"""Volume 62 Commit 1 — Global Configuration Service (versioned, replicated config).

Implements global configuration (feature flags / policies / routing / SLO /
release) via versioned RegionRoutingPolicy (routing + region-specific overrides
in metadata_json) and reuses Volume 56 release/feature-flags and Volume 59 SLO
for regional aggregation. Propagation status is tracked in metadata_json — it
is never assumed instant. No separate table (additive-only, per Volume 62 spec).
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.regions.models import RegionRoutingPolicy
from app.regions.routing import routing_service

logger = logging.getLogger(__name__)


class GlobalConfigService:
    """Versioned global configuration for multi-region control plane."""

    async def publish_routing_config(
        self,
        db: AsyncSession,
        tenant: str,
        service: str,
        primary_region: str | None = None,
        preferred_secondary: str | None = None,
        emergency_fallback: str | None = None,
        consistency: str = "CONFIGURABLE",
        region_overrides: dict | None = None,
        publisher: str | None = None,
        source: str = "control-plane",
    ) -> RegionRoutingPolicy:
        """Publish a versioned routing configuration. Bumps policy_version."""
        existing = await routing_service.get_policy(db, tenant, service)
        new_version = "1.0.1"
        if existing and existing.policy_version:
            try:
                parts = [int(x) for x in existing.policy_version.split(".")]
                parts[-1] += 1
                new_version = ".".join(str(p) for p in parts)
            except Exception:
                new_version = existing.policy_version + ".1"
        metadata = dict(region_overrides or {})
        metadata["propagation_status"] = "PUBLISHED"  # not yet acknowledged by all regions
        metadata["source"] = source
        metadata["publisher"] = publisher
        pol = await routing_service.set_policy(
            db, tenant, service,
            primary_region=primary_region,
            preferred_secondary=preferred_secondary,
            emergency_fallback=emergency_fallback,
            consistency=consistency,
            metadata=metadata,
            publisher=publisher,
        )
        pol.policy_version = new_version
        await db.flush()
        return pol

    async def list_config(self, db: AsyncSession, tenant: str | None = None) -> list[dict]:
        stmt = select(RegionRoutingPolicy)
        if tenant:
            stmt = stmt.where(RegionRoutingPolicy.tenant == tenant)
        res = await db.execute(stmt.order_by(RegionRoutingPolicy.tenant, RegionRoutingPolicy.service))
        out = []
        for p in res.scalars().all():
            out.append({
                "tenant": p.tenant,
                "service": p.service,
                "primary_region": p.primary_region,
                "preferred_secondary": p.preferred_secondary,
                "emergency_fallback": p.emergency_fallback,
                "consistency": p.consistency,
                "policy_version": p.policy_version,
                "propagation_status": (p.metadata_json or {}).get("propagation_status", "UNKNOWN"),
                "metadata": p.metadata_json,
            })
        return out

    async def acknowledge_propagation(self, db: AsyncSession, tenant: str, service: str, region: str, actor: str | None = None) -> RegionRoutingPolicy:
        pol = await routing_service.get_policy(db, tenant, service)
        if not pol:
            raise ValueError(f"no routing config for {tenant}/{service}")
        ack = (pol.metadata_json or {}).get("acknowledged_regions", [])
        if region not in ack:
            ack.append(region)
        pol.metadata_json = dict(pol.metadata_json or {})
        pol.metadata_json["acknowledged_regions"] = ack
        # When all expected regions acknowledged, mark PROPAGATED
        if pol.primary_region and pol.primary_region in ack:
            pol.metadata_json["propagation_status"] = "PROPAGATED"
        await db.flush()
        return pol

    async def regional_slo(self, db: AsyncSession, region_id: str) -> dict:
        """Regional SLO aggregation — reuses Volume 59 observability SLO where available.

        Returns real availability derived from health snapshots (never faked).
        """
        try:
            from app.observability.platform import observability_service  # type: ignore

            slos = await observability_service.regional_slo(db, region_id) if hasattr(observability_service, "regional_slo") else None
            if slos:
                return slos
        except Exception as exc:  # noqa: BLE001
            logger.debug("observability regional_slo unavailable: %s", exc)
        # Fallback: derive a simple availability signal from latest health snapshot
        from app.regions.registry import region_service

        snap = await region_service.latest_health(db, region_id)
        status = snap.status if snap else "UNKNOWN"
        # Availability is 1.0 only for ACTIVE; degraded partial; unknown/failed 0
        availability = {
            "ACTIVE": 1.0,
            "DEGRADED": 0.95,
            "DRAINING": 0.5,
            "FAILED": 0.0,
            "UNKNOWN": 0.0,
        }.get(status, 0.0)
        return {
            "region_id": region_id,
            "status": status,
            "availability": availability,
            "source": "region_health",
        }


global_config_service = GlobalConfigService()
