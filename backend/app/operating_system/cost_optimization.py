"""Cost Optimization — tracks LLM cost, embedding cost, infrastructure cost, storage, bandwidth, agent cost, and identifies optimization opportunities."""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional


@dataclass
class CostEntry:
    id: str
    category: str  # llm, embedding, infrastructure, storage, bandwidth, agent
    operation: str
    cost: float  # USD
    tokens: int = 0
    duration_ms: float = 0.0
    model: str = ""
    timestamp: str = ""
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class CostSummary:
    total_cost: float = 0.0
    daily_cost: float = 0.0
    weekly_cost: float = 0.0
    monthly_cost: float = 0.0
    by_category: dict[str, float] = field(default_factory=dict)
    by_model: dict[str, float] = field(default_factory=dict)
    by_operation: dict[str, float] = field(default_factory=dict)


@dataclass
class OptimizationSuggestion:
    id: str
    category: str
    title: str
    description: str
    estimated_savings_monthly: float
    effort: str  # low, medium, high
    risk: str = "low"
    recommendation: str = ""


@dataclass
class CostReport:
    repo_id: str
    repo_name: str
    timestamp: str
    summary: CostSummary = field(default_factory=CostSummary)
    recent_entries: list[CostEntry] = field(default_factory=list)
    optimization_opportunities: list[OptimizationSuggestion] = field(default_factory=list)
    trends: dict[str, list[float]] = field(default_factory=dict)
    cost_health_score: float = 100.0
    recommendations: list[str] = field(default_factory=list)


