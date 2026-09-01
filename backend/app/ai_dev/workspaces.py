"""Developer workspaces — Volume 67 Commit 1."""

from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_dev.common import (
    PermissionError_,
    _as_uuid,
    emit_event,
    resolve_repository,
)
from app.ai_dev.models import CodeWorkspace
from app.models.repository import Repository


async def create_workspace(
    db: AsyncSession,
    tenant: str,
    user_id: str,
    *,
    name: str,
    repository_id,
    branch: str = "main",
    commit_sha: Optional[str] = None,
    description: Optional[str] = None,
    owner: Optional[str] = None,
    pinned: bool = False,
    classification: str = "INTERNAL",
) -> CodeWorkspace:
    repo = await resolve_repository(db, tenant, repository_id)
    ws = CodeWorkspace(
        tenant=tenant,
        name=name[:128],
        description=description,
        repository_id=repo.id,
        branch=branch or "main",
        commit_sha=commit_sha,
        owner=owner or user_id,
        pinned=bool(pinned),
        classification=classification,
        metadata_={"created_by": user_id, "repository_name": repo.name},
    )
    db.add(ws)
    await db.flush()
    await emit_event(
        "CodeWorkspaceCreated",
        {
            "workspace_id": str(ws.id),
            "repository_id": str(repo.id),
            "branch": ws.branch,
            "created_by": user_id,
        },
        tenant,
    )
    return ws


async def get_workspace(db: AsyncSession, tenant: str, workspace_id) -> CodeWorkspace | None:
    ws = await db.get(CodeWorkspace, _as_uuid(workspace_id))
    if ws is None or ws.tenant != tenant:
        return None
    return ws


async def list_workspaces(db: AsyncSession, tenant: str, *, repository_id=None, limit: int = 50) -> list[CodeWorkspace]:
    stmt = select(CodeWorkspace).where(CodeWorkspace.tenant == tenant)
    if repository_id:
        stmt = stmt.where(CodeWorkspace.repository_id == repository_id)
    rows = (
        (
            await db.execute(
                stmt.order_by(desc(CodeWorkspace.created_at)).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def pin_workspace(db: AsyncSession, tenant: str, workspace_id, *, pinned: bool) -> CodeWorkspace:
    ws = await get_workspace(db, tenant, workspace_id)
    if ws is None:
        raise NotFoundError("workspace not found")
    ws.pinned = bool(pinned)
    await db.flush()
    await emit_event(
        "CodeWorkspacePinned",
        {"workspace_id": str(ws.id), "pinned": ws.pinned},
        tenant,
    )
    return ws


async def enforce_scope(db: AsyncSession, tenant: str, repository_id):
    """Authorization: ensure repository belongs to the tenant before use."""
    repo = await resolve_repository(db, tenant, repository_id)
    if isinstance(repo, Repository) is False and not repo:
        raise PermissionError_("repository not accessible")
    return repo