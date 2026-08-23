"""Emergency package blocking — immediate, auditable, expirations."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.marketplace.models import MarketplaceEmergencyBlock


class EmergencyBlockService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_block(
        self,
        target_type: str,
        target_id: str,
        reason: str,
        scope: str = "global",
        expires_at: Optional[datetime] = None,
        created_by: Optional[str] = None,
    ) -> MarketplaceEmergencyBlock:
        if target_type not in ("package", "version", "publisher"):
            raise ValueError("target_type must be package|version|publisher")
        block = MarketplaceEmergencyBlock(
            target_type=target_type,
            target_id=target_id,
            reason=reason,
            scope=scope,
            expires_at=expires_at,
            created_by=created_by,
            audit_trail=[{"action": "created", "reason": reason, "at": datetime.now(timezone.utc).isoformat(), "by": created_by}],
        )
        self.db.add(block)
        await self.db.flush()
        return block

    async def list_blocks(self, active_only: bool = True) -> list[MarketplaceEmergencyBlock]:
        stmt = select(MarketplaceEmergencyBlock).order_by(MarketplaceEmergencyBlock.created_at.desc())
        res = await self.db.execute(stmt)
        rows = list(res.scalars().all())
        if active_only:
            now = datetime.now(timezone.utc)
            rows = [r for r in rows if r.expires_at is None or r.expires_at > now]
        return rows

    async def is_blocked(self, target_type: str, target_id: str) -> tuple[bool, Optional[MarketplaceEmergencyBlock]]:
        blocks = await self.list_blocks(active_only=True)
        for b in blocks:
            if b.target_type == target_type and b.target_id == target_id:
                return True, b
            # publisher block also blocks its packages/versions via caller check
        return False, None

    async def is_publisher_blocked(self, publisher_id: str) -> bool:
        blocked, _ = await self.is_blocked("publisher", str(publisher_id))
        return blocked

    async def remove_block(self, block_id: str, removed_by: Optional[str] = None) -> Optional[MarketplaceEmergencyBlock]:
        block = await self.db.get(MarketplaceEmergencyBlock, block_id)
        if not block:
            return None
        block.audit_trail = (block.audit_trail or []) + [{"action": "removed", "at": datetime.now(timezone.utc).isoformat(), "by": removed_by}]
        await self.db.delete(block)
        await self.db.flush()
        return block
