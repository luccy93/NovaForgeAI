"""Budget enforcement for autonomous engineering tasks."""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.models import AutomationBudget

logger = logging.getLogger(__name__)


class BudgetService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create(self, tenant: str) -> AutomationBudget:
        res = await self.db.execute(
            select(AutomationBudget).where(AutomationBudget.tenant == tenant)
        )
        budget = res.scalar_one_or_none()
        if not budget:
            budget = AutomationBudget(tenant=tenant)
            self.db.add(budget)
            await self.db.flush()
        return budget

    async def update_limits(
        self,
        tenant: str,
        max_tokens: Optional[int] = None,
        max_tool_calls: Optional[int] = None,
        max_files: Optional[int] = None,
        max_runtime_s: Optional[int] = None,
        max_cost_usd: Optional[float] = None,
    ) -> AutomationBudget:
        budget = await self.get_or_create(tenant)
        if max_tokens is not None:
            budget.max_tokens = max_tokens
        if max_tool_calls is not None:
            budget.max_tool_calls = max_tool_calls
        if max_files is not None:
            budget.max_files = max_files
        if max_runtime_s is not None:
            budget.max_runtime_s = max_runtime_s
        if max_cost_usd is not None:
            budget.max_cost_usd = max_cost_usd
        budget.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return budget

    async def record_usage(
        self,
        tenant: str,
        tokens: int = 0,
        tool_calls: int = 0,
        files: int = 0,
        runtime_s: int = 0,
        cost_usd: float = 0.0,
    ) -> AutomationBudget:
        budget = await self.get_or_create(tenant)
        budget.used_tokens += tokens
        budget.used_tool_calls += tool_calls
        budget.used_files += files
        budget.used_runtime_s += runtime_s
        budget.used_cost_usd = round(budget.used_cost_usd + cost_usd, 6)
        budget.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        return budget

    async def check_budget(self, tenant: str, estimated_tokens: int = 0,
                           estimated_tool_calls: int = 0, estimated_cost: float = 0.0) -> dict:
        budget = await self.get_or_create(tenant)
        violations = []
        if budget.used_tokens + estimated_tokens > budget.max_tokens:
            violations.append(f"tokens: {budget.used_tokens + estimated_tokens} > {budget.max_tokens}")
        if budget.used_tool_calls + estimated_tool_calls > budget.max_tool_calls:
            violations.append(f"tool_calls: {budget.used_tool_calls + estimated_tool_calls} > {budget.max_tool_calls}")
        if budget.used_cost_usd + estimated_cost > budget.max_cost_usd:
            violations.append(f"cost: {budget.used_cost_usd + estimated_cost} > {budget.max_cost_usd}")
        if budget.used_runtime_s > budget.max_runtime_s:
            violations.append(f"runtime: {budget.used_runtime_s} > {budget.max_runtime_s}")
        return {
            "within_budget": len(violations) == 0,
            "violations": violations,
            "budget": {
                "tokens": f"{budget.used_tokens}/{budget.max_tokens}",
                "tool_calls": f"{budget.used_tool_calls}/{budget.max_tool_calls}",
                "cost": f"{budget.used_cost_usd}/{budget.max_cost_usd}",
                "runtime": f"{budget.used_runtime_s}/{budget.max_runtime_s}",
            },
        }

    async def increment_active_tasks(self, tenant: str) -> AutomationBudget:
        budget = await self.get_or_create(tenant)
        budget.active_tasks += 1
        await self.db.flush()
        return budget

    async def decrement_active_tasks(self, tenant: str) -> AutomationBudget:
        budget = await self.get_or_create(tenant)
        budget.active_tasks = max(0, budget.active_tasks - 1)
        await self.db.flush()
        return budget

    async def get_usage_summary(self, tenant: str) -> dict:
        budget = await self.get_or_create(tenant)
        return {
            "tenant": tenant,
            "tokens": {"used": budget.used_tokens, "limit": budget.max_tokens,
                       "pct": round(budget.used_tokens / max(budget.max_tokens, 1) * 100, 1)},
            "tool_calls": {"used": budget.used_tool_calls, "limit": budget.max_tool_calls,
                           "pct": round(budget.used_tool_calls / max(budget.max_tool_calls, 1) * 100, 1)},
            "cost_usd": {"used": budget.used_cost_usd, "limit": budget.max_cost_usd,
                         "pct": round(budget.used_cost_usd / max(budget.max_cost_usd, 0.01) * 100, 1)},
            "runtime_s": {"used": budget.used_runtime_s, "limit": budget.max_runtime_s,
                          "pct": round(budget.used_runtime_s / max(budget.max_runtime_s, 1) * 100, 1)},
            "active_tasks": budget.active_tasks,
        }
