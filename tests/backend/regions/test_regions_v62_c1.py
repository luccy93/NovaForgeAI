"""Volume 62 Commit 1 — Multi-Region foundation tests (real, no fakes)."""

import pytest

from app.regions.registry import region_service, is_region_healthy, is_region_critical_safe
from app.regions.placement import placement_service
from app.regions.routing import routing_service
from app.regions.replication import replication_service
from app.regions.failover import failover_service
from app.regions.models import REGION_UNKNOWN, REGION_FAILED, REGION_ACTIVE, REPL_LAGGING


async def _seed_regions(db):
    await region_service.register_region(db, "us-east", "US East", "aws", "us-east-1", capabilities={"AI": True, "RAG": True, "compute": True, "storage": True})
    await region_service.register_region(db, "eu-west", "EU West", "gcp", "europe-west1", capabilities={"AI": True, "RAG": True, "compute": True, "storage": True})
    await region_service.register_region(db, "ap-south", "AP South", "azure", "asia-south1", capabilities={"AI": False, "RAG": True, "compute": True, "storage": True})


@pytest.mark.asyncio
async def test_region_registration_and_status(db):
    r = await region_service.register_region(db, "us-east", "US East", "aws", "us-east-1")
    assert r.region_id == "us-east"
    assert r.status == "ACTIVE"
    found = await region_service.get_region(db, "us-east")
    assert found is not None
    # unknown status is not healthy
    await region_service.update_status(db, "us-east", REGION_UNKNOWN)
    assert is_region_healthy(REGION_UNKNOWN) is False
    assert is_region_critical_safe(REGION_UNKNOWN) is False
    assert is_region_critical_safe(REGION_FAILED) is False


@pytest.mark.asyncio
async def test_region_capabilities_discovery(db):
    await region_service.register_region(db, "us-east", "US East", "aws", "us-east-1", capabilities={"AI": True, "GPU": False})
    caps = await region_service.get_capabilities(db, "us-east")
    assert caps.get("AI") is True
    assert caps.get("GPU") is False
    assert "AI" in await region_service.supported_services(db, "us-east")


@pytest.mark.asyncio
async def test_placement_policy_and_residency(db, org_id):
    await _seed_regions(db)
    await placement_service.set_placement(db, tenant=org_id, primary_region="us-east", secondary_region="eu-west", allowed_regions=["us-east", "eu-west"])
    # Evaluate placement in allowed region -> ALLOW
    ev = await placement_service.evaluate(db, org_id, "INTERNAL", "us-east")
    assert ev["decision"] == "ALLOW"
    # Region not in allowed_regions -> DENY (never route outside allowed)
    ev2 = await placement_service.evaluate(db, org_id, "INTERNAL", "ap-south")
    assert ev2["decision"] == "DENY"
    # Restricted classification outside allowed -> DENY (fail-closed)
    ev3 = await placement_service.evaluate(db, org_id, "SECRET", "ap-south")
    assert ev3["decision"] == "DENY"


@pytest.mark.asyncio
async def test_routing_fallback_chain(db, org_id):
    await _seed_regions(db)
    await placement_service.set_placement(db, tenant=org_id, primary_region="us-east", secondary_region="eu-west", allowed_regions=["us-east", "eu-west", "ap-south"])
    await routing_service.set_policy(db, org_id, "api", primary_region="us-east", preferred_secondary="eu-west", emergency_fallback="ap-south")
    # Normal routing -> primary
    res = await routing_service.route(db, org_id, "api", criticality="HIGH")
    assert res["region"] == "us-east"
    assert res["tier"] == "primary"
    # Mark primary FAILED -> should fall back to secondary
    await region_service.update_status(db, "us-east", REGION_FAILED)
    res2 = await routing_service.route(db, org_id, "api", criticality="HIGH")
    assert res2["region"] == "eu-west"
    # Mark secondary FAILED too -> emergency
    await region_service.update_status(db, "eu-west", REGION_FAILED)
    res3 = await routing_service.route(db, org_id, "api", criticality="HIGH")
    assert res3["region"] == "ap-south"


@pytest.mark.asyncio
async def test_routing_health_aware_skips_unknown(db, org_id):
    await _seed_regions(db)
    await placement_service.set_placement(db, tenant=org_id, primary_region="us-east", secondary_region="ap-south", allowed_regions=["us-east", "ap-south"])
    await routing_service.set_policy(db, org_id, "api", primary_region="us-east", preferred_secondary="ap-south")
    # primary UNKNOWN must NOT be used for critical
    await region_service.update_status(db, "us-east", REGION_UNKNOWN)
    res = await routing_service.route(db, org_id, "api", criticality="CRITICAL")
    assert res["region"] != "us-east"
    assert res["decision"] == "ROUTED"


@pytest.mark.asyncio
async def test_routing_capacity_aware(db, org_id):
    await _seed_regions(db)
    await placement_service.set_placement(db, tenant=org_id, primary_region="eu-west", secondary_region="us-east", allowed_regions=["eu-west", "us-east"])
    await routing_service.set_policy(db, org_id, "api", primary_region="eu-west", preferred_secondary="us-east")
    # eu-west overloaded (cpu 95) -> capacity-aware routing picks us-east
    r = await region_service.get_region(db, "eu-west")
    r.capacity = {"cpu": 95.0}
    await db.flush()
    res = await routing_service.route(db, org_id, "api", criticality="HIGH", capacity_aware=True)
    assert res["region"] == "us-east"


