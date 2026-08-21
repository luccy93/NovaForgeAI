"""Unified Analytics Platform -- Budget Management Service (Volume 50).

In-memory budget definitions and threshold evaluation for NovaForge.
Budgets are evaluated against spend recorded by the cost attribution
service (``backend.app.analytics.cost_service``). Spend figures are always
computed from recorded cost entries -- never fabricated. Budgets that have
not been evaluated yet report ``status: "unchecked"`` rather than guessing.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

BUDGET_STATUS_OK = "ok"
BUDGET_STATUS_WARNING = "warning"
BUDGET_STATUS_SOFT_LIMIT = "soft_limit"
BUDGET_STATUS_HARD_LIMIT = "hard_limit"
BUDGET_STATUS_UNCHECKED = "unchecked"

PERIOD_HOURLY = "hourly"
PERIOD_DAILY = "daily"
PERIOD_WEEKLY = "weekly"
PERIOD_MONTHLY = "monthly"
PERIOD_QUARTERLY = "quarterly"
PERIOD_YEARLY = "yearly"
PERIODS = (PERIOD_HOURLY, PERIOD_DAILY, PERIOD_WEEKLY, PERIOD_MONTHLY, PERIOD_QUARTERLY, PERIOD_YEARLY)

SCOPES = (
    "organization",
    "workspace",
    "project",
    "repository",
    "environment",
    "model",
    "provider",
    "agent",
    "workflow",
    "user_id",
    "tenant",
    "global",
)

DEFAULT_WARNING_THRESHOLD = 0.8
DEFAULT_SOFT_LIMIT_THRESHOLD = 0.95
DEFAULT_HARD_LIMIT_THRESHOLD = 1.0

UPDATABLE_FIELDS = (
    "name",
    "scope",
    "scope_value",
    "limit_usd",
    "cost_type",
    "period",
    "warning_threshold",
    "soft_limit_threshold",
    "hard_limit_threshold",
    "active",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _period_start(period: str, now: datetime) -> datetime:
    moment = now.astimezone(timezone.utc)
    if period == PERIOD_HOURLY:
        return moment.replace(minute=0, second=0, microsecond=0)
    if period == PERIOD_DAILY:
        return moment.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == PERIOD_WEEKLY:
        monday = moment.date() - timedelta(days=moment.weekday())
        return datetime(monday.year, monday.month, monday.day, tzinfo=timezone.utc)
    if period == PERIOD_MONTHLY:
        return datetime(moment.year, moment.month, 1, tzinfo=timezone.utc)
    if period == PERIOD_QUARTERLY:
        quarter_month = ((moment.month - 1) // 3) * 3 + 1
        return datetime(moment.year, quarter_month, 1, tzinfo=timezone.utc)
    if period == PERIOD_YEARLY:
        return datetime(moment.year, 1, 1, tzinfo=timezone.utc)
    raise ValueError(f"unsupported budget period: {period!r}")


def _validate_thresholds(warning: float, soft: float, hard: float) -> None:
    for label, value in (("warning_threshold", warning), ("soft_limit_threshold", soft), ("hard_limit_threshold", hard)):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"{label} must be a number")
        if not 0.0 < value <= 1.0:
            raise ValueError(f"{label} must be within (0, 1]")
    if not warning <= soft <= hard:
        raise ValueError("thresholds must satisfy warning <= soft_limit <= hard_limit")


class BudgetService:
    """In-memory budget registry with threshold evaluation."""

    def __init__(self) -> None:
        self._budgets: dict[str, dict] = {}

    def create_budget(
        self,
        tenant: str,
        name: str,
        scope: str,
        scope_value: str,
        limit_usd: float,
        cost_type: str = "total",
        period: str = "monthly",
        warning_threshold: float = DEFAULT_WARNING_THRESHOLD,
        soft_limit_threshold: float = DEFAULT_SOFT_LIMIT_THRESHOLD,
        hard_limit_threshold: float = DEFAULT_HARD_LIMIT_THRESHOLD,
    ) -> dict:
        if not tenant:
            raise ValueError("tenant is required")
        if not name:
            raise ValueError("name is required")
        if scope not in SCOPES:
            raise ValueError(f"unsupported scope: {scope!r}")
        if not isinstance(limit_usd, (int, float)) or isinstance(limit_usd, bool) or limit_usd <= 0:
            raise ValueError("limit_usd must be a positive number")
        if period not in PERIODS:
            raise ValueError(f"unsupported period: {period!r}")
        _validate_thresholds(warning_threshold, soft_limit_threshold, hard_limit_threshold)
        now = _utcnow().isoformat()
        budget = {
            "id": f"budget_{uuid.uuid4().hex}",
            "tenant": tenant,
            "name": name,
            "scope": scope,
            "scope_value": scope_value,
            "limit_usd": round(float(limit_usd), 6),
            "cost_type": cost_type or "total",
            "period": period,
            "warning_threshold": float(warning_threshold),
            "soft_limit_threshold": float(soft_limit_threshold),
            "hard_limit_threshold": float(hard_limit_threshold),
            "active": True,
            "created_at": now,
            "updated_at": now,
            "last_check": {},
        }
        self._budgets[budget["id"]] = budget
        return self._copy(budget)

    def get_budget(self, budget_id: str) -> dict | None:
        budget = self._budgets.get(budget_id)
        return self._copy(budget) if budget else None

    def list_budgets(self, tenant: str = "", scope: str = "") -> list[dict]:
        results = []
        for budget in self._budgets.values():
            if tenant and budget.get("tenant") != tenant:
                continue
            if scope and budget.get("scope") != scope:
                continue
            results.append(self._copy(budget))
        results.sort(key=lambda item: item.get("created_at") or "")
        return results

    def update_budget(self, budget_id: str, **kwargs) -> dict | None:
        budget = self._budgets.get(budget_id)
        if budget is None:
            return None
        unknown = set(kwargs) - set(UPDATABLE_FIELDS)
        if unknown:
            raise ValueError(f"cannot update fields: {sorted(unknown)}")
        candidate = dict(budget)
        for field in UPDATABLE_FIELDS:
            if field in kwargs:
                candidate[field] = kwargs[field]
        if not candidate.get("name"):
            raise ValueError("name is required")
        if candidate.get("scope") not in SCOPES:
            raise ValueError(f"unsupported scope: {candidate.get('scope')!r}")
        limit_usd = candidate.get("limit_usd")
        if not isinstance(limit_usd, (int, float)) or isinstance(limit_usd, bool) or limit_usd <= 0:
            raise ValueError("limit_usd must be a positive number")
        if candidate.get("period") not in PERIODS:
            raise ValueError(f"unsupported period: {candidate.get('period')!r}")
        _validate_thresholds(
            candidate["warning_threshold"],
            candidate["soft_limit_threshold"],
            candidate["hard_limit_threshold"],
        )
        candidate["limit_usd"] = round(float(limit_usd), 6)
        candidate["updated_at"] = _utcnow().isoformat()
        self._budgets[budget_id] = candidate
        return self._copy(candidate)

    def check_budget(self, budget_id: str, current_spend: float) -> dict:
        budget = self._budgets.get(budget_id)
        if budget is None:
            raise KeyError(f"budget not found: {budget_id}")
        if not isinstance(current_spend, (int, float)) or isinstance(current_spend, bool):
            raise ValueError("current_spend must be a number")
        if current_spend < 0:
            raise ValueError("current_spend must be non-negative")
        limit_usd = float(budget["limit_usd"])
        ratio = current_spend / limit_usd if limit_usd > 0 else 0.0
        if ratio >= float(budget["hard_limit_threshold"]):
            status = BUDGET_STATUS_HARD_LIMIT
        elif ratio >= float(budget["soft_limit_threshold"]):
            status = BUDGET_STATUS_SOFT_LIMIT
        elif ratio >= float(budget["warning_threshold"]):
            status = BUDGET_STATUS_WARNING
        else:
            status = BUDGET_STATUS_OK
        result = {
            "budget_id": budget_id,
            "tenant": budget["tenant"],
            "name": budget["name"],
            "scope": budget["scope"],
            "scope_value": budget["scope_value"],
            "period": budget["period"],
            "cost_type": budget["cost_type"],
            "limit_usd": round(limit_usd, 6),
            "current_spend_usd": round(float(current_spend), 6),
            "threshold_percentage": round(ratio * 100.0, 2),
            "remaining_usd": round(limit_usd - float(current_spend), 6),
            "status": status,
            "thresholds": {
                "warning": float(budget["warning_threshold"]),
                "soft_limit": float(budget["soft_limit_threshold"]),
                "hard_limit": float(budget["hard_limit_threshold"]),
            },
            "checked_at": _utcnow().isoformat(),
        }
        budget["last_check"] = {
            "status": status,
            "current_spend_usd": result["current_spend_usd"],
            "threshold_percentage": result["threshold_percentage"],
            "remaining_usd": result["remaining_usd"],
            "checked_at": result["checked_at"],
        }
        budget["updated_at"] = result["checked_at"]
        return result

    def check_all_budgets(self, tenant: str, cost_service) -> list[dict]:
        now = _utcnow()
        results = []
        for budget in self._budgets.values():
            if tenant and budget.get("tenant") != tenant:
                continue
            if not budget.get("active", True):
                continue
            period_start = _period_start(budget["period"], now)
            spend = self._current_spend(cost_service, budget, period_start, now)
            evaluation = self.check_budget(budget["id"], spend)
            evaluation["period_start"] = period_start.isoformat()
            evaluation["period_end"] = now.isoformat()
            results.append(evaluation)
        results.sort(key=lambda item: item.get("threshold_percentage") or 0.0, reverse=True)
        return results

    def get_budget_status(self, tenant: str) -> list[dict]:
        summaries = []
        for budget in self._budgets.values():
            if tenant and budget.get("tenant") != tenant:
                continue
            last = budget.get("last_check") or {}
            summaries.append(
                {
                    "budget_id": budget["id"],
                    "tenant": budget["tenant"],
                    "name": budget["name"],
                    "scope": budget["scope"],
                    "scope_value": budget["scope_value"],
                    "period": budget["period"],
                    "cost_type": budget["cost_type"],
                    "limit_usd": budget["limit_usd"],
                    "status": last.get("status", BUDGET_STATUS_UNCHECKED),
                    "current_spend_usd": last.get("current_spend_usd"),
                    "threshold_percentage": last.get("threshold_percentage"),
                    "remaining_usd": last.get("remaining_usd"),
                    "checked_at": last.get("checked_at"),
                }
            )
        summaries.sort(key=lambda item: item.get("name") or "")
        return summaries

    def delete_budget(self, budget_id: str) -> bool:
        return self._budgets.pop(budget_id, None) is not None

    def to_json(self, tenant: str = "") -> str:
        return json.dumps(self.list_budgets(tenant), indent=2, default=str)

    def _current_spend(self, cost_service, budget: dict, period_start: datetime, now: datetime) -> float:
        cost_type = budget.get("cost_type") or "total"
        entries = cost_service.get_costs(
            budget["tenant"],
            cost_type="" if cost_type == "total" else cost_type,
            start_time=period_start.isoformat(),
            end_time=now.isoformat(),
            limit=None,
        )
        scope = budget.get("scope")
        scope_value = budget.get("scope_value")
        if scope not in ("tenant", "global"):
            entries = [entry for entry in entries if entry.get(scope) == scope_value]
        return sum(float(entry.get("amount_usd") or 0.0) for entry in entries)

    @staticmethod
    def _copy(budget: dict) -> dict:
        copied = dict(budget)
        copied["last_check"] = dict(budget.get("last_check") or {})
        return copied


budget_service = BudgetService()
