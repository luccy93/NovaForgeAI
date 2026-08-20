"""Package reviews, ratings and moderation."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.marketplace.models import (
    MarketplaceInstallation,
    MarketplacePackage,
    MarketplaceReview,
    ReviewStatus,
)
from app.marketplace.schemas import ReviewCreate


class ReviewService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _has_active_install(self, package_id, user_id, organization_id) -> bool:
        stmt = select(MarketplaceInstallation).where(
            MarketplaceInstallation.package_id == package_id,
            MarketplaceInstallation.status.in_(["active", "installed", "configuring"]),
        )
        if organization_id:
            stmt = stmt.where(MarketplaceInstallation.organization_id == organization_id)
        return (await self.db.execute(stmt)).first() is not None

    async def create(self, package_slug: str, user_id, organization_id, data: ReviewCreate) -> MarketplaceReview:
        pkg = await self._pkg(package_slug)
        if not pkg:
            raise ValueError("package not found")

        is_vs = bool(data.version)
        # Prevent duplicate / fraudulent reviews: one general review per user
        # per package; one version-specific review per user per version.
        existing = await self.db.execute(
            select(MarketplaceReview).where(
                MarketplaceReview.package_id == pkg.id,
                MarketplaceReview.user_id == user_id,
                MarketplaceReview.is_version_specific == is_vs,
                MarketplaceReview.release_id == (None if not is_vs else await self._release_id(pkg.id, data.version)),
            )
        )
        prev = existing.scalar_one_or_none()
        verified = await self._has_active_install(pkg.id, user_id, organization_id)

        if prev:
            prev.rating = data.rating
            prev.title = data.title
            prev.body = data.body
            prev.verified_install = verified
            prev.updated_at = datetime.now(timezone.utc)
            await self.db.flush()
            return prev

        rel_id = await self._release_id(pkg.id, data.version) if is_vs else None
        review = MarketplaceReview(
            package_id=pkg.id,
            release_id=rel_id,
            organization_id=organization_id,
            user_id=user_id,
            rating=data.rating,
            title=data.title,
            body=data.body,
            is_version_specific=is_vs,
            verified_install=verified,
            status=ReviewStatus.PUBLISHED,
        )
        self.db.add(review)
        await self.db.flush()
        await self._recompute(pkg)
        return review

    async def moderate(self, review_id, status: ReviewStatus, moderator_user_id=None, reason: Optional[str] = None) -> Optional[MarketplaceReview]:
        rev = await self.db.get(MarketplaceReview, review_id)
        if not rev:
            return None
        rev.status = status
        rev.moderated_by = moderator_user_id
        rev.moderation_reason = reason
        await self.db.flush()
        await self._recompute(await self._pkg_by_id(rev.package_id))
        return rev

    async def mark_helpful(self, review_id) -> None:
        rev = await self.db.get(MarketplaceReview, review_id)
        if rev:
            rev.helpful_count += 1
            await self.db.flush()

    async def list(self, package_id, limit=50, offset=0, status=None):
        stmt = select(MarketplaceReview).where(MarketplaceReview.package_id == package_id)
        if status:
            stmt = stmt.where(MarketplaceReview.status == status)
        else:
            stmt = stmt.where(MarketplaceReview.status == ReviewStatus.PUBLISHED)
        total = await self.db.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = (await self.db.execute(stmt.order_by(MarketplaceReview.created_at.desc()).limit(limit).offset(offset))).scalars().all()
        return rows, total

    async def _recompute(self, pkg: Optional[MarketplacePackage]) -> None:
        if not pkg:
            return
        res = await self.db.execute(
            select(func.avg(MarketplaceReview.rating), func.count(MarketplaceReview.id)).where(
                MarketplaceReview.package_id == pkg.id, MarketplaceReview.status == ReviewStatus.PUBLISHED
            )
        )
        avg, cnt = res.one()
        pkg.average_rating = round(float(avg or 0.0), 2)
        pkg.rating_count = int(cnt or 0)
        await self.db.flush()

    async def _pkg(self, slug: str) -> Optional[MarketplacePackage]:
        res = await self.db.execute(
            select(MarketplacePackage)
            .options(selectinload(MarketplacePackage.publisher))
            .where(MarketplacePackage.slug == slug)
        )
        return res.scalar_one_or_none()

    async def _pkg_by_id(self, package_id) -> Optional[MarketplacePackage]:
        return await self.db.get(MarketplacePackage, package_id)

    async def _release_id(self, package_id, version: Optional[str]):
        if not version:
            return None
        from app.marketplace.models import MarketplaceRelease

        res = await self.db.execute(
            select(MarketplaceRelease.id).where(MarketplaceRelease.package_id == package_id, MarketplaceRelease.version == version)
        )
        return res.scalar_one_or_none()
