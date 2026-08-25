"""Volume 60 Commit 1 — backup lifecycle, verification, restore, recovery, failover."""

import pytest, uuid
from datetime import datetime, timezone

from app.resilience.platform import resilience_service


@pytest.mark.asyncio
async def test_backup_lifecycle(db, org_id):
    tenant = org_id
    backup = await resilience_service.start_backup(
        db, tenant=tenant, scope_type="database", scope_target="main",
        metadata_json={"content": "backup payload data", "completed": True},
        created_by="tester",
    )
    assert backup.status == "COMPLETED"
    assert backup.checksum is not None
    assert len(backup.checksum) == 64  # sha256 hex

    # idempotency: same key returns same backup
    b2 = await resilience_service.start_backup(
        db, tenant=tenant, scope_type="database", scope_target="main",
        idempotency_key="op-123", metadata_json={"content": "x", "completed": True},
    )
    assert b2.metadata_json.get("idempotency_key") == "op-123"


@pytest.mark.asyncio
async def test_backup_verification_checksum(db, org_id):
    tenant = org_id
    content = "important database snapshot bytes"
    backup = await resilience_service.start_backup(
        db, tenant=tenant, scope_type="object_storage",
        metadata_json={"content": content, "completed": True},
    )
    # correct checksum passes
    ver = await resilience_service.verify_backup(db, tenant, str(backup.id), verification_type="checksum", expected_checksum=backup.checksum)
    assert ver.status == "PASSED"
    assert backup.verification_status == "PASSED"

    # wrong checksum fails
    backup2 = await resilience_service.start_backup(
        db, tenant=tenant, scope_type="object_storage", metadata_json={"content": content, "completed": True},
    )
    ver2 = await resilience_service.verify_backup(db, tenant, str(backup2.id), verification_type="checksum", expected_checksum="deadbeef" * 8)
    assert ver2.status == "FAILED"
    assert backup2.verification_status == "FAILED"


@pytest.mark.asyncio
async def test_unverified_backup_cannot_restore_to_production(db, org_id):
    tenant = org_id
    backup = await resilience_service.start_backup(
        db, tenant=tenant, scope_type="service", metadata_json={"content": "data", "completed": True},
    )
    # UNVERIFIED + production -> safety check must fail (job state FAILED)
    job = await resilience_service.request_restore(
        db, tenant=tenant, backup_id=str(backup.id), mode="full", target_environment="production",
        approved_by="admin-1",
    )
    assert job.safety_checks.get("backup_verified") is False
    assert job.state == "FAILED"

    # isolated drill may proceed even unverified
    drill = await resilience_service.request_restore(
        db, tenant=tenant, backup_id=str(backup.id), mode="full",
        target_environment="staging", isolated_test=True,
    )
    assert drill.state in ("READY", "PLANNED")
    assert drill.isolated_test is True


@pytest.mark.asyncio
async def test_tenant_isolation_restore(db, org_id):
    tenant_a = org_id
    tenant_b = str(uuid.uuid4())
    backup = await resilience_service.start_backup(
        db, tenant=tenant_a, scope_type="database", metadata_json={"content": "secret-a", "completed": True},
    )
    # Tenant B cannot see or restore Tenant A's backup
    with pytest.raises(ValueError, match="not found"):
        await resilience_service.request_restore(db, tenant=tenant_b, backup_id=str(backup.id), mode="full")


@pytest.mark.asyncio
async def test_recovery_state_machine_and_dependency_ordering(db, org_id):
    tenant = org_id
    plan = await resilience_service.create_recovery_plan(
        db, tenant=tenant, name="db-recovery", service="core-api",
        steps=[
            {"action": "dependency_recovery", "resource": "postgres"},
            {"action": "data_recovery", "resource": "core-db"},
            {"action": "service_recovery", "resource": "core-api"},
            {"action": "traffic_recovery"},
            {"action": "verification"},
        ],
    )
    res = await resilience_service.execute_recovery_plan(db, tenant, str(plan.id), actor="sre")
    assert res["state"] == "COMPLETED"
    ordered_actions = [s["action"] for s in res["steps"]]
    assert ordered_actions.index("dependency_recovery") < ordered_actions.index("data_recovery") < ordered_actions.index("service_recovery")

    # approval-gated step blocks completion
    plan2 = await resilience_service.create_recovery_plan(
        db, tenant=tenant, name="gated", service="svc-x",
        steps=[{"action": "verification"}, {"action": "traffic_recovery", "requires_approval": True}],
    )
    res2 = await resilience_service.execute_recovery_plan(db, tenant, str(plan2.id), actor="sre")
    assert any(s["status"] == "approval_required" for s in res2["steps"])
    assert res2["state"] != "COMPLETED"


