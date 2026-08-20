"""Integration tests for the full review pipeline (Volume 48)."""

import pytest

from app.quality.analyzers.base import ReviewContext
from app.quality.config import ReviewConfig
from app.quality.pipeline import ReviewPipeline
from app.quality.context_retrieval import ContextBuilder
from app.quality.diff_parser import DiffParser, ChangeSet
from app.quality.baseline import BaselineService
from app.quality.remediation import RemediationService
from app.quality.test_generation import TestGenerator
from app.quality.historical import HistoricalAnalyzer
from app.quality.prompt_versioning import PromptVersionManager
from app.quality.cost_tracker import CostTracker, BudgetLimits


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_quick_review():
    pipeline = ReviewPipeline()
    ctx = ReviewContext(
        tenant="test", repo_id="org/repo",
        file_contents={"app.py": "def hello():\n    return 'world'"},
        changed_files=["app.py"],
        review_mode="quick",
    )
    config = ReviewConfig.from_mode("quick")
    result = await pipeline.run_review(ctx, config)
    assert result.status == "completed"
    assert isinstance(result.quality_scores, dict)
    assert isinstance(result.risk_score, float)


@pytest.mark.asyncio
async def test_pipeline_finds_issues():
    pipeline = ReviewPipeline()
    code = "try:\n    pass\nexcept:\n    pass\nimport os\nimport sys"
    ctx = ReviewContext(
        tenant="test", repo_id="r1",
        file_contents={"app.py": code},
        changed_files=["app.py"],
        review_mode="standard",
    )
    result = await pipeline.run_review(ctx)
    assert len(result.deduplicated) > 0
    assert result.quality_scores.get("overall", 1.0) < 1.0


@pytest.mark.asyncio
async def test_pipeline_gate_block():
    pipeline = ReviewPipeline()
    critical_code = "\n".join(["except:\n    pass"] * 5)
    ctx = ReviewContext(
        tenant="test", repo_id="r1",
        file_contents={"app.py": critical_code},
        changed_files=["app.py"],
    )
    gate_rules = [{"rule_type": "max_findings", "params": {"severity": "medium", "max_count": 2}, "severity": "critical"}]
    result = await pipeline.run_review(ctx, gate_rules=gate_rules)
    assert result.gate_result["verdict"] in ("fail", "block")


@pytest.mark.asyncio
async def test_pipeline_dedup_and_correlate():
    pipeline = ReviewPipeline()
    code = "import os\nimport sys\ntry:\n    pass\nexcept:\n    pass"
    ctx = ReviewContext(
        tenant="test", repo_id="r1",
        file_contents={"app.py": code},
        changed_files=["app.py"],
    )
    result = await pipeline.run_review(ctx)
    assert len(result.findings) >= len(result.deduplicated)


# ---------------------------------------------------------------------------
# Context Builder
# ---------------------------------------------------------------------------

def test_context_builder_from_files():
    builder = ContextBuilder()
    ctx = builder.build_from_files(
        tenant="test", repo_id="r1",
        file_contents={"app.py": "x = 1"},
        changed_files=["app.py"],
    )
    assert ctx.tenant == "test"
    assert "app.py" in ctx.file_contents


def test_context_builder_limit_by_budget():
    builder = ContextBuilder()
    files = {f"file{i}.py": f"x = {i}" for i in range(100)}
    ctx = builder.build_from_files(tenant="test", repo_id="r1", file_contents=files)
    ctx = builder.limit_by_budget(ctx, max_files=5, max_tokens=1000)
    assert len(ctx.changed_files) <= 5


# ---------------------------------------------------------------------------
# Diff Parser
# ---------------------------------------------------------------------------

def test_diff_parser_parse():
    parser = DiffParser()
    diff = "diff --git a/app.py b/app.py\n+new line\n-old line"
    cs = parser.parse_diff_text(diff)
    assert cs.total_changed >= 1


def test_diff_parser_analyze():
    parser = DiffParser()
    cs = ChangeSet(
        modified=[{"file_path": "app.py", "change_type": "MODIFIED"}],
    )
    # Create a proper ChangeSet
    from app.quality.diff_parser import FileChange
    cs = ChangeSet(
        modified=[FileChange(file_path="app.py", change_type="MODIFIED")],
    )
    analysis = parser.analyze_changes(cs)
    assert "total_files_changed" in analysis
    assert "risk_factors" in analysis


def test_diff_parser_scope_factor():
    parser = DiffParser()
    from app.quality.diff_parser import FileChange
    cs = ChangeSet(modified=[FileChange(file_path=f"f{i}.py", change_type="MODIFIED") for i in range(20)])
    factor = parser.compute_change_scope_factor(cs)
    assert factor > 1.0


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------

def test_baseline_create_and_get():
    svc = BaselineService()
    b = svc.create(tenant="t", repo_id="r", name="v1", snapshot={"scores": {"overall": 0.9}})
    assert b["name"] == "v1"
    got = svc.get(tenant="t", repo_id="r", name="v1")
    assert got is not None
    assert got["snapshot"]["scores"]["overall"] == 0.9


