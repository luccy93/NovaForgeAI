"""NovaForge Analytics Platform -- Forecasting Service (Volume 50).

In-memory cost/resource forecasting. Historical data points are fitted
with ordinary least-squares linear regression and projected forward with
an approximate 95% prediction band. Every output is a statistical
estimate derived from past observations -- never a guarantee.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone
from uuid import uuid4

DEFAULT_HORIZON_DAYS = 30
MIN_DATA_POINTS = 5
MAX_POINTS_PER_SERIES = 5000
Z_95 = 1.96


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_day(value: str) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed.replace(hour=0, minute=0, second=0, microsecond=0)


class ForecastingService:
    """Projects metric trends forward using simple linear regression."""

    def __init__(self, min_points: int = MIN_DATA_POINTS):
        self._min_points = max(2, int(min_points))
        self._history: dict[tuple[str, str], list[dict]] = {}
        self._forecasts: list[dict] = []

    # ── Historical data ────────────────────────────────────────────────

    def record_data_point(self, tenant: str, metric_name: str, value: float,
                          timestamp: str = "") -> dict:
        ts = timestamp or _utc_now()
        day = _parse_day(ts)
        point = {
            "date": day.date().isoformat() if day else ts[:10],
            "value": float(value),
            "timestamp": ts,
        }
        series = self._history.setdefault((tenant, metric_name), [])
        series.append(point)
        if len(series) > MAX_POINTS_PER_SERIES:
            del series[:len(series) - MAX_POINTS_PER_SERIES]
        return point

    # ── Forecasting ────────────────────────────────────────────────────

    def forecast(self, tenant: str, metric_name: str,
                 horizon_days: int = DEFAULT_HORIZON_DAYS,
                 scope: str = "", scope_value: str = "") -> list[dict]:
        horizon_days = max(1, int(horizon_days))
        points = sorted(self._history.get((tenant, metric_name), []),
                        key=lambda point: point["date"])
        if len(points) < self._min_points:
            return []
        xs = list(range(len(points)))
        ys = [point["value"] for point in points]
        n = len(xs)
        x_bar = statistics.fmean(xs)
        y_bar = statistics.fmean(ys)
        s_xx = sum((x - x_bar) ** 2 for x in xs)
        s_xy = sum((x - x_bar) * (y - y_bar) for x, y in zip(xs, ys))
        slope = s_xy / s_xx if s_xx else 0.0
        intercept = y_bar - slope * x_bar
        residuals = [y - (slope * x + intercept) for x, y in zip(xs, ys)]
        residual_std = statistics.stdev(residuals) if n > 1 else 0.0
        non_negative = all(y >= 0 for y in ys)
        last_day = _parse_day(points[-1]["date"])
        if last_day is None:
            return []
        results: list[dict] = []
        for step in range(1, horizon_days + 1):
            x_future = (n - 1) + step
            predicted = slope * x_future + intercept
            leverage = ((x_future - x_bar) ** 2 / s_xx) if s_xx else 0.0
            margin = Z_95 * residual_std * ((1.0 + 1.0 / n + leverage) ** 0.5)
            lower = predicted - margin
            upper = predicted + margin
            if non_negative:
                predicted = max(0.0, predicted)
                lower = max(0.0, lower)
            forecast_day = last_day + timedelta(days=step)
            results.append({
                "forecast_date": forecast_day.date().isoformat(),
                "predicted_value": round(predicted, 6),
                "confidence_lower": round(lower, 6),
                "confidence_upper": round(upper, 6),
            })
        return results

    # ── Stored forecasts ───────────────────────────────────────────────

    def record_forecast(self, tenant: str, metric_name: str,
                        forecast_date: str, predicted_value: float,
                        confidence_lower: float, confidence_upper: float,
                        scope: str = "", scope_value: str = "",
                        methodology: str = "linear") -> dict:
        day = _parse_day(forecast_date)
        record = {
            "forecast_id": uuid4().hex,
            "tenant": tenant,
            "metric_name": metric_name,
            "forecast_date": day.date().isoformat() if day else forecast_date,
            "predicted_value": float(predicted_value),
            "confidence_lower": float(confidence_lower),
            "confidence_upper": float(confidence_upper),
            "scope": scope,
            "scope_value": scope_value,
            "methodology": methodology or "linear",
            "status": "active",
            "created_at": _utc_now(),
        }
        self._forecasts.append(record)
        return record

    def get_forecasts(self, tenant: str, metric_name: str = "",
                      limit: int = 100) -> list[dict]:
        selected = [
            record for record in reversed(self._forecasts)
            if record["tenant"] == tenant
            and (not metric_name or record["metric_name"] == metric_name)
        ]
        return selected[:max(0, limit)]

    # ── Accuracy ───────────────────────────────────────────────────────

    def get_forecast_accuracy(self, tenant: str, metric_name: str = "") -> dict:
        actuals: dict[str, list[float]] = {}
        for (history_tenant, history_metric), series in self._history.items():
            if history_tenant != tenant:
                continue
            if metric_name and history_metric != metric_name:
                continue
            bucket = actuals.setdefault(history_metric, {})
            for point in series:
                bucket.setdefault(point["date"], []).append(point["value"])
        actual_by_day = {
            metric: {day: statistics.fmean(values) for day, values in days.items()}
            for metric, days in actuals.items()
        }
        today = datetime.now(timezone.utc).date().isoformat()
        errors_by_metric: dict[str, list[tuple[float, float]]] = {}
        for record in self._forecasts:
            if record["tenant"] != tenant:
                continue
            if metric_name and record["metric_name"] != metric_name:
                continue
            day = _parse_day(record["forecast_date"])
            if day is None or day.date().isoformat() > today:
                continue
            actual = actual_by_day.get(record["metric_name"], {}).get(day.date().isoformat())
            if actual is None:
                continue
            errors_by_metric.setdefault(record["metric_name"], []).append(
                (actual, record["predicted_value"]))
        by_metric: dict[str, dict] = {}
        all_errors: list[tuple[float, float]] = []
        for metric, pairs in errors_by_metric.items():
            stats = self._score(pairs)
            by_metric[metric] = {"evaluated": len(pairs), **stats}
            all_errors.extend(pairs)
        overall = self._score(all_errors)
        return {
            "tenant": tenant,
            "forecasts_evaluated": len(all_errors),
            "mean_absolute_error": overall["mean_absolute_error"],
            "mean_absolute_percentage_error": overall["mean_absolute_percentage_error"],
            "accuracy_pct": overall["accuracy_pct"],
            "by_metric": by_metric,
            "note": "Forecasts are statistical estimates based on historical data, not guarantees.",
        }

    @staticmethod
    def _score(pairs: list[tuple[float, float]]) -> dict:
        if not pairs:
            return {"mean_absolute_error": 0.0,
                    "mean_absolute_percentage_error": 0.0,
                    "accuracy_pct": 0.0}
        absolute_errors = [abs(actual - predicted) for actual, predicted in pairs]
        mae = statistics.fmean(absolute_errors)
        percentage_errors = [
            abs(actual - predicted) / abs(actual) * 100.0
            for actual, predicted in pairs if actual != 0
        ]
        mape = statistics.fmean(percentage_errors) if percentage_errors else 0.0
        return {
            "mean_absolute_error": round(mae, 6),
            "mean_absolute_percentage_error": round(mape, 4),
            "accuracy_pct": round(max(0.0, 100.0 - mape), 4),
        }


forecasting_service = ForecastingService()
