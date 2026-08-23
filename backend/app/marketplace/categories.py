"""Marketplace categories — configurable, hierarchical, seedable.

Additive extension for Volume 55. Existing hard-coded CATEGORIES in
app/api/marketplace.py remain as fallback; this service provides DB-backed
configurable categories so hierarchy is not hard-coded.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.marketplace.models import MarketplaceCategory

DEFAULT_CATEGORIES = [
    ("ai-agents", "AI Agents", "Autonomous agents and assistants"),
    ("developer-tools", "Developer Tools", "Editors, CLIs, SDKs"),
    ("security", "Security", "SAST, secrets, policy, supply chain"),
    ("devops", "DevOps", "CI/CD, delivery, infra"),
    ("testing", "Testing", "Unit, integration, e2e, mocks"),
    ("data", "Data", "ETL, warehouses, pipelines"),
    ("integrations", "Integrations", "External service connectors"),
    ("productivity", "Productivity", "Docs, planning, collaboration"),
    ("observability", "Observability", "Metrics, tracing, logging"),
    ("documentation", "Documentation", "Docs generation, RAG"),
    ("workflows", "Workflows", "Automation templates"),
    ("coding", "Coding", "Code search, review, refactor"),
    ("code-review", "Code Review", "Review assistants"),
]


class CategoryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def ensure_seeded(self) -> None:
        from sqlalchemy import func
        cnt = await self.db.scalar(select(func.count()).select_from(MarketplaceCategory))
        if cnt and cnt > 0:
            return
        for slug, name, desc in DEFAULT_CATEGORIES:
            cat = MarketplaceCategory(slug=slug, name=name, description=desc, sort_order=0, is_active=True)
            self.db.add(cat)
        await self.db.flush()

    async def list(self, active_only: bool = True) -> list[MarketplaceCategory]:
        stmt = select(MarketplaceCategory).order_by(MarketplaceCategory.sort_order, MarketplaceCategory.name)
        if active_only:
            stmt = stmt.where(MarketplaceCategory.is_active == True)  # noqa: E712
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def create(self, slug: str, name: str, description: str = "", parent_id: Optional[str] = None) -> MarketplaceCategory:
        existing = await self.db.scalar(select(MarketplaceCategory).where(MarketplaceCategory.slug == slug))
        if existing:
            raise ValueError(f"category slug '{slug}' already exists")
        cat = MarketplaceCategory(slug=slug, name=name, description=description, parent_id=parent_id, is_active=True)
        self.db.add(cat)
        await self.db.flush()
        return cat

    async def get_by_slug(self, slug: str) -> Optional[MarketplaceCategory]:
        res = await self.db.execute(select(MarketplaceCategory).where(MarketplaceCategory.slug == slug))
        return res.scalar_one_or_none()