class CostOptimization:
    """Tracks and optimizes costs across LLM, embeddings, infrastructure, storage, bandwidth, and agents."""

    MODEL_COSTS: dict[str, dict] = {
        "gpt-4": {"input_per_1k": 0.03, "output_per_1k": 0.06, "embedding_per_1k": 0.0},
        "gpt-4-turbo": {"input_per_1k": 0.01, "output_per_1k": 0.03, "embedding_per_1k": 0.0},
        "gpt-3.5-turbo": {"input_per_1k": 0.001, "output_per_1k": 0.002, "embedding_per_1k": 0.0},
        "claude-3-opus": {"input_per_1k": 0.015, "output_per_1k": 0.075, "embedding_per_1k": 0.0},
        "claude-3-sonnet": {"input_per_1k": 0.003, "output_per_1k": 0.015, "embedding_per_1k": 0.0},
        "text-embedding-3-small": {"input_per_1k": 0.0, "output_per_1k": 0.0, "embedding_per_1k": 0.00002},
        "text-embedding-3-large": {"input_per_1k": 0.0, "output_per_1k": 0.0, "embedding_per_1k": 0.00013},
    }

    def __init__(self, repo_path: str = ""):
        self.repo_path = Path(repo_path) if repo_path else Path()
        self.entries: list[CostEntry] = []

    def record(self, category: str, operation: str, cost: float, tokens: int = 0,
               duration_ms: float = 0.0, model: str = "", tags: dict = None) -> CostEntry:
        entry = CostEntry(
            id=f"cost-{uuid.uuid4().hex[:12]}",
            category=category, operation=operation, cost=cost,
            tokens=tokens, duration_ms=duration_ms, model=model,
            timestamp=datetime.now(timezone.utc).isoformat(),
            tags=tags or {},
        )
        self.entries.append(entry)
        if len(self.entries) > 10000:
            self.entries = self.entries[-5000:]
        return entry

    def estimate_llm_cost(self, model: str, input_tokens: int, output_tokens: int = 0) -> float:
        costs = self.MODEL_COSTS.get(model, {"input_per_1k": 0.01, "output_per_1k": 0.03})
        input_cost = (input_tokens / 1000) * costs["input_per_1k"]
        output_cost = (output_tokens / 1000) * costs["output_per_1k"]
        return round(input_cost + output_cost, 6)

    def estimate_embedding_cost(self, model: str, tokens: int) -> float:
        costs = self.MODEL_COSTS.get(model, {"embedding_per_1k": 0.0001})
        return round((tokens / 1000) * costs["embedding_per_1k"], 6)

    def get_summary(self, days: int = 30) -> CostSummary:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        recent = [e for e in self.entries if e.timestamp >= cutoff]

        summary = CostSummary()
        if not recent:
            return summary

        by_cat = defaultdict(float)
        by_model = defaultdict(float)
        by_op = defaultdict(float)

        for e in recent:
            by_cat[e.category] += e.cost
            if e.model:
                by_model[e.model] += e.cost
            by_op[e.operation] += e.cost

        daily_entries = [e for e in recent if e.timestamp >= (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()]
        weekly_entries = [e for e in recent if e.timestamp >= (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()]

        summary.total_cost = round(sum(e.cost for e in recent), 4)
        summary.daily_cost = round(sum(e.cost for e in daily_entries), 4)
        summary.weekly_cost = round(sum(e.cost for e in weekly_entries), 4)
        summary.monthly_cost = round(summary.total_cost, 4)
        summary.by_category = dict(by_cat)
        summary.by_model = dict(by_model)
        summary.by_operation = dict(by_op)

        return summary

    def analyze(self) -> CostReport:
        report = CostReport(
            repo_id=str(hash(str(self.repo_path))),
            repo_name=self.repo_path.name,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        report.summary = self.get_summary(30)
        report.recent_entries = self.entries[-50:]

        self._find_optimizations(report)
        self._calculate_trends(report)
        self._calculate_health_score(report)
        self._generate_recommendations(report)

        return report

    def _find_optimizations(self, report: CostReport):
        s = report.summary

        if s.by_category.get("llm", 0) > s.total_cost * 0.5:
            report.optimization_opportunities.append(OptimizationSuggestion(
                id=f"opt-{uuid.uuid4().hex[:8]}",
                category="llm",
                title="Reduce LLM API costs",
                description=f"LLM costs ({s.by_category.get('llm', 0):.2f}) dominate total spend",
                estimated_savings_monthly=round(s.by_category.get('llm', 0) * 0.3, 2),
                effort="medium",
                recommendation="Consider using cheaper models (GPT-3.5 instead of GPT-4) for simpler tasks, implement caching, and reduce prompt token count",
            ))

        if s.by_category.get("embedding", 0) > s.total_cost * 0.2:
            report.optimization_opportunities.append(OptimizationSuggestion(
                id=f"opt-{uuid.uuid4().hex[:8]}",
                category="embedding",
                title="Optimize embedding usage",
                description=f"Embedding costs ({s.by_category.get('embedding', 0):.2f}) are significant",
                estimated_savings_monthly=round(s.by_category.get('embedding', 0) * 0.4, 2),
                effort="low",
                recommendation="Cache embeddings, use text-embedding-3-small instead of large, batch embedding requests",
            ))

        if s.by_model:
            model_costs = sorted(s.by_model.items(), key=lambda x: -x[1])
            if model_costs and model_costs[0][0] in ("gpt-4", "claude-3-opus"):
                report.optimization_opportunities.append(OptimizationSuggestion(
                    id=f"opt-{uuid.uuid4().hex[:8]}",
                    category="llm",
                    title=f"Switch from expensive model: {model_costs[0][0]}",
                    description=f"Model {model_costs[0][0]} costs ${model_costs[0][1]:.2f}",
                    estimated_savings_monthly=round(model_costs[0][1] * 0.5, 2),
                    effort="low",
                    recommendation="Evaluate if a cheaper model (GPT-3.5, Claude-3-Sonnet) meets quality requirements for most tasks",
                ))

        if not report.optimization_opportunities:
            report.optimization_opportunities.append(OptimizationSuggestion(
                id=f"opt-{uuid.uuid4().hex[:8]}",
                category="general",
                title="No major cost optimization needed",
                description="Current costs are within reasonable bounds",
                estimated_savings_monthly=0,
                effort="low",
                recommendation="Continue monitoring costs and set up budget alerts",
            ))

    def _calculate_trends(self, report: CostReport):
        daily_costs = defaultdict(float)
        for e in self.entries[-500:]:
            day = e.timestamp[:10]
            daily_costs[day] += e.cost

        days = sorted(daily_costs.keys())[-30:]
        report.trends = {
            "daily_cost": [daily_costs[d] for d in days],
            "labels": days,
        }

    def _calculate_health_score(self, report: CostReport):
        s = report.summary
        score = 100.0

        if s.monthly_cost > 100:
            score -= 20
        elif s.monthly_cost > 50:
            score -= 10
        elif s.monthly_cost > 20:
            score -= 5

        if s.by_category.get("llm", 0) > s.total_cost * 0.7:
            score -= 15

        if not self.entries:
            score = 50.0

        report.cost_health_score = round(max(0, score), 1)

    def _generate_recommendations(self, report: CostReport):
        if report.optimization_opportunities:
            for opt in report.optimization_opportunities[:2]:
                report.recommendations.append(
                    f"{opt.title}: {opt.recommendation[:100]} (save ~${opt.estimated_savings_monthly:.2f}/mo)"
                )
        if report.summary.total_cost > 50:
            report.recommendations.append(f"Monthly cost ${report.summary.monthly_cost:.2f} — review for optimization")
        if not self.entries:
            report.recommendations.append("Start tracking costs to identify optimization opportunities")

    def get_cost_by_project(self, project_tag: str) -> float:
        return round(sum(e.cost for e in self.entries if e.tags.get("project") == project_tag), 4)

    def get_most_expensive_operations(self, limit: int = 10) -> list[dict]:
        op_costs = defaultdict(float)
        op_counts = defaultdict(int)
        for e in self.entries:
            op_costs[e.operation] += e.cost
            op_counts[e.operation] += 1
        sorted_ops = sorted(op_costs.items(), key=lambda x: -x[1])[:limit]
        return [{"operation": op, "cost": round(cost, 4), "count": op_counts[op]} for op, cost in sorted_ops]
