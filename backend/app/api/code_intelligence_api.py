"""Code Intelligence API — indexing, search, analysis, and RAG endpoints."""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import _get_current_user
from app.core.database import get_db
from app.models.user import User
from app.models.repository import Repository

from app.code_intelligence.models import (
    CodeIndex,
    CodeIndexVersion,
    CodeFile,
    CodeSymbol,
    CodeReference,
    CodeCall,
    CodeImport,
    CodeMetrics,
    CodeSmell,
    CodeChunk,
    IndexStatus,
    FileStatus,
    SymbolType,
    ReferenceType,
    Severity,
    SmellType,
)
from app.code_intelligence.pipeline import IndexingPipeline
from app.code_intelligence.search import HybridSearchEngine, SearchResult
from app.code_intelligence.impact import ImpactAnalyzer, ImpactResult, ChangeScope, RenameImpact
from app.code_intelligence.chunking import RAGContextBuilder
from app.code_intelligence.metrics import MetricsCalculator
from app.code_intelligence.smells import SmellDetector
from app.code_intelligence.security import SecurityScanner
from app.code_intelligence.architecture import ArchitectureDiscovery, ArchitectureResult, RepositorySummary
from app.code_intelligence.incremental import IncrementalIndexer

router = APIRouter(tags=["Code Intelligence"])


# ─── Pydantic Request / Response Models ─────────────────────────────────────

# -- Index Management

class IndexCreateRequest(BaseModel):
    branch: str = "main"
    force_rebuild: bool = False

class IndexOut(BaseModel):
    id: str
    repository_id: str
    status: str
    branch: str
    file_count: int = 0
    symbol_count: int = 0
    index_size_bytes: int = 0
    created_at: str
    updated_at: str

class IndexVersionOut(BaseModel):
    id: str
    index_id: str
    version: int
    status: str
    commit_sha: Optional[str] = None
    files_changed: int = 0
    created_at: str

class IndexDiffRequest(BaseModel):
    base_version_id: str
    target_version_id: str

class IndexDiffOut(BaseModel):
    files_added: list[str] = []
    files_removed: list[str] = []
    files_modified: list[str] = []
    symbols_added: int = 0
    symbols_removed: int = 0
    symbols_modified: int = 0

# -- File Intelligence

class FileOut(BaseModel):
    id: str
    index_id: str
    path: str
    language: Optional[str] = None
    size_bytes: int = 0
    line_count: int = 0
    symbol_count: int = 0
    status: str
    indexed_at: Optional[str] = None

class FileContentRequest(BaseModel):
    file_id: str
    include_symbols: bool = True
    include_references: bool = True

class FileContentOut(BaseModel):
    file: FileOut
    symbols: list[dict] = []
    references: list[dict] = []
    imports: list[dict] = []

# -- Symbol Intelligence

class SymbolOut(BaseModel):
    id: str
    file_id: str
    name: str
    symbol_type: str
    qualified_name: Optional[str] = None
    line_start: int
    line_end: int
    column_start: int = 0
    column_end: int = 0
    docstring: Optional[str] = None
    signature: Optional[str] = None
    complexity: int = 0

class SymbolDetailOut(SymbolOut):
    calls: list[dict] = []
    called_by: list[dict] = []
    references: list[dict] = []
    children: list[dict] = []

# -- Graph Intelligence

class GraphNodeOut(BaseModel):
    id: str
    label: str
    type: str
    file_path: Optional[str] = None

class GraphEdgeOut(BaseModel):
    source: str
    target: str
    edge_type: str
    weight: float = 1.0

class GraphOut(BaseModel):
    nodes: list[GraphNodeOut] = []
    edges: list[GraphEdgeOut] = []
    stats: dict = {}

class GraphTraversalRequest(BaseModel):
    symbol_id: str
    direction: str = Field("both", pattern=r"^(outgoing|incoming|both)$")
    max_depth: int = Field(3, ge=1, le=10)
    edge_types: list[str] = []

# -- Code Quality

class CodeSmellOut(BaseModel):
    id: str
    file_id: str
    symbol_id: Optional[str] = None
    smell_type: str
    severity: str
    message: str
    line_start: int
    line_end: int
    suggestion: Optional[str] = None
    effort_estimate: Optional[str] = None

class SmellScanRequest(BaseModel):
    file_paths: list[str] = []
    smell_types: list[str] = []
    min_severity: str = "info"

class SmellScanOut(BaseModel):
    total_smells: int = 0
    by_severity: dict = {}
    by_type: dict = {}
    smells: list[CodeSmellOut] = []

class CodeMetricsOut(BaseModel):
    file_id: str
    path: str
    line_count: int = 0
    code_lines: int = 0
    comment_lines: int = 0
    blank_lines: int = 0
    cyclomatic_complexity: int = 0
    cognitive_complexity: int = 0
    maintainability_index: float = 0.0

# -- Security

class SecurityVulnerabilityOut(BaseModel):
    id: str
    file_id: str
    symbol_id: Optional[str] = None
    vulnerability_type: str
    severity: str
    message: str
    line_start: int
    line_end: int
    recommendation: Optional[str] = None

class SecurityScanRequest(BaseModel):
    file_paths: list[str] = []
    vulnerability_types: list[str] = []

class SecurityScanOut(BaseModel):
    total_vulnerabilities: int = 0
    by_severity: dict = {}
    vulnerabilities: list[SecurityVulnerabilityOut] = []

class SecretOut(BaseModel):
    file_id: str
    file_path: str
    line: int
    secret_type: str
    severity: str = "high"

class SecretScanOut(BaseModel):
    total_secrets: int = 0
    secrets: list[SecretOut] = []

# -- Architecture

class ArchitectureOverviewOut(BaseModel):
    layers: list[dict] = []
    modules: list[dict] = []
    dependencies: list[dict] = []
    summary: Optional[RepositorySummary] = None

class DependencyGraphOut(BaseModel):
    nodes: list[dict] = []
    edges: list[dict] = []
    circular_dependencies: list[list[str]] = []

# -- Impact Analysis

class ImpactAnalysisRequest(BaseModel):
    symbol_id: Optional[str] = None
    file_path: Optional[str] = None
    change_type: str = Field("modify", pattern=r"^(modify|delete|move)$")

class BreakingChangeOut(BaseModel):
    symbol_name: str
    symbol_type: str
    file_path: str
    line: int
    reason: str
    severity: str

class UnusedItemOut(BaseModel):
    symbol_name: str
    symbol_type: str
    file_path: str
    line: int
    confidence: float = 0.0

class ImpactAnalysisOut(BaseModel):
    affected_files: int = 0
    affected_symbols: int = 0
    breaking_changes: list[BreakingChangeOut] = []
    unused_items: list[UnusedItemOut] = []
    impact_score: float = 0.0
    risk_level: str = "low"

class DownstreamRequest(BaseModel):
    symbol_id: str
    max_depth: int = Field(5, ge=1, le=15)

class DownstreamOut(BaseModel):
    direct_dependencies: list[dict] = []
    transitive_dependencies: list[dict] = []
    total_affected: int = 0

