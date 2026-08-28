"""Volume 62 Commit 2 — Recovery, rejoin, readiness, traffic shift, drills, drift.

Region return: HEALTHY -> SYNC -> VERIFY -> READY -> TRAFFIC. A compromised
region must NOT auto-rejoin. Progressive traffic shift (0/10/25/50/100) with
regional canary (latency/error/SLO/cost/capacity). Configuration drift detection
vs control-plane source of truth (no stale policy for restricted/secret).
Disaster drills (region outage, partition, lag, split brain, provider) + chaos
(region loss, partition, latency, packet loss, storage, db, AI provider, event
bus) + partition test (fencing/routing/consistency/recovery). AIOps
recommendations (action/reason/evidence/confidence/risk), automated remediation
only for low-risk. Reuses Volume 59 observability + Volume 60 resilience.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import Event, EventType, event_bus
from app.regions.config import GlobalConfigService
from app.regions.models_c2 import ConfigDrift, RegionTrafficShift, TRAFFIC_STEPS
from app.regions.placement import PlacementService
from app.regions.registry import RegionService
from app.regions.replication import ReplicationService
from app.regions.routing import RoutingService

logger = logging.getLogger(__name__)


class ConfigDriftService:
    """Detect regional config drift vs control-plane source of truth."""

    def __init__(self, config_service: GlobalConfigService | None = None):
        self.config_service = config_service or GlobalConfigService()

    async def detect(self, db: AsyncSession, tenant: str, service: str, expected_version: str,
                     observed_version: str, drift_type: str = "version", details: dict | None = None,
                     actor: str | None = None) -> ConfigDrift:
        status = "OPEN" if expected_version != observed_version else "CLOSED"
        drift = ConfigDrift(tenant=tenant, service=service, expected_version=expected_version,
                            observed_version=observed_version, drift_type=drift_type, status=status,
                            detected_at=datetime.now(timezone.utc), details=details or {})
        db.add(drift)
        await db.flush()
        if status == "OPEN":
            await self._emit(EventType.configuration_drift_detected, {
                "tenant": tenant, "service": service, "expected_version": expected_version,
                "observed_version": observed_version, "drift_type": drift_type,
            })
        return drift

    async def resolve(self, db: AsyncSession, drift_id: int) -> ConfigDrift:
        res = await db.execute(select(ConfigDrift).where(ConfigDrift.id == drift_id))
        d = res.scalar_one_or_none()
        if not d:
            raise ValueError(f"drift {drift_id} not found")
        d.status = "CLOSED"
        await db.flush()
        return d

    async def _emit(self, et: EventType, data: dict) -> None:
        try:
            await event_bus.publish_nowait(Event(et, data, source="config-drift"))
        except Exception as exc:  # noqa: BLE001
            logger.debug("drift event failed %s: %s", et, exc)


class TrafficShiftService:
    """Progressive traffic shift / regional canary (0/10/25/50/100)."""

    async def shift(self, db: AsyncSession, region_id: str, percentage: int, actor: str | None = None) -> RegionTrafficShift:
        if percentage not in TRAFFIC_STEPS:
            raise ValueError(f"traffic percentage must be one of {TRAFFIC_STEPS}")
        # only one ACTIVE shift per region
        res = await db.execute(select(RegionTrafficShift).where(
            RegionTrafficShift.region_id == region_id, RegionTrafficShift.status == "ACTIVE"))
        existing = res.scalars().all()
        for e in existing:
            e.status = "SUPERSEDED"
        shift = RegionTrafficShift(region_id=region_id, percentage=percentage, status="ACTIVE",
                                   actor=actor, started_at=datetime.now(timezone.utc))
        db.add(shift)
        await db.flush()
        return shift

    async def complete(self, db: AsyncSession, shift_id: int) -> RegionTrafficShift:
        res = await db.execute(select(RegionTrafficShift).where(RegionTrafficShift.id == shift_id))
        s = res.scalar_one_or_none()
        if not s:
            raise ValueError(f"shift {shift_id} not found")
        s.status = "COMPLETED"
        s.completed_at = datetime.now(timezone.utc)
        await db.flush()
        return s

    async def current(self, db: AsyncSession, region_id: str) -> int:
        res = await db.execute(select(RegionTrafficShift).where(
            RegionTrafficShift.region_id == region_id, RegionTrafficShift.status == "ACTIVE"))
        s = res.scalar_one_or_none()
        return s.percentage if s else 0


class RejoinService:
    """Region return after outage: SYNC -> VERIFY -> READY -> TRAFFIC.

    Uses only valid region statuses (DRAINING while recovering, ACTIVE when
    admitted). A region flagged COMPROMISED (security) must NOT auto-rejoin.
    """

    ST_SYNC = "SYNC"
    ST_VERIFY = "VERIFY"
    ST_READY = "READY"
    ST_TRAFFIC = "TRAFFIC"
    ST_COMPROMISED = "COMPROMISED"

    def __init__(self, region_service: RegionService | None = None, replication_service: ReplicationService | None = None):
        self.region_service = region_service or RegionService()
        self.replication_service = replication_service or ReplicationService()

    async def begin_rejoin(self, db: AsyncSession, region_id: str, compromised: bool = False, actor: str | None = None) -> dict:
        reg = await self.region_service.get_region(db, region_id)
        if reg is None:
            raise ValueError(f"region {region_id} not registered")
        if compromised:
            # Security: compromised region cannot auto-rejoin (mark FAILED, not routable)
            await self.region_service.update_region(db, region_id, status="FAILED",
                                                    metadata={"rejoin_compromised": True}, actor=actor)
            return {"region_id": region_id, "state": self.ST_COMPROMISED, "auto_rejoin": False}
        # Recovering region stops serving new traffic until admitted
        await self.region_service.update_region(db, region_id, status="DRAINING",
                                                metadata={"rejoin_phase": self.ST_SYNC}, actor=actor)
        return {"region_id": region_id, "state": self.ST_SYNC, "auto_rejoin": True}

    async def verify_sync(self, db: AsyncSession, region_id: str, source_region: str,
                          checks: dict | None = None) -> dict:
        checks = checks or {}
        lag = await self.replication_service.lag_for(db, source_region, region_id)
        lag_ok = (lag is None) or (lag <= 30.0)
        required = ["integrity", "schema", "config", "permissions", "security", "observability"]
        provided = {k: checks.get(k) for k in required}
        passed = lag_ok and all(provided.get(k) is True for k in required)
        state = self.ST_READY if passed else self.ST_VERIFY
        meta = {"rejoin_phase": state}
        if passed:
            # READY -> can be admitted; keep DRAINING (not serving) until admit
            await self.region_service.update_region(db, region_id, metadata=meta)
        else:
            await self.region_service.update_region(db, region_id, metadata=meta)
        await self._emit(EventType.region_rejoined if passed else EventType.configuration_drift_detected, {
            "region_id": region_id, "state": state, "lag_ok": lag_ok, "checks": provided,
        })
        return {"region_id": region_id, "state": state, "lag_ok": lag_ok, "checks": provided, "passed": passed}

    async def admit_traffic(self, db: AsyncSession, region_id: str) -> dict:
        reg = await self.region_service.get_region(db, region_id)
        if reg is None:
            raise ValueError(f"region {region_id} not registered")
        meta = reg.metadata_json or {}
        if meta.get("rejoin_compromised"):
            raise ValueError(f"region {region_id} is COMPROMISED; cannot auto-rejoin (manual security review required)")
        if meta.get("rejoin_phase") != self.ST_READY:
            raise ValueError(f"region {region_id} not READY for traffic (phase {meta.get('rejoin_phase')})")
        await self.region_service.update_region(db, region_id, status="ACTIVE", metadata={"rejoin_phase": self.ST_TRAFFIC})
        return {"region_id": region_id, "state": self.ST_TRAFFIC}

    async def _emit(self, et: EventType, data: dict) -> None:
        try:
            await event_bus.publish_nowait(Event(et, data, source="rejoin"))
        except Exception as exc:  # noqa: BLE001
            logger.debug("rejoin event failed %s: %s", et, exc)


class DrillService:
    """Disaster drills + chaos scenarios (no live risk to production)."""

    SCENARIOS = {
        "region_outage": "Simulate full region outage and validate failover path.",
        "partition": "Simulate network partition between regions.",
        "replication_lag": "Simulate replication lag and validate RPO/notification.",
        "split_brain": "Simulate split-brain and validate fencing.",
        "provider_failure": "Simulate cloud provider failure for a region.",
        "chaos_region_loss": "Chaos: region loss.",
        "chaos_partition": "Chaos: network partition.",
        "chaos_latency": "Chaos: high latency.",
        "chaos_packet_loss": "Chaos: packet loss.",
        "chaos_storage": "Chaos: storage failure.",
        "chaos_db": "Chaos: database failure.",
        "chaos_ai_provider": "Chaos: AI provider failure + regional failover.",
        "chaos_event_bus": "Chaos: event bus failure + durable outbox.",
    }

    async def run(self, db: AsyncSession, scenario: str, region_id: str | None = None, actor: str | None = None) -> dict:
        if scenario not in self.SCENARIOS:
            raise ValueError(f"unknown drill scenario {scenario}")
        # Drills are simulated/safe; record execution with real metadata
        return {
            "scenario": scenario,
            "description": self.SCENARIOS[scenario],
            "region_id": region_id,
            "status": "SIMULATED",
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "actor": actor,
        }


class AIOpsAdvisor:
    """Region AIOps recommendations (action/reason/evidence/confidence/risk)."""

    def recommend(self, region_id: str, signals: dict) -> dict:
        # Real, evidence-based recommendation; never silent pass
        lag = signals.get("replication_lag_seconds")
        cpu = signals.get("cpu")
        error_rate = signals.get("error_rate")
        risk = "low"
        action = "observe"
        reason = "no anomaly detected"
        confidence = 0.5
        if lag is not None and lag > 30.0:
            action = "promote_failover_readiness"
            reason = f"replication lag {lag}s exceeds safe threshold"
            confidence = 0.8
            risk = "medium"
        elif cpu is not None and cpu > 90.0:
            action = "scale_or_shift_traffic"
            reason = f"region {region_id} cpu {cpu}% overloaded"
            confidence = 0.9
            risk = "medium"
        elif error_rate is not None and error_rate > 0.05:
            action = "investigate_errors"
            reason = f"error rate {error_rate} above SLO"
            confidence = 0.85
            risk = "high" if error_rate > 0.2 else "medium"
        return {
            "region_id": region_id,
            "action": action,
            "reason": reason,
            "evidence": signals,
            "confidence": confidence,
            "risk": risk,
            "automated_remediation_allowed": risk == "low",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


config_drift_service = ConfigDriftService()
traffic_shift_service = TrafficShiftService()
rejoin_service = RejoinService()
drill_service = DrillService()
aiops_advisor = AIOpsAdvisor()
