"""Environment management: create, lock, freeze, health checks."""

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.delivery.models import DeliveryEnvironment

logger = logging.getLogger(__name__)


class EnvironmentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, tenant: str, name: str, env_type: str, region: str = "default",
                     cluster: str = "", variables: Optional[dict] = None,
                     secrets_refs: Optional[list] = None, **kwargs) -> DeliveryEnvironment:
        env = DeliveryEnvironment(
            tenant=tenant, name=name, env_type=env_type, region=region,
            cluster=cluster, variables=variables or {}, secrets_refs=secrets_refs or [],
            **kwargs,
        )
        self.db.add(env)
        await self.db.flush()
        return env

    async def get(self, env_id: UUID) -> Optional[DeliveryEnvironment]:
        return await self.db.get(DeliveryEnvironment, env_id)

    async def get_by_name(self, tenant: str, name: str) -> Optional[DeliveryEnvironment]:
        res = await self.db.execute(
            select(DeliveryEnvironment).where(
                DeliveryEnvironment.tenant == tenant, DeliveryEnvironment.name == name
            ).limit(1)
        )
        return res.scalar_one_or_none()

    async def list_environments(self, tenant: Optional[str] = None,
                                 env_type: Optional[str] = None) -> list[DeliveryEnvironment]:
        stmt = select(DeliveryEnvironment)
        if tenant:
            stmt = stmt.where(DeliveryEnvironment.tenant == tenant)
        if env_type:
            stmt = stmt.where(DeliveryEnvironment.env_type == env_type)
        res = await self.db.execute(stmt.order_by(DeliveryEnvironment.name))
        return list(res.scalars().all())

    async def lock(self, env_id: UUID, locked_by: str) -> DeliveryEnvironment:
        env = await self.get(env_id)
        if not env:
            raise ValueError(f"environment {env_id} not found")
        if env.locked:
            raise ValueError(f"environment {env_id} is already locked by {env.locked_by}")
        env.locked = True
        env.locked_by = locked_by
        await self.db.flush()
        return env

    async def unlock(self, env_id: UUID) -> DeliveryEnvironment:
        env = await self.get(env_id)
        if not env:
            raise ValueError(f"environment {env_id} not found")
        env.locked = False
        env.locked_by = None
        await self.db.flush()
        return env

    async def freeze(self, env_id: UUID, reason: str = "") -> DeliveryEnvironment:
        env = await self.get(env_id)
        if not env:
            raise ValueError(f"environment {env_id} not found")
        env.frozen = True
        env.freeze_reason = reason
        await self.db.flush()
        return env

    async def unfreeze(self, env_id: UUID) -> DeliveryEnvironment:
        env = await self.get(env_id)
        if not env:
            raise ValueError(f"environment {env_id} not found")
        env.frozen = False
        env.freeze_reason = None
        await self.db.flush()
        return env

    async def can_deploy(self, env_id: UUID) -> dict:
        env = await self.get(env_id)
        if not env:
            return {"allowed": False, "reason": "environment not found"}
        if env.frozen:
            return {"allowed": False, "reason": f"frozen: {env.freeze_reason}"}
        if env.locked:
            return {"allowed": False, "reason": f"locked by {env.locked_by}"}
        return {"allowed": True, "reason": "ok"}
