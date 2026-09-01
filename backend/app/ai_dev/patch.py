"""Patch engineering — Volume 67 Commit 1.

Patches are first-class versioned artifacts with integrity hashes
(sha256 per file), unified diffs and generated rollback diffs. Applying
a patch requires the caller to supply current file content so a stale
edit is rejected deterministically.
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_dev.common import (
    MAX_PATCH_FILES,
    NotFoundError,
    PatchAlreadyAppliedError,
    StalePatchError,
    _as_uuid,
    emit_event,
    resolve_repository,
)
from app.ai_dev.models import CodePatch

logger = logging.getLogger(__name__)


def sha256_of(text: str | None) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def build_unified_diff(path: str, old_content: str, new_content: str, context: int = 3) -> str:
    import difflib

    old_lines = (old_content or "").splitlines(True)
    new_lines = (new_content or "").splitlines(True)
    return "".join(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            n=context,
        )
    )


def _normalize_files(files: list[dict]) -> list[dict]:
    normalized = []
    for entry in files:
        path = (entry.get("path") or "").strip()
        if not path:
            continue
        old_content = entry.get("old_content") or ""
        new_content = entry.get("new_content")
        if new_content is None:
            new_content = old_content
        old_hash = entry.get("old_hash") or sha256_of(old_content)
        new_hash = sha256_of(new_content)
        if old_hash and old_hash == new_hash:
            continue  # no-op edit dropped
        normalized.append(
            {
                "path": path,
                "old_hash": old_hash,
                "new_hash": new_hash,
                "old_content": old_content,
                "new_content": new_content,
            }
        )
    return normalized


async def create_patch(
    db: AsyncSession,
    tenant: str,
    user_id: str,
    *,
    repository_id,
    title: str,
    files: list[dict],
    branch: str = "main",
    base_commit_sha: Optional[str] = None,
    workspace_id=None,
    model: Optional[str] = None,
    source: str = "ai",
    metadata: Optional[dict] = None,
) -> CodePatch:
    repo = await resolve_repository(db, tenant, repository_id)
    normalized = _normalize_files(files or [])
    if not normalized:
        raise ValueError("patch must contain at least one content-changing file")
    if len(normalized) > MAX_PATCH_FILES:
        raise ValueError(f"patch exceeds max files ({MAX_PATCH_FILES})")

    diffs = {}
    rollback_diffs = {}
    for entry in normalized:
        old_content = entry.get("old_content") or ""
        new_content = entry["new_content"]
        diffs[entry["path"]] = build_unified_diff(entry["path"], old_content, new_content)
        rollback_diffs[entry["path"]] = build_unified_diff(
            entry["path"], new_content, old_content
        )

    patch = CodePatch(
        tenant=tenant,
        workspace_id=workspace_id,
        repository_id=repo.id,
        branch=branch or repo.default_branch,
        base_commit_sha=base_commit_sha,
        title=title[:255],
        model=model,
        source=source or "ai",
        status="CREATED",
        files=normalized,
        diffs=diffs,
        rollback_diffs=rollback_diffs,
        created_by=user_id,
        author=user_id,
        metadata_=metadata or {"repository_full_name": repo.full_name},
    )
    db.add(patch)
    await db.flush()
    await emit_event(
        "CodePatchProposed",
        {
            "patch_id": str(patch.id),
            "repository_id": str(repo.id),
            "title": patch.title,
            "files": len(normalized),
            "model": model,
        },
        tenant,
    )
    return patch


async def get_patch(db: AsyncSession, tenant: str, patch_id) -> CodePatch:
    patch = await db.get(CodePatch, _as_uuid(patch_id))
    if patch is None or patch.tenant != tenant:
        raise NotFoundError("patch not found")
    return patch


async def list_patches(
    db: AsyncSession,
    tenant: str,
    *,
    repository_id=None,
    status: Optional[str] = None,
    limit: int = 50,
) -> list[CodePatch]:
    stmt = select(CodePatch).where(CodePatch.tenant == tenant)
    if repository_id:
        stmt = stmt.where(CodePatch.repository_id == repository_id)
    if status:
        stmt = stmt.where(CodePatch.status == status.upper())
    rows = (
        (
            await db.execute(
                stmt.order_by(desc(CodePatch.created_at)).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def apply_patch(
    db: AsyncSession,
    tenant: str,
    user_id: str,
    patch_id,
    *,
    current_files: Optional[dict] = None,
) -> CodePatch:
    """Apply a patch after re-verifying staleness against current content."""
    patch = await get_patch(db, tenant, patch_id)
    if patch.status != "CREATED":
        raise PatchAlreadyAppliedError(f"patch is {patch.status}, not CREATED")
    current_files = current_files or {}
    for entry in patch.files or []:
        path = entry["path"]
        expected = entry.get("old_hash")
        if not expected:
            continue
        if path not in current_files:
            raise StalePatchError(f"current content missing for {path}")
        current_hash = sha256_of(current_files[path])
        if current_hash != expected:
            raise StalePatchError(f"{path} changed since patch was created (stale)")
    patch.status = "APPLIED"
    patch.applied_at = datetime.now(timezone.utc)
    patch.metadata_ = dict(patch.metadata_ or {})
    patch.metadata_["applied_by"] = user_id
    await db.flush()
    await emit_event(
        "CodePatchApplied",
        {"patch_id": str(patch.id), "repository_id": str(patch.repository_id), "applied_by": user_id},
        tenant,
    )
    return patch


async def rollback_patch(
    db: AsyncSession, tenant: str, user_id: str, patch_id
) -> CodePatch:
    patch = await get_patch(db, tenant, patch_id)
    if patch.status != "APPLIED":
        raise ValueError(f"only APPLIED patches can be rolled back (status={patch.status})")
    patch.status = "ROLLED_BACK"
    patch.rolled_back_at = datetime.now(timezone.utc)
    patch.metadata_ = dict(patch.metadata_ or {})
    patch.metadata_["rolled_back_by"] = user_id
    await db.flush()
    await emit_event(
        "CodePatchRolledBack",
        {"patch_id": str(patch.id), "repository_id": str(patch.repository_id)},
        tenant,
    )
    return patch


async def reject_patch(db: AsyncSession, tenant: str, user_id: str, patch_id, reason: Optional[str] = None) -> CodePatch:
    patch = await get_patch(db, tenant, patch_id)
    if patch.status not in ("CREATED", "APPLIED"):
        raise ValueError(f"patch cannot be rejected (status={patch.status})")
    patch.status = "REJECTED"
    patch.metadata_ = dict(patch.metadata_ or {})
    patch.metadata_["rejected_by"] = user_id
    patch.metadata_["rejection_reason"] = reason
    await db.flush()
    return patch