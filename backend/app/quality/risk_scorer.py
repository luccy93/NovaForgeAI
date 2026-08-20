"""AI Software Quality Engine -- Risk Scoring (Volume 48).

Composite risk scoring from severity weights, confidence, reachability,
asset criticality, and change scope.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.quality.config import RISK_THRESHOLDS, SEVERITY_WEIGHTS


@dataclass
class RiskScore:
    score: float = 0.0
    level: str = "low"
    breakdown: dict[str, float] = field(default_factory=dict)
    factors: list[str] = field(default_factory=list)


class RiskScorer:
    """Compute composite risk from findings and context."""

    def score_findings(
        self,
        findings: list[dict[str, Any]],
        change_scope_factor: float = 1.0,
        asset_criticality: float = 0.5,
    ) -> RiskScore:
        if not findings:
            return RiskScore(score=0.0, level="low", factors=["no_findings"])

        severity_total = 0.0
        confidence_total = 0.0
        count = len(findings)

        severity_counts: dict[str, int] = {}
        for f in findings:
            sev = f.get("severity", "info")
            conf = f.get("confidence", 0.5)
            weight = SEVERITY_WEIGHTS.get(sev, 1.0)
            severity_total += weight * conf
            confidence_total += conf
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        avg_confidence = confidence_total / count
        max_possible = count * 10.0
        raw_score = severity_total / max(max_possible, 1.0)

        adjusted = raw_score * change_scope_factor * (0.5 + 0.5 * asset_criticality)
        adjusted = min(1.0, max(0.0, adjusted))

        level = "low"
        for threshold_name, threshold_val in sorted(
            RISK_THRESHOLDS.items(), key=lambda x: x[1], reverse=True
        ):
            if adjusted >= threshold_val:
                level = threshold_name
                break

        factors: list[str] = []
        if severity_counts.get("critical", 0) > 0:
            factors.append(f"{severity_counts['critical']} critical findings")
        if severity_counts.get("high", 0) > 0:
            factors.append(f"{severity_counts['high']} high findings")
        if avg_confidence > 0.8:
            factors.append("high average confidence")
        if change_scope_factor > 1.5:
            factors.append("large change scope")
        if asset_criticality > 0.8:
            factors.append("high asset criticality")
        if not factors:
            factors.append("low overall risk")

        breakdown = {
            "severity_component": raw_score,
            "change_scope_factor": change_scope_factor,
            "asset_criticality": asset_criticality,
            "avg_confidence": avg_confidence,
        }

        return RiskScore(
            score=round(adjusted, 4),
            level=level,
            breakdown=breakdown,
            factors=factors,
        )

    def score_review(self, finding_scores: dict[str, float], weights: dict[str, float] | None = None) -> float:
        if not finding_scores:
            return 0.0
        if weights is None:
            weights = {k: 1.0 for k in finding_scores}
        total_weight = sum(weights.get(k, 1.0) for k in finding_scores)
        if total_weight == 0:
            return 0.0
        weighted = sum(finding_scores[k] * weights.get(k, 1.0) for k in finding_scores)
        return round(weighted / total_weight, 4)
