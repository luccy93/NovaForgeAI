"""Code-domain evaluation (Volume 34).

Metrics for code generation, repair, review, security analysis, test
generation, documentation and architecture evaluation. All checks are
rule-based and deterministic (no external compilers required).
"""
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


def _count_definitions(code: str) -> int:
    return len(re.findall(r"^\s*(def|class|function|const|let|var|func|type)\s+", code, re.M))


def code_generation_report(expected_code: str, actual_code: str,
                           tests_pass: Optional[bool] = None,
                           has_security_issues: bool = False,
                           complexity_delta: float = 0.0) -> dict:
    """Evaluate generated code: compilation shape, tests, correctness,
    maintainability, complexity and regression risk."""
    expected_tokens = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", expected_code))
    actual_tokens = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", actual_code))
    overlap = len(expected_tokens & actual_tokens)
    recall = overlap / len(expected_tokens) if expected_tokens else 0.0
    precision = overlap / len(actual_tokens) if actual_tokens else 0.0
    correctness = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    expected_defs = _count_definitions(expected_code)
    actual_defs = _count_definitions(actual_code)
    maintainability = 1.0 - min(1.0, abs(actual_defs - expected_defs) / max(1, expected_defs))
    style = 1.0 if (len(actual_code.splitlines()) > 1 and
                    re.search(r"^import |^from |^require\(|^using ", actual_code, re.M)) else 0.6
    security = 0.0 if has_security_issues else 1.0
    if tests_pass is None:
        tests_pass = recall >= 0.5
    regression_risk = 1.0 - correctness
    return {
        "compilation": 1.0 if actual_code.strip() else 0.0,
        "tests_pass": 1.0 if tests_pass else 0.0,
        "correctness": round(correctness, 4),
        "security": security,
        "maintainability": round(maintainability, 4),
        "style": round(style, 4),
        "complexity": round(1.0 - abs(complexity_delta), 4),
        "regression_risk": round(regression_risk, 4),
        "overall": round((correctness * 0.4 + (1.0 if tests_pass else 0.0) * 0.3
                          + security * 0.2 + maintainability * 0.1), 4),
    }


def code_repair_report(bug_fixed: bool, tests_passing: bool,
                       regression: bool = False, minimality: float = 1.0,
                       security_ok: bool = True, time_to_resolution_ms: float = 0.0) -> dict:
    """Code repair: fix rate, regression rate, minimality, security."""
    return {
        "bug_fix_rate": 1.0 if bug_fixed else 0.0,
        "tests_passing": 1.0 if tests_passing else 0.0,
        "regression_rate": 1.0 if regression else 0.0,
        "minimality": round(minimality, 4),
        "security": 1.0 if security_ok else 0.0,
        "time_to_resolution_ms": time_to_resolution_ms,
        "overall": round((bug_fixed * 0.5 + tests_passing * 0.3
                          + (0.0 if regression else 1.0) * 0.1
                          + security_ok * 0.1), 4),
    }


def code_review_report(findings: list[dict], real_issues: list[str],
                       accepted_findings: Optional[list[str]] = None) -> dict:
    """Code review: precision, recall, severity accuracy, actionability."""
    total_findings = len(findings)
    true_positives = [f for f in findings
                      if _issue_key(f) in real_issues or f.get("issue") in real_issues]
    false_positives = total_findings - len(true_positives)
    all_issues = set(real_issues)
    detected_keys = {_issue_key(f) for f in findings} | {f.get("issue", "") for f in findings}
    false_negatives = len(all_issues - detected_keys)
    precision = len(true_positives) / total_findings if total_findings else 0.0
    recall = len(true_positives) / len(all_issues) if all_issues else (1.0 if not findings else 0.0)
    severity_accuracy = 0.0
    if true_positives:
        severity_accuracy = sum(
            1.0 for f in true_positives if _severity_ok(f)) / len(true_positives)
    if accepted_findings is None:
        actionability = precision
    else:
        actionability = (len([f for f in findings
                              if _issue_key(f) in accepted_findings]) /
                         total_findings if total_findings else 0.0)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "finding_precision": round(precision, 4),
        "finding_recall": round(recall, 4),
        "f1": round(f1, 4),
        "false_positive_rate": round(false_positives / total_findings, 4) if total_findings else 0.0,
        "false_negative_rate": round(false_negatives / len(all_issues), 4) if all_issues else 0.0,
        "severity_accuracy": round(severity_accuracy, 4),
        "actionability": round(actionability, 4),
        "overall": round((f1 * 0.4 + severity_accuracy * 0.3 + actionability * 0.3), 4),
    }


