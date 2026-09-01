"""Repository assistance: change summaries, reviewers, PR drafts — Volume 67.

Honest diff-derived summaries (no fabricated outcomes) and reviewer
suggestions from the existing ownership index.
"""

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_dev.common import emit_event, resolve_repository
from app.code_intelligence.models import CodeOwnership, CodeSymbol
from app.models.repository import Commit

logger = logging.getLogger(__name__)


def _diff_stats(files: Optional[list[dict]]) -> dict:
    """Compute real additions/deletions from unified diff text."""
    stats = {"files": 0, "additions": 0, "deletions": 0}
    for entry in files or []:
        diff = entry.get("diff") or entry.get("unified_diff") or ""
        if not diff and "new_content" in entry and "old_content" in entry:
            import difflib

            diff = "".join(
                difflib.unified_diff(
                    (entry.get("old_content") or "").splitlines(True),
                    (entry.get("new_content") or "").splitlines(True),
                )
            )
        stats["files"] += 1
        for line in diff.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                stats["additions"] += 1
            elif line.startswith("-") and not line.startswith("---"):
                stats["deletions"] += 1
    return stats


async def change_summary(
    db: AsyncSession,
    tenant: str,
    repository_id,
    *,
    commit_sha: Optional[str] = None,
    files: Optional[list[dict]] = None,
) -> dict:
    repo = await resolve_repository(db, tenant, repository_id)
    commit = None
    if commit_sha:
        commit = (
            (
                await db.execute(
                    select(Commit).where(
                        Commit.repository_id == repo.id,
                        Commit.sha == commit_sha,
                    )
                )
            )
            .scalars()
            .first()
        )
    stats = _diff_stats(files)
    return {
        "repository_id": str(repo.id),
        "commit_sha": commit_sha,
        "commit_message": commit.message if commit else None,
        "author": f"{commit.author_name} <{commit.author_email}>" if commit else None,
        "stats": stats,
        "notes": [
            "critical paths changed"
            if any((f or {}).get("path", "").startswith(("core/", "src/core/", "app/models/")) for f in (files or []))
            else "no critical paths detected"
        ],
    }


async def suggest_reviewers(
    db: AsyncSession, tenant: str, repository_id, files: list[str], *, limit: int = 3
) -> list[dict]:
    repo = await resolve_repository(db, tenant, repository_id)
    reviewers: dict[str, int] = {}
    for path in files or []:
        rows = (
            (
                await db.execute(
                    select(CodeOwnership).where(
                        CodeOwnership.repository_id == repo.id,
                        CodeOwnership.file_path == path,
                    )
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            reviewers[row.owner_email] = reviewers.get(row.owner_email, 0) + 1
    ranked = sorted(reviewers.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return [
        {"email": email, "file_hits": hits}
        for email, hits in ranked
    ]


async def pr_assistant(
    db: AsyncSession,
    tenant: str,
    repository_id,
    *,
    title: str,
    files: list[dict],
    commit_sha: Optional[str] = None,
    test_summary: Optional[dict] = None,
    findings: Optional[list[dict]] = None,
) -> dict:
    """Draft a PR body from real evidence; never overrides repo policy."""
    repo = await resolve_repository(db, tenant, repository_id)
    summary = await change_summary(db, tenant, repo.id, commit_sha=commit_sha, files=files)
    stats = summary["stats"]
    reviewers = await suggest_reviewers(
        db, tenant, repo.id, [f.get("path") for f in (files or [])]
    )
    preview_findings = findings or []
    draft = [
        f"## {title}",
        "",
        f"Files changed: {stats['files']} · +{stats['additions']}/-{stats['deletions']}",
        "",
        "### Proposed changes",
        *[f"- {f.get('path')} ({_delta(f)})" for f in (files or [])],
        "",
        "### Verification",
        (
            f"- Tests: {test_summary.get('status', 'not run')} "
            f"({test_summary.get('passed', 0)} passed) — recorded by CI"
            if test_summary
            else "- Tests: no recorded CI run for this change"
        ),
        (
            f"- Review findings: {len(preview_findings)} open "
            f"({sum(1 for x in preview_findings if x.get('severity') in ('HIGH', 'CRITICAL'))} high/critical)"
            if preview_findings
            else "- Review findings: none flagged"
        ),
        "",
        "### Suggested reviewers",
        *(f"- {r['email']}" for r in reviewers),
    ]
    await emit_event(
        "CodePrAssisted",
        {
            "repository_id": str(repo.id),
            "commit_sha": commit_sha,
            "title": title,
            "files": stats["files"],
        },
        tenant,
    )
    return {
        "repository_id": str(repo.id),
        "draft": "\n".join(draft),
        "summary": summary,
        "suggested_reviewers": reviewers,
        "uncertain": not findings,
    }


def _delta(f: dict) -> str:
    nc = (f.get("new_content") or "")
    oc = (f.get("old_content") or "")
    return "new file" if not oc else ("modified" if nc else "deleted")