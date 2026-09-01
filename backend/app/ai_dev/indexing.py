"""Index orchestration and embedding provenance — Volume 67 Commit 1.

Reuses the existing code_intelligence tables (code_indexes,
code_index_versions, code_symbols, ...) — no duplicate models.
The index contract is recorded honestly: provenance is persisted, but
status only transitions to READY when the real indexing pipeline
completes. This module never fabricates index results.
"""

import logging
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_dev.common import (
    NotFoundError,
    _as_uuid,
    emit_event,
    get_symbols_for_path,
    resolve_repository,
)
from app.code_intelligence.models import CodeIndex, CodeIndexVersion, IndexStatus
from app.models.repository import Repository

logger = logging.getLogger(__name__)


def _embedding_provenance() -> dict:
    """Current embedding provenance (model/version/dimension) or empty."""
    try:
        from app.embeddings.service import embeddings_service

        return {
            "embedding_model": getattr(embeddings_service, "model", None) or getattr(
                embeddings_service, "model_name", None
            ),
            "embedding_version": getattr(embeddings_service, "version", None)
            or getattr(embeddings_service, "model_version", None),
            "embedding_dimension": getattr(embeddings_service, "dimension", None)
            or getattr(embeddings_service, "dimensions", None),
        }
    except Exception as exc:  # pragma: no cover - environment dependent
        logger.debug("embedding provenance unavailable: %s", exc)
        return {}


async def record_index_contract(
    db: AsyncSession,
    tenant: str,
    repository_id,
    *,
    branch: str = "main",
    commit_sha: Optional[str] = None,
) -> CodeIndexVersion:
    """Persist an honest index contract + embedding provenance.

    Creates (or reuses) the code_indexes row, bumps code_index_versions
    with embedding provenance, and leaves status as QUEUED until a real
    pipeline reports completion.
    """
    repo = await resolve_repository(db, tenant, repository_id)
    existing = (
        (
            await db.execute(
                select(CodeIndex)
                .where(CodeIndex.repository_id == repo.id)
                .order_by(CodeIndex.created_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    provenance = _embedding_provenance()
    embedding_model = provenance.get("embedding_model")
    embedding_version = provenance.get("embedding_version")
    embedding_dimension = provenance.get("embedding_dimension")

    if existing is None:
        index = CodeIndex(
            repository_id=repo.id,
            status=IndexStatus.QUEUED.value,
            commit_sha=commit_sha,
            embedding_model=embedding_model,
            embedding_version=embedding_version,
            embedding_dimension=embedding_dimension,
        )
        db.add(index)
        await db.flush()
    else:
        index = existing
        if commit_sha:
            index.commit_sha = commit_sha
        if embedding_model:
            index.embedding_model = embedding_model
            index.embedding_version = embedding_version
            index.embedding_dimension = embedding_dimension
        index.status = IndexStatus.QUEUED.value

    count = (
        await db.scalar(
            select(func.count())
            .select_from(CodeIndexVersion)
            .where(CodeIndexVersion.index_id == index.id)
        )
    ) or 0
    version = CodeIndexVersion(
        index_id=index.id,
        version_number=int(count) + 1,
        embedding_model=embedding_model,
        embedding_version=embedding_version,
        embedding_dimension=embedding_dimension,
        commit_sha=commit_sha,
        is_active=(count == 0),
    )
    db.add(version)
    await db.flush()
    await emit_event(
        "CodeIndexRequested",
        {
            "index_id": str(index.id),
            "repository_id": str(repo.id),
            "commit_sha": commit_sha,
            "embedding_model": embedding_model,
            "embedding_version": embedding_version,
            "embedding_dimension": embedding_dimension,
            "version_number": version.version_number,
        },
        tenant,
    )
    return version


async def activate_index_version(
    db: AsyncSession, tenant: str, index_id, version_id
) -> CodeIndexVersion:
    """Activate a version after a real pipeline confirms completion."""
    index = await db.get(CodeIndex, _as_uuid(index_id))
    if index is None:
        raise NotFoundError("index not found")
    version = await db.get(CodeIndexVersion, _as_uuid(version_id))
    if version is None or version.index_id != index.id:
        raise NotFoundError("index version not found")
    await db.execute(
        CodeIndexVersion.__table__
        .update()
        .where(CodeIndexVersion.index_id == index.id)
        .values(is_active=False)
    )
    version.is_active = True
    await db.flush()
    return version


async def ensure_symbols_for_path(
    db: AsyncSession,
    tenant: str,
    repository_id,
    path: str,
    *,
    limit: int = 50,
):
    """Scoped symbol retrieval for a workspace file path."""
    repo = await resolve_repository(db, tenant, repository_id)
    return await get_symbols_for_path(db, repo.id, path, limit=limit)


async def index_overview(db: AsyncSession, tenant: str, repository_id) -> dict:
    repo = await resolve_repository(db, tenant, repository_id)
    index = (
        (
            await db.execute(
                select(CodeIndex)
                .where(CodeIndex.repository_id == repo.id)
                .order_by(CodeIndex.created_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    if index is None:
        return {
            "repository_id": str(repo.id),
            "indexed": False,
            "status": "NO_INDEX",
        }
    return {
        "repository_id": str(repo.id),
        "index_id": str(index.id),
        "indexed": index.status == IndexStatus.READY.value,
        "status": index.status,
        "embedding_model": index.embedding_model,
        "embedding_version": index.embedding_version,
        "embedding_dimension": index.embedding_dimension,
        "commit_sha": index.commit_sha,
        "files_total": index.files_total,
        "symbols_extracted": index.symbols_extracted,
    }


async def trigger_full_pipeline(
    db: AsyncSession,
    tenant: str,
    repository_id,
    *,
    branch: str = "main",
    commit_sha: Optional[str] = None,
    rebuild: bool = False,
) -> dict:
    """Best-effort dispatch to the real indexing pipeline.

    If the pipeline is unavailable (no cloned content), the index stays
    QUEUED and an honest error is surfaced — results are never faked.
    """
    repo = await resolve_repository(db, tenant, repository_id)
    try:
        from app.code_intelligence.pipeline import IndexingPipeline

        pipeline = IndexingPipeline(db)
        result = await pipeline.index_repository(
            repo_id=repo.id, commit_sha=commit_sha, branch=branch, rebuild=rebuild
        )
        return {
            "ok": True,
            "repository_id": str(repo.id),
            "result": result,
        }
    except Exception as exc:
        logger.warning("indexing pipeline unavailable for %s: %s", repo.id, exc)
        return {
            "ok": False,
            "repository_id": str(repo.id),
            "error": f"indexing content unavailable: {exc}",
            "index_status": IndexStatus.QUEUED.value,
        }


def _repo_payload(repo: Repository) -> dict:
    return {
        "id": str(repo.id),
        "name": repo.name,
        "default_branch": repo.default_branch,
    }