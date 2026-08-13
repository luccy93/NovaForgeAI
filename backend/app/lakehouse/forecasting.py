"""Forecasting - abstractable time-series models with measurable accuracy."""
from abc import ABC, abstractmethod
import statistics
from dataclasses import dataclass


class ForecastModel(ABC):
    name = "abstract"

    @abstractmethod
    def fit(self, series: list[float]) -> None: ...
    @abstractmethod
    def predict(self, horizon: int) -> list[float]: ...

    def fit_predict(self, series: list[float], horizon: int) -> list[float]:
        self.fit(series)
        return self.predict(horizon)


class NaiveModel(ForecastModel):
    """Last observed value repeated - the honest baseline."""
    name = "naive"

    def __init__(self):
        self.last = 0.0

    def fit(self, series: list[float]) -> None:
        self.last = series[-1] if series else 0.0

    def predict(self, horizon: int) -> list[float]:
        return [self.last] * horizon


class MovingAverageModel(ForecastModel):
    name = "moving_average"

    def __init__(self, window: int = 7):
        self.window = window
        self.mean_value = 0.0

    def fit(self, series: list[float]) -> None:
        recent = series[-self.window:]
        self.mean_value = statistics.mean(recent) if recent else 0.0

    def predict(self, horizon: int) -> list[float]:
        return [self.mean_value] * horizon


class ExponentialSmoothingModel(ForecastModel):
    """Single exponential smoothing (Holt's linear via second pass when growth present)."""
    name = "exponential_smoothing"

    def __init__(self, alpha: float = 0.3, beta: float = 0.2):
        self.alpha = alpha
        self.beta = beta
        self.level = 0.0
        self.trend = 0.0

    def fit(self, series: list[float]) -> None:
        if not series:
            return
        self.level = series[0]
        self.trend = (series[-1] - series[0]) / max(1, len(series))
        for v in series[1:]:
            prev_level = self.level
            self.level = self.alpha * v + (1 - self.alpha) * (prev_level + self.trend)
            self.trend = self.beta * (self.level - prev_level) + (1 - self.beta) * self.trend

    def predict(self, horizon: int) -> list[float]:
        return [self.level + (i + 1) * self.trend for i in range(horizon)]


class LinearTrendModel(ForecastModel):
    name = "linear_trend"

    def __init__(self):
        self.intercept = 0.0
        self.slope = 0.0

    def fit(self, series: list[float]) -> None:
        n = len(series)
        if n < 2:
            self.intercept = series[0] if series else 0.0
            self.slope = 0.0
            return
        x_mean = (n - 1) / 2.0
        y_mean = statistics.mean(series)
        num = sum((i - x_mean) * (series[i] - y_mean) for i in range(n))
        den = sum((i - x_mean) ** 2 for i in range(n))
        self.slope = num / den if den else 0.0
        self.intercept = y_mean - self.slope * x_mean

    def predict(self, horizon: int) -> list[float]:
        return [self.intercept + self.slope * (len(self.series) + i) if hasattr(self, "series") else self.intercept + self.slope * i
                for i in range(horizon)]


class SeasonalNaiveModel(ForecastModel):
    """Repeats the value 'period' positions back (seasonal naive)."""
    name = "seasonal_naive"

    def __init__(self, period: int = 7):
        self.period = period
        self.series: list[float] = []

    def fit(self, series: list[float]) -> None:
        self.series = list(series)

    def predict(self, horizon: int) -> list[float]:
        if not self.series:
            return [0.0] * horizon
        return [self.series[-self.period + (i % self.period)] if len(self.series) >= self.period else self.series[-1]
                for i in range(horizon)]


class ForecastEngine:
    """Choose models, fit, predict with confidence intervals and accuracy metrics."""

    MODELS = {
        "naive": NaiveModel,
        "moving_average": MovingAverageModel,
        "exponential_smoothing": ExponentialSmoothingModel,
        "linear_trend": LinearTrendModel,
        "seasonal_naive": SeasonalNaiveModel,
    }

    def __init__(self, default_model: str = "exponential_smoothing"):
        self.default_model = default_model
        self.runs: list[dict] = []

    def forecast(self, metric: str, series: list[float], horizon: int = 30,
                 model: str = "") -> dict:
        model_name = model or self.default_model
        if model_name not in self.MODELS:
            raise ValueError(f"unknown model: {model_name}")
        inst = self.MODELS[model_name]()
        fitted = inst.fit_predict(series, horizon)
        forecast_values = [round(x, 4) for x in fitted]

        if len(series) >= 8:
            train = series[:-7]
            test = series[-7:]
            inst2 = self.MODELS[model_name]()
            pred = inst2.fit_predict(train, len(test))
            mae = sum(abs(p - t) for p, t in zip(pred, test)) / len(test)
            mape = sum(abs(p - t) / abs(t) if t else 0 for p, t in zip(pred, test)) / len(test)
        else:
            mae, mape = 0.0, 0.0

        std = statistics.pstdev(series) or 0.0
        result = {"metric": metric, "model": model_name, "horizon": horizon,
                  "forecast": forecast_values,
                  "confidence_lower": [round(v - 1.96 * std, 4) for v in forecast_values],
                  "confidence_upper": [round(v + 1.96 * std, 4) for v in forecast_values],
                  "validation": {"mae": round(mae, 4), "mape": round(mape, 4)},
                  "observed_mean": round(statistics.mean(series), 4) if series else 0.0}
        self.runs.append(result)
        return result

    def history(self, limit: int = 50) -> list[dict]:
        return self.runs[-limit:]