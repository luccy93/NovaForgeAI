"""AI Software Quality Engine -- Review Lifecycle (Volume 48).

Manages review creation, analysis orchestration, state machine,
and finding aggregation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


REVIEW_STATES = {"queued", "analyzing", "completed", "failed", "cancelled", "blocked"}

REVIEW_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"analyzing", "cancelled"},
    "analyzing": {"completed", "failed", "cancelled", "blocked"},
    "completed": set(),
    "failed": set(),
    "cancelled": set(),
    "blocked": set(),
}


@dataclass
class ReviewResult:
    review_id: str
    status: str
    findings: list[dict[str, Any]] = field(default_factory=list)
    quality_scores: dict[str, float] = field(default_factory=dict)
    risk_score: float = 0.0
    gate_passed: bool | None = None
    severity_counts: dict[str, int] = field(default_factory=dict)
    duration_ms: int = 0
    analyzer_runs: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


class ReviewService:
    """In-memory review lifecycle manager."""

    def __init__(self):
        self._reviews: dict[str, dict[str, Any]] = {}
        self._findings: dict[str, list[dict[str, Any]]] = {}
        self._runs: dict[str, list[dict[str, Any]]] = {}

    def create_review(
        self,
        tenant: str = "default",
        repo_id: str = "",
        review_type: str = "file",
        target_ref: str = "",
        mode: str = "standard",
        prompt_version: str = "1.0",
        model_id: str = "",
        triggered_by: str = "user",
        metadata_extra: dict | None = None,
    ) -> dict[str, Any]:
        review_id = str(uuid4())
        review = {
            "id": review_id,
            "tenant": tenant,
            "repo_id": repo_id,
            "review_type": review_type,
            "target_ref": target_ref,
            "status": "queued",
            "mode": mode,
            "prompt_version": prompt_version,
            "model_id": model_id,
            "total_findings": 0,
            "critical_count": 0,
            "high_count": 0,
            "medium_count": 0,
            "low_count": 0,
            "info_count": 0,
            "quality_scores": {},
            "risk_score": 0.0,
            "gate_passed": None,
            "started_at": None,
            "finished_at": None,
            "duration_ms": 0,
            "error": None,
            "triggered_by": triggered_by,
            "metadata_extra": metadata_extra or {},
        }
        self._reviews[review_id] = review
        self._findings[review_id] = []
        self._runs[review_id] = []
        return review

    def get_review(self, review_id: str) -> dict[str, Any] | None:
        return self._reviews.get(review_id)

    def list_reviews(
        self, tenant: str = "", repo_id: str = "", limit: int = 20
    ) -> list[dict[str, Any]]:
        results = []
        for r in self._reviews.values():
            if tenant and r["tenant"] != tenant:
                continue
            if repo_id and r["repo_id"] != repo_id:
                continue
            results.append(r)
        results.sort(key=lambda x: x.get("started_at") or "", reverse=True)
        return results[:limit]

    def transition(self, review_id: str, new_status: str) -> bool:
        review = self._reviews.get(review_id)
        if not review:
            return False
        current = review["status"]
        if new_status not in REVIEW_TRANSITIONS.get(current, set()):
            return False
        now = datetime.now(timezone.utc)
        review["status"] = new_status
        if new_status == "analyzing":
            review["started_at"] = now.isoformat()
        elif new_status in ("completed", "failed", "cancelled", "blocked"):
            review["finished_at"] = now.isoformat()
            if review["started_at"]:
                started = datetime.fromisoformat(review["started_at"])
                review["duration_ms"] = int((now - started).total_seconds() * 1000)
        return True

    def add_findings(self, review_id: str, findings: list[dict[str, Any]]) -> int:
        if review_id not in self._findings:
            return 0
        self._findings[review_id].extend(findings)
        self._update_counts(review_id)
        return len(findings)

    def get_findings(
        self,
        review_id: str,
        severity: str = "",
        category: str = "",
        status: str = "",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        findings = self._findings.get(review_id, [])
        filtered = findings
        if severity:
            filtered = [f for f in filtered if f.get("severity") == severity]
        if category:
            filtered = [f for f in filtered if f.get("category") == category]
        if status:
            filtered = [f for f in filtered if f.get("status") == status]
        return filtered[:limit]

    def update_finding_status(
        self, review_id: str, finding_index: int, new_status: str
    ) -> bool:
        findings = self._findings.get(review_id, [])
        if 0 <= finding_index < len(findings):
            findings[finding_index]["status"] = new_status
            return True
        return False

    def add_run(self, review_id: str, run: dict[str, Any]) -> None:
        if review_id in self._runs:
            self._runs[review_id].append(run)

    def get_runs(self, review_id: str) -> list[dict[str, Any]]:
        return self._runs.get(review_id, [])

    def set_quality_scores(
        self, review_id: str, scores: dict[str, float]
    ) -> None:
        review = self._reviews.get(review_id)
        if review:
            review["quality_scores"] = scores

    def set_risk_score(self, review_id: str, risk_score: float) -> None:
        review = self._reviews.get(review_id)
        if review:
            review["risk_score"] = risk_score

    def set_gate_passed(self, review_id: str, passed: bool) -> None:
        review = self._reviews.get(review_id)
        if review:
            review["gate_passed"] = passed

    def get_summary(self, review_id: str) -> dict[str, Any]:
        review = self._reviews.get(review_id)
        if not review:
            return {}
        findings = self._findings.get(review_id, [])
        return {
            "review": review,
            "finding_count": len(findings),
            "by_severity": {
                "critical": review["critical_count"],
                "high": review["high_count"],
                "medium": review["medium_count"],
                "low": review["low_count"],
                "info": review["info_count"],
            },
            "by_category": self._count_by_category(findings),
            "by_source": self._count_by_source(findings),
        }

    def _update_counts(self, review_id: str) -> None:
        review = self._reviews.get(review_id)
        findings = self._findings.get(review_id, [])
        if not review:
            return
        counts: dict[str, int] = {}
        for f in findings:
            sev = f.get("severity", "info")
            counts[sev] = counts.get(sev, 0) + 1
        review["critical_count"] = counts.get("critical", 0)
        review["high_count"] = counts.get("high", 0)
        review["medium_count"] = counts.get("medium", 0)
        review["low_count"] = counts.get("low", 0)
        review["info_count"] = counts.get("info", 0)
        review["total_findings"] = len(findings)

    def _count_by_category(self, findings: list[dict]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for f in findings:
            cat = f.get("category", "unknown")
            counts[cat] = counts.get(cat, 0) + 1
        return counts

    def _count_by_source(self, findings: list[dict]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for f in findings:
            src = f.get("source", "unknown")
            counts[src] = counts.get(src, 0) + 1
        return counts
