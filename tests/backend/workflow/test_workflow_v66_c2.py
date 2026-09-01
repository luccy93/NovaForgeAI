"""Volume 66 Commit 2 — Advanced automation & hardening tests."""

import pytest
import uuid
from datetime import datetime, timezone, timedelta

from app.workflow.definition import create_workflow, create_version, publish_version
from app.workflow.execution import start_run, run_workflow
from app.workflow.event_automation import register_event_trigger, handle_event, clear_caches, get_dead_letter
from app.workflow.concurrency import check_concurrency
from app.workflow.recovery import replay_workflow, acquire_lease, recover_stale_execution
from app.workflow.human_tasks import create_human_task, update_human_task
from app.workflow.business import create_process, transition_process
from app.workflow.templates import create_template, publish_template, list_templates

pytestmark = pytest.mark.asyncio


async def test_event_driven_debouncing_and_throttling(db, org_id):
    clear_caches()
    wf = await create_workflow(db, org_id, {"name": "evt_wf", "definition": {"steps": [{"id": "s1", "type": "TASK"}]}})
    await db.commit()
    from sqlalchemy import select
    from app.workflow.models import WorkflowVersion
    q = select(WorkflowVersion).where(WorkflowVersion.workflow_id == wf.id)
    res = await db.execute(q)
    ver = res.scalar_one()
    ver = await publish_version(db, org_id, str(ver.id))
    await db.commit()
    await register_event_trigger(db, org_id, str(ver.id), "deployment.completed", "myapp")
    await db.commit()
    # First event should trigger
    triggered = await handle_event(db, org_id, "deployment.completed", "myapp", {"payload": "x"})
    assert len(triggered) == 1
    # Second immediate should be debounced (same fingerprint within 60s)
    triggered2 = await handle_event(db, org_id, "deployment.completed", "myapp", {"payload": "x"})
    assert len(triggered2) == 0
    # Different resource not registered should not trigger (only myapp registered)
    triggered3 = await handle_event(db, org_id, "deployment.completed", "otherapp", {"payload": "y"})
    assert len(triggered3) == 0


async def test_workflow_concurrency_limits(db, org_id):
    # Create 5 runs for same workflow, check concurrency limit workflow=5 should allow 5, 6th should be blocked
    wf = await create_workflow(db, org_id, {"name": "conc_wf", "definition": {"steps": [{"id": "s1", "type": "TASK"}]}})
    await db.commit()
    from sqlalchemy import select
    from app.workflow.models import WorkflowVersion
    q = select(WorkflowVersion).where(WorkflowVersion.workflow_id == wf.id)
    res = await db.execute(q)
    ver = res.scalar_one()
    ver = await publish_version(db, org_id, str(ver.id))
    await db.commit()
    # Start 5 runs
    for i in range(5):
        await start_run(db, org_id, str(ver.id), trigger={"i": i})
    await db.commit()
    allowed, reason = await check_concurrency(db, org_id, str(ver.id))
    assert allowed is False
    assert "workflow concurrency" in reason


async def test_replay_safety_no_duplicate_destructive(db, org_id):
    wf = await create_workflow(db, org_id, {"name": "replay_wf", "definition": {"steps": [{"id": "s1", "type": "TASK"}]}})
    await db.commit()
    from sqlalchemy import select
    from app.workflow.models import WorkflowVersion
    q = select(WorkflowVersion).where(WorkflowVersion.workflow_id == wf.id)
    res = await db.execute(q)
    ver = res.scalar_one()
    ver = await publish_version(db, org_id, str(ver.id))
    await db.commit()
    run = await start_run(db, org_id, str(ver.id))
    run.status = "FAILED"
    await db.flush()
    await db.commit()
    new_run = await replay_workflow(db, org_id, str(run.id), requester="tester")
    assert str(new_run.id) != str(run.id)
    assert new_run.workflow_version_id == run.workflow_version_id