class DependencyRequest(BaseModel):
    symbol_id: str
    max_depth: int = Field(5, ge=1, le=15)

class DependencyOut(BaseModel):
    direct_upstreams: list[dict] = []
    transitive_upstreams: list[dict] = []
    total_dependencies: int = 0

# -- Search

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    file_types: list[str] = []
    symbol_types: list[str] = []
    max_results: int = Field(20, ge=1, le=100)
    include_context: bool = True

class SearchResultItemOut(BaseModel):
    id: str
    name: str
    result_type: str
    file_path: Optional[str] = None
    line: Optional[int] = None
    score: float = 0.0
    snippet: Optional[str] = None
    context: Optional[dict] = None

class SearchOut(BaseModel):
    query: str
    total_results: int = 0
    results: list[SearchResultItemOut] = []
    search_time_ms: float = 0.0

class SymbolSearchRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    symbol_types: list[str] = []
    fuzzy: bool = True

class SymbolSearchOut(BaseModel):
    results: list[SymbolOut] = []
    total: int = 0

# -- RAG Context

class RAGContextRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    file_path: Optional[str] = None
    symbol_id: Optional[str] = None
    max_tokens: int = Field(4096, ge=256, le=32000)
    include_graph: bool = True
    include_metrics: bool = False

class RAGContextOut(BaseModel):
    query: str
    context_chunks: list[dict] = []
    relevant_symbols: list[dict] = []
    graph_context: Optional[dict] = None
    metrics_summary: Optional[dict] = None
    total_tokens_estimate: int = 0

# -- Index Health

class IndexHealthOut(BaseModel):
    index_id: str
    status: str
    last_updated: Optional[str] = None
    file_count: int = 0
    symbol_count: int = 0
    chunk_count: int = 0
    index_size_bytes: int = 0
    health_score: float = 0.0
    issues: list[str] = []

class IndexRepairRequest(BaseModel):
    repair_types: list[str] = []

class IndexRepairOut(BaseModel):
    repairs_performed: list[str] = []
    issues_fixed: int = 0
    issues_remaining: int = 0


# ─── Helpers ────────────────────────────────────────────────────────────────

async def _get_repo_access(
    repository_id: uuid.UUID,
    user: User,
    db: AsyncSession,
) -> Repository:
    """Fetch repository and verify user has access."""
    result = await db.execute(
        select(Repository).where(Repository.id == repository_id)
    )
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
    if repo.organization_id:
        user_org_ids = [o.id for o in getattr(user, "organizations", []) or []]
        if user_org_ids and repo.organization_id not in user_org_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return repo


async def _get_active_index(
    repository_id: uuid.UUID,
    db: AsyncSession,
) -> CodeIndex:
    """Fetch the most recent non-failed index for a repository."""
    result = await db.execute(
        select(CodeIndex)
        .where(CodeIndex.repository_id == repository_id)
        .where(CodeIndex.status != IndexStatus.FAILED)
        .order_by(CodeIndex.created_at.desc())
        .limit(1)
    )
    idx = result.scalar_one_or_none()
    if not idx:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active index found for this repository",
        )
    return idx


async def _get_file(
    file_id: uuid.UUID,
    index_id: uuid.UUID,
    db: AsyncSession,
) -> CodeFile:
    result = await db.execute(
        select(CodeFile).where(CodeFile.id == file_id, CodeFile.index_id == index_id)
    )
    f = result.scalar_one_or_none()
    if not f:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return f


async def _get_symbol(
    symbol_id: uuid.UUID,
    index_id: uuid.UUID,
    db: AsyncSession,
) -> CodeSymbol:
    result = await db.execute(
        select(CodeSymbol).where(CodeSymbol.id == symbol_id)
        .join(CodeFile, CodeSymbol.file_id == CodeFile.id)
        .where(CodeFile.index_id == index_id)
    )
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Symbol not found")
    return s


# ─── 1. Index Management ───────────────────────────────────────────────────

