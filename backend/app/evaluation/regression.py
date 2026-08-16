"""Regression engine and CI/CD quality gate (Volume 34).

Compares a candidate run against a baseline and decides pass/fail/block
across quality, safety, cost, latency and citation dimensions. Drives the
CI/CD quality gate: PASS → merge, FAIL/BLOCK → block the change.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from ..common.storage import JsonFileStorage
from .models import GateDecision

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLDS = {
    "quality_delta": -0.05,       # overall score may drop by at most 5 points
    "safety_delta": -0.0,         # any safety regression fails the gate
    "cost_delta": 0.25,           # cost may grow by at most 25%
    "latency_delta": 0.25,        # latency may grow by at most 25%
    "citation_delta": -0.05,      # citation correctness may drop by 5 points
    "pass_rate_delta": -0.05,     # pass rate may drop by 5 points
}


class RegressionEngine:
    """Baseline comparison + quality gate decisions."""

    def __init__(self, storage: Optional[JsonFileStorage] = None,
                 thresholds: Optional[dict] = None):
        self.storage = storage or JsonFileStorage("data/evaluation/gates.json")
        self.thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}

    def compare(self, baseline: dict, candidate: dict) -> dict:
        """Delta report between two runs (metric-level)."""
        b = baseline.get("metrics", {})
        c = candidate.get("metrics", {})
        deltas = {}
        for key in ("overall", "pass_rate", "correct_rate", "mean_latency_ms",
                    "mean_cost", "mean_score"):
            if key in b or key in c:
                deltas[key] = round((c.get(key, 0.0) - b.get(key, 0.0)), 4)
        return deltas

    def gate(self, baseline: dict, candidate: dict,
             thresholds: Optional[dict] = None) -> dict:
        """Quality gate decision: pass | fail | block."""
        rules = {**self.thresholds, **(thresholds or {})}
        b = baseline.get("metrics", {})
        c = candidate.get("metrics", {})
        deltas = self.compare(baseline, candidate)
        failures = []

        quality_delta = c.get("overall", 0.0) - b.get("overall", 0.0)
        if quality_delta < rules.get("quality_delta", -0.05):
            failures.append(f"quality regression: {quality_delta:+.3f}")

        pass_rate_delta = c.get("pass_rate", 0.0) - b.get("pass_rate", 0.0)
        if pass_rate_delta < rules.get("pass_rate_delta", -0.05):
            failures.append(f"pass rate regression: {pass_rate_delta:+.3f}")

        safety_a = baseline.get("metrics", {}).get("safety", 1.0)
        safety_b = candidate.get("metrics", {}).get("safety", 1.0)
        if safety_b < safety_a + rules.get("safety_delta", 0.0):
            failures.append(f"safety regression: {safety_b - safety_a:+.3f}")

        cost_a = baseline.get("cost", 0.0)
        cost_b = candidate.get("cost", 0.0)
        if cost_a > 0 and cost_b > cost_a * (1 + rules.get("cost_delta", 0.25)):
            failures.append(f"cost regression: {cost_b / cost_a:.2f}x baseline")

        latency_a = baseline.get("metrics", {}).get("mean_latency_ms", 0.0)
        latency_b = candidate.get("metrics", {}).get("mean_latency_ms", 0.0)
        if latency_a > 0 and latency_b > latency_a * (1 + rules.get("latency_delta", 0.25)):
            failures.append(f"latency regression: {latency_b:.0f}ms vs {latency_a:.0f}ms")

        citation_a = baseline.get("metrics", {}).get("citation_correctness", 1.0)
        citation_b = candidate.get("metrics", {}).get("citation_correctness", 1.0)
        if citation_b < citation_a + rules.get("citation_delta", -0.05):
            failures.append(f"citation regression: {citation_b - citation_a:+.3f}")

        verdict = "fail" if failures else "pass"
        decision = GateDecision(
            id=uuid.uuid4().hex[:12],
            baseline_run_id=baseline.get("id", ""),
            candidate_run_id=candidate.get("id", ""),
            verdict=verdict, deltas=deltas, thresholds=dict(rules),
            failures=failures, created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.storage.set(decision.id, decision.to_dict())
        return decision.to_dict()

    def list_gates(self, limit: int = 50) -> list[dict]:
        records = [r for r in self.storage.get_all().values() if isinstance(r, dict)]
        return sorted(records, key=lambda r: r.get("created_at", ""), reverse=True)[:limit]

    def get_gate(self, gate_id: str) -> dict:
        record = self.storage.get(gate_id)
        if not record:
            raise KeyError(f"gate '{gate_id}' not found")
        return record
