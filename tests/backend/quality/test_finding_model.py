"""Finding model, dedup, risk scoring, correlation, gates tests (Volume 48)."""

from app.quality.finding_model import (
    FindingData, validate_finding, transition_status, severity_weight,
)
from app.quality.dedup import FindingDeduplicator
from app.quality.risk_scorer import RiskScorer
from app.quality.correlation import FindingCorrelator
from app.quality.gates import QualityGateEngine


# ---------------------------------------------------------------------------
# Finding Model
# ---------------------------------------------------------------------------

def test_finding_creation():
    f = FindingData(
        category="correctness", severity="high", confidence=0.8,
        file_path="app.py", line_start=10, line_end=12,
        symbol="my_func", description="Logic error",
        evidence={"line": "if x:"}, rule_id="correctness.logic",
    )
    assert f.category == "correctness"
    assert f.severity == "high"
    assert f.confidence == 0.8
    assert f.finding_hash


def test_finding_validation_valid():
    f = FindingData(
        category="security", severity="critical", confidence=0.9,
        file_path="auth.py", line_start=5, line_end=5,
        symbol="", description="Hardcoded secret",
        evidence={"line": "password = 'abc'"},
    )
    errors = validate_finding(f)
    assert errors == []


def test_finding_validation_no_evidence():
    f = FindingData(
        category="correctness", severity="medium", confidence=0.5,
        file_path="a.py", line_start=1, line_end=1,
        symbol="", description="Issue", evidence={},
    )
    errors = validate_finding(f)
    assert any("evidence" in e for e in errors)


def test_finding_confidence_clamp():
    f = FindingData(
        category="correctness", severity="low", confidence=1.5,
        file_path="a.py", line_start=0, line_end=0,
        symbol="", description="Test", evidence={"x": 1},
    )
    assert f.confidence == 1.0


def test_severity_weight():
    assert severity_weight("critical") == 10.0
    assert severity_weight("info") == 1.0


def test_status_transitions():
    assert transition_status("open", "acknowledged")
    assert transition_status("open", "in_progress")
    assert not transition_status("verified", "open")
    assert transition_status("false_positive", "open")
    assert transition_status("reopened", "in_progress")


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def test_dedup_merge():
    dedup = FindingDeduplicator()
    findings = [
        {"category": "correctness", "severity": "high", "confidence": 0.8,
         "file_path": "a.py", "line_start": 10, "line_end": 10,
         "description": "Bug here", "rule_id": "r1", "source": "sast"},
        {"category": "correctness", "severity": "medium", "confidence": 0.6,
         "file_path": "a.py", "line_start": 10, "line_end": 10,
         "description": "Bug here", "rule_id": "r1", "source": "ai_review"},
    ]
    groups = dedup.deduplicate(findings)
    assert len(groups) == 1
    assert groups[0].merged_severity == "high"
    assert "sast" in groups[0].sources
    assert "ai_review" in groups[0].sources


def test_dedup_no_merge_different_desc():
    dedup = FindingDeduplicator()
    findings = [
        {"category": "correctness", "severity": "high", "confidence": 0.8,
         "file_path": "a.py", "line_start": 10, "line_end": 10,
         "description": "Bug A", "rule_id": "r1", "source": "sast"},
        {"category": "correctness", "severity": "high", "confidence": 0.8,
         "file_path": "a.py", "line_start": 10, "line_end": 10,
         "description": "Bug B", "rule_id": "r2", "source": "sast"},
    ]
    groups = dedup.deduplicate(findings)
    assert len(groups) == 2


# ---------------------------------------------------------------------------
# Risk Scorer
# ---------------------------------------------------------------------------

def test_risk_score_no_findings():
    scorer = RiskScorer()
    result = scorer.score_findings([])
    assert result.score == 0.0
    assert result.level == "low"


def test_risk_score_critical():
    scorer = RiskScorer()
    findings = [
        {"severity": "critical", "confidence": 0.9},
        {"severity": "critical", "confidence": 0.8},
    ]
    result = scorer.score_findings(findings)
    assert result.score > 0.5
    assert result.level in ("medium", "high", "critical")


def test_risk_score_low():
    scorer = RiskScorer()
    findings = [{"severity": "info", "confidence": 0.3}]
    result = scorer.score_findings(findings)
    assert result.level == "low"


def test_risk_score_with_scope():
    scorer = RiskScorer()
    findings = [{"severity": "high", "confidence": 0.8}]
    small = scorer.score_findings(findings, change_scope_factor=1.0)
    large = scorer.score_findings(findings, change_scope_factor=2.0)
    assert large.score >= small.score


# ---------------------------------------------------------------------------
# Correlation
# ---------------------------------------------------------------------------

def test_correlation_multi_category():
    correlator = FindingCorrelator()
    findings = [
        {"category": "security", "severity": "high", "confidence": 0.8,
         "file_path": "auth.py", "line_start": 10, "line_end": 10, "source": "sast"},
        {"category": "correctness", "severity": "medium", "confidence": 0.7,
         "file_path": "auth.py", "line_start": 10, "line_end": 10, "source": "ai_review"},
    ]
    groups = correlator.correlate(findings)
    assert len(groups) >= 1
    assert any("security" in g.categories and "correctness" in g.categories for g in groups)


def test_correlation_no_match():
    correlator = FindingCorrelator()
    findings = [
        {"category": "security", "severity": "high", "confidence": 0.8,
         "file_path": "a.py", "line_start": 1, "line_end": 1, "source": "sast"},
        {"category": "documentation", "severity": "low", "confidence": 0.3,
         "file_path": "b.py", "line_start": 1, "line_end": 1, "source": "ai_review"},
    ]
    groups = correlator.correlate(findings)
    assert len(groups) == 0


# ---------------------------------------------------------------------------
# Quality Gates
# ---------------------------------------------------------------------------

def test_gate_pass_no_findings():
    engine = QualityGateEngine()
    result = engine.evaluate(findings=[], quality_scores={"overall": 1.0})
    assert result.verdict == "pass"
    assert result.score == 1.0


def test_gate_fail_critical():
    engine = QualityGateEngine()
    findings = [{"severity": "critical", "confidence": 0.9}]
    result = engine.evaluate(findings=findings, quality_scores={"overall": 0.5})
    assert result.verdict == "block"


def test_gate_fail_low_score():
    engine = QualityGateEngine([{
        "rule_type": "min_score",
        "params": {"dimension": "overall", "min_value": 0.6},
        "severity": "high",
    }])
    result = engine.evaluate(findings=[], quality_scores={"overall": 0.3})
    assert result.verdict == "fail"
