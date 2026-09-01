"""Code review — Volume 67 Commit 1.

Reviews are produced from real evidence only: the secret scanner and
SAST scanner run over submitted file content, plus deterministic static
checks (over-long lines, dangerous runtime calls, test gaps). No
coverage/severity values are fabricated.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_dev.common import NotFoundError, _as_uuid, emit_event, resolve_repository
from app.ai_dev.models import CodeReview, CodeReviewFinding
from app.code_intelligence.models import CodeTest

logger = logging.getLogger(__name__)

MAX_REVIEW_FILES = 20


def _secret_findings(content: str, path: str) -> list[dict]:
    try:
        from app.security.secret_scanner import scan_content

        return list(scan_content(content, file_path=path))
    except Exception as exc:  # pragma: no cover
        logger.debug("secret scan unavailable: %s", exc)
        return []


def _sast_findings(content: str, path: str) -> list[dict]:
    try:
        from app.security.sast_scanner import scan_ast

        return list(scan_ast(content, file_path=path))
    except Exception as exc:  # pragma: no cover
        logger.debug("sast scan unavailable: %s", exc)
        return []


def _sev_rank(sev: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get((sev or "medium").lower(), 4)


def _sast_category(message: str, rule: str) -> str:
    msg = f"{message} {rule}".lower()
    if any(k in msg for k in ("injection", "secret", "insecure", "ssl", "deserialization", "cors", "cookie")):
        return "SECURITY"
    if any(k in msg for k in ("dos", "request", "debug", "performance")):
        return "PERFORMANCE"
    return "BUG"


def _static_checks(content: str, path: str) -> list[dict]:
    """Deterministic static checks (real, machine-verifiable)."""
    checks: list[dict] = []
    for line_no, line in enumerate(content.splitlines(), start=1):
        if len(line) > 120:
            checks.append(
                {
                    "category": "MAINTAINABILITY",
                    "severity": "LOW",
                    "line_start": line_no,
                    "line_end": line_no,
                    "message": "Line exceeds 120 characters",
                    "reason": "static: line length",
                    "confidence": 0.95,
                }
            )
            if len(checks) >= 3:
                break
    lowered = content.lower()
    if "eval(" in lowered or "exec(" in lowered:
        checks.append(
            {
                "category": "SECURITY",
                "severity": "HIGH",
                "message": "Arbitrary code execution via eval/exec present",
                "reason": "static: eval/exec usage",
                "confidence": 0.9,
            }
        )
    if "pickle.loads(" in lowered or "yaml.load(" in lowered:
        checks.append(
            {
                "category": "SECURITY",
                "severity": "HIGH",
                "message": "Unsafe deserialization present",
                "reason": "static: unsafe deserialization",
                "confidence": 0.9,
            }
        )
    if "except " in content and "except exception" not in lowered:
        checks.append(
            {
                "category": "BUG",
                "severity": "LOW",
                "message": "Bare or broad exception clause",
                "reason": "static: broad except",
                "confidence": 0.5,
            }
        )
    return checks


async def _test_gap(db, repository_id, path: str, content: str) -> Optional[dict]:
    is_test = path.rsplit(".", 1)[0].endswith("test") or path.split("/")[-1].startswith("test_")
    if is_test:
        return None
    rows = (
        (
            await db.execute(
                select(CodeTest).where(
                    CodeTest.repository_id == repository_id,
                    CodeTest.source_file_path == path,
                )
            )
        )
        .scalars()
        .all()
    )
    if rows:
        return None
    return {
        "category": "TEST_GAP",
        "severity": "MEDIUM",
        "message": f"No indexed test covers {path}",
        "reason": "static: test gap detected from code_tests index",
        "confidence": 0.5,
    }


async def generate_review(
    db: AsyncSession,
    tenant: str,
    user_id: str,
    *,
    repository_id,
    files: list[dict],
    branch: Optional[str] = None,
    commit_sha: Optional[str] = None,
    patch_id=None,
    workspace_id=None,
    model: Optional[str] = None,
    rules_version: str = "1.0",
) -> CodeReview:
    repo = await resolve_repository(db, tenant, repository_id)
    if not files:
        raise ValueError("review requires at least one file")
    files = files[:MAX_REVIEW_FILES]

    findings: list[dict] = []
    for entry in files:
        path = entry.get("path") or ""
        content = entry.get("content") or ""
        for f in _secret_findings(content, path):
            findings.append(
                {
                    "category": "SECURITY",
                    "severity": (f.get("severity") or "critical").upper(),
                    "file_path": path,
                    "line_start": f.get("line_start"),
                    "line_end": f.get("line_start"),
                    "message": f.get("message") or "Secret detected",
                    "reason": f"scanner:secret rule={f.get('rule')} cwe={f.get('cwe_id')} evidence={f.get('evidence')}",
                    "confidence": 0.95 if str(f.get("confidence", "")).lower() == "high" else 0.8,
                }
            )
        for f in _sast_findings(content, path):
            findings.append(
                {
                    "category": _sast_category(f.get("message", ""), f.get("rule", "")),
                    "severity": (f.get("severity") or "medium").upper(),
                    "file_path": path,
                    "line_start": f.get("line_start"),
                    "line_end": f.get("line_start"),
                    "message": f.get("message") or "Static analysis finding",
                    "reason": f"scanner:sast rule={f.get('rule')} cwe={f.get('cwe_id')}",
                    "confidence": 0.9 if str(f.get("confidence", "")).lower() == "high" else 0.75,
                }
            )
        for chk in _static_checks(content, path):
            findings.append(
                {
                    **chk,
                    "file_path": path,
                }
            )
        gap = await _test_gap(db, repo.id, path, content)
        if gap:
            findings.append({**gap, "file_path": path})

    review = CodeReview(
        tenant=tenant,
        repository_id=repo.id,
        branch=branch or repo.default_branch,
        commit_sha=commit_sha,
        patch_id=patch_id,
        workspace_id=workspace_id,
        model=model,
        rules_version=rules_version,
        status="OPEN",
        created_by=user_id,
        context_snapshot={
            "repository_full_name": repo.full_name,
            "files_reviewed": len(files),
            "rules_version": rules_version,
        },
    )
    db.add(review)
    await db.flush()

    for f in findings:
        finding = CodeReviewFinding(
            tenant=tenant,
            review_id=review.id,
            file_path=f["file_path"],
            line_start=f.get("line_start"),
            line_end=f.get("line_end"),
            category=f["category"],
            severity=f.get("severity", "MEDIUM"),
            message=f["message"],
            reason=f.get("reason"),
            confidence=f.get("confidence", 0.5),
            evidence=f.get("evidence") or {},
        )
        db.add(finding)
    review.summary = (
        f"Reviewed {len(files)} file(s); {len(findings)} finding(s) "
        f"({sum(1 for x in findings if x.get('severity') in ('HIGH', 'CRITICAL'))} high/critical)."
    )
    await db.flush()
    await emit_event(
        "CodeReviewGenerated",
        {
            "review_id": str(review.id),
            "repository_id": str(repo.id),
            "commit_sha": commit_sha,
            "findings": len(findings),
            "high_critical": sum(1 for x in findings if x.get("severity") in ("HIGH", "CRITICAL")),
        },
        tenant,
    )
    return review


async def get_review(db: AsyncSession, tenant: str, review_id) -> CodeReview:
    review = await db.get(CodeReview, _as_uuid(review_id))
    if review is None or review.tenant != tenant:
        raise NotFoundError("review not found")
    return review


async def list_reviews(db: AsyncSession, tenant: str, *, repository_id=None, limit: int = 50) -> list[CodeReview]:
    stmt = select(CodeReview).where(CodeReview.tenant == tenant)
    if repository_id:
        stmt = stmt.where(CodeReview.repository_id == repository_id)
    rows = (
        (
            await db.execute(
                stmt.order_by(CodeReview.created_at.desc()).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def review_with_findings(db: AsyncSession, tenant: str, review_id) -> dict:
    review = await get_review(db, tenant, review_id)
    findings = (
        (
            await db.execute(
                select(CodeReviewFinding)
                .where(CodeReviewFinding.review_id == review.id)
                .order_by(CodeReviewFinding.created_at)
            )
        )
        .scalars()
        .all()
    )
    return {
        "review": review,
        "findings": list(findings),
    }


async def dismiss_finding(
    db: AsyncSession,
    tenant: str,
    user_id: str,
    review_id,
    finding_id,
    reason: Optional[str] = None,
) -> CodeReviewFinding:
    review = await get_review(db, tenant, review_id)
    finding = await db.get(CodeReviewFinding, _as_uuid(finding_id))
    if finding is None or finding.review_id != review.id or finding.tenant != tenant:
        raise NotFoundError("finding not found")
    if finding.status == "DISMISSED":
        raise ValueError("finding already dismissed")
    finding.status = "DISMISSED"
    finding.dismissed_by = user_id
    finding.dismissed_reason = reason
    finding.dismissed_at = datetime.now(timezone.utc)
    await db.flush()
    await emit_event(
        "CodeReviewFindingDismissed",
        {
            "review_id": str(review.id),
            "finding_id": str(finding.id),
            "dismissed_by": user_id,
        },
        tenant,
    )
    return finding