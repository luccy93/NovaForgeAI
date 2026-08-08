import json
import uuid
import hashlib
import time
import math
import os
import logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class CostCategory(Enum):
    PROMPT_TOKENS = "prompt_tokens"
    COMPLETION_TOKENS = "completion_tokens"
    EMBEDDING_TOKENS = "embedding_tokens"
    SEARCH_REQUESTS = "search_requests"
    RAG_OPERATIONS = "rag_operations"
    AGENT_RUNTIME = "agent_runtime"
    STREAMING_SESSIONS = "streaming_sessions"
    CONTEXT_BUILDING = "context_building"
    VECTOR_QUERIES = "vector_queries"
    MODEL_SWITCHING = "model_switching"
    PROVIDER_COSTS = "provider_costs"
    ORGANIZATION_COSTS = "organization_costs"
    WORKSPACE_COSTS = "workspace_costs"
    USER_COSTS = "user_costs"
    CPU_USAGE = "cpu_usage"
    MEMORY_USAGE = "memory_usage"
    GPU_USAGE = "gpu_usage"
    STORAGE = "storage"
    BANDWIDTH = "bandwidth"
    DATABASE_USAGE = "database_usage"
    REDIS = "redis"
    NEO4J = "neo4j"
    QDRANT = "qdrant"
    OBJECT_STORAGE = "object_storage"
    CONTAINER_RUNTIME = "container_runtime"
    NETWORK = "network"
    LOAD_BALANCER = "load_balancer"
    MONITORING = "monitoring"
    LOGGING = "logging"


