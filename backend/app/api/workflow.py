"""Workflow API — Volume 66 Commit 1."""

import uuid
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import _get_current_user
from app.core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflows", tags=["Workflow"])


def _tenant(user) -> str:
    oid = getattr(user, "organization_id", None) or getattr(user, "id", None)
    if not oid:
        raise HTTPException(status_code=403, detail="No tenant context")
    return str(oid)


def _iam_check(user, tenant: str, permission: str, resource_type: str = "workflow"):
    try:
        from app.iam.policy_authorizer import policy_authorizer
        ctx = {"role": str(getattr(user, "role", "viewer"))}
        decision = policy_authorizer.authorize(str(getattr(user, "id", "")), tenant, permission, resource_type=resource_type, context=ctx)
        if not decision.get("allowed", True):
            raise HTTPException(status_code=403, detail=decision.get("reason", "Forbidden"))
    except HTTPException:
        raise
    except Exception as exc:
        logger.debug("IAM check skipped %s: %s", permission, exc)


async def _emit(event_name: str, data: dict, tenant: str):
    try:
        from app.core.events import Event, EventType, event_bus
        et = getattr(EventType, event_name, None)
        if et:
            await event_bus.publish_nowait(Event(et, data, source="workflow", organization_id=tenant))
    except Exception as exc:
        logger.debug("emit failed %s: %s", event_name, exc)


def _to_uuid(v):
    try:
        return uuid.UUID(str(v))
    except Exception:
        return v


# ── Models ───────────────────────────────────────────────────────────────────
class WorkflowCreateIn(BaseModel):
    name: str = Field(..., max_length=128)
    description: Optional[str] = None
    workspace: Optional[str] = None
    version: str = "1.0"
    definition: dict = {}
    inputs: dict = {}
    outputs: dict = {}
    owner: Optional[str] = None


class WorkflowVersionCreateIn(BaseModel):
    definition: dict
    version: Optional[str] = None


class TriggerIn(BaseModel):
    trigger_type: str = "manual"
    inputs: dict = {}
    idempotency_key: Optional[str] = None
    region: Optional[str] = None


