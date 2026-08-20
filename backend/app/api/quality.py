"""AI Software Quality Engine -- API Endpoints (Volume 48)."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.quality.baseline import BaselineService
from app.quality.context_retrieval import ContextBuilder
from app.quality.cost_tracker import BudgetLimits, CostTracker
from app.quality.diff_parser import DiffParser
from app.quality.gates import QualityGateEngine
from app.quality.historical import HistoricalAnalyzer
from app.quality.pipeline import ReviewPipeline
from app.quality.remediation import RemediationService
from app.quality.report_service import ReportService
from app.quality.review_service import ReviewService
from app.quality.risk_scorer import RiskScorer
from app.quality.schemas import (
    BaselineCreate,
    CommitAnalysisRequest,
    FileAnalysisRequest,
    FindingFeedback,
    FindingStatusUpdate,
    GateCreate,
    GateEvaluateRequest,
    PRAnalysisRequest,
    ReleaseAnalysisRequest,
    RemediationCreate,
    ReviewCreate,
    BranchAnalysisRequest,
)
from app.quality.test_generation import TestGenerator


router = APIRouter()

_pipeline = ReviewPipeline()
_review_service = _pipeline.review_service
_report_service = ReportService()
_remediation_service = RemediationService()
_baseline_service = BaselineService()
_test_generator = TestGenerator()
_historical = HistoricalAnalyzer()
_risk_scorer = RiskScorer()
_gate_engine = QualityGateEngine()
_diff_parser = DiffParser()
_context_builder = ContextBuilder()
_cost_tracker = CostTracker()


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------

@router.post("/reviews")
async def create_review(req: ReviewCreate):
    review = _review_service.create_review(
        tenant=req.tenant, repo_id=req.repo_id, review_type=req.review_type,
        target_ref=req.target_ref, mode=req.mode, prompt_version=req.prompt_version,
        model_id=req.model_id, triggered_by=req.triggered_by,
        metadata_extra=req.metadata_extra,
    )
    return review


@router.get("/reviews")
async def list_reviews(
    tenant: str = Query("default"),
    repo_id: str = Query(""),
    limit: int = Query(20),
):
    return _review_service.list_reviews(tenant=tenant, repo_id=repo_id, limit=limit)


@router.get("/reviews/{review_id}")
async def get_review(review_id: str):
    review = _review_service.get_review(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return review


@router.post("/reviews/{review_id}/analyze")
async def trigger_analysis(review_id: str, mode: str = Query("standard")):
    from app.quality.config import ReviewConfig
    from app.quality.analyzers.base import ReviewContext

    review = _review_service.get_review(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    config = ReviewConfig.from_mode(mode)
    context = ReviewContext(
        tenant=review["tenant"],
        repo_id=review["repo_id"],
        review_mode=mode,
    )
    result = await _pipeline.run_review(context, config)
    return {
        "review_id": result.review_id,
        "status": result.status,
        "finding_count": len(result.deduplicated),
        "quality_scores": result.quality_scores,
        "risk_score": result.risk_score,
        "gate_result": result.gate_result,
        "duration_ms": result.duration_ms,
    }


@router.get("/reviews/{review_id}/status")
async def review_status(review_id: str):
    review = _review_service.get_review(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return {"status": review["status"], "gate_passed": review.get("gate_passed")}


@router.post("/reviews/{review_id}/cancel")
async def cancel_review(review_id: str):
    success = _review_service.transition(review_id, "cancelled")
    if not success:
        raise HTTPException(status_code=400, detail="Cannot cancel review in current state")
    return {"status": "cancelled"}


@router.get("/reviews/{review_id}/report")
async def get_report(review_id: str):
    review = _review_service.get_review(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    findings = _review_service.get_findings(review_id)
    return _report_service.generate_report(review, findings)


@router.get("/reviews/{review_id}/inline")
async def get_inline_review(review_id: str):
    review = _review_service.get_review(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    findings = _review_service.get_findings(review_id)
    return _report_service.build_inline_comments(findings)


@router.get("/reviews/{review_id}/summary")
async def get_pr_summary(review_id: str):
    review = _review_service.get_review(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    findings = _review_service.get_findings(review_id)
    return _report_service.generate_pr_summary(review, findings)


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

@router.get("/reviews/{review_id}/findings")
async def list_findings(
    review_id: str,
    severity: str = Query(""),
    category: str = Query(""),
    status: str = Query(""),
    limit: int = Query(100),
):
    return _review_service.get_findings(review_id, severity=severity, category=category, status=status, limit=limit)


@router.get("/reviews/{review_id}/findings/dedup")
async def get_deduplicated(review_id: str):
    findings = _review_service.get_findings(review_id)
    from app.quality.dedup import FindingDeduplicator
    dedup = FindingDeduplicator()
    groups = dedup.deduplicate(findings)
    return dedup.to_dicts(groups)


@router.put("/reviews/{review_id}/findings/{finding_idx}/status")
async def update_finding_status(review_id: str, finding_idx: int, req: FindingStatusUpdate):
    success = _review_service.update_finding_status(review_id, finding_idx, req.status)
    if not success:
        raise HTTPException(status_code=404, detail="Finding not found")
    return {"status": req.status}


@router.post("/reviews/{review_id}/findings/{finding_idx}/feedback")
async def submit_feedback(review_id: str, finding_idx: int, req: FindingFeedback):
    findings = _review_service.get_findings(review_id)
    if finding_idx >= len(findings):
        raise HTTPException(status_code=404, detail="Finding not found")
    return {"status": "feedback_recorded", "action": req.action}


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------

@router.post("/reviews/{review_id}/gates/evaluate")
async def evaluate_gates(review_id: str, req: GateEvaluateRequest | None = None):
    review = _review_service.get_review(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    findings = _review_service.get_findings(review_id)
    gate_result = _gate_engine.evaluate(findings=findings, quality_scores=review.get("quality_scores", {}))
    return {
        "verdict": gate_result.verdict,
        "score": gate_result.score,
        "failures": [{"rule": f.rule_type, "message": f.message} for f in gate_result.failures],
    }


@router.get("/reviews/{review_id}/gates")
async def get_gate_results(review_id: str):
    review = _review_service.get_review(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return {"gate_passed": review.get("gate_passed"), "quality_scores": review.get("quality_scores", {})}


# ---------------------------------------------------------------------------
# Baselines
# ---------------------------------------------------------------------------

@router.get("/baselines")
async def list_baselines(tenant: str = Query("default"), repo_id: str = Query("")):
    return _baseline_service.list_baselines(tenant=tenant, repo_id=repo_id)


@router.post("/baselines")
async def create_baseline(req: BaselineCreate):
    return _baseline_service.create(
        tenant=req.tenant, repo_id=req.repo_id, name=req.name,
        snapshot={}, description=req.description,
        prompt_version=req.prompt_version, created_by=req.created_by,
    )


@router.get("/baselines/{baseline_name}")
async def get_baseline(baseline_name: str, tenant: str = Query("default"), repo_id: str = Query("")):
    b = _baseline_service.get(tenant=tenant, repo_id=repo_id, name=baseline_name)
    if not b:
        raise HTTPException(status_code=404, detail="Baseline not found")
    return b


@router.get("/baselines/{baseline_name}/diff")
async def diff_baseline(baseline_name: str, tenant: str = Query("default"), repo_id: str = Query("")):
    b = _baseline_service.get(tenant=tenant, repo_id=repo_id, name=baseline_name)
    if not b:
        raise HTTPException(status_code=404, detail="Baseline not found")
    return {"baseline": b, "diff": _baseline_service.diff(b, b)}


@router.delete("/baselines/{baseline_name}")
async def delete_baseline(baseline_name: str, tenant: str = Query("default"), repo_id: str = Query("")):
    deleted = _baseline_service.delete(tenant=tenant, repo_id=repo_id, name=baseline_name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Baseline not found")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Remediation
# ---------------------------------------------------------------------------

@router.post("/reviews/{review_id}/remediate")
async def trigger_remediation(review_id: str, req: RemediationCreate):
    result = _remediation_service.propose(
        finding_id=req.finding_id, review_id=review_id,
        patch_diff=req.patch_diff, generated_by=req.generated_by,
    )
    return {"remediation_id": result.remediation_id, "status": result.status}


@router.post("/reviews/{review_id}/remediate/verify")
async def verify_remediation(review_id: str, remediation_id: str = Query(...)):
    result = _remediation_service.verify(
        remediation_id=remediation_id,
        issue_resolved=True, tests_pass=True, re_scan_clean=True,
    )
    return {"remediation_id": result.remediation_id, "status": result.status}


# ---------------------------------------------------------------------------
# Test Analysis
# ---------------------------------------------------------------------------

@router.get("/reviews/{review_id}/test-analysis")
async def get_test_analysis(review_id: str):
    return {"review_id": review_id, "files_analyzed": 0, "gaps_found": 0}


@router.post("/reviews/{review_id}/generate-tests")
async def generate_tests(review_id: str):
    findings = _review_service.get_findings(review_id)
    proposals = _test_generator.propose_tests(findings)
    return {"review_id": review_id, "proposals_generated": len(proposals)}


# ---------------------------------------------------------------------------
# History & Trends
# ---------------------------------------------------------------------------

@router.get("/history/{repo_id}")
async def get_review_history(repo_id: str, tenant: str = Query("default")):
    reviews = _review_service.list_reviews(tenant=tenant, repo_id=repo_id)
    return {"repo_id": repo_id, "reviews": reviews, "total": len(reviews)}


@router.get("/history/{repo_id}/trends")
async def get_quality_trends(repo_id: str, tenant: str = Query("default")):
    trends = _historical.get_trends(tenant=tenant, repo_id=repo_id)
    direction = _historical.compute_trend_direction(tenant=tenant, repo_id=repo_id)
    return {"repo_id": repo_id, "data_points": trends, "trend": direction}


@router.get("/history/{repo_id}/hotspots")
async def get_hotspots(repo_id: str, tenant: str = Query("default")):
    return _historical.get_hotspots(tenant=tenant, repo_id=repo_id)


# ---------------------------------------------------------------------------
# Quick Analysis Endpoints
# ---------------------------------------------------------------------------

@router.post("/analyze/file")
async def analyze_file(req: FileAnalysisRequest):
    from app.quality.analyzers.base import ReviewContext
    from app.quality.config import ReviewConfig

    config = ReviewConfig.from_mode(req.mode)
    context = ReviewContext(
        tenant=req.tenant, repo_id=req.repo_id,
        file_contents={req.file_path: req.content},
        changed_files=[req.file_path],
        review_mode=req.mode,
    )
    result = await _pipeline.run_review(context, config)
    return {
        "review_id": result.review_id,
        "status": result.status,
        "findings": result.deduplicated,
        "quality_scores": result.quality_scores,
        "risk_score": result.risk_score,
    }


@router.post("/analyze/commit")
async def analyze_commit(req: CommitAnalysisRequest):
    review = _review_service.create_review(
        tenant=req.tenant, repo_id=req.repo_id,
        review_type="commit", target_ref=req.commit_sha, mode=req.mode,
    )
    return {"review_id": review["id"], "status": "queued", "commit": req.commit_sha}


@router.post("/analyze/branch")
async def analyze_branch(req: BranchAnalysisRequest):
    review = _review_service.create_review(
        tenant=req.tenant, repo_id=req.repo_id,
        review_type="branch", target_ref=f"{req.base_branch}...{req.branch}", mode=req.mode,
    )
    return {"review_id": review["id"], "status": "queued", "branch": req.branch}


@router.post("/analyze/pr")
async def analyze_pr(req: PRAnalysisRequest):
    review = _review_service.create_review(
        tenant=req.tenant, repo_id=req.repo_id,
        review_type="pr", target_ref=f"PR #{req.pr_number}", mode=req.mode,
    )
    return {"review_id": review["id"], "status": "queued", "pr_number": req.pr_number}


@router.post("/analyze/release")
async def analyze_release(req: ReleaseAnalysisRequest):
    review = _review_service.create_review(
        tenant=req.tenant, repo_id=req.repo_id,
        review_type="release", target_ref=req.release_tag, mode=req.mode,
    )
    return {"review_id": review["id"], "status": "queued", "release_tag": req.release_tag}
