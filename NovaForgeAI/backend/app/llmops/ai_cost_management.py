import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
import json, uuid, hashlib, time, math
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)


class CostCategory(Enum):
    PROMPT_TOKENS = "prompt_tokens"
    COMPLETION_TOKENS = "completion_tokens"
    EMBEDDING_TOKENS = "embedding_tokens"
    SEARCH_REQUESTS = "search_requests"
    AGENT_RUNTIME = "agent_runtime"
    API_CALLS = "api_calls"
    STREAMING = "streaming"
    BATCH_PROCESSING = "batch_processing"
    FINE_TUNING = "fine_tuning"
    STORAGE = "storage"


class BudgetPeriod(Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class AlertLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EXCEEDED = "exceeded"


@dataclass
class CostEntry:
    id: str = ""
    org_id: str = ""
    workspace_id: Optional[str] = None
    project_id: Optional[str] = None
    category: CostCategory = CostCategory.API_CALLS
    provider: str = ""
    model: str = ""
    tokens: int = 0
    amount: float = 0.0
    currency: str = "USD"
    timestamp: str = ""
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["category"] = self.category.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "CostEntry":
        data = data.copy()
        data["category"] = CostCategory(data.get("category", "api_calls"))
        return CostEntry(**data)


@dataclass
class CostSummary:
    id: str = ""
    org_id: str = ""
    period_start: str = ""
    period_end: str = ""
    total_cost: float = 0.0
    by_category: dict = field(default_factory=dict)
    by_provider: dict = field(default_factory=dict)
    by_model: dict = field(default_factory=dict)
    by_workspace: dict = field(default_factory=dict)
    daily_costs: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "CostSummary":
        return CostSummary(**data)


@dataclass
class Budget:
    id: str = ""
    org_id: str = ""
    name: str = ""
    period: BudgetPeriod = BudgetPeriod.MONTHLY
    limit: float = 0.0
    spent: float = 0.0
    remaining: float = 0.0
    alerts: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now
        self.remaining = max(0.0, self.limit - self.spent)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["period"] = self.period.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "Budget":
        data = data.copy()
        data["period"] = BudgetPeriod(data.get("period", "monthly"))
        return Budget(**data)


@dataclass
class CostForecast:
    id: str = ""
    org_id: str = ""
    forecast_date: str = ""
    predicted_cost: float = 0.0
    lower_bound: float = 0.0
    upper_bound: float = 0.0
    confidence: float = 0.0
    based_on_days: int = 0

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.forecast_date:
            self.forecast_date = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "CostForecast":
        return CostForecast(**data)


@dataclass
class CostAlert:
    id: str = ""
    budget_id: str = ""
    level: AlertLevel = AlertLevel.INFO
    message: str = ""
    threshold: float = 0.0
    current: float = 0.0
    created_at: str = ""
    acknowledged: bool = False

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["level"] = self.level.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "CostAlert":
        data = data.copy()
        data["level"] = AlertLevel(data.get("level", "info"))
        return CostAlert(**data)


class CostTracker:
    def __init__(self, storage_dir: str):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._entries_file = self.storage_dir / "cost_entries.json"
        self._entries: list[CostEntry] = []
        self._telemetry = defaultdict(int)
        self._load()

    def _save(self):
        try:
            data = [e.to_dict() for e in self._entries]
            self._entries_file.write_text(json.dumps(data, indent=2, default=str))
        except Exception as e:
            logger.error("Failed to save cost entries: %s", e, exc_info=True)
            raise

    def _load(self):
        try:
            if self._entries_file.exists():
                data = json.loads(self._entries_file.read_text())
                self._entries = [CostEntry.from_dict(e) for e in data]
        except Exception as e:
            logger.error("Failed to load cost entries: %s", e, exc_info=True)

    def track_cost(self, entry: CostEntry) -> CostEntry:
        self._telemetry["costs_tracked"] += 1
        self._entries.append(entry)
        self._save()
        logger.debug("Tracked cost: %s %.4f %s", entry.category.value, entry.amount, entry.currency)
        return entry

    def get_costs(self, org_id: Optional[str] = None, limit: int = 100) -> list[CostEntry]:
        self._telemetry["get_costs_calls"] += 1
        if org_id:
            return [e for e in self._entries if e.org_id == org_id][-limit:]
        return self._entries[-limit:]

    def get_cost_summary(self, org_id: str, start: Optional[str] = None, end: Optional[str] = None) -> CostSummary:
        self._telemetry["get_cost_summary_calls"] += 1
        entries = [e for e in self._entries if e.org_id == org_id]
        if start:
            entries = [e for e in entries if e.timestamp >= start]
        if end:
            entries = [e for e in entries if e.timestamp <= end]

        if not entries:
            return CostSummary(org_id=org_id, period_start=start or "", period_end=end or "")

        total = sum(e.amount for e in entries)
        by_category = defaultdict(float)
        by_provider = defaultdict(float)
        by_model = defaultdict(float)
        by_workspace = defaultdict(float)
        daily = defaultdict(float)

        for e in entries:
            by_category[e.category.value] += e.amount
            by_provider[e.provider] += e.amount
            by_model[e.model] += e.amount
            if e.workspace_id:
                by_workspace[e.workspace_id] += e.amount
            day = e.timestamp[:10]
            daily[day] += e.amount

        return CostSummary(
            org_id=org_id,
            period_start=start or entries[0].timestamp,
            period_end=end or entries[-1].timestamp,
            total_cost=round(total, 6),
            by_category=dict(by_category),
            by_provider=dict(by_provider),
            by_model=dict(by_model),
            by_workspace=dict(by_workspace),
            daily_costs=dict(daily),
        )

    def get_costs_by_range(self, org_id: str, start: str, end: str) -> list[CostEntry]:
        self._telemetry["get_costs_by_range_calls"] += 1
        return [e for e in self._entries if e.org_id == org_id and start <= e.timestamp <= end]

    def get_costs_by_category(self, org_id: str, category: CostCategory) -> list[CostEntry]:
        self._telemetry["get_costs_by_category_calls"] += 1
        return [e for e in self._entries if e.org_id == org_id and e.category == category]

    def get_costs_by_provider(self, org_id: str, provider: str) -> list[CostEntry]:
        self._telemetry["get_costs_by_provider_calls"] += 1
        return [e for e in self._entries if e.org_id == org_id and e.provider == provider]

    def get_costs_by_model(self, org_id: str, model: str) -> list[CostEntry]:
        self._telemetry["get_costs_by_model_calls"] += 1
        return [e for e in self._entries if e.org_id == org_id and e.model == model]

    def get_daily_costs(self, org_id: str, days: int = 30) -> dict[str, float]:
        self._telemetry["get_daily_costs_calls"] += 1
        daily = defaultdict(float)
        for e in self._entries:
            if e.org_id == org_id:
                day = e.timestamp[:10]
                daily[day] += e.amount
        sorted_days = sorted(daily.keys(), reverse=True)[:days]
        return {d: round(daily[d], 6) for d in sorted_days}

    def get_org_costs(self, org_id: str) -> float:
        self._telemetry["get_org_costs_calls"] += 1
        return round(sum(e.amount for e in self._entries if e.org_id == org_id), 6)

    def get_workspace_costs(self, org_id: str, workspace_id: str) -> float:
        self._telemetry["get_workspace_costs_calls"] += 1
        return round(sum(e.amount for e in self._entries if e.org_id == org_id and e.workspace_id == workspace_id), 6)


class BudgetManager:
    def __init__(self, storage_dir: str):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._budgets_file = self.storage_dir / "budgets.json"
        self._alerts_file = self.storage_dir / "cost_alerts.json"
        self._budgets: dict[str, Budget] = {}
        self._alerts: list[CostAlert] = []
        self._telemetry = defaultdict(int)
        self._load()

    def _save(self):
        try:
            budgets_data = {bid: b.to_dict() for bid, b in self._budgets.items()}
            self._budgets_file.write_text(json.dumps(budgets_data, indent=2, default=str))
            alerts_data = [a.to_dict() for a in self._alerts]
            self._alerts_file.write_text(json.dumps(alerts_data, indent=2, default=str))
        except Exception as e:
            logger.error("Failed to save budget data: %s", e, exc_info=True)
            raise

    def _load(self):
        try:
            if self._budgets_file.exists():
                data = json.loads(self._budgets_file.read_text())
                for bid, bdata in data.items():
                    try:
                        self._budgets[bid] = Budget.from_dict(bdata)
                    except Exception as e:
                        logger.warning("Skipping malformed budget %s: %s", bid, e)
            if self._alerts_file.exists():
                data = json.loads(self._alerts_file.read_text())
                self._alerts = [CostAlert.from_dict(a) for a in data]
        except Exception as e:
            logger.error("Failed to load budget data: %s", e, exc_info=True)

    def create_budget(self, budget: Budget) -> Budget:
        self._telemetry["budgets_created"] += 1
        if budget.id in self._budgets:
            raise ValueError(f"Budget {budget.id} already exists")
        self._budgets[budget.id] = budget
        self._save()
        logger.info("Created budget %s: %s (%.2f %s)", budget.id, budget.name, budget.limit, budget.period.value)
        return budget

    def get_budget(self, budget_id: str) -> Optional[Budget]:
        self._telemetry["get_budget_calls"] += 1
        return self._budgets.get(budget_id)

    def update_budget(self, budget_id: str, **updates) -> Optional[Budget]:
        self._telemetry["update_budget_calls"] += 1
        budget = self._budgets.get(budget_id)
        if not budget:
            logger.warning("Budget %s not found for update", budget_id)
            return None
        for key, val in updates.items():
            if hasattr(budget, key) and key not in ("id", "created_at"):
                if key == "period":
                    val = BudgetPeriod(val) if isinstance(val, str) else val
                setattr(budget, key, val)
        budget.updated_at = datetime.now(timezone.utc).isoformat()
        budget.remaining = max(0.0, budget.limit - budget.spent)
        self._save()
        logger.info("Updated budget %s", budget_id)
        return budget

    def check_budget(self, budget_id: str, current_spent: float) -> list[CostAlert]:
        self._telemetry["check_budget_calls"] += 1
        budget = self._budgets.get(budget_id)
        if not budget:
            logger.warning("Budget %s not found for check", budget_id)
            return []
        budget.spent = current_spent
        budget.remaining = max(0.0, budget.limit - budget.spent)
        budget.updated_at = datetime.now(timezone.utc).isoformat()
        alerts = []
        usage_pct = (current_spent / budget.limit * 100.0) if budget.limit > 0 else 0.0

        thresholds = [
            (50.0, AlertLevel.INFO, "Budget {name} is at {pct:.1f}% usage"),
            (75.0, AlertLevel.WARNING, "Budget {name} is at {pct:.1f}% usage"),
            (90.0, AlertLevel.WARNING, "Budget {name} is at {pct:.1f}% usage — approaching limit"),
            (100.0, AlertLevel.CRITICAL, "Budget {name} has reached {pct:.1f}% usage"),
        ]
        for pct, level, msg_template in thresholds:
            if usage_pct >= pct:
                alert = self.generate_alert(
                    budget_id=budget_id,
                    level=level,
                    message=msg_template.format(name=budget.name, pct=usage_pct),
                    threshold=pct,
                    current=usage_pct,
                )
                alerts.append(alert)

        if usage_pct > 100.0:
            exceeded = self.generate_alert(
                budget_id=budget_id,
                level=AlertLevel.EXCEEDED,
                message=f"Budget {budget.name} exceeded! Usage: {usage_pct:.1f}%",
                threshold=100.0,
                current=usage_pct,
            )
            alerts.append(exceeded)

        self._save()
        return alerts

    def get_budget_usage(self, budget_id: str) -> dict:
        self._telemetry["get_budget_usage_calls"] += 1
        budget = self._budgets.get(budget_id)
        if not budget:
            return {}
        usage_pct = (budget.spent / budget.limit * 100.0) if budget.limit > 0 else 0.0
        return {
            "budget_id": budget.id,
            "name": budget.name,
            "limit": budget.limit,
            "spent": budget.spent,
            "remaining": budget.remaining,
            "usage_pct": round(usage_pct, 2),
            "period": budget.period.value,
        }

    def list_budgets(self, org_id: Optional[str] = None) -> list[Budget]:
        self._telemetry["list_budgets_calls"] += 1
        if org_id:
            return [b for b in self._budgets.values() if b.org_id == org_id]
        return list(self._budgets.values())

    def generate_alert(self, budget_id: str, level: AlertLevel, message: str, threshold: float, current: float) -> CostAlert:
        self._telemetry["alerts_generated"] += 1
        alert = CostAlert(
            budget_id=budget_id,
            level=level,
            message=message,
            threshold=threshold,
            current=current,
        )
        self._alerts.append(alert)
        budget = self._budgets.get(budget_id)
        if budget:
            budget.alerts.append(alert.id)
        self._save()
        logger.warning("Cost alert [%s] for budget %s: %s", level.value, budget_id, message)
        return alert

    def acknowledge_alert(self, alert_id: str) -> bool:
        for alert in self._alerts:
            if alert.id == alert_id:
                alert.acknowledged = True
                self._save()
                return True
        return False

    def get_alerts(self, budget_id: Optional[str] = None, acknowledged: Optional[bool] = None) -> list[CostAlert]:
        results = list(self._alerts)
        if budget_id:
            results = [a for a in results if a.budget_id == budget_id]
        if acknowledged is not None:
            results = [a for a in results if a.acknowledged == acknowledged]
        return results


class CostForecaster:
    def __init__(self, storage_dir: str):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._forecasts_file = self.storage_dir / "cost_forecasts.json"
        self._forecasts: dict[str, CostForecast] = {}
        self._telemetry = defaultdict(int)
        self._cost_tracker: Optional[CostTracker] = None
        self._load()

    def set_cost_tracker(self, tracker: CostTracker):
        self._cost_tracker = tracker

    def _save(self):
        try:
            data = {fid: f.to_dict() for fid, f in self._forecasts.items()}
            self._forecasts_file.write_text(json.dumps(data, indent=2, default=str))
        except Exception as e:
            logger.error("Failed to save forecasts: %s", e, exc_info=True)
            raise

    def _load(self):
        try:
            if self._forecasts_file.exists():
                data = json.loads(self._forecasts_file.read_text())
                for fid, fdata in data.items():
                    try:
                        self._forecasts[fid] = CostForecast.from_dict(fdata)
                    except Exception as e:
                        logger.warning("Skipping malformed forecast %s: %s", fid, e)
        except Exception as e:
            logger.error("Failed to load forecasts: %s", e, exc_info=True)

    def forecast(self, org_id: str, days: int = 30, based_on_days: int = 90) -> CostForecast:
        self._telemetry["forecasts_created"] += 1
        if not self._cost_tracker:
            raise RuntimeError("CostForecaster requires a CostTracker to be set via set_cost_tracker()")

        entries = self._cost_tracker.get_costs(org_id=org_id, limit=100000)
        if not entries:
            forecast = CostForecast(
                org_id=org_id,
                predicted_cost=0.0,
                lower_bound=0.0,
                upper_bound=0.0,
                confidence=0.0,
                based_on_days=0,
            )
            self._forecasts[forecast.id] = forecast
            self._save()
            return forecast

        sorted_entries = sorted(entries, key=lambda e: e.timestamp)
        recent = sorted_entries[-min(len(sorted_entries), based_on_days):]

        daily_costs = defaultdict(float)
        for e in recent:
            day = e.timestamp[:10]
            daily_costs[day] += e.amount

        if len(daily_costs) < 2:
            forecast = CostForecast(
                org_id=org_id,
                predicted_cost=0.0,
                lower_bound=0.0,
                upper_bound=0.0,
                confidence=0.0,
                based_on_days=len(daily_costs),
            )
            self._forecasts[forecast.id] = forecast
            self._save()
            return forecast

        values = list(daily_costs.values())
        n = len(values)
        avg_daily = sum(values) / n
        variance = sum((v - avg_daily) ** 2 for v in values) / n if n > 1 else 0
        std_dev = math.sqrt(variance)

        predicted = avg_daily * days
        margin = 1.96 * std_dev * math.sqrt(days)  # 95% confidence interval
        confidence = max(0.0, min(100.0, 100.0 - (std_dev / avg_daily * 100.0) if avg_daily > 0 else 0.0))

        forecast = CostForecast(
            org_id=org_id,
            forecast_date=datetime.now(timezone.utc).isoformat(),
            predicted_cost=round(predicted, 6),
            lower_bound=round(max(0.0, predicted - margin), 6),
            upper_bound=round(predicted + margin, 6),
            confidence=round(confidence, 2),
            based_on_days=n,
        )
        self._forecasts[forecast.id] = forecast
        self._save()
        logger.info("Forecasted cost for org %s: %.2f (%.2f-%.2f) over %d days", org_id, predicted, forecast.lower_bound, forecast.upper_bound, days)
        return forecast

    def get_forecast(self, forecast_id: str) -> Optional[CostForecast]:
        self._telemetry["get_forecast_calls"] += 1
        return self._forecasts.get(forecast_id)

    def calculate_trend(self, org_id: str, days: int = 30) -> dict:
        self._telemetry["calculate_trend_calls"] += 1
        if not self._cost_tracker:
            return {"error": "CostTracker not set"}

        entries = self._cost_tracker.get_costs(org_id=org_id, limit=100000)
        if not entries:
            return {"trend": "insufficient_data", "slope": 0.0, "avg_daily": 0.0}

        sorted_entries = sorted(entries, key=lambda e: e.timestamp)
        recent = sorted_entries[-min(len(sorted_entries), days):]

        daily_costs = defaultdict(float)
        for e in recent:
            day = e.timestamp[:10]
            daily_costs[day] += e.amount

        sorted_days = sorted(daily_costs.keys())
        if len(sorted_days) < 2:
            return {"trend": "insufficient_data", "slope": 0.0, "avg_daily": sum(daily_costs.values()) / max(len(daily_costs), 1)}

        x_vals = list(range(len(sorted_days)))
        y_vals = [daily_costs[d] for d in sorted_days]
        n = len(x_vals)
        sum_x = sum(x_vals)
        sum_y = sum(y_vals)
        sum_xy = sum(x * y for x, y in zip(x_vals, y_vals))
        sum_xx = sum(x * x for x in x_vals)
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_xx - sum_x * sum_x) if (n * sum_xx - sum_x * sum_x) != 0 else 0.0
        avg_daily = sum_y / n

        trend = "stable"
        if slope > avg_daily * 0.05:
            trend = "increasing"
        elif slope < -avg_daily * 0.05:
            trend = "decreasing"

        return {
            "trend": trend,
            "slope": round(slope, 6),
            "avg_daily": round(avg_daily, 6),
            "days_analyzed": n,
        }

    def predict_next_month(self, org_id: str) -> CostForecast:
        self._telemetry["predict_next_month_calls"] += 1
        return self.forecast(org_id, days=30, based_on_days=90)

    def get_forecast_accuracy(self, forecast_id: str) -> dict:
        self._telemetry["get_forecast_accuracy_calls"] += 1
        forecast = self._forecasts.get(forecast_id)
        if not forecast:
            return {"error": "Forecast not found"}
        if not self._cost_tracker:
            return {"error": "CostTracker not set"}

        entries = self._cost_tracker.get_costs(org_id=forecast.org_id, limit=100000)
        actuals = [e for e in entries if e.timestamp >= forecast.forecast_date]
        actual_total = sum(e.amount for e in actuals)

        if actual_total == 0:
            return {"forecast_id": forecast_id, "accuracy": 0.0, "actual": 0.0, "predicted": forecast.predicted_cost}

        error_pct = abs(actual_total - forecast.predicted_cost) / actual_total * 100.0
        accuracy = max(0.0, 100.0 - error_pct)
        return {
            "forecast_id": forecast_id,
            "accuracy": round(accuracy, 2),
            "actual": round(actual_total, 6),
            "predicted": forecast.predicted_cost,
            "lower_bound": forecast.lower_bound,
            "upper_bound": forecast.upper_bound,
            "within_bounds": forecast.lower_bound <= actual_total <= forecast.upper_bound,
        }


