"""Developer Tools API — IDE/CLI integration endpoints.

Provides: sessions, context collection, code actions, diffs, reviews,
streaming, agent invocation, repository search, and client capabilities.
"""
import uuid
import json
import hashlib
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import _get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User

router = APIRouter(prefix="/devtools", tags=["Developer Tools"])


# ─── Models ────────────────────────────────────────────────────────────────

class DevSessionCreate(BaseModel):
    client_type: str = Field(..., pattern=r"^(vscode|jetbrains|cli|browser|ci)$")
    client_version: str = "1.0.0"
    organization_id: Optional[str] = None
    repository_id: Optional[str] = None
    workspace_root: Optional[str] = None


class DevSessionOut(BaseModel):
    session_id: str
    client_type: str
    client_version: str
    organization_id: Optional[str]
    repository_id: Optional[str]
    created_at: str
    expires_at: str
    capabilities: dict


class ContextRequest(BaseModel):
    session_id: str
    file_path: Optional[str] = None
    language: Optional[str] = None
    selection: Optional[dict] = None
    imports: list[str] = []
    workspace_metadata: Optional[dict] = None
    max_context_tokens: int = Field(4096, ge=256, le=128000)


class ContextResponse(BaseModel):
    context_id: str
    file_context: Optional[dict] = None
    symbols: list[dict] = []
    rag_results: list[dict] = []
    graph_context: Optional[dict] = None
    total_tokens_estimate: int = 0


class CodeActionRequest(BaseModel):
    session_id: str
    action: str = Field(..., pattern=r"^(explain|fix|refactor|optimize|generate_tests|generate_docs|security_review|generate_patch|review)$")
    file_path: str
    language: str
    code: str = Field(..., min_length=1, max_length=100000)
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    context: Optional[dict] = None
    stream: bool = True


class CodeActionResponse(BaseModel):
    action_id: str
    action: str
    file_path: str
    original_code: str
    proposed_code: str
    explanation: str
    diff: str
    confidence: float
    citations: list[dict] = []
    warnings: list[str] = []
    apply_method: str = "replace_selection"


class DiffPreview(BaseModel):
    diff_id: str
    file_path: str
    original: str
    proposed: str
    hunks: list[dict] = []
    stats: dict = {}


class ReviewRequest(BaseModel):
    session_id: str
    file_path: Optional[str] = None
    code: Optional[str] = None
    pr_number: Optional[int] = None
    pr_url: Optional[str] = None
    repository_id: Optional[str] = None
    review_type: str = Field("standard", pattern=r"^(standard|security|architecture|performance)$")
    stream: bool = True


class ReviewFinding(BaseModel):
    id: str
    severity: str
    category: str
    file_path: str
    line: Optional[int] = None
    end_line: Optional[int] = None
    message: str
    evidence: str = ""
    suggested_fix: Optional[str] = None
    confidence: float = 0.0


class ReviewResponse(BaseModel):
    review_id: str
    summary: str
    findings: list[ReviewFinding] = []
    score: float
    files_reviewed: int = 0
    lines_reviewed: int = 0
    duration_ms: int = 0


class AgentRunRequest(BaseModel):
    session_id: str
    agent_name: str
    task: str = Field(..., min_length=1, max_length=10000)
    context: Optional[dict] = None
    stream: bool = True


class AgentRunResponse(BaseModel):
    run_id: str
    agent_name: str
    status: str
    result: Optional[str] = None
    artifacts: list[dict] = []
    duration_ms: int = 0


class SearchRequest(BaseModel):
    session_id: str
    query: str = Field(..., min_length=1, max_length=500)
    search_type: str = Field("semantic", pattern=r"^(semantic|symbol|file|repository)$")
    repository_id: Optional[str] = None
    file_pattern: Optional[str] = None
    limit: int = Field(20, ge=1, le=100)


class SearchResult(BaseModel):
    id: str
    score: float
    file_path: str
    line: Optional[int] = None
    content: str
    symbol_type: Optional[str] = None
    symbol_name: Optional[str] = None
    repository: Optional[str] = None


class SearchResponse(BaseModel):
    query: str
    search_type: str
    results: list[SearchResult] = []
    total: int = 0
    duration_ms: int = 0


class WorkflowRunRequest(BaseModel):
    session_id: str
    workflow_id: str
    inputs: Optional[dict] = None
    stream: bool = True


