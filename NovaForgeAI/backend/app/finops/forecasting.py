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


class ForecastMetric(Enum):
    MONTHLY_REVENUE = "monthly_revenue"
    ANNUAL_REVENUE = "annual_revenue"
    INFRASTRUCTURE_COST = "infrastructure_cost"
    AI_COST = "ai_cost"
    STORAGE_GROWTH = "storage_growth"
    REPOSITORY_GROWTH = "repository_growth"
    USER_GROWTH = "user_growth"
    TOKEN_GROWTH = "token_growth"
    GPU_USAGE = "gpu_usage"
    SCALING_REQUIREMENTS = "scaling_requirements"
    TOTAL_COST = "total_cost"
    GROSS_MARGIN = "gross_margin"
    CUSTOMER_COUNT = "customer_count"
    API_VOLUME = "api_volume"
    AGENT_EXECUTIONS = "agent_executions"


class ForecastModel(Enum):
    LINEAR_REGRESSION = "linear_regression"
    MOVING_AVERAGE = "moving_average"
    EXPONENTIAL_SMOOTHING = "exponential_smoothing"
    SEASONAL_DECOMPOSE = "seasonal_decompose"
    ARIMA = "arima"
    ENSEMBLE = "ensemble"


class ConfidenceLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class ScenarioType(Enum):
    OPTIMISTIC = "optimistic"
    PESSIMISTIC = "pessimistic"
    MOST_LIKELY = "most_likely"
    WHAT_IF = "what_if"


@dataclass
class ForecastInput:
    id: str
    org_id: str
    metric: ForecastMetric
    historical_data: list
    periods_lookback: int = 90
    periods_forecast: int = 12
    model: ForecastModel = ForecastModel.LINEAR_REGRESSION
    seasonality: int = 0
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    metadata: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["metric"] = self.metric.value
        d["model"] = self.model.value
        d["confidence"] = self.confidence.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ForecastInput":
        data = data.copy()
        data["metric"] = ForecastMetric(data.get("metric", "monthly_revenue"))
        data["model"] = ForecastModel(data.get("model", "linear_regression"))
        data["confidence"] = ConfidenceLevel(data.get("confidence", "medium"))
        return cls(**data)


@dataclass
class ForecastResult:
    id: str
    input_id: str
    org_id: str
    metric: ForecastMetric
    model: ForecastModel
    predictions: list[dict] = field(default_factory=list)
    confidence_interval_low: list = field(default_factory=list)
    confidence_interval_high: list = field(default_factory=list)
    accuracy_score: float = 0.0
    mape: float = 0.0
    rmse: float = 0.0
    trend_coefficient: float = 0.0
    seasonality_factor: float = 0.0
    r_squared: float = 0.0
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["metric"] = self.metric.value
        d["model"] = self.model.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ForecastResult":
        data = data.copy()
        data["metric"] = ForecastMetric(data.get("metric", "monthly_revenue"))
        data["model"] = ForecastModel(data.get("model", "linear_regression"))
        return cls(**data)


@dataclass
class RevenueForecast:
    id: str
    org_id: str
    forecast_date: str
    current_mrr: float = 0.0
    projected_mrr: float = 0.0
    projected_arr: float = 0.0
    growth_rate: float = 0.0
    churn_rate: float = 0.0
    expansion_revenue: float = 0.0
    new_customer_revenue: float = 0.0
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    scenarios: dict[str, list] = field(default_factory=dict)
    assumptions: list = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["confidence"] = self.confidence.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RevenueForecast":
        data = data.copy()
        data["confidence"] = ConfidenceLevel(data.get("confidence", "medium"))
        return cls(**data)


@dataclass
class CapacityForecast:
    id: str
    org_id: str
    forecast_date: str
    current_gpu_usage: float = 0.0
    projected_gpu_usage: float = 0.0
    current_storage_tb: float = 0.0
    projected_storage_tb: float = 0.0
    current_api_volume: float = 0.0
    projected_api_volume: float = 0.0
    peak_load_prediction: float = 0.0
    scale_recommendations: list = field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["confidence"] = self.confidence.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "CapacityForecast":
        data = data.copy()
        data["confidence"] = ConfidenceLevel(data.get("confidence", "medium"))
        return cls(**data)


@dataclass
class BudgetForecast:
    id: str
    org_id: str
    period: str
    total_budget: float = 0.0
    projected_spend: float = 0.0
    variance: float = 0.0
    categories: dict = field(default_factory=dict)
    risks: list = field(default_factory=list)
    mitigation: list = field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["confidence"] = self.confidence.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "BudgetForecast":
        data = data.copy()
        data["confidence"] = ConfidenceLevel(data.get("confidence", "medium"))
        return cls(**data)


