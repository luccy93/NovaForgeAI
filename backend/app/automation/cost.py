"""Automation cost tracking (Volume 33).

Per-organization budgets, per-run cost estimates and step-level cost
attribution. Estimates are always labeled as estimates; the gateway uses
these to stop workflows that would exceed their budget.
"""
import logging, time
from dataclasses import dataclass, field
from typing import Any, Optional

from ..common.storage import JsonFileStorage

logger = logging.getLogger(__name__)


@dataclass
class CostEntry:
    execution_id: str
    step_id: str
    cost_usd: float
    currency: str = "USD"
    estimated: bool = True
    workflow_id: str = ""
    organization_id: str = ""
    created_at: str = field(default_factory=lambda: time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    def to_dict(self) -> dict:
        return self.__dict__


class CostTracker:
    def __init__(self, storage: Optional[JsonFileStorage] = None,
                 budgets: Optional[dict] = None):
        self._storage = storage or JsonFileStorage(
            "data/automation/costs.json")
        self.budgets = budgets or {}  # org -> monthly budget USD

    def record(self, execution_id: str, step_id: str, cost_usd: float,
               workflow_id: str = "", organization_id: str = "",
               estimated: bool = True) -> CostEntry:
        entry = CostEntry(execution_id=execution_id, step_id=step_id,
                          cost_usd=round(float(cost_usd), 6),
                          workflow_id=workflow_id,
                          organization_id=organization_id,
                          estimated=estimated)
        self._storage.set(self._key(entry), entry.to_dict())
        return entry

    def _key(self, entry: CostEntry) -> str:
        return (f"{entry.organization_id or 'default'}:"
                f"{entry.execution_id}:{entry.step_id}")

    def total_for(self, organization_id: str = "") -> float:
        prefix = f"{organization_id or 'default'}:"
        return round(sum(float(v.get("cost_usd", 0))
                         for k, v in self._storage.get_all().items()
                         if k.startswith(prefix)), 6)

    def total_for_execution(self, execution_id: str) -> float:
        rows = self._storage.get_all()
        return round(sum(float(v.get("cost_usd", 0))
                         for k, v in rows.items()
                         if k.split(":")[1] == execution_id), 6)

    def budget_remaining(self, organization_id: str = "") -> float:
        budget = self.budgets.get(organization_id,
                                  self.budgets.get("*", float("inf")))
        if budget == float("inf"):
            return float("inf")
        return round(max(0.0, budget - self.total_for(organization_id)), 6)

    def within_budget(self, organization_id: str = "",
                      projected: float = 0.0) -> bool:
        remaining = self.budget_remaining(organization_id)
        if remaining == float("inf"):
            return True
        return projected <= remaining

    def estimate_workflow(self, steps: list[Any],
                          per_step_usd: float = 0.001) -> float:
        return round(per_step_usd * len(steps), 6)

    def count(self) -> int:
        return len(self._storage.get_all())