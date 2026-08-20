"""Release lifecycle: create, promote, status."""

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.delivery.models import DeliveryRelease

logger = logging.getLogger(__name__)


class ReleaseService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, tenant: str, project: str, repository: str, version: str,
                     release_channel: str = "stable", commit_sha: str = "",
                     artifact_ids: Optional[list] = None, release_notes: str = "",
                     created_by: str = "") -> DeliveryRelease:
        rel = DeliveryRelease(
            tenant=tenant, project=project, repository=repository, version=version,
            release_channel=release_channel, commit_sha=commit_sha,
            artifact_ids=artifact_ids or [], release_notes=release_notes,
            created_by=created_by, status="draft",
        )
        self.db.add(rel)
        await self.db.flush()
        return rel

    async def get(self, release_id: UUID) -> Optional[DeliveryRelease]:
        return await self.db.get(DeliveryRelease, release_id)

    async def get_by_version(self, tenant: str, version: str) -> Optional[DeliveryRelease]:
        res = await self.db.execute(
            select(DeliveryRelease).where(
                DeliveryRelease.tenant == tenant, DeliveryRelease.version == version
            ).limit(1)
        )
        return res.scalar_one_or_none()

    async def list_releases(self, tenant: Optional[str] = None, project: Optional[str] = None,
                             release_channel: Optional[str] = None,
                             limit: int = 20, offset: int = 0) -> tuple[list, int]:
        stmt = select(DeliveryRelease)
        count_stmt = select(func.count()).select_from(DeliveryRelease)
        if tenant:
            stmt = stmt.where(DeliveryRelease.tenant == tenant)
            count_stmt = count_stmt.where(DeliveryRelease.tenant == tenant)
        if project:
            stmt = stmt.where(DeliveryRelease.project == project)
            count_stmt = count_stmt.where(DeliveryRelease.project == project)
        if release_channel:
            stmt = stmt.where(DeliveryRelease.release_channel == release_channel)
            count_stmt = count_stmt.where(DeliveryRelease.release_channel == release_channel)
        total = await self.db.scalar(count_stmt)
        rows = (await self.db.execute(stmt.order_by(DeliveryRelease.created_at.desc()).limit(limit).offset(offset))).scalars().all()
        return list(rows), total or 0

    async def promote(self, release_id: UUID, environment: str) -> DeliveryRelease:
        rel = await self.get(release_id)
        if not rel:
            raise ValueError(f"release {release_id} not found")
        envs = rel.deployed_environments or []
        if environment not in envs:
            envs.append(environment)
            rel.deployed_environments = envs
        rel.status = "promoted"
        await self.db.flush()
        return rel

    async def finalize(self, release_id: UUID) -> DeliveryRelease:
        rel = await self.get(release_id)
        if not rel:
            raise ValueError(f"release {release_id} not found")
        rel.status = "released"
        await self.db.flush()
        return rel

    async def deprecate(self, release_id: UUID) -> DeliveryRelease:
        rel = await self.get(release_id)
        if not rel:
            raise ValueError(f"release {release_id} not found")
        rel.status = "deprecated"
        await self.db.flush()
        return rel
