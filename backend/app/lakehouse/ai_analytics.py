"""AI Analytics Service - model metrics, prompt cost, latency, tokens, drift, ROI."""
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class AIModelMetric:
    model: str
    organization_id: str
    latency_ms: float
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    success: bool = True
    at: str = ""


class AIAnalytics:
    """Aggregates AI/LLM usage metrics per model and organization."""

    def __init__(self):
        self.records: list[AIModelMetric] = []
        self.drift_baselines: dict[str, dict] = {}

    def record(self, model: str, organization_id: str, latency_ms: float,
               tokens_in: int = 0, tokens_out: int = 0, cost_usd: float = 0.0,
               success: bool = True) -> AIModelMetric:
        metric = AIModelMetric(model, organization_id, latency_ms, tokens_in,
                               tokens_out, cost_usd, success,
                               datetime.now(timezone.utc).isoformat())
        self.records.append(metric)
        return metric

    def _filter(self, organization_id: Optional[str] = None, model: Optional[str] = None):
        rows = self.records
        if organization_id:
            rows = [r for r in rows if r.organization_id == organization_id]
        if model:
            rows = [r for r in rows if r.model == model]
        return rows

    def usage(self, organization_id: Optional[str] = None, model: Optional[str] = None) -> dict:
        rows = self._filter(organization_id, model)
        if not rows:
            return {"calls": 0}
        total_tokens_in = sum(r.tokens_in for r in rows)
        total_tokens_out = sum(r.tokens_out for r in rows)
        return {
            "calls": len(rows),
            "total_tokens_in": total_tokens_in,
            "total_tokens_out": total_tokens_out,
            "total_tokens": total_tokens_in + total_tokens_out,
            "success_rate": round(sum(1 for r in rows if r.success) / len(rows), 4),
            "total_cost_usd": round(sum(r.cost_usd for r in rows), 4),
            "avg_latency_ms": round(statistics.mean(r.latency_ms for r in rows), 2),
            "p95_latency_ms": round(self._percentile([r.latency_ms for r in rows], 0.95), 2),
            "models_used": sorted({r.model for r in rows}),
        }

    def by_model(self, organization_id: Optional[str] = None) -> list[dict]:
        models = {}
        for r in self._filter(organization_id):
            entry = models.setdefault(r.model, {"organization_id": organization_id or r.organization_id,
                                                "calls": 0, "total_cost_usd": 0.0,
                                                "tokens_in": 0, "tokens_out": 0,
                                                "latencies": []})
            entry["calls"] += 1
            entry["total_cost_usd"] += r.cost_usd
            entry["tokens_in"] += r.tokens_in
            entry["tokens_out"] += r.tokens_out
            entry["latencies"].append(r.latency_ms)
        return [{"model": m, "calls": d["calls"],
                 "total_cost_usd": round(d["total_cost_usd"], 4),
                 "tokens_in": d["tokens_in"], "tokens_out": d["tokens_out"],
                 "avg_latency_ms": round(statistics.mean(d["latencies"]), 2)}
                for m, d in sorted(models.items())]

    def cost_trend(self, period: str = "day") -> dict:
        out = {}
        for r in self.records:
            key = r.at[:10] if period == "day" else r.at[:7]
            existing = out.setdefault(key, {"calls": 0, "cost_usd": 0.0})
            existing["calls"] += 1
            existing["cost_usd"] += r.cost_usd
        return {k: {"calls": v["calls"], "cost_usd": round(v["cost_usd"], 4)}
                for k, v in sorted(out.items())}

    def distribution_drift(self, model: str, tokens: list[int], window: int = 100) -> dict:
        """Compares the latest batch vs a stored baseline; returns drift."""

        baseline = self.drift_baseline(model, tokens, window)
        if not baseline:
            return {"model": model, "drift": 0.0, "baseline_set": False}
        recent = tokens[-window:] if len(tokens) > window else tokens
        if not recent:
            return {"model": model, "drift": 0.0, "baseline_set": True}
        mean_recent = statistics.mean(recent)
        std_recent = statistics.pstdev(recent) or 1.0
        z = (mean_recent - baseline["mean"]) / (baseline["std"] or 1.0)
        return {"model": model, "drift": round(abs(z), 4),
                "recent_mean": round(mean_recent, 2), "baseline_set": True,
                "drift_detected": abs(z) > 2.0}

    def drift_baseline(self, model: str, tokens: list[float], window: int = 100) -> dict:
        baseline = self.drift_baselines.get(model)
        if baseline:
            return baseline
        sample = tokens[-window:] if len(tokens) > window else tokens
        if len(sample) < 10:
            return {}
        baseline = {"mean": statistics.mean(sample), "std": statistics.pstdev(sample) or 1.0,
                    "window": len(sample)}
        self.drift_baselines[model] = baseline
        return baseline

    def roi_estimate(self, organization_id: str, cost_saved_usd: float) -> dict:
        usage = self.usage(organization_id)
        cost = usage.get("total_cost_usd", 0.0)
        roi = (cost_saved_usd - cost) / max(cost, 1e-6)
        return {"organization_id": organization_id, "cost_usd": cost,
                "estimated_savings_usd": cost_saved_usd,
                "roi_multiple": round(roi, 2),
                "calls": usage.get("calls", 0)}

    @staticmethod
    def _percentile(values: list[float], p: float) -> float:
        if not values:
            return 0.0
        s = sorted(values)
        idx = min(len(s) - 1, max(0, int(p * len(s))))
        return s[idx]

    def _bump_cache(self):
        self.drift_baselines = {}