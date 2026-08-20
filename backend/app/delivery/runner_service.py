"""Runner lifecycle: register, heartbeat, schedule, quarantine."""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.delivery.models import DeliveryRunner

logger = logging.getLogger(__name__)


class RunnerService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(self, name: str, region: str = "default", runner_type: str = "ephemeral",
                       capabilities: Optional[list] = None, labels: Optional[list] = None,
                       tenant: str = "", cpu: int = 4, memory_mb: int = 8192,
                       disk_gb: int = 50, capacity: int = 1) -> DeliveryRunner:
        runner = DeliveryRunner(
            name=name, region=region, runner_type=runner_type,
            capabilities=capabilities or [], labels=labels or [],
            tenant=tenant, cpu=cpu, memory_mb=memory_mb,
            disk_gb=disk_gb, capacity=capacity, status="available",
        )
        self.db.add(runner)
        await self.db.flush()
        return runner

    async def get(self, runner_id: UUID) -> Optional[DeliveryRunner]:
        return await self.db.get(DeliveryRunner, runner_id)

    async def list_runners(self, tenant: Optional[str] = None, region: Optional[str] = None,
                            status: Optional[str] = None, limit: int = 50, offset: int = 0) -> tuple[list, int]:
        stmt = select(DeliveryRunner)
        count_stmt = select(__import__("sqlalchemy").func.count()).select_from(DeliveryRunner)
        if tenant:
            stmt = stmt.where(DeliveryRunner.tenant == tenant)
            count_stmt = count_stmt.where(DeliveryRunner.tenant == tenant)
        if region:
            stmt = stmt.where(DeliveryRunner.region == region)
            count_stmt = count_stmt.where(DeliveryRunner.region == region)
        if status:
            stmt = stmt.where(DeliveryRunner.status == status)
            count_stmt = count_stmt.where(DeliveryRunner.status == status)
        total = await self.db.scalar(count_stmt)
        rows = (await self.db.execute(stmt.order_by(DeliveryRunner.created_at.desc()).limit(limit).offset(offset))).scalars().all()
        return list(rows), total or 0

    async def heartbeat(self, runner_id: UUID) -> DeliveryRunner:
        runner = await self.get(runner_id)
        if not runner:
            raise ValueError(f"runner {runner_id} not found")
        runner.last_heartbeat = datetime.now(timezone.utc)
        await self.db.flush()
        return runner

    async def acquire(self, runner_id: UUID) -> DeliveryRunner:
        runner = await self.get(runner_id)
        if not runner:
            raise ValueError(f"runner {runner_id} not found")
        if runner.quarantined:
            raise ValueError(f"runner {runner_id} is quarantined")
        if runner.current_jobs >= runner.capacity:
            raise ValueError(f"runner {runner_id} is at capacity")
        runner.current_jobs += 1
        if runner.current_jobs >= runner.capacity:
            runner.status = "busy"
        await self.db.flush()
        return runner

    async def release(self, runner_id: UUID) -> DeliveryRunner:
        runner = await self.get(runner_id)
        if not runner:
            raise ValueError(f"runner {runner_id} not found")
        runner.current_jobs = max(0, runner.current_jobs - 1)
        if runner.current_jobs < runner.capacity:
            runner.status = "available"
        await self.db.flush()
        return runner

    async def quarantine(self, runner_id: UUID, reason: str = "") -> DeliveryRunner:
        runner = await self.get(runner_id)
        if not runner:
            raise ValueError(f"runner {runner_id} not found")
        runner.quarantined = True
        runner.quarantine_reason = reason
        runner.status = "quarantined"
        await self.db.flush()
        return runner

    async def release_from_quarantine(self, runner_id: UUID) -> DeliveryRunner:
        runner = await self.get(runner_id)
        if not runner:
            raise ValueError(f"runner {runner_id} not found")
        runner.quarantined = False
        runner.quarantine_reason = None
        runner.status = "available"
        await self.db.flush()
        return runner

    async def drain(self, runner_id: UUID) -> DeliveryRunner:
        runner = await self.get(runner_id)
        if not runner:
            raise ValueError(f"runner {runner_id} not found")
        runner.status = "draining"
        await self.db.flush()
        return runner

    async def find_available(self, tenant: str, region: Optional[str] = None,
                              required_labels: Optional[list] = None) -> Optional[DeliveryRunner]:
        stmt = select(DeliveryRunner).where(
            DeliveryRunner.tenant == tenant,
            DeliveryRunner.status == "available",
            DeliveryRunner.quarantined == False,
        )
        if region:
            stmt = stmt.where(DeliveryRunner.region == region)
        stmt = stmt.order_by(DeliveryRunner.current_jobs.asc()).limit(5)
        runners = (await self.db.execute(stmt)).scalars().all()
        for r in runners:
            if required_labels:
                if all(l in (r.labels or []) for l in required_labels):
                    return r
            else:
                return r
        return runners[0] if runners else None