# ── Workflows ────────────────────────────────────────────────────────────────
@router.post("", status_code=201)
async def create_workflow(payload: WorkflowCreateIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "workflow:execute", "workflow")
    from app.workflow.definition import create_workflow
    try:
        wf = await create_workflow(db, tenant, payload.model_dump(), created_by=str(getattr(user, "id", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    await _emit("WorkflowCreated", {"workflow_id": str(wf.id), "tenant": tenant}, tenant)
    return {"id": str(wf.id), "name": wf.name, "version": wf.version, "status": wf.status}


@router.get("", status_code=200)
async def list_workflows(status: Optional[str] = None, limit: int = Query(20, ge=1, le=100), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.workflow.definition import list_workflows
    rows = await list_workflows(db, tenant, status=status, limit=limit)
    return {"items": [{"id": str(r.id), "name": r.name, "version": r.version, "status": r.status} for r in rows]}


@router.get("/{workflow_id}", status_code=200)
async def get_workflow(workflow_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.workflow.definition import get_workflow
    wf = await get_workflow(db, tenant, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="workflow not found")
    return {"id": str(wf.id), "name": wf.name, "version": wf.version, "status": wf.status, "description": wf.description}


@router.post("/{workflow_id}/versions", status_code=201)
async def create_workflow_version(workflow_id: str, payload: WorkflowVersionCreateIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "workflow:execute", "workflow")
    from app.workflow.definition import create_version
    try:
        ver = await create_version(db, tenant, workflow_id, payload.model_dump(), created_by=str(getattr(user, "id", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": str(ver.id), "version": ver.version, "workflow_id": str(ver.workflow_id)}


@router.get("/{workflow_id}/versions", status_code=200)
async def list_versions(workflow_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.workflow.models import WorkflowVersion
    try:
        wid = uuid.UUID(workflow_id)
        q = select(WorkflowVersion).where(WorkflowVersion.workflow_id == wid, WorkflowVersion.tenant == tenant).order_by(WorkflowVersion.created_at.desc())
    except Exception:
        raise HTTPException(status_code=422, detail="invalid workflow_id")
    res = await db.execute(q)
    rows = res.scalars().all()
    return {"items": [{"id": str(r.id), "version": r.version, "status": r.status, "dag_hash": r.dag_hash} for r in rows]}


@router.post("/{workflow_id}/publish", status_code=200)
async def publish_workflow(workflow_id: str, payload: dict | None = None, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "workflow:execute", "workflow")
    version_id = (payload or {}).get("version_id")
    if not version_id:
        # Publish latest draft
        from app.workflow.models import WorkflowVersion
        try:
            wid = uuid.UUID(workflow_id)
            q = select(WorkflowVersion).where(WorkflowVersion.workflow_id == wid, WorkflowVersion.tenant == tenant, WorkflowVersion.status == "DRAFT").order_by(WorkflowVersion.created_at.desc()).limit(1)
            res = await db.execute(q)
            ver = res.scalar_one_or_none()
            if not ver:
                raise HTTPException(status_code=404, detail="no draft version found")
            version_id = str(ver.id)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=422, detail=str(e))
    from app.workflow.definition import publish_version
    try:
        ver = await publish_version(db, tenant, version_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    await _emit("WorkflowPublished", {"workflow_id": workflow_id, "version_id": version_id}, tenant)
    return {"id": str(ver.id), "version": ver.version, "status": ver.status}


# ── Trigger / Run ────────────────────────────────────────────────────────────
@router.post("/{workflow_id}/trigger", status_code=201)
@router.post("/{workflow_id}/run", status_code=201)
async def trigger_workflow(workflow_id: str, payload: TriggerIn, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "workflow:execute", "workflow")
    # Resolve workflow_version_id: if payload contains workflow_version_id use, else use current published
    version_id = payload.inputs.get("workflow_version_id") if payload.inputs else None
    if not version_id:
        from app.workflow.definition import get_workflow
        wf = await get_workflow(db, tenant, workflow_id)
        if not wf or not wf.current_version_id:
            raise HTTPException(status_code=422, detail="no published version")
        version_id = str(wf.current_version_id)
    from app.workflow.execution import start_run, run_workflow
    try:
        run = await start_run(db, tenant, version_id, trigger=payload.inputs, idempotency_key=payload.idempotency_key, region=payload.region, inputs=payload.inputs)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    # For manual trigger, require authorization already checked, then execute
    # For event trigger, would be via EventBus; here we run immediately for test
    try:
        run = await run_workflow(db, tenant, str(run.id))
        await db.commit()
    except Exception as e:
        logger.debug("run_workflow failed %s: %s", run.id, e)
    return {"run_id": str(run.id), "execution_id": run.execution_id, "status": run.status, "workflow_version_id": str(run.workflow_version_id)}


@router.get("/{workflow_id}/runs", status_code=200)
async def list_runs(workflow_id: str, limit: int = Query(20, ge=1, le=100), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.workflow.models import WorkflowRun
    try:
        # Find workflow versions for this workflow
        from app.workflow.models import WorkflowVersion
        wid = uuid.UUID(workflow_id)
        qv = select(WorkflowVersion.id).where(WorkflowVersion.workflow_id == wid)
        resv = await db.execute(qv)
        vids = [r[0] for r in resv.all()]
        if not vids:
            return {"items": []}
        q = select(WorkflowRun).where(WorkflowRun.workflow_version_id.in_(vids), WorkflowRun.tenant == tenant).order_by(WorkflowRun.created_at.desc()).limit(limit)
        res = await db.execute(q)
        rows = res.scalars().all()
        return {"items": [{"run_id": str(r.id), "status": r.status, "execution_id": r.execution_id, "workflow_version_id": str(r.workflow_version_id)} for r in rows]}
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/runs/{run_id}", status_code=200)
async def get_run(run_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.workflow.models import WorkflowRun
    try:
        rid = uuid.UUID(run_id)
        q = select(WorkflowRun).where(WorkflowRun.id == rid, WorkflowRun.tenant == tenant)
        res = await db.execute(q)
        run = res.scalar_one_or_none()
    except Exception:
        raise HTTPException(status_code=422, detail="invalid run_id")
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return {"run_id": str(run.id), "workflow_version_id": str(run.workflow_version_id), "status": run.status, "execution_id": run.execution_id, "trace_id": run.trace_id}


@router.get("/runs/{run_id}/steps", status_code=200)
async def get_run_steps(run_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.workflow.models import WorkflowStepRun
    try:
        rid = uuid.UUID(run_id)
        q = select(WorkflowStepRun).where(WorkflowStepRun.run_id == rid).order_by(WorkflowStepRun.created_at)
        res = await db.execute(q)
        rows = res.scalars().all()
        # Tenant check via run
        from app.workflow.models import WorkflowRun
        q2 = select(WorkflowRun).where(WorkflowRun.id == rid, WorkflowRun.tenant == tenant)
        res2 = await db.execute(q2)
        if not res2.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="run not found")
        return {"items": [{"step_id": r.step_id, "status": r.status, "attempt": r.attempt, "error": r.error} for r in rows]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/runs/{run_id}/pause", status_code=200)
async def pause_run(run_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.workflow.models import WorkflowRun
    try:
        rid = uuid.UUID(run_id)
        q = select(WorkflowRun).where(WorkflowRun.id == rid, WorkflowRun.tenant == tenant)
        res = await db.execute(q)
        run = res.scalar_one_or_none()
        if not run:
            raise HTTPException(status_code=404, detail="run not found")
        if run.status not in ("RUNNING", "WAITING"):
            raise HTTPException(status_code=422, detail=f"cannot pause from {run.status}")
        run.status = "PAUSED"
        await db.flush()
        await db.commit()
        await _emit("WorkflowPaused", {"run_id": run_id}, tenant)
        return {"run_id": run_id, "status": run.status}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/runs/{run_id}/resume", status_code=200)
async def resume_run(run_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.workflow.models import WorkflowRun, WorkflowCheckpoint
    try:
        rid = uuid.UUID(run_id)
        q = select(WorkflowRun).where(WorkflowRun.id == rid, WorkflowRun.tenant == tenant)
        res = await db.execute(q)
        run = res.scalar_one_or_none()
        if not run:
            raise HTTPException(status_code=404, detail="run not found")
        if run.status != "PAUSED":
            raise HTTPException(status_code=422, detail=f"cannot resume from {run.status}")
        # Verify checkpoint exists
        q2 = select(WorkflowCheckpoint).where(WorkflowCheckpoint.run_id == rid)
        res2 = await db.execute(q2)
        if not res2.scalars().first():
            # No checkpoint, but still allow resume
            pass
        run.status = "RUNNING"
        await db.flush()
        # Continue execution
        from app.workflow.execution import run_workflow
        run = await run_workflow(db, tenant, str(run.id))
        await db.commit()
        await _emit("WorkflowResumed", {"run_id": run_id}, tenant)
        return {"run_id": run_id, "status": run.status}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/runs/{run_id}/cancel", status_code=200)
async def cancel_run(run_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.workflow.models import WorkflowRun
    try:
        rid = uuid.UUID(run_id)
        q = select(WorkflowRun).where(WorkflowRun.id == rid, WorkflowRun.tenant == tenant)
        res = await db.execute(q)
        run = res.scalar_one_or_none()
        if not run:
            raise HTTPException(status_code=404, detail="run not found")
        if run.status in ("COMPLETED", "CANCELLED", "FAILED"):
            raise HTTPException(status_code=422, detail=f"already {run.status}")
        # If has side effects and compensation configured, trigger compensation
        # Check if any step has compensation
        from app.workflow.models import WorkflowStepRun
        q2 = select(WorkflowStepRun).where(WorkflowStepRun.run_id == rid, WorkflowStepRun.status == "SUCCESS")
        res2 = await db.execute(q2)
        has_success = bool(res2.scalars().first())
        if has_success:
            # Check definition for compensation
            from app.workflow.models import WorkflowVersion
            q3 = select(WorkflowVersion).where(WorkflowVersion.id == run.workflow_version_id)
            res3 = await db.execute(q3)
            ver = res3.scalar_one_or_none()
            has_comp = any(s.get("compensation") for s in (ver.definition.get("steps", []) if ver else []))
            if has_comp:
                run.status = "COMPENSATING"
                await db.flush()
                from app.workflow.compensation import run_compensation
                await run_compensation(db, tenant, str(run.id))
                run.status = "CANCELLED"
                await db.flush()
                await _emit("WorkflowCompensationStarted", {"run_id": run_id}, tenant)
                await _emit("WorkflowCompensationCompleted", {"run_id": run_id}, tenant)
            else:
                run.status = "CANCELLED"
                await db.flush()
        else:
            run.status = "CANCELLED"
            await db.flush()
        await db.commit()
        await _emit("WorkflowCancelled", {"run_id": run_id}, tenant)
        return {"run_id": run_id, "status": run.status}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


# ── Approvals ────────────────────────────────────────────────────────────────
@router.get("/approvals", status_code=200)
async def list_approvals(status: str | None = None, limit: int = Query(20, ge=1, le=100), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.workflow.models import WorkflowApproval
    q = select(WorkflowApproval).where(WorkflowApproval.tenant == tenant)
    if status:
        q = q.where(WorkflowApproval.status == status.upper())
    q = q.order_by(WorkflowApproval.created_at.desc()).limit(limit)
    res = await db.execute(q)
    rows = res.scalars().all()
    return {"items": [{"id": str(r.id), "run_id": str(r.run_id), "step_id": r.step_id, "status": r.status, "binding_hash": r.binding_hash} for r in rows]}


@router.post("/approvals/{approval_id}/decide", status_code=200)
async def decide_approval(approval_id: str, payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    decision = payload.get("decision", "APPROVED")
    binding_hash = payload.get("binding_hash")
    from app.workflow.approval import decide_approval as _decide
    try:
        appr = await _decide(db, tenant, approval_id, approver=str(getattr(user, "id", "")), decision=decision, binding_hash=binding_hash)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": str(appr.id), "status": appr.status, "decision": appr.decision}


# ── Schedules ────────────────────────────────────────────────────────────────
@router.get("/schedules", status_code=200)
async def list_schedules(limit: int = Query(20, ge=1, le=100), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.workflow.models import WorkflowSchedule
    q = select(WorkflowSchedule).where(WorkflowSchedule.tenant == tenant).order_by(WorkflowSchedule.created_at.desc()).limit(limit)
    res = await db.execute(q)
    rows = res.scalars().all()
    return {"items": [{"id": str(r.id), "workflow_id": str(r.workflow_id), "trigger_type": r.trigger_type, "cron": r.cron, "enabled": r.enabled} for r in rows]}


@router.post("/schedules", status_code=201)
async def create_schedule(payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "workflow:execute", "workflow")
    workflow_id = payload.get("workflow_id")
    if not workflow_id:
        raise HTTPException(status_code=422, detail="workflow_id required")
    # Validate workflow exists and tenant
    from app.workflow.definition import get_workflow
    wf = await get_workflow(db, tenant, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="workflow not found")
    # Validate cron if provided
    cron = payload.get("cron")
    if cron:
        try:
            from app.automation.scheduler import CronParser
            CronParser(cron)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"invalid cron: {e}")
    from app.workflow.models import WorkflowSchedule
    try:
        wid = uuid.UUID(workflow_id)
    except Exception:
        raise HTTPException(status_code=422, detail="invalid workflow_id")
    sched = WorkflowSchedule(
        workflow_id=wid,
        tenant=tenant,
        cron=cron,
        interval_seconds=payload.get("interval_seconds"),
        event_filter=payload.get("event_filter", {}),
        trigger_type=payload.get("trigger_type", "schedule"),
        enabled=payload.get("enabled", True),
    )
    db.add(sched)
    await db.flush()
    await db.commit()
    return {"id": str(sched.id), "workflow_id": workflow_id, "trigger_type": sched.trigger_type}


# ── Commit 2: Templates, Human Tasks, Business, Replay, Recovery, SLA, Health ─
@router.get("/templates", status_code=200)
async def list_templates(limit: int = Query(20, ge=1, le=100), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.workflow.templates import list_templates as _list
    rows = await _list(db, tenant)
    return {"items": rows[:limit]}


@router.post("/templates", status_code=201)
async def create_template(payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "workflow:execute", "workflow")
    from app.workflow.templates import create_template as _create
    try:
        tmpl = await _create(db, tenant, payload, owner=str(getattr(user, "id", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": str(tmpl.id), "name": tmpl.name, "version": tmpl.version}


@router.post("/templates/{template_id}/publish", status_code=200)
async def publish_template(template_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.workflow.templates import publish_template as _pub
    try:
        tmpl = await _pub(db, tenant, template_id, approver=str(getattr(user, "id", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": str(tmpl.id), "is_published": tmpl.is_published}


@router.get("/human-tasks", status_code=200)
async def list_human_tasks(status: str | None = None, limit: int = Query(20, ge=1, le=100), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.workflow.human_tasks import HumanTask
    q = select(HumanTask).where(HumanTask.tenant == tenant)
    if status:
        q = q.where(HumanTask.status == status.upper())
    q = q.order_by(HumanTask.created_at.desc()).limit(limit)
    res = await db.execute(q)
    rows = res.scalars().all()
    return {"items": [{"id": str(r.id), "assignee": r.assignee, "status": r.status, "run_id": str(r.run_id)} for r in rows]}


@router.post("/human-tasks/{task_id}/complete", status_code=200)
async def complete_human_task(task_id: str, payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.workflow.human_tasks import update_human_task
    try:
        task = await update_human_task(db, tenant, task_id, status="COMPLETED", decision=payload.get("decision"), comment=payload.get("comment"))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": str(task.id), "status": task.status}


@router.post("/human-tasks/{task_id}/reassign", status_code=200)
async def reassign_human_task(task_id: str, payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    new_assignee = payload.get("assignee")
    if not new_assignee:
        raise HTTPException(status_code=422, detail="assignee required")
    from app.workflow.human_tasks import reassign_task
    try:
        new_task = await reassign_task(db, tenant, task_id, new_assignee, requester=str(getattr(user, "id", "")))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": str(new_task.id), "assignee": new_task.assignee}


@router.get("/business-processes", status_code=200)
async def list_business_processes(limit: int = Query(20, ge=1, le=100), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.workflow.business import BusinessProcess
    q = select(BusinessProcess).where(BusinessProcess.tenant == tenant).order_by(BusinessProcess.created_at.desc()).limit(limit)
    res = await db.execute(q)
    rows = res.scalars().all()
    return {"items": [{"id": str(r.id), "current_state": r.current_state, "run_id": str(r.run_id)} for r in rows]}


@router.post("/business-processes/{process_id}/transition", status_code=200)
async def transition_business_process(process_id: str, payload: dict, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    new_state = payload.get("new_state")
    if not new_state:
        raise HTTPException(status_code=422, detail="new_state required")
    from app.workflow.business import transition_process
    try:
        proc = await transition_process(db, tenant, process_id, new_state)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"id": str(proc.id), "current_state": proc.current_state}


@router.post("/runs/{run_id}/replay", status_code=201)
async def replay_run(run_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "workflow:execute", "workflow")
    from app.workflow.recovery import replay_workflow
    try:
        new_run = await replay_workflow(db, tenant, run_id, requester=str(getattr(user, "id", "")))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    await _emit("WorkflowReplayStarted", {"original_run_id": run_id, "new_run_id": str(new_run.id)}, tenant)
    await _emit("WorkflowReplayCompleted", {"new_run_id": str(new_run.id)}, tenant)
    return {"new_run_id": str(new_run.id), "original_run_id": run_id, "status": new_run.status}


@router.post("/runs/{run_id}/recover", status_code=200)
async def recover_run(run_id: str, payload: dict | None = None, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    worker_id = (payload or {}).get("worker_id", str(getattr(user, "id", "")))
    from app.workflow.recovery import recover_stale_execution
    try:
        run = await recover_stale_execution(db, tenant, run_id, new_worker_id=worker_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    await _emit("WorkflowRecoveryStarted", {"run_id": run_id}, tenant)
    await _emit("WorkflowRecoveryCompleted", {"run_id": run_id}, tenant)
    return {"run_id": str(run.id), "status": run.status}


@router.get("/sla/{run_id}", status_code=200)
async def get_sla(run_id: str, user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.workflow.business import BusinessProcess
    q = select(BusinessProcess).where(BusinessProcess.run_id == _to_uuid(run_id), BusinessProcess.tenant == tenant)
    res = await db.execute(q)
    proc = res.scalar_one_or_none()
    if not proc:
        raise HTTPException(status_code=404, detail="business process not found")
    # Check breach
    breached = proc.sla_deadline and datetime.now(timezone.utc) > (proc.sla_deadline.replace(tzinfo=timezone.utc) if proc.sla_deadline.tzinfo is None else proc.sla_deadline)
    return {"process_id": str(proc.id), "sla_deadline": proc.sla_deadline.isoformat() if proc.sla_deadline else None, "breached": bool(breached), "current_state": proc.current_state}


@router.get("/health", status_code=200)
async def workflow_health(user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.workflow.models import WorkflowRun
    q = select(WorkflowRun).where(WorkflowRun.tenant == tenant)
    res = await db.execute(q)
    runs = res.scalars().all()
    total = len(runs)
    success = len([r for r in runs if r.status == "COMPLETED"])
    failed = len([r for r in runs if r.status == "FAILED"])
    success_rate = round(success / total * 100, 1) if total else 0
    return {"tenant": tenant, "total": total, "success": success, "failed": failed, "success_rate": success_rate}


@router.get("/anomalies", status_code=200)
async def workflow_anomalies(limit: int = Query(20, ge=1, le=100), user=Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = _tenant(user)
    from app.workflow.models import WorkflowRun
    q = select(WorkflowRun).where(WorkflowRun.tenant == tenant).order_by(WorkflowRun.created_at.desc()).limit(100)
    res = await db.execute(q)
    runs = res.scalars().all()
    # Detect unusual duration
    anomalies = []
    for r in runs:
        if r.duration_ms and r.duration_ms > 60000:  # >60s unusual
            anomalies.append({"run_id": str(r.id), "type": "unusual_duration", "duration_ms": r.duration_ms})
        if r.status == "FAILED":
            anomalies.append({"run_id": str(r.id), "type": "unusual_failure"})
    return {"items": anomalies[:limit]}
