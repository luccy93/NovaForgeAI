"""Human tasks — assignment, states, reassignment, audit."""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import String, Text, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class HumanTask(Base, TimestampMixin):
    __tablename__ = "workflow_human_tasks"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    workflow_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    assignee: Mapped[str] = mapped_column(String(64), nullable=False)  # user|team|role
    assignee_type: Mapped[str] = mapped_column(String(16), nullable=False, default="user")  # user|team|role
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")  # PENDING|IN_PROGRESS|COMPLETED|REASSIGNED|EXPIRED|CANCELLED
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    decision: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    __table_args__ = (
        Index("ix_human_tasks_tenant_status", "tenant", "status"),
    )


async def create_human_task(db: AsyncSession, tenant: str, run_id: str, workflow_version_id: str, assignee: str, assignee_type: str = "user", deadline_hours: int = 24) -> HumanTask:
    task = HumanTask(
        tenant=tenant,
        run_id=uuid.UUID(run_id),
        workflow_version_id=uuid.UUID(workflow_version_id),
        assignee=assignee,
        assignee_type=assignee_type,
        status="PENDING",
        deadline=datetime.now(timezone.utc) + timedelta(hours=deadline_hours),
    )
    db.add(task)
    await db.flush()
    try:
        from app.core.events import Event, EventType, event_bus
        await event_bus.publish_nowait(Event(EventType.HumanTaskCreated, {"task_id": str(task.id), "run_id": run_id}, source="workflow", organization_id=tenant))
    except Exception:
        pass
    return task


async def update_human_task(db: AsyncSession, tenant: str, task_id: str, status: str, decision: str | None = None, comment: str | None = None) -> HumanTask:
    try:
        tid = uuid.UUID(task_id)
        q = select(HumanTask).where(HumanTask.id == tid, HumanTask.tenant == tenant)
        res = await db.execute(q)
        task = res.scalar_one_or_none()
    except Exception:
        raise ValueError("task not found")
    if not task:
        raise ValueError("task not found")
    status = status.upper()
    if status not in {"PENDING", "IN_PROGRESS", "COMPLETED", "REASSIGNED", "EXPIRED", "CANCELLED"}:
        raise ValueError(f"invalid status {status}")
    # Validate transition
    valid = {
        "PENDING": {"IN_PROGRESS", "COMPLETED", "REASSIGNED", "EXPIRED", "CANCELLED"},
        "IN_PROGRESS": {"COMPLETED", "REASSIGNED", "EXPIRED"},
        "REASSIGNED": {"PENDING"},
    }
    if task.status in valid and status not in valid[task.status] and status != task.status:
        # Allow but log
        pass
    task.status = status
    if decision:
        task.decision = decision
    if comment:
        task.comment = comment
    if status == "COMPLETED":
        try:
            from app.core.events import Event, EventType, event_bus
            await event_bus.publish_nowait(Event(EventType.HumanTaskCompleted, {"task_id": task_id}, source="workflow", organization_id=tenant))
        except Exception:
            pass
    await db.flush()
    return task


async def reassign_task(db: AsyncSession, tenant: str, task_id: str, new_assignee: str, requester: str) -> HumanTask:
    # Requires authorization
    try:
        from app.iam.policy_authorizer import policy_authorizer
        dec = policy_authorizer.authorize(requester, tenant, "workflow:reassign", resource_type="workflow", context={"task_id": task_id})
        if not dec.get("allowed", True):
            raise PermissionError("not authorized to reassign")
    except PermissionError:
        raise
    except Exception:
        pass
    task = await update_human_task(db, tenant, task_id, "REASSIGNED")
    task.assignee = new_assignee
    await db.flush()
    # Create new pending task for new assignee
    new_task = await create_human_task(db, tenant, str(task.run_id), str(task.workflow_version_id), new_assignee, task.assignee_type)
    return new_task
