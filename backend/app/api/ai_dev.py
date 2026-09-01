"""AI Developer Experience API — Volume 67 Commit 1.

Namespace: /api/v1/ai-dev
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.ai_dev import chat as chat_svc
from app.ai_dev import context as context_svc
from app.ai_dev import deps as deps_svc
from app.ai_dev import explain as explain_svc
from app.ai_dev import fix as fix_svc
from app.ai_dev import indexing as indexing_svc
from app.ai_dev import patch as patch_svc
from app.ai_dev import repo_assist as repo_assist_svc
from app.ai_dev import review as review_svc
from app.ai_dev import search as search_svc
from app.ai_dev import tests as tests_svc
from app.ai_dev import usage as usage_svc
from app.ai_dev import workspaces as workspaces_svc
from app.ai_dev.common import (
    NotFoundError as AiDevNotFound,
    PatchAlreadyAppliedError,
    StalePatchError,
)
from app.ai_dev.models import (
    CodeAIUsage,
    CodePatch,
    CodeReview,
    CodeReviewFinding,
    CodeTestRun,
    CodeWorkspace,
)
from app.api.auth import _get_current_user
from app.core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai-dev", tags=["AI Developer Experience"])


# ── imports ──────────────────────────────────────────────────────────────────
from app.ai_dev import agent as agent_svc
from app.ai_dev import workers as agent_workers


# ── helpers ─────────────────────────────────────────────────────────────────


def _tenant(user) -> str:
    oid = getattr(user, "organization_id", None) or getattr(user, "id", None)
    if not oid:
        raise HTTPException(status_code=403, detail="No tenant context")
    return str(oid)


def _user_id(user) -> str:
    return str(getattr(user, "id", "") or "")


def _iam_check(user, tenant: str, permission: str, resource_type: str = "ai_dev"):
    try:
        from app.iam.policy_authorizer import policy_authorizer

        ctx = {"role": str(getattr(user, "role", "viewer"))}
        decision = policy_authorizer.authorize(
            str(getattr(user, "id", "")), tenant, permission,
            resource_type=resource_type, context=ctx,
        )
        if not decision.get("allowed", True):
            raise HTTPException(status_code=403, detail=decision.get("reason", "Forbidden"))
    except HTTPException:
        raise
    except Exception as exc:
        logger.debug("IAM check skipped %s: %s", permission, exc)


def _rate(tenant: str, endpoint: str, limit: int = 60):
    if not usage_svc.check_rate_limit(tenant, endpoint, limit=limit):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")


async def _emit_usage(user, tenant: str, action: str):
    del user
    try:
        from app.core.events import Event, EventType, event_bus

        et = getattr(EventType, "DeveloperAIUsageRecorded", None)
        if et is not None:
            await event_bus.publish_nowait(
                Event(et, {"action": action}, source="ai_dev", organization_id=tenant)
            )
    except Exception:
        pass


# ── request models ──────────────────────────────────────────────────────────


class WorkspaceCreateIn(BaseModel):
    name: str = Field(..., max_length=128)
    repository_id: str
    branch: str = "main"
    commit_sha: Optional[str] = None
    description: Optional[str] = None
    pinned: bool = False
    classification: str = "INTERNAL"


class ChatIn(BaseModel):
    repository_id: str
    question: str
    workspace_id: Optional[str] = None
    model_hint: Optional[str] = None


class ExplainIn(BaseModel):
    repository_id: str
    kind: str = "file"
    target: str
    top: int = 20


class FileEdit(BaseModel):
    path: str
    old_content: Optional[str] = None
    old_hash: Optional[str] = None
    new_content: str


class PatchCreateIn(BaseModel):
    repository_id: str
    title: str
    files: list[FileEdit] = Field(..., min_length=1)
    branch: Optional[str] = None
    base_commit_sha: Optional[str] = None
    workspace_id: Optional[str] = None
    model: Optional[str] = None
    source: str = "ai"


class ApplyIn(BaseModel):
    current_files: Optional[dict] = None


class ReviewFile(BaseModel):
    path: str
    content: str


class ReviewCreateIn(BaseModel):
    repository_id: str
    files: list[ReviewFile] = Field(..., min_length=1)
    branch: Optional[str] = None
    commit_sha: Optional[str] = None
    patch_id: Optional[str] = None
    workspace_id: Optional[str] = None
    rules_version: str = "1.0"


class DismissIn(BaseModel):
    reason: Optional[str] = None


class TestGenerateIn(BaseModel):
    repository_id: str
    patch_id: Optional[str] = None
    commit_sha: Optional[str] = None
    branch: Optional[str] = None
    framework: Optional[str] = None


class TestResultIn(BaseModel):
    status: str
    results: Optional[list] = None
    logs: Optional[str] = None
    failures_analysis: Optional[str] = None
    duration_ms: Optional[int] = None


class FixRunIn(BaseModel):
    repository_id: str
    files: list[ReviewFile] = Field(..., min_length=1)
    goal: str
    patch_title: str
    branch: Optional[str] = None
    model: Optional[str] = None
    max_iterations: int = 3


class DepScanIn(BaseModel):
    files: Optional[list[dict]] = None


class ChangeSummaryIn(BaseModel):
    repository_id: str
    commit_sha: Optional[str] = None
    files: Optional[list[dict]] = None


class PrAssistIn(BaseModel):
    repository_id: str
    title: str
    files: list[dict]
    commit_sha: Optional[str] = None
    test_summary: Optional[dict] = None
    findings: Optional[list[dict]] = None


# ── serializers ─────────────────────────────────────────────────────────────


def _ws_payload(w: CodeWorkspace) -> dict:
    return {
        "id": str(w.id),
        "name": w.name,
        "repository_id": str(w.repository_id),
        "branch": w.branch,
        "commit_sha": w.commit_sha,
        "owner": w.owner,
        "status": w.status,
        "pinned": w.pinned,
        "classification": w.classification,
    }


def _patch_payload(p: CodePatch) -> dict:
    return {
        "id": str(p.id),
        "repository_id": str(p.repository_id),
        "title": p.title,
        "branch": p.branch,
        "status": p.status,
        "files": p.files or [],
        "diffs": p.diffs or {},
        "rollback_diffs": p.rollback_diffs or {},
        "model": p.model,
        "source": p.source,
        "base_commit_sha": p.base_commit_sha,
        "applied_at": p.applied_at.isoformat() if p.applied_at else None,
        "rolled_back_at": p.rolled_back_at.isoformat() if p.rolled_back_at else None,
        "error": p.error,
    }


def _finding_payload(f: CodeReviewFinding) -> dict:
    return {
        "id": str(f.id),
        "file_path": f.file_path,
        "line_start": f.line_start,
        "line_end": f.line_end,
        "category": f.category,
        "severity": f.severity,
        "message": f.message,
        "reason": f.reason,
        "confidence": f.confidence,
        "status": f.status,
        "dismissed_by": f.dismissed_by,
        "dismissed_reason": f.dismissed_reason,
    }


def _review_payload(r: CodeReview) -> dict:
    return {
        "id": str(r.id),
        "repository_id": str(r.repository_id),
        "branch": r.branch,
        "commit_sha": r.commit_sha,
        "patch_id": str(r.patch_id) if r.patch_id else None,
        "status": r.status,
        "summary": r.summary,
        "rules_version": r.rules_version,
        "model": r.model,
        "created_by": r.created_by,
        "context_snapshot": r.context_snapshot,
    }


def _testrun_payload(t: CodeTestRun) -> dict:
    return {
        "id": str(t.id),
        "repository_id": str(t.repository_id),
        "branch": t.branch,
        "commit_sha": t.commit_sha,
        "patch_id": str(t.patch_id) if t.patch_id else None,
        "status": t.status,
        "framework": t.framework,
        "command": t.command,
        "test_plan": t.test_plan,
        "test_results": t.test_results,
        "failures_analysis": t.failures_analysis,
        "duration_ms": t.duration_ms,
        "ci_pipeline_run_id": t.ci_pipeline_run_id,
    }


def _usage_payload(u: CodeAIUsage) -> dict:
    return {
        "id": str(u.id),
        "user_id": u.user_id,
        "action": u.action,
        "model": u.model,
        "prompt_tokens": u.prompt_tokens,
        "completion_tokens": u.completion_tokens,
        "total_tokens": u.total_tokens,
        "cost_cents": u.cost_cents,
        "latency_ms": u.latency_ms,
        "repository_id": str(u.repository_id) if u.repository_id else None,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


def _err(exc: Exception) -> HTTPException:
    if isinstance(exc, (AiDevNotFound, ValueError)):
        detail = str(exc)
        if "not found" in detail:
            return HTTPException(status_code=404, detail=detail)
        return HTTPException(status_code=422, detail=detail)
    if isinstance(exc, StalePatchError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, PatchAlreadyAppliedError):
        return HTTPException(status_code=409, detail=str(exc))
    logger.exception("ai-dev handler failed")
    return HTTPException(status_code=500, detail="internal error")


# ── workspaces ──────────────────────────────────────────────────────────────


@router.post("/workspaces", status_code=201)
async def create_workspace(body: WorkspaceCreateIn, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:write")
    _rate(tenant, "ai_dev_workspace")
    try:
        ws = await workspaces_svc.create_workspace(
            db, tenant, _user_id(user),
            name=body.name,
            repository_id=body.repository_id,
            branch=body.branch,
            commit_sha=body.commit_sha,
            description=body.description,
            pinned=body.pinned,
            classification=body.classification,
        )
        return _ws_payload(ws)
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/workspaces")
async def list_workspaces(repository_id: Optional[str] = Query(default=None), limit: int = Query(default=50), user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:read")
    rows = await workspaces_svc.list_workspaces(db, tenant, repository_id=repository_id, limit=limit)
    return {"items": [_ws_payload(w) for w in rows], "count": len(rows)}


@router.get("/workspaces/{workspace_id}")
async def get_workspace(workspace_id: str, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:read")
    try:
        ws = await workspaces_svc.get_workspace(db, tenant, workspace_id)
        if ws is None:
            raise AiDevNotFound("workspace not found")
        return _ws_payload(ws)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/workspaces/{workspace_id}/pin")
async def pin_workspace(workspace_id: str, body: dict = None, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:write")
    pinned = bool((body or {}).get("pinned", True))
    try:
        ws = await workspaces_svc.pin_workspace(db, tenant, workspace_id, pinned=pinned)
        return _ws_payload(ws)
    except Exception as exc:
        raise _err(exc) from exc


# ── index ───────────────────────────────────────────────────────────────────


@router.get("/repositories/{repository_id}/index")
async def index_overview(repository_id: str, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:read")
    try:
        return await indexing_svc.index_overview(db, tenant, repository_id)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/repositories/{repository_id}/index", status_code=201)
async def record_index(repository_id: str, body: dict = None, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:write")
    body = body or {}
    try:
        version = await indexing_svc.record_index_contract(
            db, tenant, repository_id,
            branch=body.get("branch", "main"),
            commit_sha=body.get("commit_sha"),
        )
        return {
            "index_id": str(version.index_id),
            "version_id": str(version.id),
            "version_number": version.version_number,
            "embedding_model": version.embedding_model,
            "embedding_version": version.embedding_version,
            "embedding_dimension": version.embedding_dimension,
            "commit_sha": version.commit_sha,
            "status": "QUEUED",
        }
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/repositories/{repository_id}/index/full")
async def full_index(repository_id: str, body: dict = None, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:write")
    body = body or {}
    try:
        return await indexing_svc.trigger_full_pipeline(
            db, tenant, repository_id,
            branch=body.get("branch", "main"),
            commit_sha=body.get("commit_sha"),
            rebuild=bool(body.get("rebuild", False)),
        )
    except Exception as exc:
        raise _err(exc) from exc


# ── search / context ────────────────────────────────────────────────────────


@router.get("/repositories/{repository_id}/search")
async def search(repository_id: str, q: str = Query(..., min_length=1), symbol_type: Optional[str] = Query(default=None), limit: int = Query(default=12), user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:read")
    _rate(tenant, "ai_dev_search")
    try:
        result = await search_svc.hybrid_search(
            db, tenant, repository_id, q, symbol_type=symbol_type, limit=limit
        )
        await _emit_usage(user, tenant, "search")
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/repositories/{repository_id}/symbols")
async def symbols(repository_id: str, q: str = Query(..., min_length=1), symbol_type: Optional[str] = Query(default=None), limit: int = Query(default=20), user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:read")
    try:
        rows = await search_svc.symbol_search(
            db, tenant, repository_id, q, symbol_type=symbol_type, limit=limit
        )
        return {"items": rows, "count": len(rows)}
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/repositories/{repository_id}/references")
async def references(repository_id: str, target: str = Query(..., min_length=1), limit: int = Query(default=20), user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:read")
    try:
        rows = await search_svc.reference_search(db, tenant, repository_id, target, limit=limit)
        return {"items": rows, "count": len(rows)}
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/repositories/{repository_id}/context")
async def context(repository_id: str, q: str = Query(..., min_length=1), token_budget: int = Query(default=4000), user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:read")
    try:
        return await context_svc.build_context(
            db, tenant, repository_id, q, token_budget=token_budget
        )
    except Exception as exc:
        raise _err(exc) from exc


# ── chat / explain ──────────────────────────────────────────────────────────


@router.post("/chat")
async def chat(body: ChatIn, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:read")
    _rate(tenant, "ai_dev_chat")
    try:
        result = await chat_svc.code_chat(
            db, tenant, _user_id(user),
            repository_id=body.repository_id,
            question=body.question,
            model_hint=body.model_hint,
            workspace_id=body.workspace_id,
        )
        await _emit_usage(user, tenant, "chat")
        return result
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/explain")
async def explain(body: ExplainIn, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:read")
    _rate(tenant, "ai_dev_explain")
    try:
        result = await explain_svc.explain(
            db, tenant, body.repository_id, body.kind, body.target, top=body.top
        )
        await _emit_usage(user, tenant, "explain")
        return result
    except Exception as exc:
        raise _err(exc) from exc


# ── patches ─────────────────────────────────────────────────────────────────


@router.post("/patch", status_code=201)
async def create_patch(body: PatchCreateIn, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:write")
    try:
        patch = await patch_svc.create_patch(
            db, tenant, _user_id(user),
            repository_id=body.repository_id,
            title=body.title,
            files=[f.model_dump() for f in body.files],
            branch=body.branch,
            base_commit_sha=body.base_commit_sha,
            workspace_id=body.workspace_id,
            model=body.model,
            source=body.source,
        )
        return _patch_payload(patch)
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/patches")
async def list_patches(repository_id: Optional[str] = Query(default=None), status: Optional[str] = Query(default=None), limit: int = Query(default=50), user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:read")
    rows = await patch_svc.list_patches(db, tenant, repository_id=repository_id, status=status, limit=limit)
    return {"items": [_patch_payload(p) for p in rows], "count": len(rows)}


@router.get("/patches/{patch_id}")
async def get_patch(patch_id: str, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:read")
    try:
        patch = await patch_svc.get_patch(db, tenant, patch_id)
        return _patch_payload(patch)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/patches/{patch_id}/apply")
async def apply_patch(patch_id: str, body: ApplyIn = None, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:write")
    try:
        patch = await patch_svc.apply_patch(
            db, tenant, _user_id(user), patch_id,
            current_files=(body.current_files if body else None),
        )
        return _patch_payload(patch)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/patches/{patch_id}/rollback")
async def rollback_patch(patch_id: str, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:write")
    try:
        patch = await patch_svc.rollback_patch(db, tenant, _user_id(user), patch_id)
        return _patch_payload(patch)
    except Exception as exc:
        raise _err(exc) from exc


# ── reviews ─────────────────────────────────────────────────────────────────


@router.post("/review", status_code=201)
async def create_review(body: ReviewCreateIn, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:write")
    try:
        review = await review_svc.generate_review(
            db, tenant, _user_id(user),
            repository_id=body.repository_id,
            files=[f.model_dump() for f in body.files],
            branch=body.branch,
            commit_sha=body.commit_sha,
            patch_id=body.patch_id,
            workspace_id=body.workspace_id,
            rules_version=body.rules_version,
        )
        return {"review": _review_payload(review), "review_id": str(review.id)}
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/reviews/{review_id}")
async def get_review(review_id: str, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:read")
    try:
        data = await review_svc.review_with_findings(db, tenant, review_id)
        return {
            "review": _review_payload(data["review"]),
            "findings": [_finding_payload(f) for f in data["findings"]],
        }
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/reviews/{review_id}/findings/{finding_id}/dismiss")
async def dismiss_finding(review_id: str, finding_id: str, body: DismissIn = None, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:write")
    try:
        finding = await review_svc.dismiss_finding(
            db, tenant, _user_id(user), review_id, finding_id,
            reason=(body.reason if body else None),
        )
        return _finding_payload(finding)
    except Exception as exc:
        raise _err(exc) from exc


# ── tests ───────────────────────────────────────────────────────────────────


@router.post("/tests/generate", status_code=201)
async def generate_tests(body: TestGenerateIn, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:write")
    try:
        run = await tests_svc.generate_test_plan(
            db, tenant, _user_id(user),
            repository_id=body.repository_id,
            patch_id=body.patch_id,
            commit_sha=body.commit_sha,
            branch=body.branch,
            framework=body.framework,
        )
        return _testrun_payload(run)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/tests/{run_id}/execute")
async def execute_tests(run_id: str, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:write")
    try:
        run = await tests_svc.execute_tests(db, tenant, _user_id(user), run_id)
        return _testrun_payload(run)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/tests/{run_id}/result")
async def record_test_result(run_id: str, body: TestResultIn, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:write")
    try:
        run = await tests_svc.record_test_result(
            db, tenant, run_id, body.status,
            results=body.results,
            logs=body.logs,
            failures_analysis=body.failures_analysis,
            duration_ms=body.duration_ms,
        )
        return _testrun_payload(run)
    except Exception as exc:
        raise _err(exc) from exc


# ── fix loop ────────────────────────────────────────────────────────────────


@router.post("/fix")
async def run_fix(body: FixRunIn, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:write")
    try:
        result = await fix_svc.run_fix_loop(
            db, tenant, _user_id(user),
            repository_id=body.repository_id,
            files=[f.model_dump() for f in body.files],
            goal=body.goal,
            patch_title=body.patch_title,
            branch=body.branch,
            model=body.model,
            max_iterations=body.max_iterations,
        )
        await _emit_usage(user, tenant, "fix")
        return result
    except Exception as exc:
        raise _err(exc) from exc


# ── dependencies / builds ───────────────────────────────────────────────────


@router.get("/repositories/{repository_id}/dependencies")
async def dependencies(repository_id: str, limit: int = Query(default=200), user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:read")
    try:
        return await deps_svc.dependency_graph(db, tenant, repository_id, limit=limit)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/repositories/{repository_id}/dependencies/scan")
async def dependencies_scan(repository_id: str, body: DepScanIn = None, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:read")
    try:
        return await deps_svc.analyze_dependencies(
            db, tenant, repository_id, files=(body.files if body else None)
        )
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/repositories/{repository_id}/builds")
async def builds(repository_id: str, commit_sha: Optional[str] = Query(default=None), user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:read")
    try:
        return await deps_svc.build_analysis(db, tenant, repository_id, commit_sha=commit_sha)
    except Exception as exc:
        raise _err(exc) from exc


# ── change / PR assistance ──────────────────────────────────────────────────


@router.post("/changes/summary")
async def change_summary(body: ChangeSummaryIn, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:read")
    try:
        return await repo_assist_svc.change_summary(
            db, tenant, body.repository_id, commit_sha=body.commit_sha, files=body.files
        )
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/changes/pr-assist")
async def pr_assist(body: PrAssistIn, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:read")
    try:
        return await repo_assist_svc.pr_assistant(
            db, tenant, body.repository_id,
            title=body.title,
            files=body.files,
            commit_sha=body.commit_sha,
            test_summary=body.test_summary,
            findings=body.findings,
        )
    except Exception as exc:
        raise _err(exc) from exc


# ── usage ───────────────────────────────────────────────────────────────────


@router.get("/usage")
async def usage(action: Optional[str] = Query(default=None), limit: int = Query(default=50, le=500), user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:read")
    rows = await usage_svc.list_usage(db, tenant, limit=limit, action=action)
    totals = await usage_svc.usage_totals(db, tenant)
    return {
        "items": [_usage_payload(u) for u in rows],
        "count": len(rows),
        "totals": totals,
    }


# ── agents (Volume 67 Commit 2) ────────────────────────────────────────────


class AgentEnqueueIn(BaseModel):
    repository_id: str
    agent_type: str = "refactor"
    name: str = "agent"
    goal: Optional[str] = None
    files: Optional[list[dict]] = None
    branch: str = "main"
    commit_sha: Optional[str] = None
    model: Optional[str] = None
    throttle: Optional[int] = None
    budget_tokens: Optional[int] = None
    checkpoint_limit: int = 10
    metadata_: Optional[dict] = None


class PlanCreateIn(BaseModel):
    plan_type: str = "PLAN"
    name: str = "Plan"
    steps: Optional[list[dict]] = None
    rationale: Optional[str] = None


class PlanApproveIn(BaseModel):
    approved: bool = True
    approved_by: str
    reason: Optional[str] = None


class CheckpointIn(BaseModel):
    sequence: Optional[int] = None
    summary: Optional[str] = None
    state: Optional[dict] = None
    is_final: bool = False


class FeedbackIn(BaseModel):
    feedback_type: str = "CONTINUE"
    message: Optional[str] = None
    patch_id: Optional[str] = None
    checkpoint_id: Optional[str] = None


class SecurityGateIn(BaseModel):
    repository_id: Optional[str] = None
    review_id: Optional[str] = None
    files: Optional[list[ReviewFile]] = None
    findings: Optional[list[dict]] = None
    branch: str = "main"
    commit_sha: Optional[str] = None


class RefactorIn(BaseModel):
    repository_id: str
    title: str
    files: list[ReviewFile] = Field(..., min_length=1)
    goal: Optional[str] = None
    branch: str = "main"
    commit_sha: Optional[str] = None
    model: Optional[str] = None


class BenchmarkCreateIn(BaseModel):
    name: str
    dataset_spec: Optional[list[dict]] = None


class BenchmarkRunIn(BaseModel):
    commit_sha: Optional[str] = None
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    budget_tokens: Optional[int] = None


class BenchmarkCompleteIn(BaseModel):
    results: Optional[dict] = None


class ReleaseHandoffIn(BaseModel):
    repository_id: str
    version: Optional[str] = None
    environment: Optional[str] = None
    release_channel: Optional[str] = None
    artifact_id: Optional[str] = None
    commit_sha: Optional[str] = None


class MigrationRollbackIn(BaseModel):
    reason: Optional[str] = None


# ── serializers (C2) ────────────────────────────────────────────────────────


def _agent_payload(run) -> dict:
    return {
        "id": str(run.id),
        "repository_id": str(run.repository_id),
        "agent_type": run.agent_type,
        "name": run.name,
        "goal": run.goal,
        "status": run.status,
        "worker_id": run.worker_id,
        "model": run.model,
        "throttle": run.throttle,
        "budget_tokens": run.budget_tokens,
        "tokens_used": run.tokens_used,
        "attempts": run.attempts,
        "last_error": run.last_error,
        "checkpoint_limit": run.checkpoint_limit,
        "start_time": run.start_time.isoformat() if run.start_time else None,
        "end_time": run.end_time.isoformat() if run.end_time else None,
        "result": run.result,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


def _plan_payload(p) -> dict:
    return {
        "id": str(p.id),
        "agent_run_id": str(p.agent_run_id),
        "plan_type": p.plan_type,
        "name": p.name,
        "steps": p.steps,
        "rationale": p.rationale,
        "approved": p.approved,
        "approved_by": p.approved_by,
        "rejected": p.rejected,
    }


def _checkpoint_payload(c) -> dict:
    return {
        "id": str(c.id),
        "sequence": c.sequence,
        "summary": c.summary,
        "state": c.state,
        "is_final": c.is_final,
    }


def _feedback_payload(f) -> dict:
    return {
        "id": str(f.id),
        "feedback_type": f.feedback_type,
        "message": f.message,
        "patch_id": str(f.patch_id) if f.patch_id else None,
        "checkpoint_id": str(f.checkpoint_id) if f.checkpoint_id else None,
        "created_by": f.created_by,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }


def _benchmark_payload(b) -> dict:
    return {
        "id": str(b.id),
        "name": b.name,
        "dataset_spec": b.dataset_spec,
        "status": b.status,
        "best_eval_id": b.best_eval_id,
    }


def _benchmark_run_payload(r) -> dict:
    return {
        "id": str(r.id),
        "benchmark_id": str(r.benchmark_id),
        "status": r.status,
        "model": r.model,
        "score": r.score,
        "results": r.results,
        "patches": r.patches,
        "tokens_used": r.tokens_used,
        "cost_cents": r.cost_cents,
        "took_ms": r.took_ms,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
    }


# ── agent routes ─────────────────────────────────────────────────────────────


@router.post("/agents", status_code=201)
async def enqueue_agent(body: AgentEnqueueIn, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:write")
    try:
        run = await agent_svc.enqueue_agent(
            db, tenant, _user_id(user),
            repository_id=body.repository_id,
            agent_type=body.agent_type,
            name=body.name,
            goal=body.goal,
            files=body.files,
            branch=body.branch,
            commit_sha=body.commit_sha,
            model=body.model,
            throttle=body.throttle,
            budget_tokens=body.budget_tokens,
            checkpoint_limit=body.checkpoint_limit,
            metadata_=body.metadata_,
        )
        return _agent_payload(run)
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/agents")
async def list_agents(
    repository_id: Optional[str] = Query(default=None),
    agent_type: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50),
    user=Depends(_get_current_user),
    db=Depends(get_db),
):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:read")
    rows = await agent_svc.list_agent_runs(
        db, tenant, repository_id=repository_id, agent_type=agent_type, status=status, limit=limit
    )
    return {"items": [_agent_payload(r) for r in rows], "count": len(rows)}


@router.get("/agents/{run_id}")
async def get_agent(run_id: str, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:read")
    try:
        run = await agent_svc.get_agent_run(db, tenant, run_id)
        return _agent_payload(run)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/agents/{run_id}/execute")
async def execute_agent(run_id: str, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:write")
    try:
        run = await agent_workers.run_agent_until_done(
            db, tenant, run_id, user_id=_user_id(user)
        )
        return _agent_payload(run)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/agents/{run_id}/cancel")
async def cancel_agent(run_id: str, body: dict = None, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:write")
    try:
        run = await agent_svc.cancel_agent(
            db, tenant, _user_id(user), run_id,
            reason=(body or {}).get("reason"),
        )
        return _agent_payload(run)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/agents/{run_id}/plan", status_code=201)
async def create_plan(run_id: str, body: PlanCreateIn, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:write")
    try:
        plan = await agent_svc.add_plan(
            db, tenant, run_id,
            plan_type=body.plan_type,
            name=body.name,
            steps=body.steps,
            rationale=body.rationale,
            created_by=_user_id(user),
        )
        return _plan_payload(plan)
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/agents/{run_id}/plans")
async def list_plans(run_id: str, limit: int = Query(default=20), user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:read")
    rows = await agent_svc.list_plans(db, tenant, run_id, limit=limit)
    return {"items": [_plan_payload(p) for p in rows], "count": len(rows)}


@router.post("/agents/{run_id}/plans/{plan_id}/approve")
async def approve_plan(run_id: str, plan_id: str, body: PlanApproveIn, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:write")
    try:
        plan = await agent_svc.approve_plan(
            db, tenant, run_id, plan_id,
            approved_by=body.approved_by,
            approved=body.approved,
            reason=body.reason,
        )
        return _plan_payload(plan)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/agents/{run_id}/checkpoints", status_code=201)
async def save_checkpoint(run_id: str, body: CheckpointIn, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:write")
    try:
        chk = await agent_svc.save_checkpoint(
            db, tenant, run_id,
            sequence=body.sequence,
            summary=body.summary,
            state=body.state,
            is_final=body.is_final,
        )
        return _checkpoint_payload(chk)
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/agents/{run_id}/checkpoints")
async def list_checkpoints(run_id: str, limit: int = Query(default=50), user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:read")
    rows = await agent_svc.list_checkpoints(db, tenant, run_id, limit=limit)
    return {"items": [_checkpoint_payload(c) for c in rows], "count": len(rows)}


@router.post("/agents/{run_id}/feedback", status_code=201)
async def add_feedback(run_id: str, body: FeedbackIn, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:write")
    try:
        fb = await agent_svc.add_feedback(
            db, tenant, run_id,
            feedback_type=body.feedback_type,
            message=body.message,
            created_by=_user_id(user),
            patch_id=body.patch_id,
            checkpoint_id=body.checkpoint_id,
        )
        return _feedback_payload(fb)
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/agents/{run_id}/feedback")
async def list_feedback(run_id: str, limit: int = Query(default=50), user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:read")
    rows = await agent_svc.list_feedback(db, tenant, run_id, limit=limit)
    return {"items": [_feedback_payload(f) for f in rows], "count": len(rows)}


# ── security gate ────────────────────────────────────────────────────────────


@router.post("/security-gate")
async def security_gate(body: SecurityGateIn, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:write")
    try:
        from app.ai_dev import security_gate as security_gate_svc

        return await security_gate_svc.run_security_gate(
            db, tenant, _user_id(user),
            repository_id=body.repository_id,
            review_id=body.review_id,
            files=[f.model_dump() for f in body.files] if body.files else None,
            findings=body.findings,
            branch=body.branch,
            commit_sha=body.commit_sha,
        )
    except Exception as exc:
        raise _err(exc) from exc


# ── refactor / migrate ───────────────────────────────────────────────────────


@router.post("/refactor", status_code=201)
async def refactor(body: RefactorIn, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:write")
    try:
        run = await agent_svc.enqueue_agent(
            db, tenant, _user_id(user),
            repository_id=body.repository_id,
            agent_type="refactor",
            name=body.title,
            goal=body.goal,
            files=[f.model_dump() for f in body.files],
            branch=body.branch,
            commit_sha=body.commit_sha,
            model=body.model,
        )
        run = await agent_workers.run_agent_until_done(db, tenant, str(run.id), user_id=_user_id(user))
        return _agent_payload(run)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/migrate", status_code=201)
async def migrate(body: RefactorIn, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:write")
    try:
        run = await agent_svc.enqueue_agent(
            db, tenant, _user_id(user),
            repository_id=body.repository_id,
            agent_type="migrate",
            name=body.title,
            goal=body.goal,
            files=[f.model_dump() for f in body.files],
            branch=body.branch,
            commit_sha=body.commit_sha,
            model=body.model,
        )
        run = await agent_workers.run_agent_until_done(db, tenant, str(run.id), user_id=_user_id(user))
        return _agent_payload(run)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/migrations/{run_id}/rollback")
async def migration_rollback(run_id: str, body: MigrationRollbackIn = None, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:write")
    try:
        from app.ai_dev import migration as migration_svc

        return await migration_svc.rollback_migration(
            db, tenant, _user_id(user), run_id,
            reason=(body.reason if body else None),
        )
    except Exception as exc:
        raise _err(exc) from exc


# ── benchmarks ───────────────────────────────────────────────────────────────


@router.get("/benchmarks")
async def list_benchmarks(limit: int = Query(default=50), user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:read")
    from app.ai_dev import benchmarks as bench_svc

    rows = await bench_svc.list_benchmarks(db, tenant, limit=limit)
    return {"items": [_benchmark_payload(b) for b in rows], "count": len(rows)}


@router.post("/benchmarks", status_code=201)
async def create_benchmark(body: BenchmarkCreateIn, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:write")
    from app.ai_dev import benchmarks as bench_svc

    try:
        b = await bench_svc.create_benchmark(
            db, tenant, _user_id(user),
            name=body.name,
            dataset_spec=body.dataset_spec,
        )
        return _benchmark_payload(b)
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/benchmarks/{benchmark_id}")
async def get_benchmark(benchmark_id: str, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:read")
    from app.ai_dev import benchmarks as bench_svc

    try:
        b = await bench_svc.get_benchmark(db, tenant, benchmark_id)
        return _benchmark_payload(b)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/benchmarks/{benchmark_id}/runs", status_code=201)
async def start_benchmark_run(benchmark_id: str, body: BenchmarkRunIn = None, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:write")
    from app.ai_dev import benchmarks as bench_svc

    body = body or BenchmarkRunIn()
    try:
        run = await bench_svc.start_benchmark_run(
            db, tenant, _user_id(user), benchmark_id,
            commit_sha=body.commit_sha,
            model=body.model,
            system_prompt=body.system_prompt,
            budget_tokens=body.budget_tokens,
        )
        run = await bench_svc.execute_benchmark_run(db, tenant, str(run.id))
        run = await bench_svc.complete_benchmark_run(db, tenant, str(run.id))
        return _benchmark_run_payload(run)
    except Exception as exc:
        raise _err(exc) from exc


@router.post("/benchmarks/{benchmark_id}/summarize")
async def summarize_benchmark(benchmark_id: str, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:read")
    from app.ai_dev import benchmarks as bench_svc

    try:
        return await bench_svc.summarize_benchmark(db, tenant, benchmark_id)
    except Exception as exc:
        raise _err(exc) from exc


@router.get("/benchmarks/{benchmark_id}/runs")
async def list_benchmark_runs(benchmark_id: str, limit: int = Query(default=50), user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:read")
    from app.ai_dev import benchmarks as bench_svc

    rows = await bench_svc.list_runs(db, tenant, benchmark_id, limit=limit)
    return {"items": [_benchmark_run_payload(r) for r in rows], "count": len(rows)}


# ── release handoff ──────────────────────────────────────────────────────────


@router.post("/release/handoff")
async def release_handoff(body: ReleaseHandoffIn, user=Depends(_get_current_user), db=Depends(get_db)):
    tenant = _tenant(user)
    _iam_check(user, tenant, "repository:write")
    try:
        from app.ai_dev import release_handoff as rh_svc

        return await rh_svc.prepare_release_handoff(
            db, tenant, _user_id(user),
            repository_id=body.repository_id,
            version=body.version,
            environment=body.environment,
            release_channel=body.release_channel,
            artifact_id=body.artifact_id,
            commit_sha=body.commit_sha,
        )
    except Exception as exc:
        raise _err(exc) from exc