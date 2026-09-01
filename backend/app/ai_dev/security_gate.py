"""Security gate — Volume 67 Commit 2.

Deterministic, evidence-based gating. A gate can only PASS when there
are no blocking findings (HIGH/CRITICAL severity or SECURITY category).
Blockers/warnings are rendered from real scanner evidence; the gate never
fabricates a clearance.
"""

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_dev.common import _as_uuid, emit_event
from app.ai_dev.models import CodeReview, CodeReviewFinding

logger = logging.getLogger(__name__)

_BLOCK_SEVERITIES = ("HIGH", "CRITICAL")


def classify_findings(findings: list[dict]) -> dict:
    blockers = [
        f
        for f in findings
        if (f.get("severity") or "MEDIUM").upper() in _BLOCK_SEVERITIES
        or str(f.get("category", "")).upper() == "SECURITY"
    ]
    warnings = [
        f
        for f in findings
        if f not in blockers
    ]
    if blockers:
        decision = "BLOCK"
    elif warnings:
        decision = "REVIEW"
    else:
        decision = "PASS"
    return {
        "decision": decision,
        "passed": decision == "PASS",
        "blockers": blockers,
        "warnings": warnings,
        "blocker_count": len(blockers),
        "warning_count": len(warnings),
    }


async def find_findings(db: AsyncSession, tenant: str, *, repository_id=None, review_id=None, files=None, findings=None, commit_sha=None) -> list[dict]:
    if findings is not None:
        return [dict(f) for f in findings]
    if review_id is not None:
        review = await db.get(CodeReview, _as_uuid(review_id))
        if review is None or review.tenant != tenant:
            raise ValueError("review not found")
        rows = (
            (
                await db.execute(
                    select(CodeReviewFinding).where(CodeReviewFinding.review_id == review.id)
                )
            )
            .scalars()
            .all()
        )
        return [
            {
                "category": r.category,
                "severity": (r.severity or "MEDIUM").upper(),
                "message": r.message,
                "reason": r.reason,
                "file_path": r.file_path,
                "line_start": r.line_start,
                "confidence": r.confidence or 0,
            }
            for r in rows
        ]
    if files:
        if not repository_id:
            raise ValueError("repository_id required when submitting raw files")
        from app.ai_dev import review as review_svc

        review = await review_svc.generate_review(
            db, tenant, "gate",
            repository_id=repository_id,
            files=files,
            commit_sha=commit_sha,
        )
        rows = (
            (
                await db.execute(
                    select(CodeReviewFinding).where(CodeReviewFinding.review_id == review.id)
                )
            )
            .scalars()
            .all()
        )
        return [
            {
                "category": r.category,
                "severity": (r.severity or "MEDIUM").upper(),
                "message": r.message,
                "reason": r.reason,
                "file_path": r.file_path,
                "line_start": r.line_start,
                "confidence": r.confidence or 0,
            }
            for r in rows
        ]
    return []


async def run_security_gate(
    db: AsyncSession,
    tenant: str,
    user_id: str,
    *,
    repository_id=None,
    review_id=None,
    files=None,
    findings=None,
    branch: str = "main",
    commit_sha: Optional[str] = None,
) -> dict:
    source = await find_findings(
        db, tenant, repository_id=repository_id, review_id=review_id, files=files, findings=findings, commit_sha=commit_sha
    )
    result = classify_findings(source)
    result.update(
        {
            "repository_id": str(repository_id) if repository_id else None,
            "review_id": str(review_id) if review_id else None,
            "commit_sha": commit_sha,
            "ran_by": user_id,
            "eligible": result["decision"] == "PASS",
        }
    )
    await emit_event(
        "CodeSecurityGateRun",
        {
            "repository_id": result["repository_id"],
            "review_id": result["review_id"],
            "decision": result["decision"],
            "blocker_count": result["blocker_count"],
            "warning_count": result["warning_count"],
        },
        tenant,
    )
    return result