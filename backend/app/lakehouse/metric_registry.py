"""Metric Registry - centralized metric definitions with formulas, + semantic business layer."""
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable


@dataclass
class MetricDef:
    id: str
    name: str
    description: str
    formula: str
    unit: str
    dimensions: list[str]
    data_source: str
    refresh_frequency: str
    owner: str
    version: int = 1
    status: str = "active"
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = uuid.uuid4().hex[:12]
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


class MetricRegistry:
    """Register, look up, and version business metrics with defined formulas."""

    def __init__(self):
        self.metrics: dict[str, MetricDef] = {}

    def register(self, name: str, description: str, formula: str, unit: str,
                 dimensions: list[str], data_source: str, refresh: str = "daily",
                 owner: str = "platform", **extra) -> MetricDef:
        m = MetricDef(id=extra.pop("id", ""), name=name, description=description,
                      formula=formula, unit=unit, dimensions=dimensions,
                      data_source=data_source, refresh_frequency=refresh,
                      owner=owner, **extra)
        self.metrics[name] = m
        return m

    def get(self, name: str) -> MetricDef:
        return self.metrics[name]

    def list(self) -> list[dict]:
        return [self._render(m) for m in self.metrics.values()]

    @staticmethod
    def _render(m: MetricDef) -> dict:
        return {"id": m.id, "name": m.name, "description": m.description,
                "formula": m.formula, "unit": m.unit, "dimensions": m.dimensions,
                "data_source": m.data_source, "refresh_frequency": m.refresh_frequency,
                "owner": m.owner, "version": m.version, "status": m.status}


class SemanticLayer:
    """Reusable business metrics computed deterministically from facts."""

    def __init__(self, metric_registry: MetricRegistry):
        self.registry = metric_registry
        self._register_core()

    def _register_core(self) -> None:
        defs = [
            ("ai_productivity", "AI Productivity", "requests per active developer per month",
             "ai_requests / active_developers", "requests/developer/month",
             ["organization_id", "month"]),
            ("repository_health", "Repository Health", "weighted score over builds, PRs, issues, debt",
             "0.25*build_health + 0.25*pr_health + 0.25*test_health + 0.25*security_health", "score",
             ["organization_id", "repository_id"]),
            ("engineering_velocity", "Engineering Velocity", "deployments per week",
             "deployments / weeks", "deployments/week", ["organization_id", "repository_id"]),
            ("deployment_reliability", "Deployment Reliability", "deployment success ratio",
             "successful_deployments / total_deployments", "ratio", ["organization_id", "environment_id"]),
            ("security_health", "Security Health", "inverse of open critical findings",
             "1 - open_critical / total_findings", "score", ["organization_id"]),
            ("technical_debt", "Technical Debt", "debt units from analysis events",
             "sum(debt_units)", "units", ["organization_id", "repository_id"]),
            ("ai_cost", "AI Cost", "sum of AI usage costs",
             "sum(cost)", "currency", ["organization_id", "month"]),
            ("ai_roi", "AI ROI", "engineering value saved / AI cost",
             "estimated_value / ai_cost", "ratio", ["organization_id"]),
            ("knowledge_growth", "Knowledge Growth", "new knowledge artifacts per month",
             "count(knowledge_artifacts)", "artifacts", ["organization_id", "month"]),
        ]
        for (key, name, desc, formula, unit, dims) in defs:
            self.registry.register(name=key, description=desc, formula=formula,
                                   unit=unit, dimensions=dims, data_source="warehouse")

    def evaluate(self, metric: str, context: dict) -> float:
        """Deterministic evaluation of registered metric formulas."""
        m = self.metrics().get(metric)
        if not m:
            raise KeyError(f"unknown metric: {metric}")
        formula = m.formula.replace(" ", "")
        value = context.get(metric)
        scope = context.get("scope", {})
        if metric == "ai_productivity":
            requests = sum(r.get("requests", 0) for r in scope.get("ai_rows", []))
            developers = max(1, scope.get("active_developers", 1))
            return round(requests / developers, 4)
        if metric == "deployment_reliability":
            total = scope.get("total_deployments", 0)
            return round(scope.get("successful_deployments", 0) / max(1, total), 4)
        if metric == "security_health":
            return round(1 - scope.get("open_critical", 0) / max(1, scope.get("total_openings", 1)), 4)
        if metric == "ai_cost":
            return round(sum(r.get("cost", 0.0) for r in scope.get("cost_rows", [])), 4)
        if metric == "repository_health":
            h = scope
            return round(0.25 * h.get("build_health", 0) + 0.25 * h.get("pr_health", 0) +
                         0.25 * h.get("test_health", 0) + 0.25 * h.get("security_health", 0), 4)
        if metric == "engineering_velocity":
            return round(scope.get("deployments", 0) / max(1, scope.get("days", 1)), 4)
        if metric == "technical_debt":
            return round(sum(r.get("debt_units", 0) for r in scope.get("debt_rows", [])), 4)
        if metric == "ai_roi":
            est = scope.get("estimated_value", 0.0)
            cost = scope.get("ai_cost", 1.0)
            return round(est / max(0.01, cost), 4)
        if metric == "knowledge_growth":
            return round(len(scope.get("knowledge_rows", [])), 4)
        return 0.0

    def metrics(self) -> dict:
        return {m.name: m for m in self.registry.metrics.values()}

    def render(self) -> list[dict]:
        return self.registry.list()