def security_eval_report(vulnerabilities: list[str], real_vulnerabilities: list[str],
                         remediations: Optional[list[dict]] = None) -> dict:
    """AI security evaluation: detection precision/recall, remediation quality."""
    detected = set(vulnerabilities)
    real = set(real_vulnerabilities)
    true_positives = detected & real
    precision = len(true_positives) / len(detected) if detected else 0.0
    recall = len(true_positives) / len(real) if real else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    remediation_quality = 0.0
    if remediations:
        remediation_quality = sum(
            1.0 for r in remediations if r.get("correct")) / len(remediations)
    return {
        "detection_precision": round(precision, 4),
        "detection_recall": round(recall, 4),
        "false_positive_rate": round((len(detected) - len(true_positives)) / len(detected), 4) if detected else 0.0,
        "false_negative_rate": round((len(real) - len(true_positives)) / len(real), 4) if real else 0.0,
        "severity_classification": round(sum(
            1.0 for v in true_positives if v) / len(true_positives), 4) if true_positives else 0.0,
        "remediation_quality": round(remediation_quality, 4),
        "overall": round((f1 * 0.5 + remediation_quality * 0.5), 4),
    }


def build_test_generation_report(coverage_delta: float, mutation_score: float,
                           bug_detected: bool, tests_correct: bool = True,
                           flaky: bool = False) -> dict:
    """Test generation: coverage improvement, mutation score, flakiness."""
    return {
        "coverage_improvement": round(max(0.0, min(1.0, coverage_delta)), 4),
        "mutation_score": round(max(0.0, min(1.0, mutation_score)), 4),
        "bug_detection": 1.0 if bug_detected else 0.0,
        "test_correctness": 1.0 if tests_correct else 0.0,
        "flakiness": 1.0 if flaky else 0.0,
        "overall": round((max(0.0, min(1.0, coverage_delta)) * 0.3 +
                          max(0.0, min(1.0, mutation_score)) * 0.3 +
                          (1.0 if bug_detected else 0.0) * 0.3 +
                          (0.0 if flaky else 1.0) * 0.1), 4),
    }


def documentation_report(accuracy: float, completeness: float,
                         code_alignment: float, freshness: float,
                         clarity: float, broken_links: int = 0,
                         missing_sections: int = 0) -> dict:
    """Documentation quality evaluation."""
    return {
        "accuracy": round(accuracy, 4),
        "completeness": round(completeness, 4),
        "code_alignment": round(code_alignment, 4),
        "freshness": round(freshness, 4),
        "clarity": round(clarity, 4),
        "broken_links": broken_links,
        "missing_sections": missing_sections,
        "overall": round((accuracy * 0.25 + completeness * 0.2 + code_alignment * 0.2 +
                          freshness * 0.15 + clarity * 0.2 -
                          min(0.2, broken_links * 0.02) - min(0.2, missing_sections * 0.03)), 4),
    }


def architecture_report(understanding: float, dependency_identification: float,
                        component_identification: float, data_flow: float,
                        drift_detected: bool = False,
                        recommendation_quality: float = 0.5) -> dict:
    """Architecture evaluation: understanding, drift detection, recommendations."""
    return {
        "architecture_understanding": round(understanding, 4),
        "dependency_identification": round(dependency_identification, 4),
        "component_identification": round(component_identification, 4),
        "data_flow_understanding": round(data_flow, 4),
        "architecture_drift": 1.0 if drift_detected else 0.0,
        "recommendation_quality": round(recommendation_quality, 4),
        "overall": round((understanding * 0.25 + dependency_identification * 0.2 +
                          component_identification * 0.2 + data_flow * 0.2 +
                          (1.0 if not drift_detected else 0.0) * 0.05 +
                          recommendation_quality * 0.1), 4),
    }


def _issue_key(finding: dict) -> str:
    return str(finding.get("id") or finding.get("key") or finding.get("issue", ""))


def _severity_ok(finding: dict) -> bool:
    expected = finding.get("expected_severity")
    actual = finding.get("severity")
    return expected is None or expected == actual