@router.post("/{repository_id}/index", response_model=IndexOut, status_code=status.HTTP_201_CREATED)
async def create_index(
    repository_id: uuid.UUID,
    body: IndexCreateRequest,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger a full code index build for a repository."""
    await _get_repo_access(repository_id, user, db)
    pipeline = IndexingPipeline(db_session=db)
    try:
        index = await pipeline.run_index(
            branch=body.branch,
            force_rebuild=body.force_rebuild,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    return IndexOut(
        id=str(index.id),
        repository_id=str(index.repository_id),
        status=index.status,
        branch=index.branch,
        file_count=index.file_count or 0,
        symbol_count=index.symbol_count or 0,
        index_size_bytes=index.index_size_bytes or 0,
        created_at=index.created_at.isoformat(),
        updated_at=index.updated_at.isoformat(),
    )


@router.get("/{repository_id}/index", response_model=IndexOut)
async def get_index(
    repository_id: uuid.UUID,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current active index for a repository."""
    await _get_repo_access(repository_id, user, db)
    idx = await _get_active_index(repository_id, db)
    return IndexOut(
        id=str(idx.id),
        repository_id=str(idx.repository_id),
        status=idx.status,
        branch=idx.branch,
        file_count=idx.file_count or 0,
        symbol_count=idx.symbol_count or 0,
        index_size_bytes=idx.index_size_bytes or 0,
        created_at=idx.created_at.isoformat(),
        updated_at=idx.updated_at.isoformat(),
    )


@router.get("/{repository_id}/index/versions", response_model=list[IndexVersionOut])
async def list_index_versions(
    repository_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List historical versions of the code index."""
    await _get_repo_access(repository_id, user, db)
    idx = await _get_active_index(repository_id, db)
    result = await db.execute(
        select(CodeIndexVersion)
        .where(CodeIndexVersion.index_id == idx.id)
        .order_by(CodeIndexVersion.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    versions = result.scalars().all()
    return [
        IndexVersionOut(
            id=str(v.id),
            index_id=str(v.index_id),
            version=v.version,
            status=v.status,
            commit_sha=v.commit_sha,
            files_changed=v.files_changed or 0,
            created_at=v.created_at.isoformat(),
        )
        for v in versions
    ]


@router.post("/{repository_id}/index/rebuild", response_model=IndexOut)
async def rebuild_index(
    repository_id: uuid.UUID,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Force a full re-index of the repository."""
    await _get_repo_access(repository_id, user, db)
    pipeline = IndexingPipeline(db_session=db)
    try:
        index = await pipeline.run_index(branch="main", force_rebuild=True)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    return IndexOut(
        id=str(index.id),
        repository_id=str(index.repository_id),
        status=index.status,
        branch=index.branch,
        file_count=index.file_count or 0,
        symbol_count=index.symbol_count or 0,
        index_size_bytes=index.index_size_bytes or 0,
        created_at=index.created_at.isoformat(),
        updated_at=index.updated_at.isoformat(),
    )


@router.delete("/{repository_id}/index", status_code=status.HTTP_204_NO_CONTENT)
async def delete_index(
    repository_id: uuid.UUID,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete the index and all associated data for a repository."""
    await _get_repo_access(repository_id, user, db)
    result = await db.execute(
        select(CodeIndex).where(CodeIndex.repository_id == repository_id)
    )
    idx = result.scalar_one_or_none()
    if not idx:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No index found")
    await db.delete(idx)
    await db.commit()
    return None


@router.post("/{repository_id}/index/diff", response_model=IndexDiffOut)
async def diff_index_versions(
    repository_id: uuid.UUID,
    body: IndexDiffRequest,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Compare two index versions and return added/removed/modified files and symbols."""
    await _get_repo_access(repository_id, user, db)
    base_result = await db.execute(
        select(CodeIndexVersion).where(CodeIndexVersion.id == uuid.UUID(body.base_version_id))
    )
    base = base_result.scalar_one_or_none()
    target_result = await db.execute(
        select(CodeIndexVersion).where(CodeIndexVersion.id == uuid.UUID(body.target_version_id))
    )
    target = target_result.scalar_one_or_none()
    if not base or not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")

    base_files_result = await db.execute(
        select(CodeFile).where(CodeFile.index_id == base.index_id)
    )
    base_files = {f.path: f for f in base_files_result.scalars().all()}
    target_files_result = await db.execute(
        select(CodeFile).where(CodeFile.index_id == target.index_id)
    )
    target_files = {f.path: f for f in target_files_result.scalars().all()}

    files_added = [p for p in target_files if p not in base_files]
    files_removed = [p for p in base_files if p not in target_files]
    files_modified = [
        p for p in base_files
        if p in target_files and target_files[p].updated_at > base_files[p].updated_at
    ]

    symbols_added_q = await db.execute(
        select(func.count()).select_from(CodeSymbol)
        .join(CodeFile, CodeSymbol.file_id == CodeFile.id)
        .where(CodeFile.index_id == target.index_id)
    )
    symbols_base_q = await db.execute(
        select(func.count()).select_from(CodeSymbol)
        .join(CodeFile, CodeSymbol.file_id == CodeFile.id)
        .where(CodeFile.index_id == base.index_id)
    )
    symbols_added_count = symbols_added_q.scalar() or 0
    symbols_base_count = symbols_base_q.scalar() or 0

    return IndexDiffOut(
        files_added=files_added,
        files_removed=files_removed,
        files_modified=files_modified,
        symbols_added=max(0, symbols_added_count - symbols_base_count),
        symbols_removed=max(0, symbols_base_count - symbols_added_count),
        symbols_modified=len(files_modified),
    )


# ─── 2. File Intelligence ──────────────────────────────────────────────────

@router.get("/{repository_id}/files", response_model=list[FileOut])
async def list_files(
    repository_id: uuid.UUID,
    language: Optional[str] = None,
    path_prefix: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all indexed files with optional filtering."""
    await _get_repo_access(repository_id, user, db)
    idx = await _get_active_index(repository_id, db)
    query = select(CodeFile).where(CodeFile.index_id == idx.id)
    if language:
        query = query.where(CodeFile.language == language)
    if path_prefix:
        query = query.where(CodeFile.file_path.startswith(path_prefix))
    query = query.order_by(CodeFile.file_path).limit(limit).offset(offset)
    result = await db.execute(query)
    files = result.scalars().all()
    return [
        FileOut(
            id=str(f.id),
            index_id=str(f.index_id),
            path=f.path,
            language=f.language,
            size_bytes=f.size_bytes or 0,
            line_count=f.line_count or 0,
            symbol_count=f.symbol_count or 0,
            status=f.status,
            indexed_at=f.indexed_at.isoformat() if f.indexed_at else None,
        )
        for f in files
    ]



@router.get("/{repository_id}/files/by-language", response_model=dict)
async def get_files_by_language(
    repository_id: uuid.UUID,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get file count grouped by programming language."""
    await _get_repo_access(repository_id, user, db)
    idx = await _get_active_index(repository_id, db)
    result = await db.execute(
        select(CodeFile.language, func.count(CodeFile.id))
        .where(CodeFile.index_id == idx.id)
        .group_by(CodeFile.language)
    )
    return {row[0] or "unknown": row[1] for row in result.all()}


@router.get("/{repository_id}/files/{file_id}", response_model=FileContentOut)
async def get_file_content(
    repository_id: uuid.UUID,
    file_id: uuid.UUID,
    include_symbols: bool = Query(True),
    include_references: bool = Query(True),
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed file information including symbols, references, and imports."""
    await _get_repo_access(repository_id, user, db)
    idx = await _get_active_index(repository_id, db)
    f = await _get_file(file_id, idx.id, db)

    file_out = FileOut(
        id=str(f.id),
        index_id=str(f.index_id),
        path=f.path,
        language=f.language,
        size_bytes=f.size_bytes or 0,
        line_count=f.line_count or 0,
        symbol_count=f.symbol_count or 0,
        status=f.status,
        indexed_at=f.indexed_at.isoformat() if f.indexed_at else None,
    )

    symbols_data: list[dict] = []
    references_data: list[dict] = []
    imports_data: list[dict] = []

    if include_symbols:
        syms_result = await db.execute(
            select(CodeSymbol).where(CodeSymbol.file_id == f.id).order_by(CodeSymbol.start_line)
        )
        symbols_data = [
            {
                "id": str(s.id),
                "name": s.name,
                "symbol_type": s.symbol_type,
                "line_start": s.line_start,
                "line_end": s.line_end,
                "signature": s.signature,
            }
            for s in syms_result.scalars().all()
        ]

    if include_references:
        refs_result = await db.execute(
            select(CodeReference).where(CodeReference.source_file_id == f.id)
        )
        references_data = [
            {
                "id": str(r.id),
                "reference_type": r.reference_type,
                "target_file_id": str(r.target_file_id) if r.target_file_id else None,
                "line": r.line,
            }
            for r in refs_result.scalars().all()
        ]

    imports_result = await db.execute(
        select(CodeImport).where(CodeImport.source_file_id == f.id)
    )
    imports_data = [
        {
            "id": str(im.id),
            "module_path": im.module_path,
            "names": im.names,
            "line": im.line,
        }
        for im in imports_result.scalars().all()
    ]

    return FileContentOut(
        file=file_out,
        symbols=symbols_data,
        references=references_data,
        imports=imports_data,
    )


@router.get("/{repository_id}/files/{file_id}/metrics", response_model=CodeMetricsOut)
async def get_file_metrics(
    repository_id: uuid.UUID,
    file_id: uuid.UUID,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed code metrics for a specific file."""
    await _get_repo_access(repository_id, user, db)
    idx = await _get_active_index(repository_id, db)
    f = await _get_file(file_id, idx.id, db)
    metrics_calc = MetricsCalculator(db_session=db)
    try:
        metrics = await metrics_calc.calculate_file_metrics(file_id=file_id)
    except Exception:
        metrics_result = await db.execute(
            select(CodeMetrics).where(CodeMetrics.file_id == file_id)
        )
        metrics = metrics_result.scalar_one_or_none()
    if not metrics:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Metrics not available for this file")
    return CodeMetricsOut(
        file_id=str(metrics.file_id),
        path=f.path,
        line_count=metrics.line_count or 0,
        code_lines=metrics.code_lines or 0,
        comment_lines=metrics.comment_lines or 0,
        blank_lines=metrics.blank_lines or 0,
        cyclomatic_complexity=metrics.cyclomatic_complexity or 0,
        cognitive_complexity=metrics.cognitive_complexity or 0,
        maintainability_index=metrics.maintainability_index or 0.0,
    )


# ─── 3. Symbol Intelligence ────────────────────────────────────────────────

@router.get("/{repository_id}/symbols", response_model=list[SymbolOut])
async def list_symbols(
    repository_id: uuid.UUID,
    symbol_type: Optional[str] = None,
    file_id: Optional[uuid.UUID] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all symbols in the repository with optional filtering."""
    await _get_repo_access(repository_id, user, db)
    idx = await _get_active_index(repository_id, db)
    query = (
        select(CodeSymbol)
        .join(CodeFile, CodeSymbol.file_id == CodeFile.id)
        .where(CodeFile.index_id == idx.id)
    )
    if symbol_type:
        query = query.where(CodeSymbol.symbol_type == symbol_type)
    if file_id:
        query = query.where(CodeSymbol.file_id == file_id)
    query = query.order_by(CodeSymbol.name).limit(limit).offset(offset)
    result = await db.execute(query)
    symbols = result.scalars().all()
    return [
        SymbolOut(
            id=str(s.id),
            file_id=str(s.file_id),
            name=s.name,
            symbol_type=s.symbol_type,
            qualified_name=s.qualified_name,
            line_start=s.line_start,
            line_end=s.line_end,
            column_start=s.column_start or 0,
            column_end=s.column_end or 0,
            docstring=s.docstring,
            signature=s.signature,
            complexity=s.complexity or 0,
        )
        for s in symbols
    ]


@router.get("/{repository_id}/symbols/{symbol_id}", response_model=SymbolDetailOut)
async def get_symbol_detail(
    repository_id: uuid.UUID,
    symbol_id: uuid.UUID,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed information about a symbol including call graph."""
    await _get_repo_access(repository_id, user, db)
    idx = await _get_active_index(repository_id, db)
    s = await _get_symbol(symbol_id, idx.id, db)

    calls_result = await db.execute(
        select(CodeCall).where(CodeCall.caller_symbol_id == symbol_id)
    )
    calls = [
        {"callee_id": str(c.callee_id), "call_type": c.call_type, "line": c.line}
        for c in calls_result.scalars().all()
    ]

    called_by_result = await db.execute(
        select(CodeCall).where(CodeCall.callee_symbol_id == symbol_id)
    )
    called_by = [
        {"caller_id": str(c.caller_id), "call_type": c.call_type, "line": c.line}
        for c in called_by_result.scalars().all()
    ]

    refs_result = await db.execute(
        select(CodeReference).where(CodeReference.source_symbol_id == symbol_id)
    )
    references = [
        {"id": str(r.id), "reference_type": r.reference_type, "line": r.line}
        for r in refs_result.scalars().all()
    ]

    children_result = await db.execute(
        select(CodeSymbol).where(CodeSymbol.parent_symbol_id == symbol_id).order_by(CodeSymbol.start_line)
    )
    children = [
        {"id": str(c.id), "name": c.name, "symbol_type": c.symbol_type}
        for c in children_result.scalars().all()
    ]

    return SymbolDetailOut(
        id=str(s.id),
        file_id=str(s.file_id),
        name=s.name,
        symbol_type=s.symbol_type,
        qualified_name=s.qualified_name,
        line_start=s.line_start,
        line_end=s.line_end,
        column_start=s.column_start or 0,
        column_end=s.column_end or 0,
        docstring=s.docstring,
        signature=s.signature,
        complexity=s.complexity or 0,
        calls=calls,
        called_by=called_by,
        references=references,
        children=children,
    )


@router.get("/{repository_id}/symbols/{symbol_id}/calls", response_model=dict)
async def get_symbol_call_graph(
    repository_id: uuid.UUID,
    symbol_id: uuid.UUID,
    depth: int = Query(3, ge=1, le=10),
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the call graph for a symbol up to a given depth."""
    await _get_repo_access(repository_id, user, db)
    idx = await _get_active_index(repository_id, db)
    await _get_symbol(symbol_id, idx.id, db)

    visited: set[str] = set()
    outgoing: list[dict] = []

    async def _traverse(cid: uuid.UUID, current_depth: int):
        if current_depth > depth or str(cid) in visited:
            return
        visited.add(str(cid))
        result = await db.execute(select(CodeCall).where(CodeCall.caller_symbol_id == cid))
        for c in result.scalars().all():
            outgoing.append({
                "caller_id": str(c.caller_id),
                "callee_id": str(c.callee_id),
                "call_type": c.call_type,
                "line": c.line,
                "depth": current_depth,
            })
            await _traverse(c.callee_id, current_depth + 1)

    await _traverse(symbol_id, 1)
    return {"symbol_id": str(symbol_id), "depth": depth, "calls": outgoing, "total_edges": len(outgoing)}


@router.get("/{repository_id}/symbols/{symbol_id}/dependencies", response_model=DependencyOut)
async def get_symbol_dependencies(
    repository_id: uuid.UUID,
    symbol_id: uuid.UUID,
    max_depth: int = Query(5, ge=1, le=15),
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all upstream dependencies for a symbol."""
    await _get_repo_access(repository_id, user, db)
    idx = await _get_active_index(repository_id, db)
    s = await _get_symbol(symbol_id, idx.id, db)
    analyzer = ImpactAnalyzer(db_session=db)
    try:
        result = await analyzer.get_upstream_dependencies(symbol_id=str(symbol_id), max_depth=max_depth)
    except Exception:
        result = {"direct": [], "transitive": []}
    direct = result.get("direct", [])
    transitive = result.get("transitive", [])
    return DependencyOut(
        direct_upstreams=direct,
        transitive_upstreams=transitive,
        total_dependencies=len(direct) + len(transitive),
    )


# ─── 4. Graph Intelligence ─────────────────────────────────────────────────

@router.get("/{repository_id}/graph", response_model=GraphOut)
async def get_repository_graph(
    repository_id: uuid.UUID,
    limit: int = Query(200, ge=1, le=2000),
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the full code graph (nodes + edges) for a repository."""
    await _get_repo_access(repository_id, user, db)
    idx = await _get_active_index(repository_id, db)

    symbols_result = await db.execute(
        select(CodeSymbol)
        .join(CodeFile, CodeSymbol.file_id == CodeFile.id)
        .where(CodeFile.index_id == idx.id)
        .limit(limit)
    )
    symbols = symbols_result.scalars().all()
    symbol_ids = {s.id for s in symbols}
    nodes = [
        GraphNodeOut(id=str(s.id), label=s.name, type=s.symbol_type, file_path=None)
        for s in symbols
    ]

    calls_result = await db.execute(
        select(CodeCall)
        .where(CodeCall.caller_symbol_id.in_(symbol_ids))
        .where(CodeCall.callee_symbol_id.in_(symbol_ids))
    )
    edges = [
        GraphEdgeOut(
            source=str(c.caller_id),
            target=str(c.callee_id),
            edge_type=c.call_type or "calls",
        )
        for c in calls_result.scalars().all()
    ]

    return GraphOut(
        nodes=nodes,
        edges=edges,
        stats={"node_count": len(nodes), "edge_count": len(edges)},
    )


@router.post("/{repository_id}/graph/traverse", response_model=GraphOut)
async def traverse_graph(
    repository_id: uuid.UUID,
    body: GraphTraversalRequest,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Traverse the graph from a given symbol in a specified direction and depth."""
    await _get_repo_access(repository_id, user, db)
    idx = await _get_active_index(repository_id, db)
    await _get_symbol(uuid.UUID(body.symbol_id), idx.id, db)

    visited_nodes: set[str] = set()
    all_edges: list[GraphEdgeOut] = []

    async def _traverse(sid: uuid.UUID, current_depth: int):
        if current_depth > body.max_depth or str(sid) in visited_nodes:
            return
        visited_nodes.add(str(sid))

        if body.direction in ("outgoing", "both"):
            out_result = await db.execute(select(CodeCall).where(CodeCall.caller_symbol_id == sid))
            for c in out_result.scalars().all():
                if body.edge_types and (c.call_type or "calls") not in body.edge_types:
                    continue
                all_edges.append(GraphEdgeOut(
                    source=str(c.caller_id), target=str(c.callee_id),
                    edge_type=c.call_type or "calls",
                ))
                await _traverse(c.callee_id, current_depth + 1)

        if body.direction in ("incoming", "both"):
            in_result = await db.execute(select(CodeCall).where(CodeCall.callee_symbol_id == sid))
            for c in in_result.scalars().all():
                if body.edge_types and (c.call_type or "calls") not in body.edge_types:
                    continue
                all_edges.append(GraphEdgeOut(
                    source=str(c.caller_id), target=str(c.callee_id),
                    edge_type=c.call_type or "calls",
                ))
                await _traverse(c.caller_id, current_depth + 1)

    await _traverse(uuid.UUID(body.symbol_id), 1)

    nodes_result = await db.execute(
        select(CodeSymbol).where(CodeSymbol.id.in_([uuid.UUID(nid) for nid in visited_nodes]))
    )
    nodes = [
        GraphNodeOut(id=str(s.id), label=s.name, type=s.symbol_type)
        for s in nodes_result.scalars().all()
    ]
    return GraphOut(nodes=nodes, edges=all_edges, stats={"depth": body.max_depth})


@router.get("/{repository_id}/graph/modules", response_model=list[dict])
async def get_module_graph(
    repository_id: uuid.UUID,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a higher-level module/directory dependency graph."""
    await _get_repo_access(repository_id, user, db)
    idx = await _get_active_index(repository_id, db)

    files_result = await db.execute(
        select(CodeFile).where(CodeFile.index_id == idx.id)
    )
    files = files_result.scalars().all()
    modules: dict[str, int] = {}
    for f in files:
        parts = f.path.replace("\\", "/").split("/")
        if len(parts) > 1:
            module = "/".join(parts[:-1])
        else:
            module = "."
        modules[module] = modules.get(module, 0) + 1

    return [{"module": m, "file_count": c} for m, c in sorted(modules.items(), key=lambda x: -x[1])]


@router.get("/{repository_id}/graph/cycles", response_model=dict)
async def detect_cycles(
    repository_id: uuid.UUID,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Detect circular dependencies in the call graph."""
    await _get_repo_access(repository_id, user, db)
    idx = await _get_active_index(repository_id, db)

    symbols_result = await db.execute(
        select(CodeSymbol)
        .join(CodeFile, CodeSymbol.file_id == CodeFile.id)
        .where(CodeFile.index_id == idx.id)
    )
    symbols = symbols_result.scalars().all()
    symbol_ids = [s.id for s in symbols]

    if not symbol_ids:
        return {"cycles": [], "total_cycles": 0}

    calls_result = await db.execute(
        select(CodeCall)
        .where(CodeCall.caller_symbol_id.in_(symbol_ids))
        .where(CodeCall.callee_symbol_id.in_(symbol_ids))
    )
    calls = calls_result.scalars().all()

    adj: dict[str, list[str]] = {str(sid): [] for sid in symbol_ids}
    for c in calls:
        adj[str(c.caller_id)].append(str(c.callee_id))

    cycles: list[list[str]] = []
    visited_global: set[str] = set()

    def _dfs(node: str, path: list[str], visited: set[str]):
        if node in visited:
            cycle_start = path.index(node) if node in path else -1
            if cycle_start >= 0:
                cycles.append(path[cycle_start:])
            return
        if node in visited_global:
            return
        visited.add(node)
        path.append(node)
        for neighbor in adj.get(node, []):
            _dfs(neighbor, path, visited)
        path.pop()
        visited.discard(node)
        visited_global.add(node)

    for sid in symbol_ids:
        sid_str = str(sid)
        if sid_str not in visited_global:
            _dfs(sid_str, [], set())

    return {"cycles": cycles, "total_cycles": len(cycles)}


# ─── 5. Code Quality ───────────────────────────────────────────────────────

@router.post("/{repository_id}/quality/smells", response_model=SmellScanOut)
async def scan_code_smells(
    repository_id: uuid.UUID,
    body: SmellScanRequest,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Scan the repository for code smells and anti-patterns."""
    await _get_repo_access(repository_id, user, db)
    idx = await _get_active_index(repository_id, db)
    detector = SmellDetector(db_session=db)

    file_ids: list[uuid.UUID] = []
    if body.file_paths:
        files_result = await db.execute(
            select(CodeFile).where(CodeFile.index_id == idx.id, CodeFile.file_path.in_(body.file_paths))
        )
        file_ids = [f.id for f in files_result.scalars().all()]
    else:
        files_result = await db.execute(
            select(CodeFile).where(CodeFile.index_id == idx.id)
        )
        file_ids = [f.id for f in files_result.scalars().all()]

    all_smells: list[CodeSmellOut] = []
    for fid in file_ids:
        try:
            smells = await detector.detect_smells(file_id=str(fid))
            for smell in smells:
                severity_val = smell.get("severity", "info") if isinstance(smell, dict) else getattr(smell, "severity", "info")
                if body.min_severity and _severity_rank(severity_val) < _severity_rank(body.min_severity):
                    continue
                if body.smell_types:
                    st = smell.get("smell_type", "") if isinstance(smell, dict) else getattr(smell, "smell_type", "")
                    if st not in body.smell_types:
                        continue
                all_smells.append(CodeSmellOut(
                    id=str(smell.get("id", "")) if isinstance(smell, dict) else str(getattr(smell, "id", "")),
                    file_id=str(fid),
                    symbol_id=str(smell.get("symbol_id", "")) if isinstance(smell, dict) else str(getattr(smell, "symbol_id", "")),
                    smell_type=smell.get("smell_type", "") if isinstance(smell, dict) else getattr(smell, "smell_type", ""),
                    severity=severity_val,
                    message=smell.get("message", "") if isinstance(smell, dict) else getattr(smell, "message", ""),
                    line_start=smell.get("line_start", 0) if isinstance(smell, dict) else getattr(smell, "line_start", 0),
                    line_end=smell.get("line_end", 0) if isinstance(smell, dict) else getattr(smell, "line_end", 0),
                    suggestion=smell.get("suggestion") if isinstance(smell, dict) else getattr(smell, "suggestion", None),
                    effort_estimate=smell.get("effort_estimate") if isinstance(smell, dict) else getattr(smell, "effort_estimate", None),
                ))
        except Exception:
            continue

    by_severity: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for s in all_smells:
        by_severity[s.severity] = by_severity.get(s.severity, 0) + 1
        by_type[s.smell_type] = by_type.get(s.smell_type, 0) + 1

    return SmellScanOut(total_smells=len(all_smells), by_severity=by_severity, by_type=by_type, smells=all_smells)


@router.get("/{repository_id}/quality/metrics", response_model=list[CodeMetricsOut])
async def get_repository_metrics(
    repository_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=500),
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get code metrics for all files in the repository."""
    await _get_repo_access(repository_id, user, db)
    idx = await _get_active_index(repository_id, db)

    result = await db.execute(
        select(CodeMetrics)
        .join(CodeFile, CodeMetrics.file_id == CodeFile.id)
        .where(CodeFile.index_id == idx.id)
        .limit(limit)
    )
    metrics_list = result.scalars().all()

    file_ids = [m.file_id for m in metrics_list]
    files_result = await db.execute(
        select(CodeFile).where(CodeFile.id.in_(file_ids))
    )
    files_map = {f.id: f for f in files_result.scalars().all()}

    return [
        CodeMetricsOut(
            file_id=str(m.file_id),
            path=files_map[m.file_id].path if m.file_id in files_map else "",
            line_count=m.line_count or 0,
            code_lines=m.code_lines or 0,
            comment_lines=m.comment_lines or 0,
            blank_lines=m.blank_lines or 0,
            cyclomatic_complexity=m.cyclomatic_complexity or 0,
            cognitive_complexity=m.cognitive_complexity or 0,
            maintainability_index=m.maintainability_index or 0.0,
        )
        for m in metrics_list
    ]


@router.get("/{repository_id}/quality/summary", response_model=dict)
async def get_quality_summary(
    repository_id: uuid.UUID,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get an overall code quality summary for the repository."""
    await _get_repo_access(repository_id, user, db)
    idx = await _get_active_index(repository_id, db)

    metrics_result = await db.execute(
        select(CodeMetrics)
        .join(CodeFile, CodeMetrics.file_id == CodeFile.id)
        .where(CodeFile.index_id == idx.id)
    )
    all_metrics = metrics_result.scalars().all()
    if not all_metrics:
        return {"total_files": 0, "avg_complexity": 0, "avg_maintainability": 0, "total_code_lines": 0}

    total_files = len(all_metrics)
    avg_complexity = sum(m.cyclomatic_complexity or 0 for m in all_metrics) / total_files
    avg_maintainability = sum(m.maintainability_index or 0 for m in all_metrics) / total_files
    total_code_lines = sum(m.code_lines or 0 for m in all_metrics)

    smell_result = await db.execute(
        select(CodeSmell)
        .join(CodeFile, CodeSmell.file_id == CodeFile.id)
        .where(CodeFile.index_id == idx.id)
    )
    smells = smell_result.scalars().all()

    return {
        "total_files": total_files,
        "avg_complexity": round(avg_complexity, 2),
        "avg_maintainability": round(avg_maintainability, 2),
        "total_code_lines": total_code_lines,
        "total_smells": len(smells),
        "smells_by_severity": _count_by_attr(smells, "severity"),
    }


# ─── 6. Security ───────────────────────────────────────────────────────────

@router.post("/{repository_id}/security/scan", response_model=SecurityScanOut)
async def scan_security(
    repository_id: uuid.UUID,
    body: SecurityScanRequest,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run a security vulnerability scan on the repository."""
    await _get_repo_access(repository_id, user, db)
    idx = await _get_active_index(repository_id, db)
    scanner = SecurityScanner(db_session=db)

    file_ids: list[uuid.UUID] = []
    if body.file_paths:
        files_result = await db.execute(
            select(CodeFile).where(CodeFile.index_id == idx.id, CodeFile.file_path.in_(body.file_paths))
        )
        file_ids = [f.id for f in files_result.scalars().all()]
    else:
        files_result = await db.execute(
            select(CodeFile).where(CodeFile.index_id == idx.id)
        )
        file_ids = [f.id for f in files_result.scalars().all()]

    vulns: list[SecurityVulnerabilityOut] = []
    for fid in file_ids:
        try:
            results = await scanner.scan_file(file_id=str(fid))
            for v in results:
                vtype = v.get("vulnerability_type", "") if isinstance(v, dict) else getattr(v, "vulnerability_type", "")
                if body.vulnerability_types and vtype not in body.vulnerability_types:
                    continue
                vulns.append(SecurityVulnerabilityOut(
                    id=str(v.get("id", "")) if isinstance(v, dict) else str(getattr(v, "id", "")),
                    file_id=str(fid),
                    symbol_id=str(v.get("symbol_id", "")) if isinstance(v, dict) else str(getattr(v, "symbol_id", "")),
                    vulnerability_type=vtype,
                    severity=v.get("severity", "medium") if isinstance(v, dict) else getattr(v, "severity", "medium"),
                    message=v.get("message", "") if isinstance(v, dict) else getattr(v, "message", ""),
                    line_start=v.get("line_start", 0) if isinstance(v, dict) else getattr(v, "line_start", 0),
                    line_end=v.get("line_end", 0) if isinstance(v, dict) else getattr(v, "line_end", 0),
                    recommendation=v.get("recommendation") if isinstance(v, dict) else getattr(v, "recommendation", None),
                ))
        except Exception:
            continue

    by_severity: dict[str, int] = {}
    for v in vulns:
        by_severity[v.severity] = by_severity.get(v.severity, 0) + 1

    return SecurityScanOut(total_vulnerabilities=len(vulns), by_severity=by_severity, vulnerabilities=vulns)


@router.post("/{repository_id}/security/secrets", response_model=SecretScanOut)
async def scan_secrets(
    repository_id: uuid.UUID,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Scan the repository for accidentally committed secrets."""
    await _get_repo_access(repository_id, user, db)
    idx = await _get_active_index(repository_id, db)
    scanner = SecurityScanner(db_session=db)

    files_result = await db.execute(
        select(CodeFile).where(CodeFile.index_id == idx.id)
    )
    files = files_result.scalars().all()

    secrets: list[SecretOut] = []
    for f in files:
        try:
            found = await scanner.scan_secrets(file_id=str(f.id))
            for s in found:
                secrets.append(SecretOut(
                    file_id=str(f.id),
                    file_path=f.path,
                    line=s.get("line", 0) if isinstance(s, dict) else getattr(s, "line", 0),
                    secret_type=s.get("secret_type", "") if isinstance(s, dict) else getattr(s, "secret_type", ""),
                    severity=s.get("severity", "high") if isinstance(s, dict) else getattr(s, "severity", "high"),
                ))
        except Exception:
            continue

    return SecretScanOut(total_secrets=len(secrets), secrets=secrets)


# ─── 7. Architecture ───────────────────────────────────────────────────────

@router.get("/{repository_id}/architecture/overview", response_model=ArchitectureOverviewOut)
async def get_architecture_overview(
    repository_id: uuid.UUID,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a high-level architecture overview of the repository."""
    await _get_repo_access(repository_id, user, db)
    idx = await _get_active_index(repository_id, db)
    discovery = ArchitectureDiscovery(db_session=db)
    try:
        result: ArchitectureResult = await discovery.discover_architecture(
            repo_id=str(repository_id), index_id=str(idx.id)
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    return ArchitectureOverviewOut(
        layers=result.layers if hasattr(result, "layers") else [],
        modules=result.modules if hasattr(result, "modules") else [],
        dependencies=result.dependencies if hasattr(result, "dependencies") else [],
        summary=result.summary if hasattr(result, "summary") else None,
    )


@router.get("/{repository_id}/architecture/dependencies", response_model=DependencyGraphOut)
async def get_architecture_dependencies(
    repository_id: uuid.UUID,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the module-level dependency graph with circular dependency detection."""
    await _get_repo_access(repository_id, user, db)
    idx = await _get_active_index(repository_id, db)
    discovery = ArchitectureDiscovery(db_session=db)
    try:
        result: ArchitectureResult = await discovery.discover_architecture(
            repo_id=str(repository_id), index_id=str(idx.id)
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    nodes = result.modules if hasattr(result, "modules") else []
    edges = result.dependencies if hasattr(result, "dependencies") else []
    circular = result.circular_dependencies if hasattr(result, "circular_dependencies") else []

    return DependencyGraphOut(
        nodes=nodes if isinstance(nodes, list) else [],
        edges=edges if isinstance(edges, list) else [],
        circular_dependencies=circular if isinstance(circular, list) else [],
    )


# ─── 8. Impact Analysis ────────────────────────────────────────────────────

@router.post("/{repository_id}/impact/analyze", response_model=ImpactAnalysisOut)
async def analyze_impact(
    repository_id: uuid.UUID,
    body: ImpactAnalysisRequest,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Analyze the impact of a proposed change to a symbol or file."""
    await _get_repo_access(repository_id, user, db)
    idx = await _get_active_index(repository_id, db)

    analyzer = ImpactAnalyzer(db_session=db)
    try:
        if body.symbol_id:
            result: ImpactResult = await analyzer.analyze_impact(
                symbol_id=body.symbol_id,
            )
        elif body.file_path:
            result = await analyzer.analyze_file_impact(
                file_id=body.file_path,
            )
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provide symbol_id or file_path")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    return ImpactAnalysisOut(
        affected_files=result.affected_files if hasattr(result, "affected_files") else [],
        affected_symbols=result.affected_symbols if hasattr(result, "affected_symbols") else [],
        breaking_changes=[
            BreakingChangeOut(
                symbol_name=bc.symbol_name if hasattr(bc, "symbol_name") else getattr(bc, "name", ""),
                symbol_type=bc.symbol_type if hasattr(bc, "symbol_type") else getattr(bc, "type", ""),
                file_path=bc.file_path if hasattr(bc, "file_path") else "",
                line=bc.line if hasattr(bc, "line") else 0,
                reason=bc.reason if hasattr(bc, "reason") else "",
                severity=bc.severity if hasattr(bc, "severity") else "medium",
            )
            for bc in (result.breaking_changes if hasattr(result, "breaking_changes") else [])
        ],
        unused_items=[
            UnusedItemOut(
                symbol_name=ui.symbol_name if hasattr(ui, "symbol_name") else getattr(ui, "name", ""),
                symbol_type=ui.symbol_type if hasattr(ui, "symbol_type") else getattr(ui, "type", ""),
                file_path=ui.file_path if hasattr(ui, "file_path") else "",
                line=ui.line if hasattr(ui, "line") else 0,
                confidence=ui.confidence if hasattr(ui, "confidence") else 0.0,
            )
            for ui in (result.unused_items if hasattr(result, "unused_items") else [])
        ],
        impact_score=result.impact_score if hasattr(result, "impact_score") else 0.0,
        risk_level=result.risk_level if hasattr(result, "risk_level") else "low",
    )


@router.post("/{repository_id}/impact/downstream", response_model=DownstreamOut)
async def get_downstream_impact(
    repository_id: uuid.UUID,
    body: DownstreamRequest,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all downstream consumers of a symbol (callers + transitive)."""
    await _get_repo_access(repository_id, user, db)
    idx = await _get_active_index(repository_id, db)
    await _get_symbol(uuid.UUID(body.symbol_id), idx.id, db)

    analyzer = ImpactAnalyzer(db_session=db)
    try:
        result = await analyzer.get_downstream_impact(
            symbol_id=body.symbol_id,
            max_depth=body.max_depth,
        )
    except Exception:
        result = {"direct": [], "transitive": []}

    direct = result.get("direct", [])
    transitive = result.get("transitive", [])
    return DownstreamOut(
        direct_dependencies=direct,
        transitive_dependencies=transitive,
        total_affected=len(direct) + len(transitive),
    )


@router.post("/{repository_id}/impact/unused", response_model=list[UnusedItemOut])
async def find_unused_code(
    repository_id: uuid.UUID,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Find potentially unused symbols (dead code detection)."""
    await _get_repo_access(repository_id, user, db)
    idx = await _get_active_index(repository_id, db)

    analyzer = ImpactAnalyzer(db_session=db)
    try:
        unused = await analyzer.find_unused_symbols(index_id=str(idx.id))
    except Exception:
        unused = []

    return [
        UnusedItemOut(
            symbol_name=u.symbol_name if hasattr(u, "symbol_name") else getattr(u, "name", ""),
            symbol_type=u.symbol_type if hasattr(u, "symbol_type") else getattr(u, "type", ""),
            file_path=u.file_path if hasattr(u, "file_path") else "",
            line=u.line if hasattr(u, "line") else 0,
            confidence=u.confidence if hasattr(u, "confidence") else 0.0,
        )
        for u in unused
    ]


# ─── 9. Search ─────────────────────────────────────────────────────────────

@router.post("/{repository_id}/search", response_model=SearchOut)
async def search_code(
    repository_id: uuid.UUID,
    body: SearchRequest,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Hybrid search across symbols, files, and code content."""
    await _get_repo_access(repository_id, user, db)
    idx = await _get_active_index(repository_id, db)
    engine = HybridSearchEngine(db_session=db)

    try:
        search_results = await engine.search(
            query=body.query,
            repo_id=str(idx.id),
            limit=body.max_results or 20,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    items = search_results.results if hasattr(search_results, "results") else []
    return SearchOut(
        query=body.query,
        total_results=search_results.total if hasattr(search_results, "total") else len(items),
        results=[
            SearchResultItemOut(
                id=r.id if hasattr(r, "id") else "",
                name=r.name if hasattr(r, "name") else "",
                result_type=r.result_type if hasattr(r, "result_type") else "",
                file_path=r.file_path if hasattr(r, "file_path") else None,
                line=r.line if hasattr(r, "line") else None,
                score=r.score if hasattr(r, "score") else 0.0,
                snippet=r.snippet if hasattr(r, "snippet") else None,
                context=r.context if hasattr(r, "context") else None,
            )
            for r in items
        ],
    )


@router.post("/{repository_id}/search/symbols", response_model=SymbolSearchOut)
async def search_symbols(
    repository_id: uuid.UUID,
    body: SymbolSearchRequest,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search for symbols by name with optional fuzzy matching."""
    await _get_repo_access(repository_id, user, db)
    idx = await _get_active_index(repository_id, db)

    query = (
        select(CodeSymbol)
        .join(CodeFile, CodeSymbol.file_id == CodeFile.id)
        .where(CodeFile.index_id == idx.id)
    )
    if body.fuzzy:
        query = query.where(CodeSymbol.name.ilike(f"%{body.name}%"))
    else:
        query = query.where(CodeSymbol.name == body.name)

    if body.symbol_types:
        query = query.where(CodeSymbol.symbol_type.in_(body.symbol_types))

    query = query.limit(50)
    result = await db.execute(query)
    symbols = result.scalars().all()

    return SymbolSearchOut(
        results=[
            SymbolOut(
                id=str(s.id),
                file_id=str(s.file_id),
                name=s.name,
                symbol_type=s.symbol_type,
                qualified_name=s.qualified_name,
                line_start=s.line_start,
                line_end=s.line_end,
                column_start=s.column_start or 0,
                column_end=s.column_end or 0,
                docstring=s.docstring,
                signature=s.signature,
                complexity=s.complexity or 0,
            )
            for s in symbols
        ],
        total=len(symbols),
    )


# ─── 10. RAG Context ───────────────────────────────────────────────────────

@router.post("/{repository_id}/rag/context", response_model=RAGContextOut)
async def get_rag_context(
    repository_id: uuid.UUID,
    body: RAGContextRequest,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Build an LLM-ready RAG context bundle for a code-related query."""
    await _get_repo_access(repository_id, user, db)
    idx = await _get_active_index(repository_id, db)
    builder = RAGContextBuilder(db_session=db)

    try:
        context_bundle = await builder.build_context(
            query=body.query,
            repo_id=str(idx.id),
            max_tokens=body.max_tokens or 4096,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    return RAGContextOut(
        query=body.query,
        context_chunks=context_bundle.get("context_chunks", []) if isinstance(context_bundle, dict) else getattr(context_bundle, "context_chunks", []),
        relevant_symbols=context_bundle.get("relevant_symbols", []) if isinstance(context_bundle, dict) else getattr(context_bundle, "relevant_symbols", []),
        graph_context=context_bundle.get("graph_context") if isinstance(context_bundle, dict) else getattr(context_bundle, "graph_context", None),
        metrics_summary=context_bundle.get("metrics_summary") if isinstance(context_bundle, dict) else getattr(context_bundle, "metrics_summary", None),
        total_tokens_estimate=context_bundle.get("total_tokens_estimate", 0) if isinstance(context_bundle, dict) else getattr(context_bundle, "total_tokens_estimate", 0),
    )


# ─── 11. Index Health ──────────────────────────────────────────────────────

@router.get("/{repository_id}/index/health", response_model=IndexHealthOut)
async def get_index_health(
    repository_id: uuid.UUID,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get health status and diagnostics for the current index."""
    await _get_repo_access(repository_id, user, db)
    idx = await _get_active_index(repository_id, db)

    file_count_result = await db.execute(
        select(func.count()).select_from(CodeFile).where(CodeFile.index_id == idx.id)
    )
    symbol_count_result = await db.execute(
        select(func.count()).select_from(CodeSymbol)
        .join(CodeFile, CodeSymbol.file_id == CodeFile.id)
        .where(CodeFile.index_id == idx.id)
    )
    chunk_count_result = await db.execute(
        select(func.count()).select_from(CodeChunk)
        .join(CodeFile, CodeChunk.file_id == CodeFile.id)
        .where(CodeFile.index_id == idx.id)
    )

    file_count = file_count_result.scalar() or 0
    symbol_count = symbol_count_result.scalar() or 0
    chunk_count = chunk_count_result.scalar() or 0

    issues: list[str] = []
    if idx.status == IndexStatus.FAILED:
        issues.append("Index is in FAILED state")
    if idx.status == IndexStatus.QUEUED:
        issues.append("Index build is still pending")
    if file_count == 0:
        issues.append("No files indexed")
    if symbol_count == 0:
        issues.append("No symbols extracted")
    if chunk_count == 0:
        issues.append("No chunks generated for RAG")

    health_score = 100.0
    if issues:
        health_score = max(0.0, 100.0 - len(issues) * 20.0)

    return IndexHealthOut(
        index_id=str(idx.id),
        status=idx.status,
        last_updated=idx.updated_at.isoformat() if idx.updated_at else None,
        file_count=file_count,
        symbol_count=symbol_count,
        chunk_count=chunk_count,
        index_size_bytes=idx.index_size_bytes or 0,
        health_score=health_score,
        issues=issues,
    )


@router.post("/{repository_id}/index/repair", response_model=IndexRepairOut)
async def repair_index(
    repository_id: uuid.UUID,
    body: IndexRepairRequest,
    user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Attempt to repair issues found in the index health check."""
    await _get_repo_access(repository_id, user, db)
    idx = await _get_active_index(repository_id, db)
    pipeline = IndexingPipeline(db_session=db)

    repairs: list[str] = []
    issues_fixed = 0
    issues_remaining = 0

    try:
        if not body.repair_types or "rebuild_missing_chunks" in body.repair_types:
            files_result = await db.execute(
                select(CodeFile).where(CodeFile.index_id == idx.id)
            )
            for f in files_result.scalars().all():
                chunk_result = await db.execute(
                    select(func.count()).select_from(CodeChunk).where(CodeChunk.file_id == f.id)
                )
                if (chunk_result.scalar() or 0) == 0:
                    try:
                        await pipeline._chunk_file(f)
                        repairs.append(f"Rebuilt chunks for {f.path}")
                        issues_fixed += 1
                    except Exception:
                        issues_remaining += 1
        if not body.repair_types or "fix_broken_references" in body.repair_types:
            refs_result = await db.execute(
                select(CodeReference)
                .join(CodeFile, CodeReference.source_file_id == CodeFile.id)
                .where(CodeFile.index_id == idx.id)
                .where(CodeReference.resolved == False)
            )
            broken_refs = refs_result.scalars().all()
            if broken_refs:
                issues_remaining += len(broken_refs)
                repairs.append(f"Found {len(broken_refs)} broken references (manual review needed)")
    except Exception:
        issues_remaining += 1

    return IndexRepairOut(
        repairs_performed=repairs,
        issues_fixed=issues_fixed,
        issues_remaining=issues_remaining,
    )


# ─── Helpers (internal) ────────────────────────────────────────────────────

_SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}

def _severity_rank(sev: str) -> int:
    return _SEVERITY_ORDER.get(sev.lower(), 0)

def _count_by_attr(items: list, attr: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        val = getattr(item, attr, None) or "unknown"
        counts[val] = counts.get(val, 0) + 1
    return counts