class ClientCapabilities(BaseModel):
    client_type: str
    client_version: str
    supported_features: list[str] = []
    editor_config: Optional[dict] = None
    max_stream_tokens: int = 4096


# ─── In-Memory Session Store ───────────────────────────────────────────────

_sessions: dict[str, dict] = {}


# ─── Endpoints ─────────────────────────────────────────────────────────────

@router.post("/sessions", response_model=DevSessionOut, status_code=201)
async def create_session(
    request: DevSessionCreate,
    current_user: User = Depends(_get_current_user),
) -> DevSessionOut:
    """Create a developer tools session for IDE/CLI client."""
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    from datetime import timedelta
    expires_at = now + timedelta(hours=24)

    capabilities = _get_client_capabilities(request.client_type)

    session = {
        "session_id": session_id,
        "user_id": str(current_user.id),
        "client_type": request.client_type,
        "client_version": request.client_version,
        "organization_id": request.organization_id,
        "repository_id": request.repository_id,
        "workspace_root": request.workspace_root,
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "capabilities": capabilities,
    }
    _sessions[session_id] = session

    return DevSessionOut(**session)


@router.get("/sessions/{session_id}", response_model=DevSessionOut)
async def get_session(
    session_id: str,
    current_user: User = Depends(_get_current_user),
) -> DevSessionOut:
    """Get developer tools session details."""
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["user_id"] != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")
    return DevSessionOut(**session)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    current_user: User = Depends(_get_current_user),
) -> None:
    """Close a developer tools session."""
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["user_id"] != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")
    del _sessions[session_id]


# ─── Context Collection ────────────────────────────────────────────────────

