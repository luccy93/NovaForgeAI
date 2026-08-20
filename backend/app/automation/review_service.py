"""Independent code review for generated changes."""

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.models import AutomationReview, AutomationPatch, ReviewStatus

logger = logging.getLogger(__name__)


class ReviewService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_review(
        self,
        task_id: UUID,
        reviewer: str,
        patch_id: Optional[UUID] = None,
    ) -> AutomationReview:
        review = AutomationReview(
            task_id=task_id,
            patch_id=patch_id,
            reviewer=reviewer,
            status=ReviewStatus.PENDING,
        )
        self.db.add(review)
        await self.db.flush()
        return review

    async def get(self, review_id: UUID) -> Optional[AutomationReview]:
        return await self.db.get(AutomationReview, review_id)

    async def list_for_task(self, task_id: UUID) -> list[AutomationReview]:
        res = await self.db.execute(
            select(AutomationReview)
            .where(AutomationReview.task_id == task_id)
            .order_by(AutomationReview.created_at.desc())
        )
        return list(res.scalars().all())

    async def submit_findings(
        self,
        review_id: UUID,
        findings: list[dict],
        summary: str = "",
        correctness_score: float = 0.0,
        security_score: float = 0.0,
        maintainability_score: float = 0.0,
        overall_score: float = 0.0,
    ) -> AutomationReview:
        review = await self.get(review_id)
        if not review:
            raise ValueError(f"review {review_id} not found")
        review.findings = findings
        review.summary = summary
        review.correctness_score = correctness_score
        review.security_score = security_score
        review.maintainability_score = maintainability_score
        review.overall_score = overall_score
        review.updated_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        await self.db.flush()
        return review

    async def approve(self, review_id: UUID) -> AutomationReview:
        review = await self.get(review_id)
        if not review:
            raise ValueError(f"review {review_id} not found")
        review.status = ReviewStatus.APPROVED
        await self.db.flush()
        return review

    async def request_changes(self, review_id: UUID) -> AutomationReview:
        review = await self.get(review_id)
        if not review:
            raise ValueError(f"review {review_id} not found")
        review.status = ReviewStatus.CHANGES_REQUESTED
        await self.db.flush()
        return review

    async def reject(self, review_id: UUID) -> AutomationReview:
        review = await self.get(review_id)
        if not review:
            raise ValueError(f"review {review_id} not found")
        review.status = ReviewStatus.REJECTED
        await self.db.flush()
        return review

    async def get_latest(self, task_id: UUID) -> Optional[AutomationReview]:
        res = await self.db.execute(
            select(AutomationReview)
            .where(AutomationReview.task_id == task_id)
            .order_by(AutomationReview.created_at.desc())
            .limit(1)
        )
        return res.scalar_one_or_none()
