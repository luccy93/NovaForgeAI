"""AI Software Quality Engine -- Quality Gate Engine (Volume 48).

Evaluates configurable rules against review results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.quality.config import DEFAULT_GATE_RULES, SEVERITY_WEIGHTS


@dataclass
class GateResult:
    rule_type: str
    passed: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class GateEvaluation:
    verdict: str  # pass/fail/block
    results: list[GateResult] = field(default_factory=list)
    failures: list[GateResult] = field(default_factory=list)
    score: float = 0.0
    duration_ms: int = 0


class QualityGateEngine:
    """Evaluate quality gates against review findings and scores."""

    def __init__(self, rules: list[dict[str, Any]] | None = None):
        self.rules = rules or list(DEFAULT_GATE_RULES)

    def evaluate(
        self,
        findings: list[dict[str, Any]],
        quality_scores: dict[str, float] | None = None,
        breaking_changes: list[dict[str, Any]] | None = None,
        tests_pass: bool | None = None,
    ) -> GateEvaluation:
        results: list[GateResult] = []
        failures: list[GateResult] = []
        should_block = False

        severity_counts: dict[str, int] = {}
        for f in findings:
            sev = f.get("severity", "info")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        for rule in self.rules:
            if not rule.get("enabled", True):
                continue
            result = self._evaluate_rule(
                rule, severity_counts, quality_scores or {},
                breaking_changes or [], tests_pass,
            )
            results.append(result)
            if not result.passed:
                failures.append(result)
                if rule.get("severity", "high") == "critical":
                    should_block = True

        verdict = "pass"
        if failures:
            verdict = "block" if should_block else "fail"

        score = self._compute_gate_score(results)

        return GateEvaluation(
            verdict=verdict,
            results=results,
            failures=failures,
            score=score,
        )

    def _evaluate_rule(
        self,
        rule: dict[str, Any],
        severity_counts: dict[str, int],
        quality_scores: dict[str, float],
        breaking_changes: list[dict[str, Any]],
        tests_pass: bool | None,
    ) -> GateResult:
        rule_type = rule.get("rule_type", "")
        params = rule.get("params", {})

        if rule_type == "max_findings":
            return self._check_max_findings(rule, severity_counts, params)
        elif rule_type == "min_score":
            return self._check_min_score(rule, quality_scores, params)
        elif rule_type == "no_breaking_changes":
            return self._check_no_breaking(rule, breaking_changes)
        elif rule_type == "tests_must_pass":
            return self._check_tests(rule, tests_pass)
        elif rule_type == "max_risk_score":
            return self._check_max_risk(rule, quality_scores, params)
        else:
            return GateResult(
                rule_type=rule_type, passed=True,
                message=f"Unknown rule type: {rule_type}",
            )

    def _check_max_findings(
        self, rule: dict, severity_counts: dict[str, int], params: dict
    ) -> GateResult:
        target_severity = params.get("severity", "critical")
        max_count = params.get("max_count", 0)
        actual = severity_counts.get(target_severity, 0)
        passed = actual <= max_count
        return GateResult(
            rule_type="max_findings",
            passed=passed,
            message=f"{target_severity} findings: {actual}/{max_count}",
            details={"severity": target_severity, "actual": actual, "max": max_count},
        )

    def _check_min_score(
        self, rule: dict, quality_scores: dict[str, float], params: dict
    ) -> GateResult:
        dimension = params.get("dimension", "overall")
        min_value = params.get("min_value", 0.6)
        actual = quality_scores.get(dimension, 0.0)
        passed = actual >= min_value
        return GateResult(
            rule_type="min_score",
            passed=passed,
            message=f"{dimension} score: {actual:.3f}/{min_value:.3f}",
            details={"dimension": dimension, "actual": actual, "min": min_value},
        )

    def _check_no_breaking(
        self, rule: dict, breaking_changes: list[dict]
    ) -> GateResult:
        count = len(breaking_changes)
        passed = count == 0
        return GateResult(
            rule_type="no_breaking_changes",
            passed=passed,
            message=f"Breaking changes: {count}",
            details={"count": count, "changes": breaking_changes[:5]},
        )

    def _check_tests(self, rule: dict, tests_pass: bool | None) -> GateResult:
        passed = tests_pass is True
        return GateResult(
            rule_type="tests_must_pass",
            passed=passed,
            message="Tests passed" if passed else "Tests failed or not run",
            details={"tests_pass": tests_pass},
        )

    def _check_max_risk(
        self, rule: dict, quality_scores: dict[str, float], params: dict
    ) -> GateResult:
        max_risk = params.get("max_risk", 0.7)
        actual = quality_scores.get("risk_score", 0.0)
        passed = actual <= max_risk
        return GateResult(
            rule_type="max_risk_score",
            passed=passed,
            message=f"Risk score: {actual:.3f}/{max_risk:.3f}",
            details={"actual": actual, "max": max_risk},
        )

    def _compute_gate_score(self, results: list[GateResult]) -> float:
        if not results:
            return 1.0
        passed = sum(1 for r in results if r.passed)
        return round(passed / len(results), 4)