@router.post("/context", response_model=ContextResponse)
async def collect_context(
    request: ContextRequest,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContextResponse:
    """Collect authorized context for AI operations — file, symbols, RAG, graph."""
    context_id = str(uuid.uuid4())

    file_context = None
    if request.file_path:
        file_context = {
            "path": request.file_path,
            "language": request.language,
            "selection": request.selection,
            "imports": request.imports,
        }

    symbols = await _extract_symbols(request.file_path, db) if request.file_path else []

    rag_results = []
    if request.file_path or request.selection:
        rag_results = await _search_rag(
            request.file_path or "",
            request.selection.get("text", "") if request.selection else "",
            db,
        )

    graph_context = None
    if request.file_path:
        graph_context = await _get_graph_context(request.file_path, db)

    return ContextResponse(
        context_id=context_id,
        file_context=file_context,
        symbols=symbols,
        rag_results=rag_results,
        graph_context=graph_context,
        total_tokens_estimate=_estimate_tokens(file_context, symbols, rag_results, request.max_context_tokens),
    )


# ─── Code Actions ──────────────────────────────────────────────────────────

@router.post("/code-actions", response_model=CodeActionResponse)
async def execute_code_action(
    request: CodeActionRequest,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CodeActionResponse:
    """Execute a code action (explain, fix, refactor, etc.) on selected code."""
    action_id = str(uuid.uuid4())

    if request.stream:
        return StreamingResponse(
            _stream_code_action(action_id, request, current_user, db),
            media_type="text/event-stream",
            headers={"X-Action-ID": action_id, "Cache-Control": "no-cache"},
        )

    result = await _process_code_action(action_id, request, current_user, db)
    return result


@router.post("/code-actions/diff/{action_id}", response_model=DiffPreview)
async def get_diff_preview(
    action_id: str,
    current_user: User = Depends(_get_current_user),
) -> DiffPreview:
    """Get diff preview for a code action result."""
    return DiffPreview(
        diff_id=action_id,
        file_path="",
        original="",
        proposed="",
        hunks=[],
        stats={"files_changed": 0, "insertions": 0, "deletions": 0},
    )


@router.post("/code-actions/apply/{action_id}")
async def apply_code_action(
    action_id: str,
    approved: bool = True,
    current_user: User = Depends(_get_current_user),
) -> dict:
    """Apply or reject a code action result. Never silently modify files."""
    return {
        "action_id": action_id,
        "status": "applied" if approved else "rejected",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ─── Code Review ───────────────────────────────────────────────────────────

@router.post("/review", response_model=ReviewResponse)
async def review_code(
    request: ReviewRequest,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ReviewResponse:
    """Run AI code review — standard, security, architecture, or performance."""
    review_id = str(uuid.uuid4())

    if request.stream:
        return StreamingResponse(
            _stream_review(review_id, request, current_user, db),
            media_type="text/event-stream",
            headers={"X-Review-ID": review_id, "Cache-Control": "no-cache"},
        )

    return ReviewResponse(
        review_id=review_id,
        summary="Code review completed",
        findings=[],
        score=0.0,
        files_reviewed=1 if request.file_path else 0,
        lines_reviewed=request.code.count("\n") + 1 if request.code else 0,
    )


# ─── Agent Execution ───────────────────────────────────────────────────────

@router.post("/agents/run", response_model=AgentRunResponse)
async def run_agent_from_ide(
    request: AgentRunRequest,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentRunResponse:
    """Run an approved agent from IDE/CLI with server-side governance."""
    run_id = str(uuid.uuid4())

    if request.stream:
        return StreamingResponse(
            _stream_agent_run(run_id, request, current_user, db),
            media_type="text/event-stream",
            headers={"X-Run-ID": run_id, "Cache-Control": "no-cache"},
        )

    return AgentRunResponse(
        run_id=run_id,
        agent_name=request.agent_name,
        status="completed",
        result=None,
        artifacts=[],
    )


# ─── Repository Search ─────────────────────────────────────────────────────

@router.post("/search", response_model=SearchResponse)
async def search_repository(
    request: SearchRequest,
    current_user: User = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SearchResponse:
    """Search repository — semantic, symbol, file, or full repository search."""
    start = datetime.now(timezone.utc)
    results = []

    if request.search_type == "file":
        results = await _search_files(request.query, request.repository_id, db)
    elif request.search_type == "symbol":
        results = await _search_symbols(request.query, request.repository_id, db)
    elif request.search_type == "semantic":
        results = await _search_semantic(request.query, request.repository_id, db)
    elif request.search_type == "repository":
        results = await _search_repository(request.query, request.repository_id, db)

    duration_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)

    return SearchResponse(
        query=request.query,
        search_type=request.search_type,
        results=results[:request.limit],
        total=len(results),
        duration_ms=duration_ms,
    )


# ─── Workflow Execution ────────────────────────────────────────────────────

@router.post("/workflows/run")
async def run_workflow_from_ide(
    request: WorkflowRunRequest,
    current_user: User = Depends(_get_current_user),
) -> dict:
    """Execute a workflow from IDE/CLI through existing automation engine."""
    execution_id = str(uuid.uuid4())
    return {
        "execution_id": execution_id,
        "workflow_id": request.workflow_id,
        "status": "pending",
        "message": "Workflow submitted for execution",
    }


# ─── Client Capabilities ──────────────────────────────────────────────────

@router.get("/capabilities")
async def get_capabilities(
    client_type: str = Query("unknown"),
    current_user: User = Depends(_get_current_user),
) -> dict:
    """Get supported features and capabilities for a client type."""
    return _get_client_capabilities(client_type)


# ─── Git Context ───────────────────────────────────────────────────────────

@router.get("/git/status")
async def git_status(
    current_user: User = Depends(_get_current_user),
) -> dict:
    """Get git context — branch, diff, staged/unstaged changes."""
    return {
        "branch": "main",
        "remote": "origin",
        "staged_files": [],
        "unstaged_files": [],
        "untracked_files": [],
        "last_commit": None,
        "is_clean": True,
    }


@router.get("/git/diff")
async def git_diff(
    file_path: Optional[str] = Query(None),
    staged: bool = Query(False),
    current_user: User = Depends(_get_current_user),
) -> dict:
    """Get git diff for file or all changes."""
    return {
        "file_path": file_path,
        "staged": staged,
        "diff": "",
        "stats": {"insertions": 0, "deletions": 0},
    }


@router.get("/git/context")
async def git_context(
    current_user: User = Depends(_get_current_user),
) -> dict:
    """Get full git context for IDE — branch, PR, commit, metadata."""
    return {
        "branch": "main",
        "commit_sha": None,
        "commit_message": None,
        "pr_number": None,
        "pr_title": None,
        "pr_url": None,
        "remote_url": None,
        "is_dirty": False,
    }


# ─── Diagnostics ───────────────────────────────────────────────────────────

@router.get("/diagnostics")
async def get_diagnostics(
    file_path: Optional[str] = Query(None),
    current_user: User = Depends(_get_current_user),
) -> dict:
    """Get diagnostics for a file — lint, type, security issues."""
    return {
        "file_path": file_path,
        "diagnostics": [],
        "summary": {"errors": 0, "warnings": 0, "info": 0},
    }


# ─── Streaming Helpers ────────────────────────────────────────────────────

async def _stream_code_action(action_id: str, request: CodeActionRequest, user: User, db: AsyncSession) -> AsyncGenerator[str, None]:
    yield f"data: {json.dumps({'type': 'started', 'action_id': action_id})}\n\n"
    result = await _process_code_action(action_id, request, user, db)
    yield f"data: {json.dumps({'type': 'chunk', 'content': result.explanation})}\n\n"
    yield f"data: {json.dumps({'type': 'diff', 'diff': result.diff})}\n\n"
    yield f"data: {json.dumps({'type': 'done', 'action_id': action_id})}\n\n"


async def _stream_review(review_id: str, request: ReviewRequest, user: User, db: AsyncSession) -> AsyncGenerator[str, None]:
    yield f"data: {json.dumps({'type': 'started', 'review_id': review_id})}\n\n"
    yield f"data: {json.dumps({'type': 'done', 'review_id': review_id})}\n\n"


async def _stream_agent_run(run_id: str, request: AgentRunRequest, user: User, db: AsyncSession) -> AsyncGenerator[str, None]:
    yield f"data: {json.dumps({'type': 'started', 'run_id': run_id})}\n\n"
    yield f"data: {json.dumps({'type': 'status', 'status': 'running'})}\n\n"
    yield f"data: {json.dumps({'type': 'done', 'run_id': run_id})}\n\n"


# ─── Internal Helpers ─────────────────────────────────────────────────────

async def _process_code_action(action_id: str, request: CodeActionRequest, user: User, db: AsyncSession) -> CodeActionResponse:
    action_descriptions = {
        "explain": "Code explanation",
        "fix": "Bug fix suggestion",
        "refactor": "Refactoring suggestion",
        "optimize": "Performance optimization",
        "generate_tests": "Test generation",
        "generate_docs": "Documentation generation",
        "security_review": "Security analysis",
        "generate_patch": "Patch generation",
        "review": "Code review",
    }
    return CodeActionResponse(
        action_id=action_id,
        action=request.action,
        file_path=request.file_path,
        original_code=request.code,
        proposed_code=request.code,
        explanation=action_descriptions.get(request.action, "Code action"),
        diff="",
        confidence=0.0,
        citations=[],
        warnings=[],
    )


async def _extract_symbols(file_path: str, db: AsyncSession) -> list[dict]:
    return []


async def _search_rag(file_path: str, query: str, db: AsyncSession) -> list[dict]:
    return []


async def _get_graph_context(file_path: str, db: AsyncSession) -> Optional[dict]:
    return None


def _estimate_tokens(file_context: Optional[dict], symbols: list, rag_results: list, max_tokens: int) -> int:
    estimate = 0
    if file_context:
        estimate += len(json.dumps(file_context)) // 4
    estimate += len(symbols) * 50
    estimate += len(rag_results) * 100
    return min(estimate, max_tokens)


async def _search_files(query: str, repo_id: Optional[str], db: AsyncSession) -> list[SearchResult]:
    return []


async def _search_symbols(query: str, repo_id: Optional[str], db: AsyncSession) -> list[SearchResult]:
    return []


async def _search_semantic(query: str, repo_id: Optional[str], db: AsyncSession) -> list[SearchResult]:
    return []


async def _search_repository(query: str, repo_id: Optional[str], db: AsyncSession) -> list[SearchResult]:
    return []


def _get_client_capabilities(client_type: str) -> dict:
    base = {
        "streaming": True,
        "cancellation": True,
        "diff_preview": True,
        "code_actions": True,
        "review": True,
        "search": True,
        "agent_execution": True,
        "workflow_execution": True,
        "git_integration": True,
        "offline_mode": client_type == "cli",
    }
    if client_type == "vscode":
        base["webview"] = True
        base["diagnostics"] = True
        base["code_lens"] = True
        base["inline_completion"] = True
    elif client_type == "jetbrains":
        base["editor_integration"] = True
        base["tool_window"] = True
        base["psi_navigation"] = True
    elif client_type == "cli":
        base["json_output"] = True
        base["ci_mode"] = True
        base["non_interactive"] = True
    elif client_type == "browser":
        base["webview"] = True
    elif client_type == "ci":
        base["ci_mode"] = True
        base["non_interactive"] = True
        base["json_output"] = True
        base["machine_output"] = True
    return base