class BudgetPeriod(Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class ChargebackStrategy(Enum):
    DIRECT_ALLOCATION = "direct_allocation"
    PROPORTIONAL = "proportional"
    FIXED_SPLIT = "fixed_split"
    USAGE_BASED = "usage_based"


class OptimizationAction(Enum):
    SCALE_DOWN = "scale_down"
    RIGHTSIZE = "rightsize"
    MOVE_TO_SPOT = "move_to_spot"
    CHANGE_PROVIDER = "change_provider"
    CHANGE_MODEL = "change_model"
    CACHE_OPTIMIZATION = "cache_optimization"
    BATCH_PROCESSING = "batch_processing"
    QUERY_COMPRESSION = "query_compression"


@dataclass
class CostEntry:
    id: str
    org_id: str
    workspace_id: str
    user_id: str
    category: CostCategory
    provider: str
    model: str
    amount: float
    tokens: int = 0
    cpu_seconds: float = 0.0
    gpu_seconds: float = 0.0
    storage_bytes: int = 0
    bandwidth_bytes: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = ""
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["category"] = self.category.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "CostEntry":
        data = data.copy()
        data["category"] = CostCategory(data.get("category", "prompt_tokens"))
        return cls(**data)


@dataclass
class CostSummary:
    id: str
    org_id: str
    start_date: str
    end_date: str
    total_cost: float = 0.0
    by_category: dict = field(default_factory=dict)
    by_provider: dict = field(default_factory=dict)
    by_model: dict = field(default_factory=dict)
    by_workspace: dict = field(default_factory=dict)
    by_user: dict = field(default_factory=dict)
    cost_trend: str = "stable"
    avg_daily_cost: float = 0.0
    projected_monthly: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CostSummary":
        return cls(**data)


@dataclass
class Budget:
    id: str
    org_id: str
    name: str
    period: BudgetPeriod
    limit: float
    current_spend: float = 0.0
    alert_threshold: float = 80.0
    start_date: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    end_date: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["period"] = self.period.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Budget":
        data["period"] = BudgetPeriod(data.get("period", "monthly"))
        return cls(**data)


@dataclass
class CostForecast:
    id: str
    org_id: str
    period: BudgetPeriod
    predicted_cost: float = 0.0
    confidence_low: float = 0.0
    confidence_high: float = 0.0
    trend_direction: str = "stable"
    factors: list = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["period"] = self.period.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "CostForecast":
        data["period"] = BudgetPeriod(data.get("period", "monthly"))
        return cls(**data)


@dataclass
class OptimizationRecommendation:
    id: str
    org_id: str
    action: OptimizationAction
    current_cost: float = 0.0
    projected_savings: float = 0.0
    implementation_cost: float = 0.0
    payback_days: int = 0
    risk_level: str = "medium"
    description: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["action"] = self.action.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "OptimizationRecommendation":
        data["action"] = OptimizationAction(data.get("action", "rightsize"))
        return cls(**data)


@dataclass
class ChargebackAllocation:
    id: str
    org_id: str
    workspace_id: str
    period: BudgetPeriod
    total_cost: float = 0.0
    allocations: list[dict] = field(default_factory=list)
    methodology: ChargebackStrategy = ChargebackStrategy.PROPORTIONAL
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["period"] = self.period.value
        d["methodology"] = self.methodology.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ChargebackAllocation":
        data["period"] = BudgetPeriod(data.get("period", "monthly"))
        data["methodology"] = ChargebackStrategy(data.get("methodology", "proportional"))
        return cls(**data)


@dataclass
class ShowbackReport:
    id: str
    org_id: str
    period: BudgetPeriod
    total_spend: float = 0.0
    by_workspace: dict = field(default_factory=dict)
    by_team: dict = field(default_factory=dict)
    by_service: dict = field(default_factory=dict)
    trend_data: list = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["period"] = self.period.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ShowbackReport":
        data["period"] = BudgetPeriod(data.get("period", "monthly"))
        return cls(**data)


@dataclass
class FinOpsDashboard:
    id: str
    org_id: str
    total_spend: float = 0.0
    budget_remaining: float = 0.0
    projected_overage: float = 0.0
    top_categories: list = field(default_factory=list)
    top_services: list = field(default_factory=list)
    savings_opportunities: list = field(default_factory=list)
    trends: list = field(default_factory=list)
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "FinOpsDashboard":
        return cls(**data)


class FinOpsEngine:
    def __init__(self, storage_dir: str = "finops_data"):
        self.storage_dir = storage_dir
        self._cost_entries: dict[str, CostEntry] = {}
        self._cost_summaries: dict[str, CostSummary] = {}
        self._budgets: dict[str, Budget] = {}
        self._forecasts: dict[str, CostForecast] = {}
        self._recommendations: dict[str, OptimizationRecommendation] = {}
        self._chargebacks: dict[str, ChargebackAllocation] = {}
        self._showbacks: dict[str, ShowbackReport] = {}
        self._dashboards: dict[str, FinOpsDashboard] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _cost_entries_path(self) -> str:
        return os.path.join(self.storage_dir, "cost_entries.json")

    def _cost_summaries_path(self) -> str:
        return os.path.join(self.storage_dir, "cost_summaries.json")

    def _budgets_path(self) -> str:
        return os.path.join(self.storage_dir, "budgets.json")

    def _forecasts_path(self) -> str:
        return os.path.join(self.storage_dir, "forecasts.json")

    def _recommendations_path(self) -> str:
        return os.path.join(self.storage_dir, "recommendations.json")

    def _chargebacks_path(self) -> str:
        return os.path.join(self.storage_dir, "chargebacks.json")

    def _showbacks_path(self) -> str:
        return os.path.join(self.storage_dir, "showbacks.json")

    def _dashboards_path(self) -> str:
        return os.path.join(self.storage_dir, "dashboards.json")

    def _save(self) -> None:
        try:
            entries_data = {eid: e.to_dict() for eid, e in self._cost_entries.items()}
            with open(self._cost_entries_path(), "w", encoding="utf-8") as f:
                json.dump(entries_data, f, indent=2, default=str)

            summaries_data = {sid: s.to_dict() for sid, s in self._cost_summaries.items()}
            with open(self._cost_summaries_path(), "w", encoding="utf-8") as f:
                json.dump(summaries_data, f, indent=2, default=str)

            budgets_data = {bid: b.to_dict() for bid, b in self._budgets.items()}
            with open(self._budgets_path(), "w", encoding="utf-8") as f:
                json.dump(budgets_data, f, indent=2, default=str)

            forecasts_data = {fid: f.to_dict() for fid, f in self._forecasts.items()}
            with open(self._forecasts_path(), "w", encoding="utf-8") as f:
                json.dump(forecasts_data, f, indent=2, default=str)

            recs_data = {rid: r.to_dict() for rid, r in self._recommendations.items()}
            with open(self._recommendations_path(), "w", encoding="utf-8") as f:
                json.dump(recs_data, f, indent=2, default=str)

            chargebacks_data = {cid: c.to_dict() for cid, c in self._chargebacks.items()}
            with open(self._chargebacks_path(), "w", encoding="utf-8") as f:
                json.dump(chargebacks_data, f, indent=2, default=str)

            showbacks_data = {sid: s.to_dict() for sid, s in self._showbacks.items()}
            with open(self._showbacks_path(), "w", encoding="utf-8") as f:
                json.dump(showbacks_data, f, indent=2, default=str)

            dashes_data = {did: d.to_dict() for did, d in self._dashboards.items()}
            with open(self._dashboards_path(), "w", encoding="utf-8") as f:
                json.dump(dashes_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save finops data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._cost_entries_path()):
                with open(self._cost_entries_path(), "r", encoding="utf-8") as f:
                    entries_data = json.load(f)
                for eid, data in entries_data.items():
                    try:
                        self._cost_entries[eid] = CostEntry.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed cost entry %s: %s", eid, e)

            if os.path.exists(self._cost_summaries_path()):
                with open(self._cost_summaries_path(), "r", encoding="utf-8") as f:
                    summaries_data = json.load(f)
                for sid, data in summaries_data.items():
                    try:
                        self._cost_summaries[sid] = CostSummary.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed cost summary %s: %s", sid, e)

            if os.path.exists(self._budgets_path()):
                with open(self._budgets_path(), "r", encoding="utf-8") as f:
                    budgets_data = json.load(f)
                for bid, data in budgets_data.items():
                    try:
                        self._budgets[bid] = Budget.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed budget %s: %s", bid, e)

            if os.path.exists(self._forecasts_path()):
                with open(self._forecasts_path(), "r", encoding="utf-8") as f:
                    forecasts_data = json.load(f)
                for fid, data in forecasts_data.items():
                    try:
                        self._forecasts[fid] = CostForecast.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed forecast %s: %s", fid, e)

            if os.path.exists(self._recommendations_path()):
                with open(self._recommendations_path(), "r", encoding="utf-8") as f:
                    recs_data = json.load(f)
                for rid, data in recs_data.items():
                    try:
                        self._recommendations[rid] = OptimizationRecommendation.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed recommendation %s: %s", rid, e)

            if os.path.exists(self._chargebacks_path()):
                with open(self._chargebacks_path(), "r", encoding="utf-8") as f:
                    chargebacks_data = json.load(f)
                for cid, data in chargebacks_data.items():
                    try:
                        self._chargebacks[cid] = ChargebackAllocation.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed chargeback %s: %s", cid, e)

            if os.path.exists(self._showbacks_path()):
                with open(self._showbacks_path(), "r", encoding="utf-8") as f:
                    showbacks_data = json.load(f)
                for sid, data in showbacks_data.items():
                    try:
                        self._showbacks[sid] = ShowbackReport.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed showback %s: %s", sid, e)

            if os.path.exists(self._dashboards_path()):
                with open(self._dashboards_path(), "r", encoding="utf-8") as f:
                    dashes_data = json.load(f)
                for did, data in dashes_data.items():
                    try:
                        self._dashboards[did] = FinOpsDashboard.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed dashboard %s: %s", did, e)
        except Exception as e:
            logger.error("Failed to load finops data: %s", e, exc_info=True)

    def track_cost(self, entry: CostEntry) -> CostEntry:
        self._telemetry["track_cost_calls"] += 1
        if not entry.id:
            entry.id = str(uuid.uuid4())
        if not entry.timestamp:
            entry.timestamp = datetime.now(timezone.utc).isoformat()
        self._cost_entries[entry.id] = entry
        # Update budget current_spend for matching org budgets
        for budget in self._budgets.values():
            if budget.org_id == entry.org_id:
                budget.current_spend += entry.amount
                budget.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Tracked cost entry %s: %.4f for org %s (%s)", entry.id, entry.amount, entry.org_id, entry.category.value)
        return entry

    def get_cost_summary(self, org_id: str, start_date: str, end_date: str, group_by: Optional[str] = None) -> CostSummary:
        self._telemetry["get_cost_summary_calls"] += 1
        filtered = []
        for entry in self._cost_entries.values():
            if entry.org_id == org_id and start_date <= entry.timestamp <= end_date:
                filtered.append(entry)

        total_cost = sum(e.amount for e in filtered)
        days_diff = max(1, (datetime.fromisoformat(end_date) - datetime.fromisoformat(start_date)).days)
        avg_daily = round(total_cost / days_diff, 4)
        projected_monthly = round(avg_daily * 30, 4)

        by_category: dict = defaultdict(float)
        by_provider: dict = defaultdict(float)
        by_model: dict = defaultdict(float)
        by_workspace: dict = defaultdict(float)
        by_user: dict = defaultdict(float)

        for e in filtered:
            by_category[e.category.value] += e.amount
            by_provider[e.provider] += e.amount
            by_model[e.model] += e.amount
            by_workspace[e.workspace_id] += e.amount
            by_user[e.user_id] += e.amount

        # Determine trend by comparing first half vs second half
        cost_trend = "stable"
        if len(filtered) >= 4:
            mid = len(filtered) // 2
            first_half = sum(e.amount for e in filtered[:mid])
            second_half = sum(e.amount for e in filtered[mid:])
            if second_half > first_half * 1.1:
                cost_trend = "increasing"
            elif second_half < first_half * 0.9:
                cost_trend = "decreasing"

        summary = CostSummary(
            id=str(uuid.uuid4()),
            org_id=org_id,
            start_date=start_date,
            end_date=end_date,
            total_cost=round(total_cost, 4),
            by_category=dict(by_category),
            by_provider=dict(by_provider),
            by_model=dict(by_model),
            by_workspace=dict(by_workspace),
            by_user=dict(by_user),
            cost_trend=cost_trend,
            avg_daily_cost=avg_daily,
            projected_monthly=projected_monthly,
        )
        self._cost_summaries[summary.id] = summary
        self._save()
        return summary

    def create_budget(self, budget: Budget) -> Budget:
        self._telemetry["create_budget_calls"] += 1
        if not budget.id:
            budget.id = str(uuid.uuid4())
        budget.created_at = datetime.now(timezone.utc).isoformat()
        budget.updated_at = budget.created_at
        self._budgets[budget.id] = budget

        # Initialize current_spend from existing cost entries
        current = 0.0
        for entry in self._cost_entries.values():
            if entry.org_id == budget.org_id:
                current += entry.amount
        budget.current_spend = round(current, 4)

        if not budget.end_date:
            if budget.period == BudgetPeriod.DAILY:
                end = datetime.now(timezone.utc) + timedelta(days=1)
            elif budget.period == BudgetPeriod.WEEKLY:
                end = datetime.now(timezone.utc) + timedelta(weeks=1)
            elif budget.period == BudgetPeriod.MONTHLY:
                end = datetime.now(timezone.utc) + timedelta(days=30)
            elif budget.period == BudgetPeriod.QUARTERLY:
                end = datetime.now(timezone.utc) + timedelta(days=91)
            else:
                end = datetime.now(timezone.utc) + timedelta(days=365)
            budget.end_date = end.isoformat()

        self._save()
        logger.info("Created budget %s: %s (%.2f)", budget.id, budget.name, budget.limit)
        return budget

    def update_budget(self, budget_id: str, updates: dict) -> Optional[Budget]:
        self._telemetry["update_budget_calls"] += 1
        budget = self._budgets.get(budget_id)
        if not budget:
            logger.warning("Attempted to update unknown budget: %s", budget_id)
            return None
        for key, value in updates.items():
            if hasattr(budget, key) and key not in ("id", "created_at"):
                if key == "period":
                    setattr(budget, key, BudgetPeriod(value) if isinstance(value, str) else value)
                else:
                    setattr(budget, key, value)
        budget.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Updated budget: %s", budget_id)
        return budget

    def get_budget_status(self, budget_id: str) -> dict:
        self._telemetry["get_budget_status_calls"] += 1
        budget = self._budgets.get(budget_id)
        if not budget:
            return {"error": "Budget not found", "budget_id": budget_id}
        percentage = round((budget.current_spend / budget.limit * 100) if budget.limit > 0 else 0, 2)
        remaining = round(budget.limit - budget.current_spend, 4)
        # Simple projected spend: if days elapsed > 0, extrapolate
        now = datetime.now(timezone.utc)
        start = datetime.fromisoformat(budget.start_date)
        end = datetime.fromisoformat(budget.end_date) if budget.end_date else now
        elapsed_days = max(1, (now - start).days)
        total_days = max(1, (end - start).days)
        daily_rate = budget.current_spend / elapsed_days
        projected_total = daily_rate * total_days
        projected_overage = max(0, round(projected_total - budget.limit, 4))

        return {
            "budget_id": budget.id,
            "name": budget.name,
            "org_id": budget.org_id,
            "period": budget.period.value,
            "limit": budget.limit,
            "current_spend": budget.current_spend,
            "remaining": remaining,
            "percentage_used": percentage,
            "alert_threshold": budget.alert_threshold,
            "threshold_breached": percentage >= budget.alert_threshold,
            "projected_total": round(projected_total, 4),
            "projected_overage": projected_overage,
            "start_date": budget.start_date,
            "end_date": budget.end_date,
            "status": "exceeded" if budget.current_spend >= budget.limit else "warning" if percentage >= budget.alert_threshold else "on_track",
        }

    def list_budgets(self, org_id: str) -> list[Budget]:
        self._telemetry["list_budgets_calls"] += 1
        return [b for b in self._budgets.values() if b.org_id == org_id]

    def forecast_costs(self, org_id: str, period: BudgetPeriod, days: int = 30) -> CostForecast:
        self._telemetry["forecast_costs_calls"] += 1
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=max(days, 7))
        entries = [e for e in self._cost_entries.values() if e.org_id == org_id and e.timestamp >= start.isoformat()]

        if not entries:
            forecast = CostForecast(
                id=str(uuid.uuid4()),
                org_id=org_id,
                period=period,
                predicted_cost=0.0,
                confidence_low=0.0,
                confidence_high=0.0,
                trend_direction="stable",
                factors=[{"note": "Insufficient data for forecasting"}],
            )
            self._forecasts[forecast.id] = forecast
            self._save()
            return forecast

        # Simple linear regression: days since start vs amount
        start_dt = datetime.fromisoformat(entries[0].timestamp)
        x_vals = []
        y_vals = []
        daily_totals: dict = defaultdict(float)
        for e in entries:
            day_key = e.timestamp[:10]
            daily_totals[day_key] += e.amount

        sorted_days = sorted(daily_totals.keys())
        for i, day_key in enumerate(sorted_days):
            x_vals.append(float(i))
            y_vals.append(daily_totals[day_key])

        n = len(x_vals)
        if n < 2:
            slope = 0.0
            intercept = sum(y_vals) / n if n > 0 else 0.0
        else:
            sum_x = sum(x_vals)
            sum_y = sum(y_vals)
            sum_xy = sum(x * y for x, y in zip(x_vals, y_vals))
            sum_xx = sum(x * x for x in x_vals)
            denom = n * sum_xx - sum_x * sum_x
            if denom == 0:
                slope = 0.0
                intercept = sum_y / n
            else:
                slope = (n * sum_xy - sum_x * sum_y) / denom
                intercept = (sum_y - slope * sum_x) / n

        # Map period to multiplier of daily rate
        period_days_map = {
            BudgetPeriod.DAILY: 1,
            BudgetPeriod.WEEKLY: 7,
            BudgetPeriod.MONTHLY: 30,
            BudgetPeriod.QUARTERLY: 91,
            BudgetPeriod.YEARLY: 365,
        }
        period_mult = period_days_map.get(period, 30)

        # Project forward
        last_x = x_vals[-1] if x_vals else 0
        predicted_daily = intercept + slope * last_x
        predicted_cost = predicted_daily * period_mult
        predicted_cost = max(0, round(predicted_cost, 4))

        # Confidence intervals (simple heuristic)
        if y_vals:
            variance = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(x_vals, y_vals)) / n
            std_dev = math.sqrt(variance)
        else:
            std_dev = predicted_cost * 0.1

        confidence_low = round(max(0, predicted_cost - 1.96 * std_dev * math.sqrt(period_mult)), 4)
        confidence_high = round(predicted_cost + 1.96 * std_dev * math.sqrt(period_mult), 4)

        trend_direction = "stable"
        if slope > 0.01:
            trend_direction = "increasing"
        elif slope < -0.01:
            trend_direction = "decreasing"

        factors = [
            {"name": "daily_rate", "value": round(predicted_daily, 4)},
            {"name": "trend_slope", "value": round(slope, 6)},
            {"name": "data_points", "value": n},
            {"name": "std_dev", "value": round(std_dev, 4)},
        ]

        forecast = CostForecast(
            id=str(uuid.uuid4()),
            org_id=org_id,
            period=period,
            predicted_cost=predicted_cost,
            confidence_low=confidence_low,
            confidence_high=confidence_high,
            trend_direction=trend_direction,
            factors=factors,
        )
        self._forecasts[forecast.id] = forecast
        self._save()
        return forecast

    def get_optimization_recommendations(self, org_id: str) -> list[OptimizationRecommendation]:
        self._telemetry["get_optimization_recommendations_calls"] += 1
        # Analyze cost entries to identify top cost areas and generate recommendations
        org_entries = [e for e in self._cost_entries.values() if e.org_id == org_id]
        if not org_entries:
            return []

        # Aggregate by category and provider
        by_category: dict[str, float] = defaultdict(float)
        by_provider: dict[str, float] = defaultdict(float)
        total = 0.0
        for e in org_entries:
            by_category[e.category.value] += e.amount
            by_provider[e.provider] += e.amount
            total += e.amount

        org_recommendations = [r for r in self._recommendations.values() if r.org_id == org_id]
        if org_recommendations:
            return org_recommendations

        recommendations = []
        # Check prompt tokens cost
        prompt_cost = by_category.get("prompt_tokens", 0) + by_category.get("completion_tokens", 0)
        if prompt_cost > total * 0.3:
            rec = OptimizationRecommendation(
                id=str(uuid.uuid4()),
                org_id=org_id,
                action=OptimizationAction.CHANGE_MODEL,
                current_cost=round(prompt_cost, 4),
                projected_savings=round(prompt_cost * 0.25, 4),
                implementation_cost=0.0,
                payback_days=0,
                risk_level="low",
                description="High LLM token cost detected. Consider switching to a lower-cost model or implementing prompt compression to reduce token usage.",
            )
            recommendations.append(rec)

        # Check embedding costs
        embed_cost = by_category.get("embedding_tokens", 0)
        if embed_cost > total * 0.1:
            rec = OptimizationRecommendation(
                id=str(uuid.uuid4()),
                org_id=org_id,
                action=OptimizationAction.CACHE_OPTIMIZATION,
                current_cost=round(embed_cost, 4),
                projected_savings=round(embed_cost * 0.4, 4),
                implementation_cost=round(embed_cost * 0.05, 4),
                payback_days=int(0.05 / 0.4 * 30) if embed_cost > 0 else 0,
                risk_level="low",
                description="High embedding costs. Implement embedding result caching to avoid redundant computations and reduce API calls.",
            )
            recommendations.append(rec)

        # Check GPU usage
        gpu_cost = by_category.get("gpu_usage", 0)
        if gpu_cost > total * 0.2:
            rec = OptimizationRecommendation(
                id=str(uuid.uuid4()),
                org_id=org_id,
                action=OptimizationAction.RIGHTSIZE,
                current_cost=round(gpu_cost, 4),
                projected_savings=round(gpu_cost * 0.3, 4),
                implementation_cost=round(gpu_cost * 0.1, 4),
                payback_days=int(0.1 / 0.3 * 30),
                risk_level="medium",
                description="High GPU usage costs. Rightsize GPU instances to match workload requirements and consider moving to spot instances for non-critical workloads.",
            )
            recommendations.append(rec)

        # Check storage costs
        storage_cost = by_category.get("storage", 0) + by_category.get("object_storage", 0)
        if storage_cost > total * 0.15:
            rec = OptimizationRecommendation(
                id=str(uuid.uuid4()),
                org_id=org_id,
                action=OptimizationAction.SCALE_DOWN,
                current_cost=round(storage_cost, 4),
                projected_savings=round(storage_cost * 0.2, 4),
                implementation_cost=round(storage_cost * 0.02, 4),
                payback_days=int(0.02 / 0.2 * 30),
                risk_level="low",
                description="High storage costs detected. Implement lifecycle policies, archive stale data, and use compression to reduce storage footprint.",
            )
            recommendations.append(rec)

        # Check database costs
        db_cost = by_category.get("database_usage", 0) + by_category.get("redis", 0) + by_category.get("neo4j", 0) + by_category.get("qdrant", 0)
        if db_cost > total * 0.2:
            rec = OptimizationRecommendation(
                id=str(uuid.uuid4()),
                org_id=org_id,
                action=OptimizationAction.BATCH_PROCESSING,
                current_cost=round(db_cost, 4),
                projected_savings=round(db_cost * 0.15, 4),
                implementation_cost=round(db_cost * 0.05, 4),
                payback_days=int(0.05 / 0.15 * 30),
                risk_level="medium",
                description="High database infrastructure costs. Consolidate query patterns, implement connection pooling, and batch write operations to reduce load.",
            )
            recommendations.append(rec)

        # Check provider costs for multi-provider optimization
        if len(by_provider) > 1:
            max_provider = max(by_provider, key=by_provider.get)
            max_cost = by_provider[max_provider]
            if max_cost > total * 0.5:
                rec = OptimizationRecommendation(
                    id=str(uuid.uuid4()),
                    org_id=org_id,
                    action=OptimizationAction.CHANGE_PROVIDER,
                    current_cost=round(max_cost, 4),
                    projected_savings=round(max_cost * 0.15, 4),
                    implementation_cost=round(total * 0.02, 4),
                    payback_days=int(0.02 / 0.15 * 30),
                    risk_level="high",
                    description=f"Provider {max_provider} accounts for {round(max_cost/total*100, 1)}% of spend. Evaluate alternative providers or negotiate better rates to reduce dependency.",
                )
                recommendations.append(rec)

        # Check network/bandwidth costs
        network_cost = by_category.get("network", 0) + by_category.get("bandwidth", 0)
        if network_cost > total * 0.1:
            rec = OptimizationRecommendation(
                id=str(uuid.uuid4()),
                org_id=org_id,
                action=OptimizationAction.QUERY_COMPRESSION,
                current_cost=round(network_cost, 4),
                projected_savings=round(network_cost * 0.25, 4),
                implementation_cost=round(network_cost * 0.03, 4),
                payback_days=int(0.03 / 0.25 * 30),
                risk_level="low",
                description="High network bandwidth costs. Implement response compression, reduce payload sizes, and enable caching at the edge.",
            )
            recommendations.append(rec)

        # Save recommendations
        for rec in recommendations:
            self._recommendations[rec.id] = rec
        self._save()
        return recommendations

    def create_chargeback(self, org_id: str, period: BudgetPeriod, methodology: ChargebackStrategy) -> ChargebackAllocation:
        self._telemetry["create_chargeback_calls"] += 1
        now = datetime.now(timezone.utc)
        period_days_map = {
            BudgetPeriod.DAILY: 1,
            BudgetPeriod.WEEKLY: 7,
            BudgetPeriod.MONTHLY: 30,
            BudgetPeriod.QUARTERLY: 91,
            BudgetPeriod.YEARLY: 365,
        }
        period_days = period_days_map.get(period, 30)
        start = now - timedelta(days=period_days)

        org_entries = [e for e in self._cost_entries.values() if e.org_id == org_id and e.timestamp >= start.isoformat()]
        total_cost = sum(e.amount for e in org_entries)

        # Group by workspace
        workspace_totals: dict[str, float] = defaultdict(float)
        for e in org_entries:
            workspace_totals[e.workspace_id] += e.amount

        allocations = []
        if methodology == ChargebackStrategy.DIRECT_ALLOCATION:
            for ws_id, ws_cost in workspace_totals.items():
                allocations.append({
                    "workspace_id": ws_id,
                    "amount": round(ws_cost, 4),
                    "percentage": round(ws_cost / total_cost * 100, 2) if total_cost > 0 else 0,
                    "basis": "direct",
                })
        elif methodology == ChargebackStrategy.PROPORTIONAL:
            # Proportional by number of entries per workspace
            ws_counts: dict[str, int] = defaultdict(int)
            for e in org_entries:
                ws_counts[e.workspace_id] += 1
            total_count = sum(ws_counts.values())
            for ws_id, count in ws_counts.items():
                proportion = count / total_count if total_count > 0 else 0
                allocations.append({
                    "workspace_id": ws_id,
                    "amount": round(total_cost * proportion, 4),
                    "percentage": round(proportion * 100, 2),
                    "basis": "proportional_by_entry_count",
                })
        elif methodology == ChargebackStrategy.FIXED_SPLIT:
            ws_ids = list(set(e.workspace_id for e in org_entries))
            if ws_ids:
                split = total_cost / len(ws_ids)
                for ws_id in ws_ids:
                    allocations.append({
                        "workspace_id": ws_id,
                        "amount": round(split, 4),
                        "percentage": round(100.0 / len(ws_ids), 2),
                        "basis": "fixed_split",
                    })
        elif methodology == ChargebackStrategy.USAGE_BASED:
            for ws_id, ws_cost in workspace_totals.items():
                ws_entries = [e for e in org_entries if e.workspace_id == ws_id]
                # Weight by tokens, cpu, gpu, storage, bandwidth
                total_weight = sum(
                    e.tokens + e.cpu_seconds * 10 + e.gpu_seconds * 50 + e.storage_bytes / (1024**3) + e.bandwidth_bytes / (1024**2)
                    for e in ws_entries
                )
                allocations.append({
                    "workspace_id": ws_id,
                    "amount": round(ws_cost, 4),
                    "percentage": round(ws_cost / total_cost * 100, 2) if total_cost > 0 else 0,
                    "basis": "usage_based",
                    "usage_weight": round(total_weight, 4),
                })

        chargeback = ChargebackAllocation(
            id=str(uuid.uuid4()),
            org_id=org_id,
            workspace_id="all",
            period=period,
            total_cost=round(total_cost, 4),
            allocations=allocations,
            methodology=methodology,
        )
        self._chargebacks[chargeback.id] = chargeback
        self._save()
        return chargeback

    def generate_showback(self, org_id: str, period: BudgetPeriod) -> ShowbackReport:
        self._telemetry["generate_showback_calls"] += 1
        now = datetime.now(timezone.utc)
        period_days_map = {
            BudgetPeriod.DAILY: 1,
            BudgetPeriod.WEEKLY: 7,
            BudgetPeriod.MONTHLY: 30,
            BudgetPeriod.QUARTERLY: 91,
            BudgetPeriod.YEARLY: 365,
        }
        period_days = period_days_map.get(period, 30)
        start = now - timedelta(days=period_days)

        org_entries = [e for e in self._cost_entries.values() if e.org_id == org_id and e.timestamp >= start.isoformat()]
        total_spend = sum(e.amount for e in org_entries)

        by_workspace: dict[str, float] = defaultdict(float)
        by_team: dict[str, float] = defaultdict(float)
        by_service: dict[str, float] = defaultdict(float)

        for e in org_entries:
            by_workspace[e.workspace_id] += e.amount
            by_service[e.category.value] += e.amount
            # Infer team from user_id prefix pattern or metadata
            team = e.metadata.get("team", "unassigned") if e.metadata else "unassigned"
            by_team[team] += e.amount

        # Build trend data (daily cost over the period)
        daily_totals: dict[str, float] = defaultdict(float)
        for e in org_entries:
            day_key = e.timestamp[:10]
            daily_totals[day_key] += e.amount
        trend_data = [{"date": day, "cost": round(cost, 4)} for day, cost in sorted(daily_totals.items())]

        report = ShowbackReport(
            id=str(uuid.uuid4()),
            org_id=org_id,
            period=period,
            total_spend=round(total_spend, 4),
            by_workspace={k: round(v, 4) for k, v in by_workspace.items()},
            by_team={k: round(v, 4) for k, v in by_team.items()},
            by_service={k: round(v, 4) for k, v in by_service.items()},
            trend_data=trend_data,
        )
        self._showbacks[report.id] = report
        self._save()
        return report

    def get_dashboard(self, org_id: str) -> FinOpsDashboard:
        self._telemetry["get_dashboard_calls"] += 1
        # Check if cached dashboard exists and is recent (within last 5 minutes)
        if org_id in self._dashboards:
            cached = self._dashboards[org_id]
            last_updated = datetime.fromisoformat(cached.last_updated)
            if (datetime.now(timezone.utc) - last_updated).total_seconds() < 300:
                return cached

        now = datetime.now(timezone.utc)
        month_start = now - timedelta(days=30)
        org_entries = [e for e in self._cost_entries.values() if e.org_id == org_id and e.timestamp >= month_start.isoformat()]
        total_spend = sum(e.amount for e in org_entries)

        # Budget info
        org_budgets = [b for b in self._budgets.values() if b.org_id == org_id]
        total_limit = sum(b.limit for b in org_budgets)
        total_current = sum(b.current_spend for b in org_budgets)
        budget_remaining = round(max(0, total_limit - total_current), 4)

        # Projected overage
        projected_overage = 0.0
        if total_limit > 0 and total_current > 0:
            daily_rate = total_current / 30
            projected_monthly = daily_rate * 30
            projected_overage = round(max(0, projected_monthly - total_limit), 4)

        # Top categories
        by_category: dict[str, float] = defaultdict(float)
        by_service: dict[str, float] = defaultdict(float)
        for e in org_entries:
            by_category[e.category.value] += e.amount
            by_service[e.model if e.model else e.provider] += e.amount

        sorted_cats = sorted(by_category.items(), key=lambda x: x[1], reverse=True)
        top_categories = [{"category": cat, "cost": round(cost, 4), "percentage": round(cost / total_spend * 100, 2) if total_spend > 0 else 0} for cat, cost in sorted_cats[:5]]

        sorted_services = sorted(by_service.items(), key=lambda x: x[1], reverse=True)
        top_services = [{"service": svc, "cost": round(cost, 4), "percentage": round(cost / total_spend * 100, 2) if total_spend > 0 else 0} for svc, cost in sorted_services[:5]]

        # Savings opportunities from recommendations
        org_recs = [r for r in self._recommendations.values() if r.org_id == org_id]
        savings_opportunities = [
            {
                "recommendation_id": r.id,
                "action": r.action.value,
                "projected_savings": r.projected_savings,
                "risk_level": r.risk_level,
                "description": r.description,
            }
            for r in org_recs[:5]
        ]

        # Trends
        daily_totals: dict[str, float] = defaultdict(float)
        for e in org_entries:
            day_key = e.timestamp[:10]
            daily_totals[day_key] += e.amount
        trends = [{"date": day, "cost": round(cost, 4)} for day, cost in sorted(daily_totals.items())][:90]

        dashboard = FinOpsDashboard(
            id=str(uuid.uuid4()),
            org_id=org_id,
            total_spend=round(total_spend, 4),
            budget_remaining=budget_remaining,
            projected_overage=projected_overage,
            top_categories=top_categories,
            top_services=top_services,
            savings_opportunities=savings_opportunities,
            trends=trends,
        )
        self._dashboards[org_id] = dashboard
        self._save()
        return dashboard

    def get_cost_trends(self, org_id: str, days: int = 90) -> list[dict]:
        self._telemetry["get_cost_trends_calls"] += 1
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=days)
        org_entries = [e for e in self._cost_entries.values() if e.org_id == org_id and e.timestamp >= start.isoformat()]

        daily_totals: dict[str, float] = defaultdict(float)
        for e in org_entries:
            day_key = e.timestamp[:10]
            daily_totals[day_key] += e.amount

        trends = []
        for i in range(days):
            day = (now - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
            cost = daily_totals.get(day, 0.0)
            trends.append({"date": day, "cost": round(cost, 4)})
        return trends

    def get_top_spenders(self, org_id: str, limit: int = 10) -> list[dict]:
        self._telemetry["get_top_spenders_calls"] += 1
        org_entries = [e for e in self._cost_entries.values() if e.org_id == org_id]

        # Per user
        user_totals: dict[str, float] = defaultdict(float)
        workspace_totals: dict[str, float] = defaultdict(float)
        for e in org_entries:
            user_totals[e.user_id] += e.amount
            workspace_totals[e.workspace_id] += e.amount

        top_users = sorted(user_totals.items(), key=lambda x: x[1], reverse=True)[:limit]
        top_workspaces = sorted(workspace_totals.items(), key=lambda x: x[1], reverse=True)[:limit]

        return {
            "top_users": [{"user_id": uid, "cost": round(cost, 4)} for uid, cost in top_users],
            "top_workspaces": [{"workspace_id": wid, "cost": round(cost, 4)} for wid, cost in top_workspaces],
        }

    def calculate_roi(self, org_id: str, investment_amount: float, savings_amount: float, period_days: int) -> dict:
        self._telemetry["calculate_roi_calls"] += 1
        if investment_amount <= 0:
            return {"error": "Investment amount must be positive"}

        net_savings = savings_amount - investment_amount
        roi_percentage = round((net_savings / investment_amount) * 100, 2) if investment_amount > 0 else 0.0
        payback_period_days = int(investment_amount / (savings_amount / period_days)) if savings_amount > 0 and period_days > 0 else 0
        annualized_roi = round(roi_percentage * (365 / period_days), 2) if period_days > 0 else 0.0

        return {
            "org_id": org_id,
            "investment_amount": round(investment_amount, 4),
            "savings_amount": round(savings_amount, 4),
            "period_days": period_days,
            "net_savings": round(net_savings, 4),
            "roi_percentage": roi_percentage,
            "payback_period_days": payback_period_days,
            "annualized_roi": annualized_roi,
            "positive_roi": roi_percentage > 0,
        }

    def get_telemetry(self) -> dict:
        self._telemetry["get_telemetry_calls"] += 1
        return dict(self._telemetry)
