"""Business processes — formal states, SLA, escalation."""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import String, Text, DateTime, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class BusinessProcess(Base, TimestampMixin):
    __tablename__ = "workflow_business_processes"

    tenant: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    workflow_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    current_state: Mapped[str] = mapped_column(String(32), nullable=False, default="REQUESTED")
    previous_state: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    sla_deadline: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    __table_args__ = (
        Index("ix_business_processes_tenant_status", "tenant", "current_state"),
    )


# Valid transitions for business workflows
VALID_TRANSITIONS = {
    "REQUESTED": {"APPROVED", "DENIED", "CANCELLED"},
    "APPROVED": {"IN_PROGRESS", "CANCELLED"},
    "IN_PROGRESS": {"VERIFIED", "FAILED", "CANCELLED"},
    "VERIFIED": {"COMPLETED", "FAILED"},
    "DENIED": set(),
    "FAILED": {"RETRY", "CANCELLED"},
    "COMPLETED": set(),
    "CANCELLED": set(),
}


async def create_process(db: AsyncSession, tenant: str, workflow_version_id: str, run_id: str, sla_hours: int = 24) -> BusinessProcess:
    proc = BusinessProcess(
        tenant=tenant,
        workflow_version_id=uuid.UUID(workflow_version_id),
        run_id=uuid.UUID(run_id),
        current_state="REQUESTED",
        sla_deadline=datetime.now(timezone.utc) + timedelta(hours=sla_hours),
    )
    db.add(proc)
    await db.flush()
    return proc


async def transition_process(db: AsyncSession, tenant: str, process_id: str, new_state: str) -> BusinessProcess:
    try:
        pid = uuid.UUID(process_id)
        q = select(BusinessProcess).where(BusinessProcess.id == pid, BusinessProcess.tenant == tenant)
        res = await db.execute(q)
        proc = res.scalar_one_or_none()
    except Exception:
        raise ValueError("process not found")
    if not proc:
        raise ValueError("process not found")
    new_state = new_state.upper()
    allowed = VALID_TRANSITIONS.get(proc.current_state, set())
    if new_state not in allowed:
        raise ValueError(f"invalid transition {proc.current_state} → {new_state}")
    proc.previous_state = proc.current_state
    proc.current_state = new_state
    await db.flush()
    # SLA breach check
    if proc.sla_deadline and datetime.now(timezone.utc) > proc.sla_deadline.replace(tzinfo=timezone.utc) if proc.sla_deadline.tzinfo is None else proc.sla_deadline:
        try:
            from app.core.events import Event, EventType, event_bus
            await event_bus.publish_nowait(Event(EventType.WorkflowSLABreached, {"process_id": process_id, "state": new_state}, source="workflow", organization_id=tenant))
        except Exception:
            pass
    return proc


async def check_sla_breach(db: AsyncSession, tenant: str) -> list[BusinessProcess]:
    now = datetime.now(timezone.utc)
    q = select(BusinessProcess).where(BusinessProcess.tenant == tenant, BusinessProcess.sla_deadline != None, BusinessProcess.sla_deadline < now, BusinessProcess.current_state.notin_(["COMPLETED", "CANCELLED", "DENIED"]))  # noqa: E712
    res = await db.execute(q)
    breached = res.scalars().all()
    for proc in breached:
        try:
            from app.core.events import Event, EventType, event_bus
            await event_bus.publish_nowait(Event(EventType.WorkflowSLAWarning, {"process_id": str(proc.id)}, source="workflow", organization_id=tenant))
        except Exception:
            pass
    return breached
