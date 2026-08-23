"""Release strategies — rolling, blue-green, canary, weighted, shadow, dark."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.release.models import ReleaseStrategy, RolloutStrategy


class StrategyService:
    async def create_strategy(self, db: AsyncSession, tenant: str, name: str, strategy_type: str, config: dict) -> ReleaseStrategy:
        if strategy_type not in [e.value for e in RolloutStrategy]:
            raise ValueError(f"unknown strategy {strategy_type}")
        strat = ReleaseStrategy(tenant=tenant, name=name, strategy_type=strategy_type, config=config or {})
        db.add(strat)
        await db.flush()
        return strat

    async def get_strategy(self, db: AsyncSession, strategy_id: str) -> ReleaseStrategy | None:
        return await db.get(ReleaseStrategy, strategy_id)

    async def list_strategies(self, db: AsyncSession, tenant: str) -> list[ReleaseStrategy]:
        res = await db.execute(select(ReleaseStrategy).where(ReleaseStrategy.tenant == tenant))
        return list(res.scalars().all())

    async def evaluate_canary(self, db: AsyncSession, release_id: str, strategy_id: str, metrics: dict) -> dict:
        strat = await self.get_strategy(db, strategy_id)
        if not strat:
            raise ValueError("strategy not found")
        cfg = strat.config or {}
        # Configurable canary: initial/step/max/success_criteria
        initial = cfg.get("initial_percentage", 5)
        step = cfg.get("step_percentage", 15)
        max_pct = cfg.get("maximum_percentage", 100)
        success = cfg.get("success_criteria", {"error_rate": 0.05, "latency_ms": 1000})
        # Evaluate metrics against thresholds
        error_rate = metrics.get("error_rate", 0)
        latency = metrics.get("latency_ms", 0)
        if error_rate > success.get("error_rate", 0.05) or latency > success.get("latency_ms", 1000):
            return {"decision": "pause", "reason": f"thresholds exceeded error={error_rate} latency={latency}", "next_weight": initial}
        # Next weight progression
        current = metrics.get("current_weight", initial)
        nxt = min(max_pct, current + step)
        if nxt >= max_pct:
            return {"decision": "promote", "next_weight": max_pct, "reason": "reached max"}
        return {"decision": "continue", "next_weight": nxt, "reason": "within thresholds"}
