"""AI Software Quality Engine -- Cost & Budget Tracking (Volume 48).

Track tokens, model cost, runtime, tool calls per review.
Enforce configured budgets. Stop safely when budget exhausted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BudgetLimits:
    max_tokens: int = 20000
    max_cost_usd: float = 0.05
    max_runtime_s: int = 120
    max_files: int = 50
    max_tool_calls: int = 100


@dataclass
class UsageRecord:
    tokens: int = 0
    cost_usd: float = 0.0
    runtime_ms: int = 0
    tool_calls: int = 0
    files_processed: int = 0
    model_calls: int = 0


class CostTracker:
    """Track and enforce resource budgets for quality reviews."""

    def __init__(self, limits: BudgetLimits | None = None):
        self.limits = limits or BudgetLimits()
        self._usage: dict[str, UsageRecord] = {}

    def start_tracking(self, review_id: str) -> None:
        self._usage[review_id] = UsageRecord()

    def record_tokens(self, review_id: str, count: int) -> None:
        usage = self._usage.get(review_id)
        if usage:
            usage.tokens += count

    def record_cost(self, review_id: str, cost_usd: float) -> None:
        usage = self._usage.get(review_id)
        if usage:
            usage.cost_usd += cost_usd

    def record_runtime(self, review_id: str, duration_ms: int) -> None:
        usage = self._usage.get(review_id)
        if usage:
            usage.runtime_ms += duration_ms

    def record_tool_call(self, review_id: str) -> None:
        usage = self._usage.get(review_id)
        if usage:
            usage.tool_calls += 1

    def record_file_processed(self, review_id: str) -> None:
        usage = self._usage.get(review_id)
        if usage:
            usage.files_processed += 1

    def record_model_call(self, review_id: str, tokens: int, cost_usd: float) -> None:
        usage = self._usage.get(review_id)
        if usage:
            usage.model_calls += 1
            usage.tokens += tokens
            usage.cost_usd += cost_usd

    def check_budget(self, review_id: str) -> dict[str, Any]:
        usage = self._usage.get(review_id)
        if not usage:
            return {"exceeded": False, "violations": []}

        violations: list[str] = []
        if usage.tokens > self.limits.max_tokens:
            violations.append(f"tokens: {usage.tokens}/{self.limits.max_tokens}")
        if usage.cost_usd > self.limits.max_cost_usd:
            violations.append(f"cost: ${usage.cost_usd:.4f}/${self.limits.max_cost_usd:.4f}")
        if usage.runtime_ms > self.limits.max_runtime_s * 1000:
            violations.append(f"runtime: {usage.runtime_ms}ms/{self.limits.max_runtime_s * 1000}ms")
        if usage.tool_calls > self.limits.max_tool_calls:
            violations.append(f"tool_calls: {usage.tool_calls}/{self.limits.max_tool_calls}")
        if usage.files_processed > self.limits.max_files:
            violations.append(f"files: {usage.files_processed}/{self.limits.max_files}")

        return {
            "exceeded": len(violations) > 0,
            "violations": violations,
            "usage": {
                "tokens": usage.tokens,
                "cost_usd": round(usage.cost_usd, 6),
                "runtime_ms": usage.runtime_ms,
                "tool_calls": usage.tool_calls,
                "files_processed": usage.files_processed,
                "model_calls": usage.model_calls,
            },
            "limits": {
                "max_tokens": self.limits.max_tokens,
                "max_cost_usd": self.limits.max_cost_usd,
                "max_runtime_s": self.limits.max_runtime_s,
                "max_files": self.limits.max_files,
                "max_tool_calls": self.limits.max_tool_calls,
            },
        }

    def is_within_budget(self, review_id: str) -> bool:
        return not self.check_budget(review_id)["exceeded"]

    def get_usage(self, review_id: str) -> dict[str, Any]:
        usage = self._usage.get(review_id)
        if not usage:
            return {}
        return {
            "tokens": usage.tokens,
            "cost_usd": round(usage.cost_usd, 6),
            "runtime_ms": usage.runtime_ms,
            "tool_calls": usage.tool_calls,
            "files_processed": usage.files_processed,
            "model_calls": usage.model_calls,
        }

    def get_remaining_budget(self, review_id: str) -> dict[str, Any]:
        usage = self._usage.get(review_id)
        if not usage:
            return {
                "tokens": self.limits.max_tokens,
                "cost_usd": self.limits.max_cost_usd,
                "runtime_s": self.limits.max_runtime_s,
                "files": self.limits.max_files,
                "tool_calls": self.limits.max_tool_calls,
            }
        return {
            "tokens": max(0, self.limits.max_tokens - usage.tokens),
            "cost_usd": max(0, self.limits.max_cost_usd - usage.cost_usd),
            "runtime_s": max(0, self.limits.max_runtime_s - usage.runtime_ms // 1000),
            "files": max(0, self.limits.max_files - usage.files_processed),
            "tool_calls": max(0, self.limits.max_tool_calls - usage.tool_calls),
        }

    def stop_tracking(self, review_id: str) -> dict[str, Any]:
        result = self.get_usage(review_id)
        return result
