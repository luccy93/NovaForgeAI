"""Approval gate: request, approve, reject."""

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.delivery.models import DeliveryApproval

logger = logging.getLogger(__name__)


class ApprovalService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def request(self, requested_by: str, gate_type: str = "manual",
                      pipeline_run_id: Optional[UUID] = None,
                      deployment_id: Optional[UUID] = None,
                      context: Optional[dict] = None) -> DeliveryApproval:
        approval = DeliveryApproval(
            requested_by=requested_by, gate_type=gate_type,
            pipeline_run_id=pipeline_run_id, deployment_id=deployment_id,
            decision="pending", context=context or {},
        )
        self.db.add(approval)
        await self.db.flush()
        return approval

    async def get(self, approval_id: UUID) -> Optional[DeliveryApproval]:
        return await self.db.get(DeliveryApproval, approval_id)

    async def list_approvals(self, pipeline_run_id: Optional[UUID] = None,
                              deployment_id: Optional[UUID] = None,
                              decision: Optional[str] = None) -> list[DeliveryApproval]:
        stmt = select(DeliveryApproval)
        if pipeline_run_id:
            stmt = stmt.where(DeliveryApproval.pipeline_run_id == pipeline_run_id)
        if deployment_id:
            stmt = stmt.where(DeliveryApproval.deployment_id == deployment_id)
        if decision:
            stmt = stmt.where(DeliveryApproval.decision == decision)
        res = await self.db.execute(stmt.order_by(DeliveryApproval.created_at.desc()))
        return list(res.scalars().all())

    async def approve(self, approval_id: UUID, decided_by: str, reason: str = "") -> DeliveryApproval:
        approval = await self.get(approval_id)
        if not approval:
            raise ValueError(f"approval {approval_id} not found")
        approval.decision = "approved"
        approval.decided_by = decided_by
        approval.reason = reason
        await self.db.flush()
        return approval

    async def reject(self, approval_id: UUID, decided_by: str, reason: str = "") -> DeliveryApproval:
        approval = await self.get(approval_id)
        if not approval:
            raise ValueError(f"approval {approval_id} not found")
        approval.decision = "rejected"
        approval.decided_by = decided_by
        approval.reason = reason
        await self.db.flush()
        return approval