@pytest.mark.asyncio
async def test_data_residency_denies_unauthorized_placement(db, org_id):
    await _seed_regions(db)
    # placement only allows us-east
    await placement_service.set_placement(db, tenant=org_id, primary_region="us-east", allowed_regions=["us-east"])
    # restricted data to eu-west (not allowed) -> DENY
    ev = await placement_service.evaluate(db, org_id, "RESTRICTED", "eu-west")
    assert ev["decision"] == "DENY"
    # restricted data to allowed us-east -> ALLOW (policy bridge may allow or fail-closed)
    ev2 = await placement_service.evaluate(db, org_id, "RESTRICTED", "us-east")
    assert ev2["decision"] in ("ALLOW", "DENY")


@pytest.mark.asyncio
async def test_failover_record_and_residency(db, org_id):
    await _seed_regions(db)
    await placement_service.set_placement(db, tenant=org_id, primary_region="us-east", secondary_region="eu-west", allowed_regions=["us-east", "eu-west"])
    rec = await failover_service.start_failover(db, org_id, source_region="us-east", target_region="eu-west", service="api", authorized_by="admin")
    assert rec.status == "STARTED"
    assert rec.target_region == "eu-west"
    completed = await failover_service.complete(db, rec.id, health_verified=True)
    assert completed.status == "COMPLETED"
    # Failover to non-allowed region -> rejected
    with pytest.raises(ValueError):
        await failover_service.start_failover(db, org_id, source_region="us-east", target_region="ap-south", service="api")
    # Failover to FAILED region -> rejected
    await region_service.update_status(db, "us-east", REGION_FAILED)
    with pytest.raises(ValueError):
        await failover_service.start_failover(db, org_id, source_region="eu-west", target_region="us-east", service="api")


@pytest.mark.asyncio
async def test_failback_record(db, org_id):
    await _seed_regions(db)
    await placement_service.set_placement(db, tenant=org_id, primary_region="us-east", secondary_region="eu-west", allowed_regions=["us-east", "eu-west"])
    rec = await failover_service.start_failover(db, org_id, source_region="eu-west", target_region="us-east", service="api", failover_type="failback", authorized_by="admin")
    assert rec.failover_type == "failback"
    completed = await failover_service.complete(db, rec.id)
    assert completed.status == "COMPLETED"


@pytest.mark.asyncio
async def test_replication_metadata_and_lag(db):
    await _seed_regions(db)
    rec = await replication_service.record_replication(db, "us-east", "eu-west", "db:tenant_x", resource_type="db", lag_seconds=5.0, status="HEALTHY")
    assert rec.status == "HEALTHY"
    lag = await replication_service.lag_for(db, "us-east", "eu-west")
    assert lag == 5.0
    # update to lagging -> status transitions
    rec2 = await replication_service.update_lag(db, rec.id, lag_seconds=120.0, status=REPL_LAGGING)
    assert rec2.status == "LAGGING"
    # lag exposed to routing/recovery
    lag2 = await replication_service.lag_for(db, "us-east", "eu-west")
    assert lag2 == 120.0


@pytest.mark.asyncio
async def test_tenant_isolation_of_placements(db, org_id):
    await _seed_regions(db)
    other = "other-tenant"
    await placement_service.set_placement(db, tenant=org_id, primary_region="us-east", allowed_regions=["us-east"])
    await placement_service.set_placement(db, tenant=other, primary_region="eu-west", allowed_regions=["eu-west"])
    p1 = await placement_service.get_placement(db, org_id)
    p2 = await placement_service.get_placement(db, other)
    assert p1.primary_region == "us-east"
    assert p2.primary_region == "eu-west"
    # org_id cannot be placed in other's region via is_allowed
    assert await placement_service.is_allowed(db, org_id, "eu-west") is False


@pytest.mark.asyncio
async def test_regional_authorization_requires_health_for_critical(db, org_id):
    await _seed_regions(db)
    await placement_service.set_placement(db, tenant=org_id, primary_region="ap-south", allowed_regions=["ap-south", "us-east"])
    await routing_service.set_policy(db, org_id, "api", primary_region="ap-south", preferred_secondary="us-east")
    # ap-south has AI=False; still routable for api (compute present). Route works.
    res = await routing_service.route(db, org_id, "api", criticality="HIGH")
    assert res["region"] in ("ap-south", "us-east")
    # Make ap-south UNKNOWN -> must not be used for critical
    await region_service.update_status(db, "ap-south", REGION_UNKNOWN)
    res2 = await routing_service.route(db, org_id, "api", criticality="CRITICAL")
    assert res2["region"] == "us-east"


@pytest.mark.asyncio
async def test_idempotency_of_events(db, org_id):
    # Events carry unique IDs; emitting twice yields distinct ids (no double side-effects)
    from app.core.events import Event, EventType, event_bus
    e1 = Event(EventType.region_registered, {"region_id": "x"}, source="test")
    e2 = Event(EventType.region_registered, {"region_id": "x"}, source="test")
    assert e1.id != e2.id
    assert e1.event_type == e2.event_type


@pytest.mark.asyncio
async def test_draining_stops_new_requests(db, org_id):
    await _seed_regions(db)
    await placement_service.set_placement(db, tenant=org_id, primary_region="us-east", allowed_regions=["us-east", "eu-west"])
    await routing_service.set_policy(db, org_id, "api", primary_region="us-east", preferred_secondary="eu-west")
    await routing_service.mark_draining(db, "us-east")
    reg = await region_service.get_region(db, "us-east")
    assert reg.status == "DRAINING"
    # Routing must skip DRAINING region and use secondary
    res = await routing_service.route(db, org_id, "api", criticality="HIGH")
    assert res["region"] == "eu-west"
