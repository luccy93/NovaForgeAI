"""Review AI refinement agent — Volume 67 Commit 2.

Deterministic triage: re-scans existing review findings, deduplicates on
(category, severity, message), and recounts. Severity and confidence are
never invented — every value comes from the original evidence.
"""

import logging
from collections import Counter
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_dev import agent as agent_svc
from app.ai_dev.models import CodeReview, CodeReviewFinding

logger = logging.getLogger(__name__)

_SEV_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def refine_findings(findings: list[dict]) -> dict:
    """Deduplicate findings; return a machine-checkable report."""
    unique: dict[tuple, dict] = {}
    for f in findings:
        key = (f.get("category", ""), (f.get("severity") or "MEDIUM").upper(), f.get("message", ""))
        cur = unique.get(key)
        if cur is None:
            unique[key] = dict(f)
            continue
        if (f.get("confidence", 0) or 0) > (cur.get("confidence", 0) or 0):
            unique[key] = dict(f)
    refined = sorted(
        unique.values(),
        key=lambda x: (_SEV_ORDER.get((x.get("severity") or "MEDIUM").upper(), 4),),
    )
    by_category = dict(Counter(str(x.get("category", "OTHER")) for x in refined))
    high_critical = sum(
        1
        for x in refined
        if (x.get("severity") or "MEDIUM").upper() in ("HIGH", "CRITICAL")
    )
    return {
        "total_source": len(findings),
        "unique": len(refined),
        "duplicates_removed": len(findings) - len(refined),
        "by_category": by_category,
        "high_critical": high_critical,
        "findings": refined,
        "summary": (
            f"Refined {len(findings)} finding(s) into {len(refined)} unique "
            f"({high_critical} high/critical)."
        ),
    }


async def resolve_source_findings(db: AsyncSession, tenant: str, run) -> list[dict]:
    meta = run.metadata_ or {}
    ids = meta.get("review_id")
    files = meta.get("findings") or meta.get("files") or []
    if ids:
        from app.ai_dev.common import _as_uuid

        review = await db.get(CodeReview, _as_uuid(ids))
        if review is None or review.tenant != tenant:
            raise agent_svc.NotFoundAgentError("review not found")
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
                "id": str(r.id),
                "category": r.category,
                "severity": r.severity,
                "message": r.message,
                "confidence": r.confidence,
                "file_path": r.file_path,
                "line_start": r.line_start,
                "line_end": r.line_end,
            }
            for r in rows
        ]
    return [dict(f) for f in files]


async def refine_review_agent(
    db: AsyncSession,
    tenant: str,
    run,
    *,
    user_id: Optional[str] = None,
) -> dict:
    await agent_svc.save_checkpoint(
        db, tenant, str(run.id), summary="Triage findings", state={"phase": "triage"}
    )
    source = await resolve_source_findings(db, tenant, run)
    report = refine_findings(source)
    await agent_svc.save_checkpoint(
        db, tenant, str(run.id),
        summary=report["summary"],
        state={"phase": "refined", "unique": report["unique"]},
        is_final=True,
    )
    return {
        "model": run.model,
        "tokens": 0,
        "patch_id": None,
        "plan_id": None,
        "data": report,
    }