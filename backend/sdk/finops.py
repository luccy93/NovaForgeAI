"""FinOps SDK mixin — Volume 69 Commit 1."""

from typing import Any, Dict, Optional


class FinOpsMixin:
    def finops_usage_summary(self, start: Optional[str] = None, end: Optional[str] = None) -> dict:
        params: Dict[str, Any] = {}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        return self.get(self._build_url("/finops/usage/summary"), params=params)

    def finops_list_costs(self, limit: int = 100, offset: int = 0, **filters: Any) -> dict:
        params: Dict[str, Any] = {"limit": limit, "offset": offset, **filters}
        return self.get(self._build_url("/finops/costs"), params=params)

    def finops_record_cost(self, usage: dict) -> dict:
        return self.post(self._build_url("/finops/costs/record"), data={"usage": usage})

    def finops_list_allocations(self, cost_record_id: Optional[str] = None, limit: int = 100) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if cost_record_id:
            params["cost_record_id"] = cost_record_id
        return self.get(self._build_url("/finops/allocations"), params=params)

    def finops_create_allocation(self, cost_record_id: str, splits: list) -> dict:
        return self.post(self._build_url("/finops/allocations"), data={"cost_record_id": cost_record_id, "splits": splits})

    def finops_list_pricing(self, provider: Optional[str] = None, model: Optional[str] = None) -> dict:
        params: Dict[str, Any] = {}
        if provider:
            params["provider"] = provider
        if model:
            params["model"] = model
        return self.get(self._build_url("/finops/pricing"), params=params)

    def finops_create_pricing(self, provider: str, **fields: Any) -> dict:
        return self.post(self._build_url("/finops/pricing"), data={"provider": provider, **fields})

    def finops_list_budgets(self) -> dict:
        return self.get(self._build_url("/finops/budgets"))

    def finops_create_budget(self, name: str, amount_cents: int, **fields: Any) -> dict:
        return self.post(self._build_url("/finops/budgets"), data={"name": name, "amount_cents": amount_cents, **fields})

    def finops_budget_status(self, budget_id: str) -> dict:
        return self.get(self._build_url(f"/finops/budgets/{budget_id}"))

    def finops_evaluate_budget(self, budget_id: str) -> dict:
        return self.post(self._build_url(f"/finops/budgets/{budget_id}/evaluate"), data={})

    def finops_run_aggregation(self, granularity: str, start: str, end: str, dimensions: Optional[dict] = None) -> dict:
        return self.post(self._build_url("/finops/aggregations/run"), data={
            "granularity": granularity, "start": start, "end": end, "dimensions": dimensions or {},
        })

    def finops_list_aggregations(self, granularity: str = "", limit: int = 100) -> dict:
        return self.get(self._build_url("/finops/aggregations"), params={"granularity": granularity, "limit": limit})


class AsyncFinOpsMixin:
    async def finops_usage_summary(self, start: Optional[str] = None, end: Optional[str] = None) -> dict:
        params: Dict[str, Any] = {}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        return await self.get(self._build_url("/finops/usage/summary"), params=params)

    async def finops_list_costs(self, limit: int = 100, offset: int = 0, **filters: Any) -> dict:
        params: Dict[str, Any] = {"limit": limit, "offset": offset, **filters}
        return await self.get(self._build_url("/finops/costs"), params=params)

    async def finops_record_cost(self, usage: dict) -> dict:
        return await self.post(self._build_url("/finops/costs/record"), data={"usage": usage})

    async def finops_list_allocations(self, cost_record_id: Optional[str] = None, limit: int = 100) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if cost_record_id:
            params["cost_record_id"] = cost_record_id
        return await self.get(self._build_url("/finops/allocations"), params=params)

    async def finops_create_allocation(self, cost_record_id: str, splits: list) -> dict:
        return await self.post(self._build_url("/finops/allocations"), data={"cost_record_id": cost_record_id, "splits": splits})

    async def finops_list_pricing(self, provider: Optional[str] = None, model: Optional[str] = None) -> dict:
        params: Dict[str, Any] = {}
        if provider:
            params["provider"] = provider
        if model:
            params["model"] = model
        return await self.get(self._build_url("/finops/pricing"), params=params)

    async def finops_create_pricing(self, provider: str, **fields: Any) -> dict:
        return await self.post(self._build_url("/finops/pricing"), data={"provider": provider, **fields})

    async def finops_list_budgets(self) -> dict:
        return await self.get(self._build_url("/finops/budgets"))

    async def finops_create_budget(self, name: str, amount_cents: int, **fields: Any) -> dict:
        return await self.post(self._build_url("/finops/budgets"), data={"name": name, "amount_cents": amount_cents, **fields})

    async def finops_budget_status(self, budget_id: str) -> dict:
        return await self.get(self._build_url(f"/finops/budgets/{budget_id}"))

    async def finops_evaluate_budget(self, budget_id: str) -> dict:
        return await self.post(self._build_url(f"/finops/budgets/{budget_id}/evaluate"), data={})

    async def finops_run_aggregation(self, granularity: str, start: str, end: str, dimensions: Optional[dict] = None) -> dict:
        return await self.post(self._build_url("/finops/aggregations/run"), data={
            "granularity": granularity, "start": start, "end": end, "dimensions": dimensions or {},
        })

    async def finops_list_aggregations(self, granularity: str = "", limit: int = 100) -> dict:
        return await self.get(self._build_url("/finops/aggregations"), params={"granularity": granularity, "limit": limit})