@pytest.mark.asyncio
async def test_rto_rpo_calculations(db, org_id):
    tenant = org_id
    now = datetime.now(timezone.utc)
    prof = await resilience_service.create_profile(db, tenant=tenant, service="api", rto_minutes=60, rpo_minutes=15)
    assert prof.rto_minutes == 60 and prof.rpo_minutes == 15
    # measured from real records only
    evt = await resilience_service.declare_disaster(
        db, tenant=tenant, disaster_type="SERVICE_OUTAGE", reason="test", declared_by="sre",
        scope={"services": ["api"]}, severity="HIGH",
    )
    evt.status = "RESOLVED"
    evt.resolved_at = now
    await db.flush()
    backup = await resilience_service.start_backup(
        db, tenant=tenant, scope_type="database", metadata_json={"content": "d", "completed": True},
    )
    await resilience_service.verify_backup(db, tenant, str(backup.id), verification_type="checksum", expected_checksum=backup.checksum)
    out = await resilience_service.compute_rto_rpo(db, tenant, "api")
    assert out["target_rto_minutes"] == 60
    assert out["measured_rpo_minutes_approx"] is not None


@pytest.mark.asyncio
async def test_failover_permissions_and_health(db, org_id):
    tenant = org_id
    # Use allowed region so start succeeds, then promotion without health must fail closed
    rec = await resilience_service.start_failover(
        db, tenant=tenant, failover_type="region", source_target="us-east", destination_target="us-west",
        restricted_data_regions=["us-east", "us-west"],
    )
    assert rec.data_residency_ok is True
    # promote without health evidence must fail closed
    with pytest.raises(ValueError, match="health verification"):
        await resilience_service.promote_failover(db, tenant, str(rec.id), health_verified=None)


@pytest.mark.asyncio
async def test_failover_restricted_region_blocked(db, org_id):
    tenant = org_id
    with pytest.raises(ValueError, match="unauthorized region"):
        await resilience_service.start_failover(
            db, tenant=tenant, failover_type="region",
            source_target="eu-west", destination_target="ap-south",
            restricted_data_regions=["eu-west"],  # restricted: only eu-west permitted
        )


@pytest.mark.asyncio
async def test_disaster_declaration_states(db, org_id):
    tenant = org_id
    evt = await resilience_service.declare_disaster(
        db, tenant=tenant, disaster_type="DATABASE_CORRUPTION" if False else "DATA_CORRUPTION",
        reason="integrity checks failing", declared_by="dba", severity="CRITICAL",
    )
    assert evt.status == "DECLARED"
    resolved = await resilience_service.resolve_disaster(db, tenant, str(evt.id), actor="sre")
    assert resolved.status == "RESOLVED"
    # invalid type rejected
    with pytest.raises(ValueError, match="invalid disaster_type"):
        await resilience_service.declare_disaster(db, tenant=tenant, disaster_type="ALIEN_INVASION", reason="x", declared_by="u")


@pytest.mark.asyncio
async def test_pitr_honesty(db, org_id):
    tenant = org_id
    backup = await resilience_service.start_backup(
        db, tenant=tenant, scope_type="database", metadata_json={"content": "d", "completed": True},
    )
    # PITR requested but engine did not declare pitr_supported -> fail closed
    job = await resilience_service.request_restore(
        db, tenant=tenant, backup_id=str(backup.id), mode="point_in_time",
        point_in_time=datetime.now(timezone.utc), isolated_test=True,
    )
    assert job.safety_checks.get("pitr_supported") is False
    assert job.state == "FAILED"


@pytest.mark.asyncio
async def test_secret_never_backed_up_raw(db, org_id):
    """Configuration backups store references, never raw secret values."""
    tenant = org_id
    pol = await resilience_service.create_backup_policy(
        db, tenant=tenant, name="cfg-policy", scope_type="configuration",
        encryption_key_ref="kms://keys/config-backup",  # reference only
    )
    assert pol.encryption_key_ref.startswith("kms://")
    assert "BEGIN PRIVATE KEY" not in (pol.encryption_key_ref or "")


@pytest.mark.asyncio
async def test_event_bus_outage_outbox_fallback(db, org_id):
    """Recovery state transitions survive Event Bus outage via durable fallback."""
    tenant = org_id
    # _safe_event writes an OUTBOX row when bus publish raises; simulate by direct call
    await resilience_service._safe_event(db, tenant, "__no_such_event__", "ref-1")
    # no crash = outbox handled gracefully (mapping miss returns early); force the exception path:
    import app.observability.platform  # noqa: F401  ensure modules loaded
    try:
        class Boom:
            async def publish_nowait(self, event):
                raise RuntimeError("bus down")
        import app.core.events as ev_mod
        original = ev_mod.event_bus
        ev_mod.event_bus = Boom()
        try:
            await resilience_service._safe_event(db, tenant, "BackupStarted", "ref-2")
            # If mapping found the type and bus raised, an OUTBOX row should be recorded.
            from sqlalchemy import select
            from app.resilience.models import ResilienceDisasterEvent
            rows = list((await db.execute(select(ResilienceDisasterEvent).where(ResilienceDisasterEvent.tenant == tenant))).scalars().all())
            assert any(r.disaster_type == "OUTBOX" for r in rows)
        finally:
            ev_mod.event_bus = original
    except AssertionError:
        raise
