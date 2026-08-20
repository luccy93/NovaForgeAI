"""Approval workflow for high-risk autonomous operations."""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.models import AutomationApproval, AutomationTask, ApprovalDecision, RiskLevel, TaskStatus

logger = logging.getLogger(__name__)


class ApprovalService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def request_approval(
        self,
        task_id: UUID,
        requested_by: str,
        planned_action: str,
        affected_resources: Optional[list] = None,
        risk_level: str = RiskLevel.LOW,
        diff_summary: Optional[str] = None,
        step_id: Optional[UUID] = None,
    ) -> AutomationApproval:
        approval = AutomationApproval(
            task_id=task_id,
            step_id=step_id,
            requested_by=requested_by,
            decision=ApprovalDecision.PENDING,
            planned_action=planned_action,
            affected_resources=affected_resources or [],
            risk_level=risk_level,
            diff_summary=diff_summary,
        )
        self.db.add(approval)
        await self.db.flush()
        return approval

    async def get(self, approval_id: UUID) -> Optional[AutomationApproval]:
        return await self.db.get(AutomationApproval, approval_id)

    async def list_for_task(self, task_id: UUID) -> list[AutomationApproval]:
        res = await self.db.execute(
            select(AutomationApproval)
            .where(AutomationApproval.task_id == task_id)
            .order_by(AutomationApproval.created_at.desc())
        )
        return list(res.scalars().all())

    async def get_pending(self, task_id: UUID) -> Optional[AutomationApproval]:
        res = await self.db.execute(
            select(AutomationApproval)
            .where(AutomationApproval.task_id == task_id)
            .where(AutomationApproval.decision == ApprovalDecision.PENDING)
            .order_by(AutomationApproval.created_at)
            .limit(1)
        )
        return res.scalar_one_or_none()

    async def decide(self, approval_id: UUID, decision: str, decided_by: str, reason: str = "") -> AutomationApproval:
        if decision not in (ApprovalDecision.APPROVED, ApprovalDecision.REJECTED):
            raise ValueError(f"invalid decision: {decision}")
        approval = await self.get(approval_id)
        if not approval:
            raise ValueError(f"approval {approval_id} not found")
        if approval.decision != ApprovalDecision.PENDING:
            raise ValueError(f"approval already decided: {approval.decision}")
        approval.decision = decision
        approval.decided_by = decided_by
        approval.reason = reason
        approval.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return approval

    async def approve(self, approval_id: UUID, decided_by: str, reason: str = "") -> AutomationApproval:
        return await self.decide(approval_id, ApprovalDecision.APPROVED, decided_by, reason)

    async def reject(self, approval_id: UUID, decided_by: str, reason: str = "") -> AutomationApproval:
        return await self.decide(approval_id, ApprovalDecision.REJECTED, decided_by, reason)

    def requires_approval(self, task: AutomationTask, planned_action: str = "") -> bool:
        if task.risk_level in (RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL):
            return True
        if task.autonomy_level >= 3:
            return True
        action_lower = planned_action.lower()
        high_risk_actions = ["deploy", "merge", "drop", "delete", "migrate", "revoke", "suspend"]
        return any(a in action_lower for a in high_risk_actions)

    async def pending_count(self) -> int:
        res = await self.db.execute(
            select(AutomationApproval)
            .where(AutomationApproval.decision == ApprovalDecision.PENDING)
        )
        return len(list(res.scalars().all()))
