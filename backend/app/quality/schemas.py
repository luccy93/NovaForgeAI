"""AI Software Quality Engine -- Pydantic Schemas (Volume 48)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------

class ReviewCreate(BaseModel):
    tenant: str = "default"
    repo_id: str = ""
    review_type: str = "file"  # file/commit/branch/pr/release/patch
    target_ref: str = ""
    mode: str = "standard"  # quick/standard/deep/security/performance/release
    prompt_version: str = "1.0"
    model_id: str = ""
    triggered_by: str = "user"
    metadata_extra: dict = Field(default_factory=dict)


class ReviewResponse(BaseModel):
    id: str
    tenant: str
    repo_id: str
    review_type: str
    target_ref: str
    status: str
    mode: str
    total_findings: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    info_count: int = 0
    quality_scores: dict = Field(default_factory=dict)
    risk_score: float = 0.0
    gate_passed: Optional[bool] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_ms: int = 0
    error: Optional[str] = None
    triggered_by: str = "system"


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------

class FindingCreate(BaseModel):
    review_id: Optional[str] = None
    tenant: str = "default"
    category: str
    severity: str = "info"
    confidence: float = 0.5
    file_path: str = ""
    line_start: int = 0
    line_end: int = 0
    symbol: str = ""
    description: str = ""
    evidence: dict = Field(default_factory=dict)
    recommendation: str = ""
    rule_id: str = ""
    source: str = "ai_review"
    suggestion: str = ""


class FindingResponse(BaseModel):
    id: str
    review_id: Optional[str] = None
    tenant: str
    category: str
    severity: str
    confidence: float
    file_path: str
    line_start: int
    line_end: int
    symbol: str
    description: str
    evidence: dict = Field(default_factory=dict)
    recommendation: str
    rule_id: str
    source: str
    finding_hash: str
    status: str
    suggestion: str
    created_at: Optional[str] = None


class FindingFeedback(BaseModel):
    developer_id: str
    action: str  # accept/dismiss/comment/false_positive/request_fix/clarification
    reason: str = ""


class FindingStatusUpdate(BaseModel):
    status: str  # open/acknowledged/in_progress/fixed/verified/false_positive/risk_accepted/reopened


# ---------------------------------------------------------------------------
# Quality Gate
# ---------------------------------------------------------------------------

class GateRule(BaseModel):
    rule_type: str  # max_findings/min_score/required_checks/no_breaking_changes
    params: dict = Field(default_factory=dict)
    severity: str = "high"
    enabled: bool = True


class GateCreate(BaseModel):
    tenant: str = "default"
    repo_id: str = ""
    name: str = "default"
    description: str = ""
    gate_type: str = "merge"  # merge/release/deploy
    rules: list[GateRule] = Field(default_factory=list)
    block_on_failure: bool = True


class GateResponse(BaseModel):
    id: str
    tenant: str
    repo_id: str
    name: str
    description: str
    gate_type: str
    rules: list[dict] = Field(default_factory=list)
    enabled: bool
    block_on_failure: bool


class GateEvaluationResponse(BaseModel):
    id: str
    review_id: Optional[str] = None
    gate_id: Optional[str] = None
    verdict: str
    triggered_by: str
    evaluated_rules: dict = Field(default_factory=dict)
    failures: dict = Field(default_factory=dict)
    duration_ms: int = 0


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------

class BaselineCreate(BaseModel):
    tenant: str = "default"
    repo_id: str = ""
    name: str = "default"
    description: str = ""
    prompt_version: str = "1.0"
    created_by: str = "user"


class BaselineResponse(BaseModel):
    id: str
    tenant: str
    repo_id: str
    name: str
    description: str
    snapshot: dict = Field(default_factory=dict)
    prompt_version: str
    created_by: str
    created_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Remediation
# ---------------------------------------------------------------------------

class RemediationCreate(BaseModel):
    finding_id: str
    review_id: Optional[str] = None
    patch_diff: str = ""
    generated_by: str = "ai"


class RemediationResponse(BaseModel):
    id: str
    finding_id: Optional[str] = None
    review_id: Optional[str] = None
    status: str
    patch_diff: str
    validation_results: dict = Field(default_factory=dict)
    verification_results: dict = Field(default_factory=dict)
    commit_sha: str
    generated_by: str


# ---------------------------------------------------------------------------
# Test Analysis
# ---------------------------------------------------------------------------

class TestAnalysisResponse(BaseModel):
    id: str
    review_id: Optional[str] = None
    repo_id: str
    files_analyzed: int = 0
    tests_added: int = 0
    tests_modified: int = 0
    tests_removed: int = 0
    coverage_delta: float = 0.0
    assertion_quality_score: float = 0.0
    gaps_found: int = 0
    edge_cases_missing: int = 0
    flaky_suspects: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

class ReviewReportResponse(BaseModel):
    review_id: str
    summary: dict = Field(default_factory=dict)
    findings: list[dict] = Field(default_factory=list)
    inline_comments: list[dict] = Field(default_factory=list)
    quality_scores: dict = Field(default_factory=dict)
    gate_results: list[dict] = Field(default_factory=list)
    risk_assessment: dict = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)


class PRSummaryResponse(BaseModel):
    review_id: str
    what_changed: str = ""
    why_changed: str = ""
    risk_level: str = ""
    affected_components: list[str] = Field(default_factory=list)
    tests_status: str = ""
    security_status: str = ""
    deployment_impact: str = ""
    findings_summary: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# History & Trends
# ---------------------------------------------------------------------------

class HistoryResponse(BaseModel):
    repo_id: str
    reviews: list[dict] = Field(default_factory=list)
    total_reviews: int = 0


class TrendsResponse(BaseModel):
    repo_id: str
    data_points: list[dict] = Field(default_factory=list)
    current_scores: dict = Field(default_factory=dict)
    trend: str = ""  # improving/stable/declining


# ---------------------------------------------------------------------------
# Inline Review
# ---------------------------------------------------------------------------

class InlineComment(BaseModel):
    file: str
    line: int
    severity: str
    finding: str
    evidence: str
    suggestion: str
    rule_id: str = ""
    category: str = ""


# ---------------------------------------------------------------------------
# File/Commit/Branch/PR/Release Analysis Requests
# ---------------------------------------------------------------------------

class FileAnalysisRequest(BaseModel):
    tenant: str = "default"
    repo_id: str = ""
    file_path: str
    content: str
    language: str = ""
    mode: str = "standard"


class CommitAnalysisRequest(BaseModel):
    tenant: str = "default"
    repo_id: str = ""
    commit_sha: str
    mode: str = "standard"


class BranchAnalysisRequest(BaseModel):
    tenant: str = "default"
    repo_id: str = ""
    branch: str
    base_branch: str = "main"
    mode: str = "standard"


class PRAnalysisRequest(BaseModel):
    tenant: str = "default"
    repo_id: str = ""
    pr_number: int = 0
    head_sha: str = ""
    base_sha: str = ""
    mode: str = "standard"


class ReleaseAnalysisRequest(BaseModel):
    tenant: str = "default"
    repo_id: str = ""
    release_tag: str
    previous_tag: str = ""
    mode: str = "release"


# ---------------------------------------------------------------------------
# Gate Evaluation Request
# ---------------------------------------------------------------------------

class GateEvaluateRequest(BaseModel):
    gate_id: Optional[str] = None
    triggered_by: str = "system"
