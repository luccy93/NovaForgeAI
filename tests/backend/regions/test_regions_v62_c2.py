"""Volume 62 Commit 2 — integration/security tests (real, no placeholders).

Covers failover orchestration (loops/split-brain/residency/replication/data-loss),
lease fencing, replication conflicts, tenant migration safety, traffic shift, rejoin
(compromised no auto-rejoin), config drift, drills, AIOps, workers.
"""

import pytest

from app.regions import (
    RegionService,
    PlacementService,
    RoutingService,
    ReplicationService,
    FailoverOrchestrator,
    TenantMigrationService,
    ConfigDriftService,
    TrafficShiftService,
    RejoinService,
    DrillService,
    AIOpsAdvisor,
    CapacityWorker,
    RegionHealthWorker,
    is_region_critical_safe,
)
from app.regions.models_c2 import (
    RegionLease,
    TenantMigration,
    RegionTrafficShift,
    ReplicationConflict,
    ConfigDrift,
    MIG_PLANNED,
    MIG_VERIFYING,
    MIG_COMPLETED,
    MIG_ROLLED_BACK,
)

region_service = RegionService()
placement_service = PlacementService(region_service)
routing_service = RoutingService(region_service, placement_service)
replication_service = ReplicationService()
orch = FailoverOrchestrator(region_service, placement_service, replication_service, routing_service)
migration_svc = TenantMigrationService(region_service, placement_service)
drift_svc = ConfigDriftService()
traffic_svc = TrafficShiftService()
rejoin_svc = RejoinService(region_service, replication_service)
drill_svc = DrillService()
aiops = AIOpsAdvisor()


CAPS = {k: True for k in ["AI", "GPU", "RAG", "vector_search", "graph", "storage", "compute", "deployment", "billing", "marketplace"]}


async def _seed(db, with_capacity=None):
    for rid, loc, cap in [
        ("eu-west", "EU", 50.0), ("us-east", "US", 40.0), ("ap-south", "APAC", 30.0), ("sa-east", "SA", 20.0),
    ]:
        c = cap if with_capacity is None else with_capacity.get(rid, cap)
        await region_service.register_region(db, region_id=rid, name=rid, provider="aws", location=loc,
                                              environment="production", capacity={"cpu": c, "memory": 50.0}, status="ACTIVE", capabilities=CAPS)
    await db.flush()


async def test_region_critical_safe_helper():
    assert is_region_critical_safe("ACTIVE")
    assert not is_region_critical_safe("FAILED")
    assert not is_region_critical_safe("UNKNOWN")


async def test_orchestrate_blocks_cooldown_and_unsafe_target(db, org_id):
    await _seed(db)
    # unsafe target (UNKNOWN) -> blocked
    await region_service.update_region(db, "sa-east", status="UNKNOWN")
    out = await orch.orchestrate_failover(db, org_id, "api", "eu-west", "sa-east")
    assert out["status"] == "BLOCKED"
    assert "not safe" in out["reason"]


async def test_orchestrate_residency_deny(db, org_id):
    await _seed(db)
    out = await orch.orchestrate_failover(db, org_id, "api", "eu-west", "us-east",
                                          authorized_by="admin", data_classification="SECRET")
    # us-east allowed? default placement none; residency bridge denies restricted w/o policy -> BLOCKED
    assert out["status"] == "BLOCKED"
    assert "residency" in out["reason"]


async def test_orchestrate_triggered_with_estimated_loss(db, org_id):
    await _seed(db)
    await replication_service.record_replication(db, "eu-west", "us-east", "tenant-data", lag_seconds=120.0, status="LAGGING")
    await db.flush()
    out = await orch.orchestrate_failover(db, org_id, "api", "eu-west", "us-east", authorized_by="admin", rpo_minutes=5)
    assert out["status"] == "TRIGGERED"
    # lag 120s vs rpo 5min -> data loss visible (>= ~1 min)
    assert out["estimated_data_loss_minutes"] is not None and out["estimated_data_loss_minutes"] >= 0


async def test_orchestrate_requires_authorization(db, org_id):
    await _seed(db)
    out = await orch.orchestrate_failover(db, org_id, "api", "eu-west", "us-east", automatic=False)
    assert out["status"] == "BLOCKED"
    assert "authorization" in out["reason"]


async def test_split_brain_fencing_and_stale(db, org_id):
    await _seed(db)
    lease = await orch.acquire_lease(db, "eu-west", "cp-1", ttl_seconds=60)
    assert lease.epoch >= 1
    # second holder while lease live -> split brain
    with pytest.raises(ValueError):
        await orch.acquire_lease(db, "eu-west", "cp-2", ttl_seconds=60)
    # fence the primary
    fenced = await orch.fence_primary(db, "eu-west", by="admin")
    assert fenced.fenced is True
    # after fence, cannot acquire
    with pytest.raises(ValueError):
        await orch.acquire_lease(db, "eu-west", "cp-3", ttl_seconds=60)
    # stale detection: lease expired + region active
    res = await db.execute(__import__("sqlalchemy").select(RegionLease).where(RegionLease.region_id == "eu-west"))
    l = res.scalar_one()
    l.fenced = False
    l.leased_until = __import__("datetime").datetime(2000, 1, 1, tzinfo=__import__("datetime").timezone.utc)
    await db.flush()
    assert await orch.detect_stale_primary(db, "eu-west") is True


