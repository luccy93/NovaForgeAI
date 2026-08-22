"""Budget service — set per-org/feature budget limits, track spend, enforce hard limits."""
import uuid
from datetime import datetime, timezone
from typing import Optional


class BudgetService:
    def __init__(self):
        self._budgets: dict[str, dict] = {}
        self._org_budgets: dict[str, list[str]] = {}
        self._alerts: list[dict] = []

    def create_budget(
        self,
        organization_id: str,
        name: str,
        limit_cents: int,
        scope: str = "organization",
        scope_value: Optional[str] = None,
        period: str = "monthly",
        warning_threshold: float = 0.80,
        hard_limit_threshold: float = 1.0,
    ) -> dict:
        budget_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        if period == "monthly":
            period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if period_start.month == 12:
                period_end = period_start.replace(year=period_start.year + 1, month=1)
            else:
                period_end = period_start.replace(month=period_start.month + 1)
        elif period == "annual":
            period_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            period_end = period_start.replace(year=period_start.year + 1)
        else:
            period_start = now
            period_end = now
        budget = {
            "id": budget_id,
            "organization_id": organization_id,
            "name": name,
            "scope": scope,
            "scope_value": scope_value,
            "limit_cents": limit_cents,
            "spent_cents": 0,
            "period": period,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "warning_threshold": warning_threshold,
            "hard_limit_threshold": hard_limit_threshold,
            "is_active": True,
            "alert_sent_at": None,
            "metadata": {},
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        self._budgets[budget_id] = budget
        self._org_budgets.setdefault(organization_id, []).append(budget_id)
        return budget

    def get_budget(self, budget_id: str) -> Optional[dict]:
        return self._budgets.get(budget_id)

    def list_budgets(
        self,
        organization_id: Optional[str] = None,
        scope: Optional[str] = None,
    ) -> list[dict]:
        if organization_id:
            ids = self._org_budgets.get(organization_id, [])
            budgets = [self._budgets[bid] for bid in ids if bid in self._budgets]
        else:
            budgets = list(self._budgets.values())
        if scope:
            budgets = [b for b in budgets if b["scope"] == scope]
        return budgets

    def update_budget(self, budget_id: str, **kwargs) -> Optional[dict]:
        budget = self._budgets.get(budget_id)
        if not budget:
            return None
        for key in ("name", "limit_cents", "warning_threshold", "hard_limit_threshold", "is_active"):
            if key in kwargs and kwargs[key] is not None:
                budget[key] = kwargs[key]
        budget["updated_at"] = datetime.now(timezone.utc).isoformat()
        return budget

    def record_spend(self, budget_id: str, amount_cents: int) -> Optional[dict]:
        budget = self._budgets.get(budget_id)
        if not budget:
            return None
        now = datetime.now(timezone.utc)
        budget["spent_cents"] += amount_cents
        budget["updated_at"] = now.isoformat()
        return budget

    def check_budget(self, budget_id: str) -> dict:
        budget = self._budgets.get(budget_id)
        if not budget:
            return {"status": "not_found"}
        limit = budget["limit_cents"]
        spent = budget["spent_cents"]
        percentage = (spent / limit * 100) if limit > 0 else 0
        if spent >= limit * budget["hard_limit_threshold"]:
            status = "hard_limit"
        elif spent >= limit * budget["warning_threshold"]:
            status = "warning"
        else:
            status = "ok"
        alert_needed = False
        if status in ("warning", "hard_limit") and not budget.get("alert_sent_at"):
            alert_needed = True
            budget["alert_sent_at"] = datetime.now(timezone.utc).isoformat()
        return {
            "budget_id": budget_id,
            "status": status,
            "limit_cents": limit,
            "spent_cents": spent,
            "remaining_cents": max(0, limit - spent),
            "percentage_used": round(percentage, 2),
            "alert_needed": alert_needed,
        }

    def check_all_budgets(self, organization_id: str) -> list[dict]:
        budgets = self.list_budgets(organization_id=organization_id)
        return [self.check_budget(b["id"]) for b in budgets if b["is_active"]]

    def delete_budget(self, budget_id: str) -> bool:
        if budget_id in self._budgets:
            budget = self._budgets.pop(budget_id)
            org_budgets = self._org_budgets.get(budget["organization_id"], [])
            if budget_id in org_budgets:
                org_budgets.remove(budget_id)
            return True
        return False

    def get_budget_status(self, organization_id: str) -> dict:
        budgets = self.list_budgets(organization_id=organization_id)
        total_limit = sum(b["limit_cents"] for b in budgets)
        total_spent = sum(b["spent_cents"] for b in budgets)
        return {
            "organization_id": organization_id,
            "total_budgets": len(budgets),
            "active_budgets": sum(1 for b in budgets if b["is_active"]),
            "total_limit_cents": total_limit,
            "total_spent_cents": total_spent,
            "overall_percentage": round((total_spent / total_limit * 100) if total_limit > 0 else 0, 2),
        }

    def get_telemetry(self) -> dict:
        return {
            "total_budgets": len(self._budgets),
            "active_budgets": sum(1 for b in self._budgets.values() if b["is_active"]),
            "hard_limit_reached": sum(1 for b in self._budgets.values() if b["spent_cents"] >= b["limit_cents"] * b["hard_limit_threshold"]),
        }


budget_service = BudgetService()
