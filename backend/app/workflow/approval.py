"""Approval handling — reuse JIT, bounded."""

import hashlib
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.workflow.models import WorkflowApproval, WorkflowRun


def _binding_hash(workflow_version_id: str, run_id: str, step_id: str, resource: str, action: str) -> str:
    raw = f"{workflow_version_id}|{run_id}|{step_id}|{resource}|{action}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def create_approval(db: AsyncSession, tenant: str, run_id: str, step_id: str, workflow_version_id: str, requester: str, scope: dict | None = None, reason: str | None = None, expiry_hours: int = 24) -> WorkflowApproval:
    run = None
    try:
        rid = uuid.UUID(run_id)
        q = select(WorkflowRun).where(WorkflowRun.id == rid, WorkflowRun.tenant == tenant)
        res = await db.execute(q)
        run = res.scalar_one_or_none()
    except Exception:
        pass
    wvid = workflow_version_id
    binding = _binding_hash(wvid, run_id, step_id, scope.get("resource", "") if scope else "", scope.get("action", "") if scope else "")
    appr = WorkflowApproval(
        run_id=uuid.UUID(run_id),
        step_id=step_id,
        workflow_version_id=uuid.UUID(wvid),
        tenant=tenant,
        requester=requester,
        scope=scope or {},
        reason=reason,
        expiry=datetime.now(timezone.utc) + timedelta(hours=expiry_hours),
        status="PENDING",
        binding_hash=binding,
    )
    db.add(appr)
    await db.flush()
    try:
        from app.core.events import Event, EventType, event_bus
        await event_bus.publish_nowait(Event(EventType.WorkflowApprovalRequested, {"run_id": run_id, "step_id": step_id}, source="workflow", organization_id=tenant))
    except Exception:
        pass
    return appr


async def decide_approval(db: AsyncSession, tenant: str, approval_id: str, approver: str, decision: str, binding_hash: str | None = None) -> WorkflowApproval:
    try:
        aid = uuid.UUID(approval_id)
        q = select(WorkflowApproval).where(WorkflowApproval.id == aid, WorkflowApproval.tenant == tenant)
        res = await db.execute(q)
        appr = res.scalar_one_or_none()
    except Exception:
        raise ValueError("approval not found")
    if not appr:
        raise ValueError("approval not found")
    if appr.status != "PENDING":
        raise ValueError(f"already {appr.status}")
    if appr.expiry and datetime.now(timezone.utc) > appr.expiry.replace(tzinfo=timezone.utc) if appr.expiry.tzinfo is None else appr.expiry:
        appr.status = "EXPIRED"
        await db.flush()
        raise ValueError("approval expired")
    if binding_hash and appr.binding_hash != binding_hash:
        raise ValueError("binding mismatch")
    # Check approver authorized via Volume 64 Zero Trust JIT
    try:
        from app.iam.policy_authorizer import policy_authorizer
        dec = policy_authorizer.authorize(approver, tenant, "workflow:approve", resource_type="workflow", context={"step": appr.step_id})
        if not dec.get("allowed", True):
            raise PermissionError("approver not authorized")
    except PermissionError:
        raise
    except Exception:
        pass
    decision = decision.upper()
    if decision not in {"APPROVED", "DENIED", "CANCELLED"}:
        raise ValueError("invalid decision")
    appr.status = decision
    appr.approver = approver
    appr.decision = decision
    await db.flush()
    # If approved, resume workflow if waiting
    if decision == "APPROVED":
        try:
            rid = appr.run_id
            q2 = select(WorkflowRun).where(WorkflowRun.id == rid)
            res2 = await db.execute(q2)
            run = res2.scalar_one_or_none()
            if run and run.status == "WAITING":
                run.status = "RUNNING"
                await db.flush()
                # Continue execution
                from app.workflow.execution import run_workflow
                await run_workflow(db, tenant, str(run.id))
        except Exception:
            pass
    return appr


async def get_approval(db: AsyncSession, tenant: str, approval_id: str) -> WorkflowApproval | None:
    try:
        aid = uuid.UUID(approval_id)
        q = select(WorkflowApproval).where(WorkflowApproval.id == aid, WorkflowApproval.tenant == tenant)
        res = await db.execute(q)
        return res.scalar_one_or_none()
    except Exception:
        return None
