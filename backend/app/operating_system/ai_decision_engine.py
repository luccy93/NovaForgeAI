"""AI Decision Engine — structured decisions with evidence, confidence, alternatives, trade-offs, business impact, engineering impact, risk, effort, rollback."""

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Callable


@dataclass
class DecisionAlternative:
    name: str
    description: str
    pros: list[str] = field(default_factory=list)
    cons: list[str] = field(default_factory=list)
    effort_hours: float = 0.0
    risk: str = "medium"
    confidence: float = 0.5


@dataclass
class DecisionTradeoff:
    dimension: str  # cost, time, quality, scope, risk, maintainability, performance
    impact: str  # positive, negative, neutral
    magnitude: float  # 1-10
    description: str = ""


@dataclass
class Decision:
    id: str
    title: str
    context: str
    evidence: str
    recommendation: str
    confidence: float
    alternatives: list[DecisionAlternative] = field(default_factory=list)
    tradeoffs: list[DecisionTradeoff] = field(default_factory=list)
    business_impact: str = ""
    engineering_impact: str = ""
    risk: str = "medium"
    estimated_effort_hours: float = 0.0
    estimated_effort: str = ""
    rollback_strategy: str = ""
    status: str = "pending"  # pending, approved, rejected, implemented
    made_by: str = ""
    made_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DecisionReport:
    repo_id: str
    repo_name: str
    timestamp: str
    decisions: list[Decision] = field(default_factory=list)
    pending_count: int = 0
    approved_count: int = 0
    rejected_count: int = 0
    implemented_count: int = 0
    high_risk_count: int = 0
    avg_confidence: float = 0.0
    recommendations: list[str] = field(default_factory=list)


class AIDecisionEngine:
    """Structured decision-making engine — evaluates evidence, alternatives, trade-offs, and recommends optimal paths."""

    def __init__(self, repo_path: str = ""):
        self.repo_path = Path(repo_path) if repo_path else Path()
        self.decisions: dict[str, Decision] = {}

    def evaluate(self, title: str, context: str, evidence: str,
                 alternatives: list[DecisionAlternative] = None,
                 tradeoffs: list[DecisionTradeoff] = None,
                 business_impact: str = "", engineering_impact: str = "",
                 risk: str = "medium", effort_hours: float = 0.0,
                 rollback: str = "") -> Decision:
        decision = Decision(
            id=f"dec-{uuid.uuid4().hex[:12]}",
            title=title, context=context, evidence=evidence,
            recommendation=self._generate_recommendation(alternatives or [], tradeoffs or []),
            confidence=self._calculate_confidence(alternatives or [], tradeoffs or []),
            alternatives=alternatives or [],
            tradeoffs=tradeoffs or [],
            business_impact=business_impact,
            engineering_impact=engineering_impact,
            risk=risk,
            estimated_effort_hours=effort_hours,
            estimated_effort=self._format_effort(effort_hours),
            rollback_strategy=rollback or "Revert changes via version control",
            made_at=datetime.now(timezone.utc).isoformat(),
        )
        self.decisions[decision.id] = decision
        return decision

    def _generate_recommendation(self, alternatives: list[DecisionAlternative],
                                 tradeoffs: list[DecisionTradeoff]) -> str:
        if not alternatives:
            return "Proceed with the described approach"
        scored = []
        for alt in alternatives:
            score = alt.confidence * 10
            score -= {"low": 1, "medium": 3, "high": 6}.get(alt.risk, 3)
            score -= alt.effort_hours * 0.1
            scored.append((score, alt))
        scored.sort(key=lambda x: -x[0])
        return f"Recommended: {scored[0][1].name} — {scored[0][1].description[:100]}..." if scored else "No clear recommendation"

    def _calculate_confidence(self, alternatives: list[DecisionAlternative],
                               tradeoffs: list[DecisionTradeoff]) -> float:
        if not alternatives:
            return 0.5
        avg_alt_conf = sum(a.confidence for a in alternatives) / len(alternatives)
        has_tradeoffs = 0.2 if tradeoffs else 0.0
        return round(min(0.95, avg_alt_conf + has_tradeoffs), 2)

    def _format_effort(self, hours: float) -> str:
        if hours < 1:
            return f"{int(hours * 60)} minutes"
        if hours < 8:
            return f"{hours} hours"
        if hours < 40:
            return f"{hours / 8:.1f} days"
        return f"{hours / 40:.1f} weeks"

    def approve(self, decision_id: str, approved: bool = True, by: str = "") -> bool:
        decision = self.decisions.get(decision_id)
        if not decision:
            return False
        decision.status = "approved" if approved else "rejected"
        decision.made_by = by
        return True

    def implement(self, decision_id: str) -> bool:
        decision = self.decisions.get(decision_id)
        if not decision:
            return False
        decision.status = "implemented"
        return True

    def analyze_decision_quality(self, decision: Decision) -> dict:
        quality_checks = {
            "has_evidence": bool(decision.evidence and len(decision.evidence) > 20),
            "has_alternatives": len(decision.alternatives) >= 2,
            "has_tradeoffs": len(decision.tradeoffs) > 0,
            "has_business_impact": bool(decision.business_impact),
            "has_engineering_impact": bool(decision.engineering_impact),
            "has_risk_assessment": decision.risk in ("low", "medium", "high", "critical"),
            "has_effort_estimate": decision.estimated_effort_hours > 0,
            "has_rollback": bool(decision.rollback_strategy),
            "has_confidence": decision.confidence > 0,
        }
        passed = sum(1 for v in quality_checks.values() if v)
        total = len(quality_checks)
        return {
            "score": round(passed / total * 100, 1),
            "passed_checks": passed,
            "total_checks": total,
            "details": quality_checks,
        }

    def generate_report(self) -> DecisionReport:
        report = DecisionReport(
            repo_id=str(hash(str(self.repo_path))),
            repo_name=self.repo_path.name,
            timestamp=datetime.now(timezone.utc).isoformat(),
            decisions=list(self.decisions.values()),
            pending_count=sum(1 for d in self.decisions.values() if d.status == "pending"),
            approved_count=sum(1 for d in self.decisions.values() if d.status == "approved"),
            rejected_count=sum(1 for d in self.decisions.values() if d.status == "rejected"),
            implemented_count=sum(1 for d in self.decisions.values() if d.status == "implemented"),
            high_risk_count=sum(1 for d in self.decisions.values() if d.risk in ("high", "critical")),
        )

        if self.decisions:
            report.avg_confidence = round(
                sum(d.confidence for d in self.decisions.values()) / len(self.decisions), 2
            )

        pending = [d for d in self.decisions.values() if d.status == "pending"]
        if pending:
            report.recommendations.append(f"Review {len(pending)} pending decisions")
        if report.high_risk_count > 0:
            report.recommendations.append(f"Review {report.high_risk_count} high-risk decisions")

        return report


from pathlib import Path  # noqa: E402