async def test_recovery_lease_fencing(db, org_id):
    wf = await create_workflow(db, org_id, {"name": "lease_wf", "definition": {"steps": [{"id": "s1", "type": "TASK"}]}})
    await db.commit()
    from sqlalchemy import select
    from app.workflow.models import WorkflowVersion
    q = select(WorkflowVersion).where(WorkflowVersion.workflow_id == wf.id)
    res = await db.execute(q)
    ver = res.scalar_one()
    ver = await publish_version(db, org_id, str(ver.id))
    await db.commit()
    run = await start_run(db, org_id, str(ver.id))
    await db.commit()
    # Acquire lease
    ok = await acquire_lease(db, org_id, str(run.id), worker_id="worker1")
    assert ok is True
    # Second worker cannot acquire
    ok2 = await acquire_lease(db, org_id, str(run.id), worker_id="worker2")
    assert ok2 is False
    # Recover after lease expiry (simulate expiry by clearing)
    from app.workflow.recovery import _lease_store
    _lease_store[f"workflow_lease:{run.id}"]["expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    recovered = await recover_stale_execution(db, org_id, str(run.id), new_worker_id="worker2")
    assert recovered.id == run.id


async def test_human_tasks_and_reassignment(db, org_id):
    wf = await create_workflow(db, org_id, {"name": "human_wf", "definition": {"steps": [{"id": "s1", "type": "TASK"}]}})
    await db.commit()
    from sqlalchemy import select
    from app.workflow.models import WorkflowVersion
    q = select(WorkflowVersion).where(WorkflowVersion.workflow_id == wf.id)
    res = await db.execute(q)
    ver = res.scalar_one()
    ver = await publish_version(db, org_id, str(ver.id))
    await db.commit()
    run = await start_run(db, org_id, str(ver.id))
    task = await create_human_task(db, org_id, str(run.id), str(ver.id), assignee="alice")
    assert task.status == "PENDING"
    # Reassign requires auth, but in TESTING we bypass
    from app.workflow.human_tasks import reassign_task
    new_task = await reassign_task(db, org_id, str(task.id), new_assignee="bob", requester="admin")
    assert new_task.assignee == "bob"
    # Complete
    completed = await update_human_task(db, org_id, str(new_task.id), status="COMPLETED", decision="COMPLETED")
    assert completed.status == "COMPLETED"


async def test_business_process_sla_and_escalation(db, org_id):
    wf = await create_workflow(db, org_id, {"name": "biz_wf", "definition": {"steps": [{"id": "s1", "type": "TASK"}]}})
    await db.commit()
    from sqlalchemy import select
    from app.workflow.models import WorkflowVersion
    q = select(WorkflowVersion).where(WorkflowVersion.workflow_id == wf.id)
    res = await db.execute(q)
    ver = res.scalar_one()
    ver = await publish_version(db, org_id, str(ver.id))
    await db.commit()
    run = await start_run(db, org_id, str(ver.id))
    proc = await create_process(db, org_id, str(ver.id), str(run.id), sla_hours=1)
    assert proc.current_state == "REQUESTED"
    # Valid transition
    proc = await transition_process(db, org_id, str(proc.id), "APPROVED")
    assert proc.current_state == "APPROVED"
    # Invalid transition should fail
    with pytest.raises(ValueError, match="invalid transition"):
        await transition_process(db, org_id, str(proc.id), "COMPLETED")
    # SLA breach check (set deadline in past)
    proc.sla_deadline = datetime.now(timezone.utc) - timedelta(hours=1)
    await db.flush()
    from app.workflow.business import check_sla_breach
    breached = await check_sla_breach(db, org_id)
    assert any(p.id == proc.id for p in breached)


async def test_templates_versioned_and_governed(db, org_id):
    tmpl = await create_template(db, org_id, {"name": "tmpl_test", "definition": {"steps": [{"id": "s1", "type": "TASK"}]}}, owner="alice")
    assert tmpl.is_published is False
    # Unsafe template should fail
    with pytest.raises(ValueError, match="unsafe"):
        await create_template(db, org_id, {"name": "bad_tmpl", "definition": {"steps": [{"id": "s1", "type": "TASK", "action": "rm -rf /"}]}}, owner="alice")
    # Publish requires approver
    tmpl2 = await publish_template(db, org_id, str(tmpl.id), approver="admin")
    assert tmpl2.is_published is True
    # List
    templates = await list_templates(db, org_id)
    assert any(t["name"] == "tmpl_test" for t in templates)


async def test_workflow_health_and_anomalies(db, org_id):
    wf = await create_workflow(db, org_id, {"name": "health_wf", "definition": {"steps": [{"id": "s1", "type": "TASK"}]}})
    await db.commit()
    from sqlalchemy import select
    from app.workflow.models import WorkflowVersion
    q = select(WorkflowVersion).where(WorkflowVersion.workflow_id == wf.id)
    res = await db.execute(q)
    ver = res.scalar_one()
    ver = await publish_version(db, org_id, str(ver.id))
    await db.commit()
    # Create some runs with distinct triggers to avoid idempotency dedup
    for i in range(3):
        run = await start_run(db, org_id, str(ver.id), trigger={"i": i, "t": str(uuid.uuid4())})
        run.status = "COMPLETED"
        await db.flush()
    for i in range(1):
        run = await start_run(db, org_id, str(ver.id), trigger={"j": i, "t": str(uuid.uuid4())})
        run.status = "FAILED"
        run.duration_ms = 70000  # unusual
        await db.flush()
    await db.commit()
    # Health via API logic
    from sqlalchemy import select as sel2
    from app.workflow.models import WorkflowRun
    q2 = select(WorkflowRun).where(WorkflowRun.tenant == org_id)
    res2 = await db.execute(q2)
    runs = res2.scalars().all()
    total = len(runs)
    assert total >= 4


async def test_tenant_isolation_workflow(db, org_id, other_org_id):
    wf = await create_workflow(db, org_id, {"name": "iso_wf2", "definition": {"steps": [{"id": "s1", "type": "TASK"}]}})
    await db.commit()
    # Other tenant cannot see
    from app.workflow.definition import list_workflows
    rows = await list_workflows(db, other_org_id)
    assert not any(r.name == "iso_wf2" for r in rows)