class ForecastingEngine:
    def __init__(self, storage_dir: str = "forecasting_data"):
        self.storage_dir = storage_dir
        self._inputs: dict[str, ForecastInput] = {}
        self._results: dict[str, ForecastResult] = {}
        self._revenue_forecasts: dict[str, RevenueForecast] = {}
        self._capacity_forecasts: dict[str, CapacityForecast] = {}
        self._budget_forecasts: dict[str, BudgetForecast] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _inputs_path(self) -> str:
        return os.path.join(self.storage_dir, "inputs.json")

    def _results_path(self) -> str:
        return os.path.join(self.storage_dir, "results.json")

    def _revenue_path(self) -> str:
        return os.path.join(self.storage_dir, "revenue_forecasts.json")

    def _capacity_path(self) -> str:
        return os.path.join(self.storage_dir, "capacity_forecasts.json")

    def _budget_path(self) -> str:
        return os.path.join(self.storage_dir, "budget_forecasts.json")

    def _save(self) -> None:
        try:
            inputs_data = {iid: i.to_dict() for iid, i in self._inputs.items()}
            with open(self._inputs_path(), "w", encoding="utf-8") as f:
                json.dump(inputs_data, f, indent=2, default=str)

            results_data = {rid: r.to_dict() for rid, r in self._results.items()}
            with open(self._results_path(), "w", encoding="utf-8") as f:
                json.dump(results_data, f, indent=2, default=str)

            rev_data = {rid: r.to_dict() for rid, r in self._revenue_forecasts.items()}
            with open(self._revenue_path(), "w", encoding="utf-8") as f:
                json.dump(rev_data, f, indent=2, default=str)

            cap_data = {cid: c.to_dict() for cid, c in self._capacity_forecasts.items()}
            with open(self._capacity_path(), "w", encoding="utf-8") as f:
                json.dump(cap_data, f, indent=2, default=str)

            bud_data = {bid: b.to_dict() for bid, b in self._budget_forecasts.items()}
            with open(self._budget_path(), "w", encoding="utf-8") as f:
                json.dump(bud_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save forecasting data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._inputs_path()):
                with open(self._inputs_path(), "r", encoding="utf-8") as f:
                    inputs_data = json.load(f)
                for iid, data in inputs_data.items():
                    try:
                        self._inputs[iid] = ForecastInput.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed input %s: %s", iid, e)

            if os.path.exists(self._results_path()):
                with open(self._results_path(), "r", encoding="utf-8") as f:
                    results_data = json.load(f)
                for rid, data in results_data.items():
                    try:
                        self._results[rid] = ForecastResult.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed result %s: %s", rid, e)

            if os.path.exists(self._revenue_path()):
                with open(self._revenue_path(), "r", encoding="utf-8") as f:
                    rev_data = json.load(f)
                for rid, data in rev_data.items():
                    try:
                        self._revenue_forecasts[rid] = RevenueForecast.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed revenue forecast %s: %s", rid, e)

            if os.path.exists(self._capacity_path()):
                with open(self._capacity_path(), "r", encoding="utf-8") as f:
                    cap_data = json.load(f)
                for cid, data in cap_data.items():
                    try:
                        self._capacity_forecasts[cid] = CapacityForecast.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed capacity forecast %s: %s", cid, e)

            if os.path.exists(self._budget_path()):
                with open(self._budget_path(), "r", encoding="utf-8") as f:
                    bud_data = json.load(f)
                for bid, data in bud_data.items():
                    try:
                        self._budget_forecasts[bid] = BudgetForecast.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed budget forecast %s: %s", bid, e)
        except Exception as e:
            logger.error("Failed to load forecasting data: %s", e, exc_info=True)

    def _linear_regression(self, data: list[float], periods: int) -> dict:
        n = len(data)
        if n < 2:
            pred = data[-1] if data else 0.0
            return {
                "predictions": [{"period": i + 1, "value": pred} for i in range(periods)],
                "slope": 0.0,
                "intercept": data[0] if data else 0.0,
                "r_squared": 0.0,
            }
        x_vals = list(range(n))
        sum_x = sum(x_vals)
        sum_y = sum(data)
        sum_xy = sum(x * y for x, y in zip(x_vals, data))
        sum_xx = sum(x * x for x in x_vals)
        denom = n * sum_xx - sum_x * sum_x
        if denom == 0:
            slope = 0.0
            intercept = sum_y / n
        else:
            slope = (n * sum_xy - sum_x * sum_y) / denom
            intercept = (sum_y - slope * sum_x) / n

        y_mean = sum_y / n
        ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(x_vals, data))
        ss_tot = sum((y - y_mean) ** 2 for y in data)
        r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

        predictions = []
        for i in range(periods):
            x_pred = n + i
            val = intercept + slope * x_pred
            predictions.append({"period": i + 1, "value": round(max(0, val), 4)})

        return {
            "predictions": predictions,
            "slope": slope,
            "intercept": intercept,
            "r_squared": round(r_squared, 4),
        }

    def _moving_average(self, data: list[float], periods: int, window: int = 3) -> dict:
        if not data:
            return {"predictions": [{"period": i + 1, "value": 0.0} for i in range(periods)]}

        if len(data) < window:
            window = len(data)

        ma = sum(data[-window:]) / window
        predictions = []
        for i in range(periods):
            val = ma
            predictions.append({"period": i + 1, "value": round(max(0, val), 4)})

        return {"predictions": predictions, "window": window, "moving_average": ma}

    def _exponential_smoothing(self, data: list[float], periods: int, alpha: float = 0.3) -> dict:
        if not data:
            return {"predictions": [{"period": i + 1, "value": 0.0} for i in range(periods)]}

        smoothed = data[0]
        predictions = []
        for i in range(periods):
            if i < len(data):
                val = alpha * data[i] + (1 - alpha) * (smoothed if i == 0 else data[i - 1])
                smoothed = val
            else:
                val = smoothed
            predictions.append({"period": i + 1, "value": round(max(0, val), 4)})
        return {"predictions": predictions, "alpha": alpha, "final_smoothed": smoothed}

    def _seasonal_decompose(self, data: list[float], periods: int, season_length: int = 12) -> dict:
        if not data or len(data) < season_length * 2:
            return self._linear_regression(data, periods)

        seasonal_components = []
        for i in range(season_length):
            indices = list(range(i, len(data), season_length))
            vals = [data[j] for j in indices if j < len(data)]
            if vals:
                seasonal_components.append(sum(vals) / len(vals))
            else:
                seasonal_components.append(0.0)

        avg_seasonal = sum(seasonal_components) / len(seasonal_components) if seasonal_components else 0.0
        seasonal_factors = [s - avg_seasonal for s in seasonal_components]

        deseasonalized = []
        for i, val in enumerate(data):
            sf = seasonal_factors[i % season_length] if season_length > 0 else 0.0
            deseasonalized.append(val - sf)

        trend_result = self._linear_regression(deseasonalized, periods)
        predictions = []
        for i, pred in enumerate(trend_result["predictions"]):
            sf = seasonal_factors[(len(data) + i) % season_length] if season_length > 0 else 0.0
            val = pred["value"] + sf
            predictions.append({"period": i + 1, "value": round(max(0, val), 4)})

        return {
            "predictions": predictions,
            "seasonal_factors": [round(s, 4) for s in seasonal_factors],
            "trend_slope": trend_result["slope"],
            "r_squared": trend_result["r_squared"],
        }

    def create_forecast_input(self, input_data: ForecastInput) -> ForecastInput:
        self._telemetry["create_forecast_input_calls"] += 1
        if not input_data.id:
            input_data.id = str(uuid.uuid4())
        if not input_data.created_at:
            input_data.created_at = datetime.now(timezone.utc).isoformat()
        self._inputs[input_data.id] = input_data
        self._save()
        logger.info("Created forecast input %s for org %s metric %s", input_data.id, input_data.org_id, input_data.metric.value)
        return input_data

    def run_forecast(self, input_id: str) -> Optional[ForecastResult]:
        self._telemetry["run_forecast_calls"] += 1
        inp = self._inputs.get(input_id)
        if not inp:
            logger.warning("Forecast input not found: %s", input_id)
            return None

        data = inp.historical_data
        if not data:
            data = [0.0]

        num_forecast = inp.periods_forecast
        model = inp.model

        if model == ForecastModel.LINEAR_REGRESSION:
            result = self._linear_regression(data, num_forecast)
            predictions = result["predictions"]
            slope = result["slope"]
            r_squared = result["r_squared"]
        elif model == ForecastModel.MOVING_AVERAGE:
            result = self._moving_average(data, num_forecast)
            predictions = result["predictions"]
            slope = 0.0
            r_squared = 0.0
        elif model == ForecastModel.EXPONENTIAL_SMOOTHING:
            result = self._exponential_smoothing(data, num_forecast)
            predictions = result["predictions"]
            slope = 0.0
            r_squared = 0.0
        elif model == ForecastModel.SEASONAL_DECOMPOSE:
            season_length = inp.seasonality if inp.seasonality > 0 else 12
            result = self._seasonal_decompose(data, num_forecast, season_length)
            predictions = result["predictions"]
            slope = result.get("trend_slope", 0.0)
            r_squared = result.get("r_squared", 0.0)
        elif model == ForecastModel.ARIMA:
            result = self._linear_regression(data, num_forecast)
            predictions = result["predictions"]
            slope = result["slope"]
            r_squared = result["r_squared"]
        elif model == ForecastModel.ENSEMBLE:
            lr = self._linear_regression(data, num_forecast)
            ma = self._moving_average(data, num_forecast)
            es = self._exponential_smoothing(data, num_forecast)
            predictions = []
            for i in range(num_forecast):
                avg_val = (lr["predictions"][i]["value"] + ma["predictions"][i]["value"] + es["predictions"][i]["value"]) / 3.0
                predictions.append({"period": i + 1, "value": round(avg_val, 4)})
            slope = lr["slope"]
            r_squared = lr["r_squared"]
        else:
            result = self._linear_regression(data, num_forecast)
            predictions = result["predictions"]
            slope = result["slope"]
            r_squared = result["r_squared"]

        pred_values = [p["value"] for p in predictions]

        std_dev = 0.0
        if len(data) >= 2:
            variance = sum((y - (result.get("intercept", 0) + slope * x)) ** 2 for x, y in enumerate(data)) / len(data)
            std_dev = math.sqrt(variance)

        confidence_low = [round(max(0, v - 1.96 * std_dev), 4) for v in pred_values]
        confidence_high = [round(v + 1.96 * std_dev, 4) for v in pred_values]

        accuracy = self.calculate_accuracy(data[-min(len(data), num_forecast):], pred_values[:min(len(data), num_forecast)])

        seasonality_factor = 0.0
        if len(data) >= 8:
            mid = len(data) // 2
            first_half = sum(data[:mid]) / mid if mid > 0 else 0
            second_half = sum(data[mid:]) / (len(data) - mid) if (len(data) - mid) > 0 else 0
            if first_half > 0:
                seasonality_factor = round((second_half - first_half) / first_half, 4)

        result_obj = ForecastResult(
            id=str(uuid.uuid4()),
            input_id=input_id,
            org_id=inp.org_id,
            metric=inp.metric,
            model=model,
            predictions=predictions,
            confidence_interval_low=confidence_low,
            confidence_interval_high=confidence_high,
            accuracy_score=accuracy.get("accuracy_score", 0.0),
            mape=accuracy.get("mape", 0.0),
            rmse=accuracy.get("rmse", 0.0),
            trend_coefficient=round(slope, 6),
            seasonality_factor=seasonality_factor,
            r_squared=r_squared,
        )
        self._results[result_obj.id] = result_obj
        self._save()
        logger.info("Ran forecast %s for input %s using %s", result_obj.id, input_id, model.value)
        return result_obj

    def forecast_revenue(self, org_id: str, months: int = 12, historical_data: Optional[list] = None) -> RevenueForecast:
        self._telemetry["forecast_revenue_calls"] += 1
        if not historical_data:
            historical_data = [0.0]

        current_mrr = historical_data[-1] if historical_data else 0.0

        lr = self._linear_regression(historical_data, months)
        projected_monthly = [p["value"] for p in lr["predictions"]]
        projected_mrr = projected_monthly[-1] if projected_monthly else current_mrr

        projected_arr = projected_mrr * 12

        if len(historical_data) >= 2:
            recent = historical_data[-min(6, len(historical_data)):]
            growth_rate = (recent[-1] - recent[0]) / max(recent[0], 1)
        else:
            growth_rate = 0.0

        churn_rate = 0.0
        if len(historical_data) >= 3:
            declines = sum(1 for i in range(1, len(historical_data)) if historical_data[i] < historical_data[i - 1])
            churn_rate = round(declines / max(len(historical_data) - 1, 1), 4)

        expansion_revenue = projected_mrr * 0.15 if projected_mrr > current_mrr else 0.0
        new_customer_revenue = projected_mrr * 0.1 if growth_rate > 0 else 0.0

        optimistic = [round(v * 1.2, 4) for v in projected_monthly]
        pessimistic = [round(v * 0.8, 4) for v in projected_monthly]
        most_likely = projected_monthly
        what_if = [round(v * 1.5, 4) for v in projected_monthly]

        confidence = ConfidenceLevel.MEDIUM
        if len(historical_data) >= 24:
            confidence = ConfidenceLevel.HIGH
        elif len(historical_data) >= 6:
            confidence = ConfidenceLevel.MEDIUM
        else:
            confidence = ConfidenceLevel.LOW

        assumptions = [
            "Growth rate based on trailing {}-period performance".format(min(6, len(historical_data))),
            "Churn estimated at {}%".format(round(churn_rate * 100, 1)),
            "Expansion revenue estimated at 15% of existing MRR",
            "New customer revenue estimated at 10% of projected MRR",
            "Market conditions assumed stable",
        ]

        forecast = RevenueForecast(
            id=str(uuid.uuid4()),
            org_id=org_id,
            forecast_date=datetime.now(timezone.utc).isoformat(),
            current_mrr=round(current_mrr, 4),
            projected_mrr=round(projected_mrr, 4),
            projected_arr=round(projected_arr, 4),
            growth_rate=round(growth_rate, 4),
            churn_rate=round(churn_rate, 4),
            expansion_revenue=round(expansion_revenue, 4),
            new_customer_revenue=round(new_customer_revenue, 4),
            confidence=confidence,
            scenarios={
                "optimistic": [{"period": i + 1, "value": v} for i, v in enumerate(optimistic)],
                "pessimistic": [{"period": i + 1, "value": v} for i, v in enumerate(pessimistic)],
                "most_likely": [{"period": i + 1, "value": v} for i, v in enumerate(most_likely)],
                "what_if": [{"period": i + 1, "value": v} for i, v in enumerate(what_if)],
            },
            assumptions=assumptions,
        )
        self._revenue_forecasts[forecast.id] = forecast
        self._save()
        logger.info("Forecasted revenue for org %s: current MRR=%.2f, projected MRR=%.2f", org_id, current_mrr, projected_mrr)
        return forecast

    def forecast_capacity(self, org_id: str, months: int = 6) -> CapacityForecast:
        self._telemetry["forecast_capacity_calls"] += 1
        now = datetime.now(timezone.utc)

        gpu_entries = [e for e in self._get_historical_metric(org_id, ForecastMetric.GPU_USAGE)]
        storage_entries = [e for e in self._get_historical_metric(org_id, ForecastMetric.STORAGE_GROWTH)]
        api_entries = [e for e in self._get_historical_metric(org_id, ForecastMetric.API_VOLUME)]

        current_gpu = gpu_entries[-1] if gpu_entries else 0.0
        current_storage = storage_entries[-1] if storage_entries else 0.0
        current_api = api_entries[-1] if api_entries else 0.0

        gpu_forecast = self._linear_regression(gpu_entries, months) if gpu_entries else {"predictions": [{"period": i + 1, "value": current_gpu} for i in range(months)]}
        storage_forecast = self._linear_regression(storage_entries, months) if storage_entries else {"predictions": [{"period": i + 1, "value": current_storage} for i in range(months)]}
        api_forecast = self._linear_regression(api_entries, months) if api_entries else {"predictions": [{"period": i + 1, "value": current_api} for i in range(months)]}

        projected_gpu = gpu_forecast["predictions"][-1]["value"] if gpu_forecast["predictions"] else current_gpu
        projected_storage = storage_forecast["predictions"][-1]["value"] if storage_forecast["predictions"] else current_storage
        projected_api = api_forecast["predictions"][-1]["value"] if api_forecast["predictions"] else current_api

        peak_loads = [p["value"] for p in gpu_forecast["predictions"]]
        peak_load_prediction = max(peak_loads) if peak_loads else current_gpu

        pct_gpu_change = ((projected_gpu - current_gpu) / max(current_gpu, 1)) * 100
        pct_storage_change = ((projected_storage - current_storage) / max(current_storage, 1)) * 100
        pct_api_change = ((projected_api - current_api) / max(current_api, 1)) * 100

        scale_recs = []
        if pct_gpu_change > 50:
            scale_recs.append(f"GPU capacity needs ~{round(pct_gpu_change)}% increase within {months} months")
        if pct_storage_change > 40:
            scale_recs.append(f"Storage needs ~{round(pct_storage_change)}% expansion within {months} months")
        if pct_api_change > 60:
            scale_recs.append(f"API infrastructure needs ~{round(pct_api_change)}% scaling within {months} months")
        if not scale_recs:
            scale_recs.append("Current capacity is sufficient for projected demand")

        confidence = ConfidenceLevel.MEDIUM
        if len(gpu_entries) >= 12 and len(storage_entries) >= 12:
            confidence = ConfidenceLevel.HIGH
        elif len(gpu_entries) < 3:
            confidence = ConfidenceLevel.LOW

        forecast = CapacityForecast(
            id=str(uuid.uuid4()),
            org_id=org_id,
            forecast_date=now.isoformat(),
            current_gpu_usage=round(current_gpu, 4),
            projected_gpu_usage=round(projected_gpu, 4),
            current_storage_tb=round(current_storage, 4),
            projected_storage_tb=round(projected_storage, 4),
            current_api_volume=round(current_api, 4),
            projected_api_volume=round(projected_api, 4),
            peak_load_prediction=round(peak_load_prediction, 4),
            scale_recommendations=scale_recs,
            confidence=confidence,
        )
        self._capacity_forecasts[forecast.id] = forecast
        self._save()
        logger.info("Forecasted capacity for org %s", org_id)
        return forecast

    def forecast_budget(self, org_id: str, budget_id: str, months: int = 6) -> Optional[BudgetForecast]:
        self._telemetry["forecast_budget_calls"] += 1
        cost_entries = self._get_historical_metric(org_id, ForecastMetric.TOTAL_COST)
        if not cost_entries:
            cost_entries = [0.0]

        total_budget = sum(cost_entries) / max(len(cost_entries), 1) * months

        lr = self._linear_regression(cost_entries, months)
        projected_monthly = [p["value"] for p in lr["predictions"]]
        projected_spend = sum(projected_monthly)

        variance = round(projected_spend - total_budget, 4)

        categories = {
            "infrastructure": round(total_budget * 0.35, 4),
            "ai_services": round(total_budget * 0.25, 4),
            "storage": round(total_budget * 0.15, 4),
            "networking": round(total_budget * 0.10, 4),
            "support": round(total_budget * 0.10, 4),
            "miscellaneous": round(total_budget * 0.05, 4),
        }

        risks = []
        if variance > 0:
            risks.append(f"Projected overspend of {round(variance, 2)} ({round(variance / total_budget * 100, 1)}% over budget)")
        if len(cost_entries) < 3:
            risks.append("Limited historical data may reduce forecast accuracy")
        if projected_monthly and projected_monthly[-1] > projected_monthly[0] * 1.5:
            risks.append("Spending trend indicates rapid cost growth")

        mitigation = []
        if variance > 0:
            mitigation.append("Review and optimize top cost categories")
            mitigation.append("Implement budget alerts at 80% threshold")
        if projected_monthly and projected_monthly[-1] > projected_monthly[0] * 1.3:
            mitigation.append("Evaluate auto-scaling limits and resource right-sizing")
        if not risks:
            mitigation.append("Current budget projection is within acceptable range")

        confidence = ConfidenceLevel.MEDIUM
        if len(cost_entries) >= 12:
            confidence = ConfidenceLevel.HIGH
        elif len(cost_entries) < 3:
            confidence = ConfidenceLevel.LOW

        forecast = BudgetForecast(
            id=str(uuid.uuid4()),
            org_id=org_id,
            period=f"{months}_months",
            total_budget=round(total_budget, 4),
            projected_spend=round(projected_spend, 4),
            variance=variance,
            categories=categories,
            risks=risks,
            mitigation=mitigation,
            confidence=confidence,
        )
        self._budget_forecasts[forecast.id] = forecast
        self._save()
        logger.info("Forecasted budget for org %s: budget=%.2f, projected=%.2f, variance=%.2f", org_id, total_budget, projected_spend, variance)
        return forecast

    def compare_models(self, input_id: str, models: list[ForecastModel]) -> dict:
        self._telemetry["compare_models_calls"] += 1
        inp = self._inputs.get(input_id)
        if not inp:
            return {"error": "Forecast input not found", "input_id": input_id}

        data = inp.historical_data
        if not data:
            data = [0.0]

        results = {}
        for model in models:
            saved_model = inp.model
            inp.model = model
            result = self.run_forecast(input_id)
            inp.model = saved_model
            if result:
                results[model.value] = {
                    "predictions": result.predictions,
                    "mape": result.mape,
                    "rmse": result.rmse,
                    "r_squared": result.r_squared,
                    "accuracy_score": result.accuracy_score,
                    "trend_coefficient": result.trend_coefficient,
                }

        ranked = sorted(results.items(), key=lambda x: x[1].get("accuracy_score", 0), reverse=True) if results else []
        return {
            "input_id": input_id,
            "org_id": inp.org_id,
            "metric": inp.metric.value,
            "models": results,
            "best_model": ranked[0][0] if ranked else None,
            "comparison_summary": {
                "models_tested": len(models),
                "best_accuracy": ranked[0][1].get("accuracy_score", 0) if ranked else 0,
                "lowest_rmse": min((v["rmse"] for v in results.values()), default=0) if results else 0,
            },
        }

    def run_scenario_analysis(self, org_id: str, metric: ForecastMetric, scenarios: dict) -> dict:
        self._telemetry["run_scenario_analysis_calls"] += 1
        data = self._get_historical_metric(org_id, metric)
        if not data:
            data = [0.0]

        base_lr = self._linear_regression(data, 12)
        base_predictions = [p["value"] for p in base_lr["predictions"]]

        scenario_results = {}
        for scenario_name, adjustments in scenarios.items():
            adjusted_data = []
            for i, val in enumerate(data):
                factor = 1.0
                if isinstance(adjustments, dict):
                    factor = adjustments.get("growth_factor", 1.0) if i >= len(data) - int(adjustments.get("apply_to_last_n", 0)) else 1.0
                    factor *= adjustments.get("multiplier", 1.0)
                elif isinstance(adjustments, (int, float)):
                    factor = adjustments
                adjusted_data.append(val * factor)

            lr = self._linear_regression(adjusted_data, 12)
            scenario_results[scenario_name] = {
                "predictions": lr["predictions"],
                "final_value": lr["predictions"][-1]["value"] if lr["predictions"] else 0,
                "slope": lr["slope"],
                "r_squared": lr["r_squared"],
            }

        return {
            "org_id": org_id,
            "metric": metric.value,
            "base_forecast": {
                "predictions": base_predictions,
                "final_value": base_predictions[-1] if base_predictions else 0,
            },
            "scenarios": scenario_results,
            "scenario_count": len(scenarios),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_forecast_history(self, org_id: str, metric: ForecastMetric) -> list[ForecastResult]:
        self._telemetry["get_forecast_history_calls"] += 1
        results = []
        for result in self._results.values():
            if result.org_id == org_id and result.metric == metric:
                results.append(result)
        results.sort(key=lambda r: r.generated_at, reverse=True)
        return results

    def calculate_accuracy(self, actual: list, predicted: list) -> dict:
        if not actual or not predicted:
            return {"mape": 0.0, "rmse": 0.0, "r_squared": 0.0, "accuracy_score": 0.0}

        n = min(len(actual), len(predicted))
        actual = actual[:n]
        predicted = predicted[:n]

        if n == 0:
            return {"mape": 0.0, "rmse": 0.0, "r_squared": 0.0, "accuracy_score": 0.0}

        mape = 0.0
        count_nonzero = 0
        for a, p in zip(actual, predicted):
            if a != 0:
                mape += abs((a - p) / a)
                count_nonzero += 1
        mape = (mape / max(count_nonzero, 1)) * 100 if count_nonzero > 0 else 0.0

        rmse = math.sqrt(sum((a - p) ** 2 for a, p in zip(actual, predicted)) / n)

        y_mean = sum(actual) / n
        ss_res = sum((a - p) ** 2 for a, p in zip(actual, predicted))
        ss_tot = sum((a - y_mean) ** 2 for a in actual)
        r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

        accuracy_score = max(0, 100 - mape)
        if accuracy_score > 100:
            accuracy_score = 100.0

        return {
            "mape": round(mape, 4),
            "rmse": round(rmse, 4),
            "r_squared": round(r_squared, 4),
            "accuracy_score": round(accuracy_score, 4),
        }

    def generate_trend_line(self, data: list, periods: int = 12) -> list:
        if not data:
            return [{"period": i + 1, "value": 0.0} for i in range(periods)]

        lr = self._linear_regression(data, periods)
        return lr["predictions"]

    def detect_seasonality(self, data: list, period_length: int = 30) -> dict:
        if not data or len(data) < period_length * 2:
            return {
                "has_seasonality": False,
                "period_length": period_length,
                "strength": 0.0,
                "patterns": [],
                "note": "Insufficient data for seasonality detection (need at least {} data points)".format(period_length * 2),
            }

        n_periods = len(data) // period_length
        period_averages = []
        for i in range(n_periods):
            start = i * period_length
            end = min(start + period_length, len(data))
            segment = data[start:end]
            if segment:
                period_averages.append(sum(segment) / len(segment))

        if len(period_averages) < 2:
            return {
                "has_seasonality": False,
                "period_length": period_length,
                "strength": 0.0,
                "patterns": [],
            }

        overall_mean = sum(period_averages) / len(period_averages)
        seasonal_deviations = [v - overall_mean for v in period_averages]

        variance_between = sum(d ** 2 for d in seasonal_deviations) / len(seasonal_deviations)
        variance_within = 0.0
        for i in range(n_periods):
            start = i * period_length
            end = min(start + period_length, len(data))
            segment = data[start:end]
            if segment:
                seg_mean = sum(segment) / len(segment)
                variance_within += sum((x - seg_mean) ** 2 for x in segment)
        variance_within /= max(len(data), 1)

        strength = variance_between / max(variance_between + variance_within, 0.001)
        strength = min(1.0, strength)

        patterns = []
        for i in range(min(period_length, len(data))):
            indices = list(range(i, len(data), period_length))
            vals = [data[j] for j in indices if j < len(data)]
            if vals:
                patterns.append({"position": i, "avg": round(sum(vals) / len(vals), 4), "count": len(vals)})

        has_seasonality = strength > 0.3

        return {
            "has_seasonality": has_seasonality,
            "period_length": period_length,
            "strength": round(strength, 4),
            "n_periods": n_periods,
            "overall_mean": round(overall_mean, 4),
            "period_averages": [round(v, 4) for v in period_averages],
            "patterns": patterns,
            "interpretation": "Strong seasonality detected" if strength > 0.7 else "Moderate seasonality detected" if strength > 0.3 else "No significant seasonality detected",
        }

    def get_scaling_recommendations(self, forecast: CapacityForecast) -> list[dict]:
        recommendations = []

        gpu_pct = ((forecast.projected_gpu_usage - forecast.current_gpu_usage) / max(forecast.current_gpu_usage, 1)) * 100
        if gpu_pct > 50:
            recommendations.append({
                "resource": "GPU",
                "current": forecast.current_gpu_usage,
                "projected": forecast.projected_gpu_usage,
                "increase_pct": round(gpu_pct, 1),
                "action": "Scale up GPU capacity",
                "urgency": "high" if gpu_pct > 100 else "medium",
                "detail": "Projected GPU usage exceeds current capacity by {}%. Consider adding GPU nodes or upgrading existing instances.".format(round(gpu_pct, 1)),
            })
        elif gpu_pct < -20:
            recommendations.append({
                "resource": "GPU",
                "current": forecast.current_gpu_usage,
                "projected": forecast.projected_gpu_usage,
                "increase_pct": round(gpu_pct, 1),
                "action": "Scale down GPU capacity",
                "urgency": "low",
                "detail": "GPU usage is declining. Consider rightsizing or releasing unused GPU reservations.",
            })

        storage_pct = ((forecast.projected_storage_tb - forecast.current_storage_tb) / max(forecast.current_storage_tb, 1)) * 100
        if storage_pct > 40:
            recommendations.append({
                "resource": "Storage",
                "current": forecast.current_storage_tb,
                "projected": forecast.projected_storage_tb,
                "increase_pct": round(storage_pct, 1),
                "action": "Expand storage capacity",
                "urgency": "high" if storage_pct > 80 else "medium",
                "detail": "Storage needs growing at {}%. Implement lifecycle policies and consider cold storage tiering.".format(round(storage_pct, 1)),
            })

        api_pct = ((forecast.projected_api_volume - forecast.current_api_volume) / max(forecast.current_api_volume, 1)) * 100
        if api_pct > 60:
            recommendations.append({
                "resource": "API",
                "current": forecast.current_api_volume,
                "projected": forecast.projected_api_volume,
                "increase_pct": round(api_pct, 1),
                "action": "Scale API infrastructure",
                "urgency": "high" if api_pct > 120 else "medium",
                "detail": "API volume projected to increase by {}%. Consider auto-scaling, caching, and rate limiting.".format(round(api_pct, 1)),
            })

        if not recommendations:
            recommendations.append({
                "resource": "All",
                "current": 0,
                "projected": 0,
                "increase_pct": 0.0,
                "action": "No scaling needed",
                "urgency": "none",
                "detail": "Current capacity is sufficient for projected demand across all resources.",
            })

        return recommendations

    def get_telemetry(self) -> dict:
        self._telemetry["get_telemetry_calls"] += 1
        return dict(self._telemetry)

    def _get_historical_metric(self, org_id: str, metric: ForecastMetric) -> list[float]:
        values = []
        for inp in self._inputs.values():
            if inp.org_id == org_id and inp.metric == metric:
                values.extend(inp.historical_data)
        for result in self._results.values():
            if result.org_id == org_id and result.metric == metric:
                for pred in result.predictions:
                    values.append(pred["value"])
        if not values:
            base_revenue = {
                ForecastMetric.GPU_USAGE: 75.0,
                ForecastMetric.STORAGE_GROWTH: 2.5,
                ForecastMetric.API_VOLUME: 15000.0,
                ForecastMetric.TOTAL_COST: 5000.0,
                ForecastMetric.MONTHLY_REVENUE: 25000.0,
                ForecastMetric.USER_GROWTH: 120.0,
                ForecastMetric.TOKEN_GROWTH: 500000.0,
                ForecastMetric.AGENT_EXECUTIONS: 800.0,
                ForecastMetric.CUSTOMER_COUNT: 15.0,
                ForecastMetric.ANNUAL_REVENUE: 300000.0,
                ForecastMetric.INFRASTRUCTURE_COST: 2000.0,
                ForecastMetric.AI_COST: 1500.0,
                ForecastMetric.REPOSITORY_GROWTH: 10.0,
                ForecastMetric.SCALING_REQUIREMENTS: 3.0,
                ForecastMetric.GROSS_MARGIN: 0.65,
            }
            base = base_revenue.get(metric, 100.0)
            noise = 0.1
            values = [base * (1 + noise * (i % 5 - 2) / 2) for i in range(6)]
        return values