class CostManager(CostTracker, BudgetManager, CostForecaster):
    def __init__(self, storage_dir: str):
        CostTracker.__init__(self, storage_dir)
        BudgetManager.__init__(self, storage_dir)
        CostForecaster.__init__(self, storage_dir)
        self.set_cost_tracker(self)
        logger.info("CostManager initialized at %s", storage_dir)

    def generate_report(self, org_id: str, start: Optional[str] = None, end: Optional[str] = None) -> dict:
        self._telemetry["generate_report_calls"] += 1
        summary = self.get_cost_summary(org_id, start, end)
        budgets = self.list_budgets(org_id)
        trend = self.calculate_trend(org_id)
        alerts = self.get_alerts()
        budget_alerts = [a for a in alerts if not a.acknowledged]

        budget_data = []
        for b in budgets:
            budget_data.append(self.get_budget_usage(b.id))

        return {
            "org_id": org_id,
            "report_generated": datetime.now(timezone.utc).isoformat(),
            "summary": summary.to_dict(),
            "budgets": budget_data,
            "trend": trend,
            "unacknowledged_alerts": len(budget_alerts),
            "telemetry": dict(self._telemetry),
        }

    def get_cost_health(self, org_id: str) -> dict:
        self._telemetry["get_cost_health_calls"] += 1
        budgets = self.list_budgets(org_id)
        total_limit = sum(b.limit for b in budgets)
        total_spent = sum(b.spent for b in budgets)
        alerts = self.get_alerts()
        unacknowledged = [a for a in alerts if not a.acknowledged]

        health_score = 100.0
        if total_limit > 0:
            usage_pct = total_spent / total_limit * 100.0
            if usage_pct > 90:
                health_score = 25.0
            elif usage_pct > 75:
                health_score = 50.0
            elif usage_pct > 50:
                health_score = 75.0

        if len(unacknowledged) > 0:
            health_score = max(0.0, health_score - len(unacknowledged) * 10.0)

        return {
            "org_id": org_id,
            "health_score": round(health_score, 2),
            "total_budgets": len(budgets),
            "total_limit": total_limit,
            "total_spent": round(total_spent, 6),
            "unacknowledged_alerts": len(unacknowledged),
            "status": "healthy" if health_score >= 75 else "warning" if health_score >= 50 else "critical",
        }

    def optimize_costs(self, org_id: str) -> dict:
        self._telemetry["optimize_costs_calls"] += 1
        entries = self.get_costs(org_id=org_id, limit=10000)
        if not entries:
            return {"org_id": org_id, "recommendations": [], "potential_savings": 0.0}

        by_provider = defaultdict(lambda: {"cost": 0.0, "count": 0, "models": set()})
        by_model = defaultdict(lambda: {"cost": 0.0, "count": 0, "provider": ""})
        total_cost = 0.0

        for e in entries:
            by_provider[e.provider]["cost"] += e.amount
            by_provider[e.provider]["count"] += 1
            by_provider[e.provider]["models"].add(e.model)
            by_model[e.model]["cost"] += e.amount
            by_model[e.model]["count"] += 1
            by_model[e.model]["provider"] = e.provider
            total_cost += e.amount

        recommendations = []

        avg_cost = total_cost / len(entries) if entries else 0
        for provider, data in by_provider.items():
            if data["cost"] > total_cost * 0.5 and data["count"] > 100:
                recommendations.append({
                    "type": "provider_concentration",
                    "provider": provider,
                    "message": f"Provider {provider} accounts for {data['cost']/total_cost*100:.1f}% of cost. Consider distributing load.",
                    "potential_savings": round(data["cost"] * 0.1, 6),
                })

        expensive_models = sorted(by_model.items(), key=lambda x: x[1]["cost"], reverse=True)
        for model, data in expensive_models[:5]:
            per_request = data["cost"] / data["count"] if data["count"] > 0 else 0
            if per_request > avg_cost * 2:
                recommendations.append({
                    "type": "expensive_model",
                    "model": model,
                    "provider": data["provider"],
                    "message": f"Model {model} costs {per_request:.4f}/req (avg: {avg_cost:.4f}). Consider cheaper alternative.",
                    "potential_savings": round((per_request - avg_cost) * data["count"] * 0.5, 6),
                })

        total_savings = sum(r["potential_savings"] for r in recommendations)

        return {
            "org_id": org_id,
            "recommendations": recommendations,
            "potential_savings": round(total_savings, 6),
            "total_cost_analyzed": round(total_cost, 6),
            "total_entries_analyzed": len(entries),
        }
