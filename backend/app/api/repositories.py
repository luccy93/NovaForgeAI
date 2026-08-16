import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.repository import Repository
from app.services.graph_store import GraphStoreService
from app.services.repo_importer import GitImportError, RepoImporter

router = APIRouter()


class RepositoryCreate(BaseModel):
    name: str
    full_name: str
    description: Optional[str] = None
    private: bool = True
    git_url: Optional[str] = None
    default_branch: str = "main"
    language: Optional[str] = None
    organization_id: Optional[str] = None


class RepositoryOut(BaseModel):
    id: str
    name: str
    full_name: str
    description: Optional[str]
    private: bool
    git_url: Optional[str]
    default_branch: str
    language: Optional[str]
    size: Optional[int]
    last_indexed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class GraphNode(BaseModel):
    id: str
    file_path: str
    language: str
    score: Optional[float] = None


class GraphRelationship(BaseModel):
    from_id: str
    to_id: str
    type: str


class CodeGraphOut(BaseModel):
    nodes: list[GraphNode]
    relationships: list[GraphRelationship]


@router.post("", response_model=RepositoryOut, status_code=status.HTTP_201_CREATED)
async def create_repository(
    request: RepositoryCreate,
    db: AsyncSession = Depends(get_db),
) -> RepositoryOut:
    org_id: Optional[uuid.UUID] = None
    if request.organization_id:
        try:
            org_id = uuid.UUID(request.organization_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid organization_id")

    repo = Repository(
        name=request.name,
        full_name=request.full_name,
        description=request.description,
        private=request.private,
        git_url=request.git_url,
        default_branch=request.default_branch,
        language=request.language,
        organization_id=org_id,
    )
    db.add(repo)
    await db.flush()
    await db.refresh(repo)
    return _repo_to_out(repo)


@router.get("", response_model=list[RepositoryOut])
async def list_repositories(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    language: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[RepositoryOut]:
    stmt = select(Repository).order_by(Repository.updated_at.desc()).offset(offset).limit(limit)
    if language:
        stmt = stmt.where(Repository.language == language)
    result = await db.execute(stmt)
    repos = result.scalars().all()
    return [_repo_to_out(r) for r in repos]


@router.get("/{repository_id}", response_model=RepositoryOut)
async def get_repository(
    repository_id: str,
    db: AsyncSession = Depends(get_db),
) -> RepositoryOut:
    repo = await _get_repo_or_404(repository_id, db)
    return _repo_to_out(repo)


@router.get("/{repository_id}/graph", response_model=CodeGraphOut)
async def get_repository_graph(
    repository_id: str,
    db: AsyncSession = Depends(get_db),
) -> CodeGraphOut:
    repo = await _get_repo_or_404(repository_id, db)

    graph_store = GraphStoreService()
    try:
        graph_data = await graph_store.get_code_graph(repo.full_name)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Graph store error: {e}")
    finally:
        await graph_store._driver.close()

    return CodeGraphOut(
        nodes=[GraphNode(**n) for n in graph_data.get("nodes", [])],
        relationships=[
            GraphRelationship(from_id=r["from"], to_id=r["to"], type=r["type"])
            for r in graph_data.get("relationships", [])
        ],
    )


@router.delete("/{repository_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_repository(
    repository_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    repo = await _get_repo_or_404(repository_id, db)
    await db.delete(repo)


@router.post("/{repository_id}/index", response_model=RepositoryOut)
async def trigger_reindex(
    repository_id: str,
    db: AsyncSession = Depends(get_db),
) -> RepositoryOut:
    repo = await _get_repo_or_404(repository_id, db)
    repo.last_indexed_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(repo)
    return _repo_to_out(repo)


@router.post("/import", response_model=RepositoryOut, status_code=status.HTTP_201_CREATED)
async def import_repository(
    request: RepositoryCreate,
    db: AsyncSession = Depends(get_db),
) -> RepositoryOut:
    org_id: Optional[uuid.UUID] = None
    if request.organization_id:
        try:
            org_id = uuid.UUID(request.organization_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid organization_id")

    if not request.git_url:
        raise HTTPException(status_code=400, detail="git_url is required for import")

    repo = Repository(
        name=request.name,
        full_name=request.full_name,
        description=request.description,
        private=request.private,
        git_url=request.git_url,
        default_branch=request.default_branch,
        language=request.language,
        organization_id=org_id,
    )
    db.add(repo)
    await db.flush()
    await db.refresh(repo)

    importer = RepoImporter(db=db)
    try:
        stats = await importer.import_from_url(repo.id, request.git_url, request.default_branch)
    except GitImportError as exc:
        raise HTTPException(status_code=502, detail=f"Repository import failed: {exc}")

    repo.last_indexed_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(repo)

    return _repo_to_out(repo)


@router.post("/{repository_id}/import-local", response_model=RepositoryOut)
async def import_local_repository(
    repository_id: str,
    local_path: str = Query(..., description="Absolute path to the local repository"),
    db: AsyncSession = Depends(get_db),
) -> RepositoryOut:
    repo = await _get_repo_or_404(repository_id, db)
    importer = RepoImporter(db=db)
    stats = await importer.import_from_path(repo.id, local_path)
    repo.last_indexed_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(repo)
    return _repo_to_out(repo)


async def _get_repo_or_404(repository_id: str, db: AsyncSession) -> Repository:
    try:
        rid = uuid.UUID(repository_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid repository_id")
    result = await db.execute(select(Repository).where(Repository.id == rid))
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repo


def _repo_to_out(repo: Repository) -> RepositoryOut:
    return RepositoryOut(
        id=str(repo.id),
        name=repo.name,
        full_name=repo.full_name,
        description=repo.description,
        private=repo.private,
        git_url=repo.git_url,
        default_branch=repo.default_branch,
        language=repo.language,
        size=repo.size,
        last_indexed_at=repo.last_indexed_at,
        created_at=repo.created_at,
        updated_at=repo.updated_at,
    )