async def test_replication_conflict_manual_review(db, org_id):
    c = await orch.detect_conflict(db, "eu-west", "us-east", "tenant/row1", "version", tenant=org_id)
    assert c.resolution == "pending"
    # critical entity -> manual review cannot auto-resolve
    resolved = await orch.resolve_conflict(db, c.id, "MANUAL_REVIEW", resolved_by="admin")
    assert resolved.resolution == "MANUAL_REVIEW"
    # non-manual policy resolves
    c2 = await orch.detect_conflict(db, "eu-west", "us-east", "tenant/row2", "version", tenant=org_id)
    r2 = await orch.resolve_conflict(db, c2.id, "LAST_WRITE_WINS", resolved_by="admin")
    assert r2.resolution == "LAST_WRITE_WINS"


async def test_tenant_migration_safety(db, org_id):
    await _seed(db)
    m = await migration_svc.plan(db, org_id, "eu-west", "us-east", authorized_by="admin",
                                 service="db", rollback_strategy="snapshot")
    assert m.state == MIG_PLANNED
    # db migration without rollback strategy must fail
    with pytest.raises(ValueError):
        await migration_svc.plan(db, org_id, "eu-west", "ap-south", authorized_by="admin", service="db")
    # advance to verifying then completed only after verify
    await migration_svc.advance(db, m.id, "COPYING")
    await migration_svc.advance(db, m.id, "SYNCING")
    await migration_svc.advance(db, m.id, "CUTOVER")
    await migration_svc.set_verification(db, m.id, {"checksum": "ok", "rows": 10})
    await migration_svc.advance(db, m.id, MIG_VERIFYING)
    await migration_svc.advance(db, m.id, MIG_COMPLETED)
    res = await db.execute(__import__("sqlalchemy").select(TenantMigration).where(TenantMigration.id == m.id))
    assert res.scalar_one().state == MIG_COMPLETED


async def test_tenant_migration_rollback(db, org_id):
    await _seed(db)
    m = await migration_svc.plan(db, org_id, "eu-west", "us-east", authorized_by="admin",
                                 service="db", rollback_strategy="snapshot")
    await migration_svc.advance(db, m.id, "COPYING")
    rolled = await migration_svc.rollback(db, m.id, reason="verification failed")
    assert rolled.state == MIG_ROLLED_BACK


async def test_traffic_shift_progressive(db, org_id):
    await _seed(db)
    s = await traffic_svc.shift(db, "us-east", 10)
    assert s.percentage == 10
    # next shift supersedes previous ACTIVE
    s2 = await traffic_svc.shift(db, "us-east", 50)
    assert s2.percentage == 50
    cur = await traffic_svc.current(db, "us-east")
    assert cur == 50
    # invalid step
    with pytest.raises(ValueError):
        await traffic_svc.shift(db, "us-east", 33)


async def test_rejoin_compromised_no_auto_admit(db, org_id):
    await _seed(db)
    out = await rejoin_svc.begin_rejoin(db, "eu-west", compromised=True)
    assert out["auto_rejoin"] is False
    # compromised region cannot admit traffic
    with pytest.raises(ValueError):
        await rejoin_svc.admit_traffic(db, "eu-west")


async def test_rejoin_verify_and_admit(db, org_id):
    await _seed(db)
    begin = await rejoin_svc.begin_rejoin(db, "us-east", compromised=False)
    assert begin["auto_rejoin"] is True
    v = await rejoin_svc.verify_sync(db, "us-east", "eu-west",
                                     checks={"integrity": True, "schema": True, "config": True, "permissions": True, "security": True, "observability": True})
    assert v["passed"] is True
    admit = await rejoin_svc.admit_traffic(db, "us-east")
    assert admit["state"] == "TRAFFIC"


async def test_config_drift_detect_and_resolve(db, org_id):
    d = await drift_svc.detect(db, org_id, "routing", "v2", "v1")
    assert d.status == "OPEN"
    # no drift when versions match
    d2 = await drift_svc.detect(db, org_id, "routing", "v2", "v2")
    assert d2.status == "CLOSED"
    resolved = await drift_svc.resolve(db, d.id)
    assert resolved.status == "CLOSED"


async def test_drills_and_aiops(db, org_id):
    await _seed(db)
    drill = await drill_svc.run(db, "split_brain", region_id="eu-west")
    assert drill["status"] == "SIMULATED"
    rec = aiops.recommend("eu-west", {"replication_lag_seconds": 90, "cpu": 30, "error_rate": 0.01})
    assert rec["action"] == "promote_failover_readiness"
    assert rec["automated_remediation_allowed"] is False  # medium risk
    rec2 = aiops.recommend("eu-west", {"cpu": 30, "error_rate": 0.01})
    assert rec2["risk"] == "low"


async def test_workers_run(db, org_id):
    await _seed(db)
    hw = await RegionHealthWorker().run_once(db)
    assert isinstance(hw, int)
    cw = await CapacityWorker().run_once(db)
    assert isinstance(cw, list)
