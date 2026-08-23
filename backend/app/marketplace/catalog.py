"""Catalog discovery & search with tenant/status/policy-aware filtering."""

from typing import Optional

from sqlalchemy import String, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.marketplace.models import (
    AccessScope,
    ApprovalStatus,
    MarketplacePackage,
    MarketplacePublisher,
    PackageStatus,
    ScanStatus,
    VerificationStatus,
)
from app.marketplace.schemas import SearchFilters, SearchResultItem


PUBLIC_STATUSES = {PackageStatus.ACTIVE, PackageStatus.DEPRECATED, PackageStatus.RESTRICTED}


class CatalogService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def search(self, filters: SearchFilters, organization_id: Optional[str] = None, limit: int = 25, offset: int = 0):
        stmt = select(MarketplacePackage, MarketplacePublisher).join(
            MarketplacePublisher, MarketplacePublisher.id == MarketplacePackage.publisher_id
        )
        # Status / governance / security policy filters.
        stmt = stmt.where(MarketplacePackage.status.in_(PUBLIC_STATUSES))
        stmt = stmt.where(MarketplacePackage.governance_status == ApprovalStatus.APPROVED)
        stmt = stmt.where(MarketplacePackage.security_status != ScanStatus.FAILED)

        # Access-scope / tenant visibility.
        if organization_id and filters.include_private:
            stmt = stmt.where(
                or_(
                    MarketplacePackage.access_scope == AccessScope.PUBLIC,
                    MarketplacePackage.organization_id == organization_id,
                )
            )
        else:
            stmt = stmt.where(MarketplacePackage.access_scope == AccessScope.PUBLIC)

        if filters.query:
            q = f"%{filters.query}%"
            stmt = stmt.where(
                or_(
                    MarketplacePackage.name.ilike(q),
                    MarketplacePackage.description.ilike(q),
                    MarketplacePackage.tags.cast(String).ilike(q),
                )
            )
        if filters.package_type:
            stmt = stmt.where(MarketplacePackage.package_type == filters.package_type)
        if filters.category:
            stmt = stmt.where(MarketplacePackage.category == filters.category)
        if filters.publisher:
            stmt = stmt.where(MarketplacePublisher.slug == filters.publisher)
        if filters.min_rating is not None:
            stmt = stmt.where(MarketplacePackage.average_rating >= filters.min_rating)
        if filters.pricing_type:
            stmt = stmt.where(MarketplacePackage.pricing_type == filters.pricing_type)
        if filters.license:
            stmt = stmt.where(MarketplacePackage.license == filters.license)
        if filters.tags:
            for t in filters.tags:
                stmt = stmt.where(MarketplacePackage.tags.contains([t]))

        total = await self.db.scalar(select(func.count()).select_from(stmt.subquery()))

        order = self._order_clause(filters.sort)
        rows = (await self.db.execute(stmt.order_by(*order).limit(limit).offset(offset))).all()

        items = []
        for pkg, pub in rows:
            items.append(SearchResultItem(
                id=pkg.id,
                slug=pkg.slug,
                name=pkg.name,
                package_type=pkg.package_type,
                description=pkg.description,
                publisher_name=pub.name,
                publisher_verified=pub.verification_status != VerificationStatus.UNVERIFIED,
                latest_version=pkg.latest_version,
                average_rating=pkg.average_rating,
                rating_count=pkg.rating_count,
                install_count=pkg.install_count,
                pricing_type=pkg.pricing_type,
                license=pkg.license,
                security_status=pkg.security_status,
                governance_status=pkg.governance_status,
                tags=pkg.tags,
                category=pkg.category,
                featured=pkg.featured,
            ))
        return items, total

    async def get_detail(self, slug: str, organization_id: Optional[str] = None) -> Optional[MarketplacePackage]:
        pkg = await self._by_slug(slug)
        if not pkg:
            return None
        if pkg.access_scope != AccessScope.PUBLIC and pkg.organization_id != (organization_id if organization_id else None):
            return None
        return pkg

    async def record_view(self, package_id) -> None:
        pkg = await self.db.get(MarketplacePackage, package_id)
        if pkg:
            pkg.view_count += 1
            await self.db.flush()

    async def _by_slug(self, slug: str) -> Optional[MarketplacePackage]:
        res = await self.db.execute(
            select(MarketplacePackage)
            .options(selectinload(MarketplacePackage.publisher))
            .where(MarketplacePackage.slug == slug)
        )
        return res.scalar_one_or_none()

    @staticmethod
    def _order_clause(sort: str):
        from sqlalchemy import desc

        pkg = MarketplacePackage
        if sort == "rating":
            return [desc(pkg.average_rating), desc(pkg.rating_count)]
        if sort == "installs":
            return [desc(pkg.install_count)]
        if sort == "updated":
            return [desc(pkg.updated_at)]
        if sort == "created":
            return [desc(pkg.created_at)]
        if sort == "name":
            return [pkg.name]
        # relevance: weighted mix (featured, rating, installs, updated) — not solely popularity
        # 40% relevance signal would be semantic embedding in prod; here we blend rating+installs+recency
        return [desc(pkg.featured), desc(pkg.average_rating), desc(pkg.install_count), desc(pkg.updated_at)]
