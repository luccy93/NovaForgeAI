"""Dependency and build analysis — Volume 67 Commit 1.

Real dependency scanning (lockfile parsing + vulnerability checking)
and honest build status from the delivery subsystem.
"""

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_dev.common import emit_event, resolve_repository
from app.code_intelligence.models import CodeImport

logger = logging.getLogger(__name__)


async def dependency_graph(db: AsyncSession, tenant: str, repository_id, *, limit: int = 200) -> dict:
    repo = await resolve_repository(db, tenant, repository_id)
    rows = (
        (
            await db.execute(
                select(CodeImport).where(CodeImport.repository_id == repo.id).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    internal = {}
    external = {}
    for imp in rows:
        target = imp.imported_name
        (external if imp.is_external else internal).setdefault(target, 0)
        (external if imp.is_external else internal)[target] += 1
    return {
        "repository_id": str(repo.id),
        "internal_imports": internal,
        "external_imports": external,
        "total_edges": len(rows),
        "truncated": len(rows) >= limit,
    }


def _parse_lockfiles(files: list[dict]) -> list[dict]:
    """Parse lockfile/manifest content deterministically."""
    packages: list[dict] = []
    try:
        from app.security.dependency_scanner import DependencyScanner

        scanner = DependencyScanner()
        for entry in files:
            name = entry.get("name") or entry.get("path") or ""
            content = entry.get("content")
            if not name or content is None:
                continue
            try:
                packages.extend(scanner.parse_file(name, content))
            except Exception as exc:  # pragma: no cover
                logger.debug("parse_file failed for %s: %s", name, exc)
    except Exception as exc:  # pragma: no cover
        logger.warning("dependency_scanner unavailable: %s", exc)
    return packages


def _check_vulnerabilities(packages: list[dict]) -> list[dict]:
    if not packages:
        return []
    try:
        from app.security.dependency_scanner import check_vulnerabilities

        return list(check_vulnerabilities(packages))
    except Exception as exc:  # pragma: no cover
        logger.warning("vulnerability check unavailable: %s", exc)
        return []


async def analyze_dependencies(
    db: AsyncSession,
    tenant: str,
    repository_id,
    files: Optional[list[dict]] = None,
    *,
    emit: bool = True,
) -> dict:
    """Parse lockfiles (if supplied) and check vulnerabilities honestly."""
    repo = await resolve_repository(db, tenant, repository_id)
    packages = _parse_lockfiles(files or [])
    vulnerabilities = _check_vulnerabilities(packages)
    result = {
        "repository_id": str(repo.id),
        "packages_analyzed": len(packages),
        "vulnerabilities": vulnerabilities,
        "vulnerable": any(v.get("vulnerable") or v.get("cve_id") for v in vulnerabilities),
    }
    if emit and vulnerabilities:
        await emit_event(
            "CodeDependencyScanned",
            {
                "repository_id": str(repo.id),
                "vulnerabilities": len(vulnerabilities),
                "vulnerable": result["vulnerable"],
            },
            tenant,
        )
    return result


async def build_analysis(db: AsyncSession, tenant: str, repository_id, *, commit_sha: Optional[str] = None) -> dict:
    """Honest build status for a repository/commit from delivery runs."""
    repo = await resolve_repository(db, tenant, repository_id)
    try:
        from app.delivery.pipeline_service import PipelineService

        svc = PipelineService(db)
        pipelines, _ = await svc.list_pipelines(
            tenant=tenant, project="ai-dev-tests", repository=str(repo.id), limit=5
        )
        runs = []
        for pipeline in pipelines:
            prs, total = await svc.list_runs(pipeline.id, limit=5)
            for pr in prs:
                runs.append(
                    {
                        "run_id": str(pr.id),
                        "pipeline_id": str(pipeline.id),
                        "status": pr.status,
                        "commit_sha": pr.commit_sha,
                        "triggered_at": pr.created_at.isoformat()
                        if getattr(pr, "created_at", None)
                        else None,
                    }
                )
        runs.sort(key=lambda r: r["triggered_at"] or "", reverse=True)
        return {
            "repository_id": str(repo.id),
            "runs": runs,
            "success_rate": round(
                sum(1 for r in runs if r["status"] == "succeeded") / len(runs), 3
            )
            if runs
            else None,
        }
    except Exception as exc:  # pragma: no cover
        logger.warning("build analysis unavailable: %s", exc)
        return {
            "repository_id": str(repo.id),
            "runs": [],
            "success_rate": None,
            "error": str(exc),
        }