def test_baseline_diff():
    svc = BaselineService()
    b1 = svc.create(tenant="t", repo_id="r", name="old", snapshot={"quality_scores": {"overall": 0.9}, "total_findings": 5})
    b2 = svc.create(tenant="t", repo_id="r", name="new", snapshot={"quality_scores": {"overall": 0.7}, "total_findings": 10})
    diff = svc.diff(b1, b2)
    assert diff.finding_delta == 5
    assert len(diff.regressions) >= 1
    assert "overall" in diff.regressions[0].lower()


# ---------------------------------------------------------------------------
# Remediation
# ---------------------------------------------------------------------------

def test_remediation_lifecycle():
    svc = RemediationService()
    r = svc.propose(finding_id="f1", patch_diff="diff")
    assert r.status == "proposed"
    r = svc.validate(r.remediation_id, syntax_valid=True, imports_valid=True, security_clean=True)
    assert r.status == "validated"
    r = svc.apply(r.remediation_id, commit_sha="abc")
    assert r.status == "applied"
    r = svc.verify(r.remediation_id, issue_resolved=True, tests_pass=True, re_scan_clean=True)
    assert r.status == "verified"


def test_remediation_validate_fail():
    svc = RemediationService()
    r = svc.propose(finding_id="f1")
    r = svc.validate(r.remediation_id, syntax_valid=False, imports_valid=True, security_clean=True)
    assert r.status == "failed"


# ---------------------------------------------------------------------------
# Test Generation
# ---------------------------------------------------------------------------

def test_test_generation_proposals():
    gen = TestGenerator()
    findings = [
        {"id": "f1", "confidence": 0.8, "category": "correctness",
         "file_path": "a.py", "symbol": "func", "severity": "high",
         "description": "Bug"},
    ]
    proposals = gen.propose_tests(findings)
    assert len(proposals) == 1
    assert proposals[0].test_type == "failure_path"


def test_test_generation_low_confidence():
    gen = TestGenerator()
    findings = [{"id": "f1", "confidence": 0.3, "category": "correctness",
                 "file_path": "a.py", "symbol": "func", "severity": "low",
                 "description": "Minor"}]
    proposals = gen.propose_tests(findings)
    assert len(proposals) == 0


def test_test_select_for_changes():
    gen = TestGenerator()
    selected = gen.select_tests_for_changes(
        changed_files=["src/auth.py"],
        all_test_files=["tests/test_auth.py", "tests/test_utils.py", "tests/test_models.py"],
    )
    assert "tests/test_auth.py" in selected


# ---------------------------------------------------------------------------
# Historical
# ---------------------------------------------------------------------------

def test_historical_record_and_trends():
    svc = HistoricalAnalyzer()
    svc.record_review("t", "r", {"id": "r1", "quality_scores": {"overall": 0.9}, "risk_score": 0.1}, [])
    svc.record_review("t", "r", {"id": "r2", "quality_scores": {"overall": 0.8}, "risk_score": 0.2}, [])
    trends = svc.get_trends("t", "r")
    assert len(trends) == 2


def test_historical_hotspots():
    svc = HistoricalAnalyzer()
    svc.record_review("t", "r", {"id": "r1"}, [
        {"file_path": "app.py", "severity": "high"},
        {"file_path": "app.py", "severity": "critical"},
    ])
    hotspots = svc.get_hotspots("t", "r")
    assert len(hotspots) >= 1
    assert hotspots[0]["defect_count"] >= 1


# ---------------------------------------------------------------------------
# Prompt Versioning
# ---------------------------------------------------------------------------

def test_prompt_versioning():
    mgr = PromptVersionManager()
    v = mgr.register_version("2.0", "new prompt text", model_id="gpt-4")
    assert v.version == "2.0"
    assert v.prompt_hash
    active = mgr.get_active_version()
    assert active.version == "1.0"
    mgr.set_active("2.0")
    assert mgr.get_active_version().version == "2.0"


# ---------------------------------------------------------------------------
# Cost Tracker
# ---------------------------------------------------------------------------

def test_cost_tracker_budget():
    tracker = CostTracker(BudgetLimits(max_tokens=100, max_cost_usd=0.01))
    tracker.start_tracking("r1")
    tracker.record_tokens("r1", 50)
    assert tracker.is_within_budget("r1")
    tracker.record_tokens("r1", 60)
    assert not tracker.is_within_budget("r1")
    report = tracker.check_budget("r1")
    assert report["exceeded"]


def test_cost_tracker_remaining():
    tracker = CostTracker(BudgetLimits(max_tokens=100))
    tracker.start_tracking("r1")
    tracker.record_tokens("r1", 30)
    remaining = tracker.get_remaining_budget("r1")
    assert remaining["tokens"] == 70
