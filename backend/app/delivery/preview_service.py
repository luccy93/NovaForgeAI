"""Preview environment lifecycle: create, expose URL, destroy."""

import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.delivery.models import DeliveryPreviewEnvironment

logger = logging.getLogger(__name__)


class PreviewService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, tenant: str, name: str, repository: str, branch: str,
                     pr_number: Optional[int] = None, commit_sha: str = "",
                     ttl_seconds: int = 3600, resource_limits: Optional[dict] = None) -> DeliveryPreviewEnvironment:
        suffix = secrets.token_hex(6)
        url = f"https://{name}-{suffix}.preview.novaforge.dev"
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds) if ttl_seconds > 0 else None
        preview = DeliveryPreviewEnvironment(
            tenant=tenant, name=name, repository=repository, branch=branch,
            pr_number=pr_number, commit_sha=commit_sha, url=url, status="creating",
            expires_at=expires_at, ttl_seconds=ttl_seconds,
            resource_limits=resource_limits or {},
        )
        self.db.add(preview)
        await self.db.flush()
        return preview

    async def get(self, preview_id: UUID) -> Optional[DeliveryPreviewEnvironment]:
        return await self.db.get(DeliveryPreviewEnvironment, preview_id)

    async def list_previews(self, tenant: Optional[str] = None, repository: Optional[str] = None,
                             pr_number: Optional[int] = None) -> list[DeliveryPreviewEnvironment]:
        stmt = select(DeliveryPreviewEnvironment)
        if tenant:
            stmt = stmt.where(DeliveryPreviewEnvironment.tenant == tenant)
        if repository:
            stmt = stmt.where(DeliveryPreviewEnvironment.repository == repository)
        if pr_number is not None:
            stmt = stmt.where(DeliveryPreviewEnvironment.pr_number == pr_number)
        res = await self.db.execute(stmt.order_by(DeliveryPreviewEnvironment.created_at.desc()))
        return list(res.scalars().all())

    async def activate(self, preview_id: UUID) -> DeliveryPreviewEnvironment:
        preview = await self.get(preview_id)
        if not preview:
            raise ValueError(f"preview {preview_id} not found")
        preview.status = "active"
        await self.db.flush()
        return preview

    async def destroy(self, preview_id: UUID) -> DeliveryPreviewEnvironment:
        preview = await self.get(preview_id)
        if not preview:
            raise ValueError(f"preview {preview_id} not found")
        preview.status = "destroyed"
        await self.db.flush()
        return preview

    async def get_by_pr(self, repository: str, pr_number: int) -> Optional[DeliveryPreviewEnvironment]:
        res = await self.db.execute(
            select(DeliveryPreviewEnvironment).where(
                DeliveryPreviewEnvironment.repository == repository,
                DeliveryPreviewEnvironment.pr_number == pr_number,
                DeliveryPreviewEnvironment.status == "active",
            ).limit(1)
        )
        return res.scalar_one_or_none()

    async def schedule_cleanup(self, preview_id: UUID) -> DeliveryPreviewEnvironment:
        preview = await self.get(preview_id)
        if not preview:
            raise ValueError(f"preview {preview_id} not found")
        preview.cleanup_scheduled = True
        await self.db.flush()
        return preview
