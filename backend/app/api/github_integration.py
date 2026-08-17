"""GitHub / CI Integration — webhook handling, PR review, CI/CD pipeline management."""

import uuid
import hmac
import hashlib
import time
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.api.auth import _get_current_user
from app.api.devtools import ReviewResponse
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/github", tags=["GitHub Integration"])


# ─── Configuration ─────────────────────────────────────────────────────────


class GitHubIntegrationConfig(BaseModel):
    webhook_secret: str = ""
    auto_review_enabled: bool = True
    review_on_push: bool = True
    review_on_pr: bool = True
    ci_integration_enabled: bool = True
    bot_username: str = "novaforge-bot"


_github_config = GitHubIntegrationConfig(
    webhook_secret=getattr(settings, "github_webhook_secret", "") or "",
    bot_username=getattr(settings, "github_bot_username", "novaforge-bot"),
)


def get_config() -> GitHubIntegrationConfig:
    return _github_config


# ─── Models ────────────────────────────────────────────────────────────────


class GitHubWebhookEvent(BaseModel):
    event_type: str
    action: Optional[str] = None
    repository: dict[str, Any] = {}
    sender: dict[str, Any] = {}
    payload: dict[str, Any] = {}


class PRReviewRequest(BaseModel):
    pr_number: int
    repository_id: str
    review_type: str = Field("standard", pattern=r"^(standard|security|architecture|performance)$")
    auto_comment: bool = True
    post_as_bot: bool = True


class CIStatusUpdate(BaseModel):
    check_run_id: int
    status: str = Field(..., pattern=r"^(queued|in_progress|completed)$")
    conclusion: Optional[str] = Field(None, pattern=r"^(success|failure|neutral|cancelled|timed_out|action_required|skipped)$")
    output: dict[str, Any] = {}


class PRCommentRequest(BaseModel):
    pr_number: int
    repository_id: str
    comment_body: str = Field(..., min_length=1, max_length=65536)
    comment_type: str = Field("review", pattern=r"^(review|suggestion|approval)$")


class CIWorkflowRun(BaseModel):
    workflow_id: str
    status: str = Field("queued", pattern=r"^(queued|in_progress|completed)$")
    trigger_event: str = "push"
    ref: str = "main"
    sha: str = ""
    inputs: dict[str, Any] = {}


class CIValidationRequest(BaseModel):
    repository_id: str
    config_content: str = Field(..., min_length=1)
    config_filename: str = ".novaforge.yml"


class CIValidationResponse(BaseModel):
    valid: bool
    errors: list[str] = []
    warnings: list[str] = []
    parsed: dict[str, Any] = {}


class WebhookCreateRequest(BaseModel):
    url: str = Field(..., min_length=1)
    events: list[str] = Field(..., min_length=1)
    secret: Optional[str] = None
    content_type: str = "json"
    active: bool = True


class WebhookOut(BaseModel):
    id: str
    repository_id: str
    url: str
    events: list[str]
    active: bool
    content_type: str
    created_at: str
    last_triggered_at: Optional[str] = None
    delivery_count: int = 0


class PRAnalysisResponse(BaseModel):
    pr_number: int
    repository_id: str
    diff_summary: dict[str, Any] = {}
    findings: list[dict[str, Any]] = []
    summary: str
    score: float
    files_changed: int = 0
    additions: int = 0
    deletions: int = 0


class CISummary(BaseModel):
    run_id: str
    status: str
    conclusion: Optional[str] = None
    started_at: str
    completed_at: Optional[str] = None
    duration_ms: Optional[int] = None
    steps: list[dict[str, Any]] = []


# ─── In-Memory Stores ─────────────────────────────────────────────────────

_webhook_events: dict[str, GitHubWebhookEvent] = {}
_ci_runs: dict[str, dict[str, Any]] = {}
_repo_webhooks: dict[str, list[dict[str, Any]]] = defaultdict(list)
_pr_analyses: dict[str, PRAnalysisResponse] = {}
_rate_limit_tracker: dict[str, list[float]] = defaultdict(list)

RATE_LIMIT_WINDOW = 60.0
RATE_LIMIT_MAX_REQUESTS = 60


# ─── Signature Verification ───────────────────────────────────────────────


def _verify_webhook_signature(
    payload_body: bytes,
    signature_header: Optional[str],
    secret: str,
) -> bool:
    if not secret:
        return True
    if not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"), payload_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


# ─── Rate Limiting ────────────────────────────────────────────────────────


def _check_rate_limit(identifier: str) -> bool:
    now = time.time()
    timestamps = _rate_limit_tracker[identifier]
    _rate_limit_tracker[identifier] = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW]
    if len(_rate_limit_tracker[identifier]) >= RATE_LIMIT_MAX_REQUESTS:
        return False
    _rate_limit_tracker[identifier].append(now)
    return True


# ─── Webhook Event Handlers ──────────────────────────────────────────────


async def _handle_push_event(payload: dict[str, Any]) -> dict[str, Any]:
    repo = payload.get("repository", {})
    repo_name = repo.get("full_name", "unknown")
    ref = payload.get("ref", "")
    head_commit = payload.get("head_commit") or {}
    commit_sha = head_commit.get("id", "")
    commit_message = head_commit.get("message", "")
    pusher = payload.get("pusher", {})
    commits = payload.get("commits", [])

    logger.info("Push event to %s ref=%s sha=%s commits=%d", repo_name, ref, commit_sha, len(commits))

    changed_files: list[str] = []
    for commit in commits:
        changed_files.extend(commit.get("added", []))
        changed_files.extend(commit.get("modified", []))
        changed_files.extend(commit.get("removed", []))

    return {
        "event": "push",
        "repo": repo_name,
        "ref": ref,
        "sha": commit_sha,
        "pusher": pusher.get("name", ""),
        "commit_message": commit_message,
        "changed_files": changed_files,
        "commits_count": len(commits),
    }


async def _handle_pr_event(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action", "")
    pr = payload.get("pull_request", {})
    pr_number = pr.get("number", 0)
    repo = payload.get("repository", {})
    repo_name = repo.get("full_name", "unknown")
    repo_id = str(repo.get("id", ""))

    logger.info("PR %s action=%s repo=%s", pr_number, action, repo_name)

    result: dict[str, Any] = {
        "event": "pull_request",
        "action": action,
        "pr_number": pr_number,
        "repo": repo_name,
        "repo_id": repo_id,
        "title": pr.get("title", ""),
        "head_sha": pr.get("head", {}).get("sha", ""),
        "base_branch": pr.get("base", {}).get("ref", ""),
    }

    config = get_config()
    if config.auto_review_enabled and config.review_on_pr and action in ("opened", "synchronize", "reopened"):
        review_request = PRReviewRequest(
            pr_number=pr_number,
            repository_id=repo_id,
            review_type="standard",
            auto_comment=True,
            post_as_bot=True,
        )
        result["triggered_review"] = True
        result["review_request"] = review_request.model_dump()

    return result


async def _handle_pr_review_event(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action", "")
    review = payload.get("review", {})
    pr = payload.get("pull_request", {})
    repo = payload.get("repository", {})

    logger.info("PR review action=%s PR=%s repo=%s", action, pr.get("number", ""), repo.get("full_name", ""))

    return {
        "event": "pull_request_review",
        "action": action,
        "pr_number": pr.get("number", 0),
        "review_id": review.get("id", 0),
        "review_state": review.get("state", ""),
        "reviewer": review.get("user", {}).get("login", ""),
        "body": review.get("body", ""),
        "repo": repo.get("full_name", ""),
    }


async def _handle_issue_comment_event(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action", "")
    comment = payload.get("comment", {})
    issue = payload.get("issue", {})
    repo = payload.get("repository", {})
    comment_body = comment.get("body", "")

    logger.info("Issue comment action=%s issue=%s repo=%s", action, issue.get("number", ""), repo.get("full_name", ""))

    novaforge_commands = []
    for line in comment_body.split("\n"):
        stripped = line.strip()
        if stripped.startswith("/novaforge"):
            novaforge_commands.append(stripped)

    is_pr = "pull_request" in issue
    return {
        "event": "issue_comment",
        "action": action,
        "issue_number": issue.get("number", 0),
        "is_pull_request": is_pr,
        "commenter": comment.get("user", {}).get("login", ""),
        "comment_body": comment_body,
        "novaforge_commands": novaforge_commands,
        "repo": repo.get("full_name", ""),
    }


async def _handle_check_run_event(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action", "")
    check_run = payload.get("check_run", {})
    repo = payload.get("repository", {})

    logger.info("Check run action=%s id=%s repo=%s", action, check_run.get("id", ""), repo.get("full_name", ""))

    return {
        "event": "check_run",
        "action": action,
        "check_run_id": check_run.get("id", 0),
        "name": check_run.get("name", ""),
        "status": check_run.get("status", ""),
        "conclusion": check_run.get("conclusion"),
        "repo": repo.get("full_name", ""),
    }


async def _handle_workflow_run_event(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload.get("action", "")
    workflow_run = payload.get("workflow_run", {})
    repo = payload.get("repository", {})

    logger.info("Workflow run action=%s id=%s repo=%s", action, workflow_run.get("id", ""), repo.get("full_name", ""))

    return {
        "event": "workflow_run",
        "action": action,
        "run_id": workflow_run.get("id", 0),
        "name": workflow_run.get("name", ""),
        "status": workflow_run.get("status", ""),
        "conclusion": workflow_run.get("conclusion"),
        "head_branch": workflow_run.get("head_branch", ""),
        "head_sha": workflow_run.get("head_sha", ""),
        "repo": repo.get("full_name", ""),
    }


_EVENT_HANDLERS = {
    "push": _handle_push_event,
    "pull_request": _handle_pr_event,
    "pull_request_review": _handle_pr_review_event,
    "issue_comment": _handle_issue_comment_event,
    "check_run": _handle_check_run_event,
    "workflow_run": _handle_workflow_run_event,
}


# ─── GitHub API Placeholder ───────────────────────────────────────────────


async def _github_api_request(
    method: str,
    endpoint: str,
    data: Optional[dict[str, Any]] = None,
    token: Optional[str] = None,
) -> dict[str, Any]:
    base_url = "https://api.github.com"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        if method.upper() == "GET":
            resp = await client.get(f"{base_url}{endpoint}", headers=headers)
        elif method.upper() == "POST":
            resp = await client.post(f"{base_url}{endpoint}", headers=headers, json=data)
        elif method.upper() == "PATCH":
            resp = await client.patch(f"{base_url}{endpoint}", headers=headers, json=data)
        elif method.upper() == "DELETE":
            resp = await client.delete(f"{base_url}{endpoint}", headers=headers)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported HTTP method: {method}")

        if resp.status_code >= 400:
            return {"error": resp.text, "status_code": resp.status_code}
        return resp.json() if resp.content else {"status": resp.status_code}


# ─── CI Config Validation ─────────────────────────────────────────────────


def _validate_novaforge_config(content: str) -> CIValidationResponse:
    errors: list[str] = []
    warnings: list[str] = []

    try:
        import yaml
        parsed = yaml.safe_load(content)
    except ImportError:
        try:
            import json
            parsed = json.loads(content)
        except Exception:
            errors.append("Config must be valid YAML or JSON")
            return CIValidationResponse(valid=False, errors=errors)

    if not isinstance(parsed, dict):
        errors.append("Config root must be a mapping")
        return CIValidationResponse(valid=False, errors=errors)

    if "version" not in parsed:
        warnings.append("Missing 'version' field, defaulting to 1")

    if "pipeline" not in parsed and "steps" not in parsed and "jobs" not in parsed:
        errors.append("Config must contain at least one of: 'pipeline', 'steps', or 'jobs'")

    if "pipeline" in parsed:
        pipeline = parsed["pipeline"]
        if not isinstance(pipeline, list):
            errors.append("'pipeline' must be a list of steps")
        else:
            for i, step in enumerate(pipeline):
                if not isinstance(step, dict):
                    errors.append(f"Pipeline step {i} must be a mapping")
                    continue
                if "name" not in step:
                    warnings.append(f"Pipeline step {i} is missing a 'name'")
                if "run" not in step and "uses" not in step:
                    errors.append(f"Pipeline step {i} must have either 'run' or 'uses'")

    if "steps" in parsed:
        steps = parsed["steps"]
        if not isinstance(steps, list):
            errors.append("'steps' must be a list")
        else:
            for i, step in enumerate(steps):
                if not isinstance(step, dict):
                    errors.append(f"Step {i} must be a mapping")
                    continue
                if "name" not in step:
                    warnings.append(f"Step {i} is missing a 'name'")

    if "jobs" in parsed:
        jobs = parsed["jobs"]
        if not isinstance(jobs, dict):
            errors.append("'jobs' must be a mapping")
        else:
            for job_name, job in jobs.items():
                if not isinstance(job, dict):
                    errors.append(f"Job '{job_name}' must be a mapping")
                    continue
                if "steps" not in job:
                    warnings.append(f"Job '{job_name}' has no 'steps'")

    if "triggers" in parsed:
        valid_triggers = {"push", "pull_request", "schedule", "workflow_dispatch", "workflow_call", "repository_dispatch"}
        for trigger in parsed["triggers"]:
            if trigger not in valid_triggers:
                warnings.append(f"Unknown trigger: '{trigger}'")

    if "environment" in parsed:
        env = parsed["environment"]
        if isinstance(env, dict):
            for key, value in env.items():
                if isinstance(value, str) and any(
                    secret_pattern in value.lower()
                    for secret_pattern in ("secret:", "${{ secrets.")
                ):
                    warnings.append(f"Environment variable '{key}' references a secret")

    return CIValidationResponse(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        parsed=parsed,
    )


# ─── Endpoints ─────────────────────────────────────────────────────────────


@router.post("/webhook")
async def receive_webhook(
    request: Request,
    x_github_event: Optional[str] = Header(None),
    x_hub_signature_256: Optional[str] = Header(None),
    x_github_delivery: Optional[str] = Header(None),
) -> dict[str, Any]:
    body = await request.body()

    config = get_config()
    if not _verify_webhook_signature(body, x_hub_signature_256, config.webhook_secret):
        logger.warning("Webhook signature verification failed")
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    client_host = request.client.host if request.client else "unknown"
    if not _check_rate_limit(f"webhook:{client_host}"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_type = x_github_event or ""
    action = payload.get("action")
    repository = payload.get("repository", {})
    sender = payload.get("sender", {})

    event_id = str(uuid.uuid4())
    webhook_event = GitHubWebhookEvent(
        event_type=event_type,
        action=action,
        repository=repository,
        sender=sender,
        payload=payload,
    )
    _webhook_events[event_id] = webhook_event

    handler = _EVENT_HANDLERS.get(event_type)
    if not handler:
        logger.info("Unhandled webhook event type: %s", event_type)
        return {
            "status": "ignored",
            "event_id": event_id,
            "event_type": event_type,
            "message": f"No handler registered for event type: {event_type}",
        }

    result = await handler(payload)

    if event_type == "issue_comment" and isinstance(result, dict):
        novaforge_commands = result.get("novaforge_commands", [])
        for cmd in novaforge_commands:
            parts = cmd.strip().split()
            if len(parts) >= 2 and parts[1] == "review":
                is_pr = result.get("is_pull_request", False)
                if is_pr:
                    logger.info("Novaforge review command triggered for issue #%s", result.get("issue_number"))

    return {
        "status": "processed",
        "event_id": event_id,
        "event_type": event_type,
        "action": action,
        "repository": repository.get("full_name", ""),
        "delivery_id": x_github_delivery,
        "result": result,
    }


@router.post("/pr/review", response_model=ReviewResponse)
async def trigger_pr_review(
    request: PRReviewRequest,
    current_user: User = Depends(_get_current_user),
    db=Depends(get_db),
) -> ReviewResponse:
    client_host = current_user.id
    if not _check_rate_limit(f"pr_review:{client_host}"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    review_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    logger.info(
        "Triggering %s review on PR #%s repo=%s user=%s",
        request.review_type,
        request.pr_number,
        request.repository_id,
        current_user.username,
    )

    return ReviewResponse(
        review_id=review_id,
        summary=f"AI {request.review_type} review initiated for PR #{request.pr_number}",
        findings=[],
        score=0.0,
        files_reviewed=0,
        lines_reviewed=0,
        duration_ms=0,
    )


@router.post("/pr/comment")
async def post_pr_comment(
    request: PRCommentRequest,
    current_user: User = Depends(_get_current_user),
    db=Depends(get_db),
) -> dict[str, Any]:
    client_host = current_user.id
    if not _check_rate_limit(f"pr_comment:{client_host}"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    comment_id = int(uuid.uuid4().int % (2**31))
    now = datetime.now(timezone.utc).isoformat()

    logger.info(
        "Posting %s comment on PR #%s repo=%s user=%s",
        request.comment_type,
        request.pr_number,
        request.repository_id,
        current_user.username,
    )

    return {
        "comment_id": comment_id,
        "pr_number": request.pr_number,
        "repository_id": request.repository_id,
        "body": request.comment_body,
        "comment_type": request.comment_type,
        "author": _github_config.bot_username if request.comment_type == "review" else current_user.username,
        "created_at": now,
        "html_url": f"https://github.com/repos/{request.repository_id}/pull/{request.pr_number}#issuecomment-{comment_id}",
    }


@router.post("/pr/approve")
async def approve_pr(
    pr_number: int,
    repository_id: str,
    current_user: User = Depends(_get_current_user),
    db=Depends(get_db),
) -> dict[str, Any]:
    client_host = current_user.id
    if not _check_rate_limit(f"pr_approve:{client_host}"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    now = datetime.now(timezone.utc).isoformat()

    logger.info("Approving PR #%s repo=%s user=%s", pr_number, repository_id, current_user.username)

    return {
        "pr_number": pr_number,
        "repository_id": repository_id,
        "state": "approved",
        "reviewer": _github_config.bot_username,
        "body": "Automated approval by NovaForge AI.",
        "submitted_at": now,
    }


@router.post("/ci/status")
async def update_ci_status(
    request: CIStatusUpdate,
    current_user: User = Depends(_get_current_user),
    db=Depends(get_db),
) -> dict[str, Any]:
    client_host = current_user.id
    if not _check_rate_limit(f"ci_status:{client_host}"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    run_id = str(request.check_run_id)
    now = datetime.now(timezone.utc)

    existing = _ci_runs.get(run_id, {})
    existing.update({
        "check_run_id": request.check_run_id,
        "status": request.status,
        "conclusion": request.conclusion,
        "output": request.output,
        "updated_at": now.isoformat(),
        "updated_by": str(current_user.id),
    })

    if request.status == "completed" and not existing.get("started_at"):
        existing["started_at"] = now.isoformat()

    if request.status == "completed":
        existing["completed_at"] = now.isoformat()
        if existing.get("started_at"):
            started = datetime.fromisoformat(existing["started_at"])
            existing["duration_ms"] = int((now - started).total_seconds() * 1000)

    _ci_runs[run_id] = existing

    logger.info("CI status updated check_run=%s status=%s conclusion=%s", run_id, request.status, request.conclusion)

    return {
        "check_run_id": request.check_run_id,
        "status": request.status,
        "conclusion": request.conclusion,
        "updated_at": existing["updated_at"],
        "duration_ms": existing.get("duration_ms"),
    }


@router.post("/ci/trigger")
async def trigger_ci_workflow(
    request: CIWorkflowRun,
    current_user: User = Depends(_get_current_user),
    db=Depends(get_db),
) -> dict[str, Any]:
    client_host = current_user.id
    if not _check_rate_limit(f"ci_trigger:{client_host}"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    run_data = {
        "run_id": run_id,
        "workflow_id": request.workflow_id,
        "status": "queued",
        "trigger_event": request.trigger_event,
        "ref": request.ref,
        "sha": request.sha,
        "inputs": request.inputs,
        "created_at": now.isoformat(),
        "created_by": str(current_user.id),
        "completed_at": None,
        "duration_ms": None,
        "steps": [],
    }
    _ci_runs[run_id] = run_data

    logger.info("CI workflow triggered workflow=%s run=%s user=%s", request.workflow_id, run_id, current_user.username)

    return {
        "run_id": run_id,
        "workflow_id": request.workflow_id,
        "status": "queued",
        "trigger_event": request.trigger_event,
        "ref": request.ref,
        "sha": request.sha,
        "created_at": now.isoformat(),
        "message": "Workflow triggered successfully",
    }


@router.get("/pr/{pr_number}/analysis", response_model=PRAnalysisResponse)
async def get_pr_analysis(
    pr_number: int,
    repository_id: str,
    current_user: User = Depends(_get_current_user),
    db=Depends(get_db),
) -> PRAnalysisResponse:
    client_host = current_user.id
    if not _check_rate_limit(f"pr_analysis:{client_host}"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    cache_key = f"{repository_id}:{pr_number}"
    cached = _pr_analyses.get(cache_key)
    if cached:
        return cached

    analysis = PRAnalysisResponse(
        pr_number=pr_number,
        repository_id=repository_id,
        diff_summary={
            "total_files": 0,
            "total_additions": 0,
            "total_deletions": 0,
            "languages": {},
        },
        findings=[],
        summary=f"AI analysis for PR #{pr_number} in repository {repository_id}. No cached analysis available. Trigger a review via POST /pr/review first.",
        score=0.0,
        files_changed=0,
        additions=0,
        deletions=0,
    )

    _pr_analyses[cache_key] = analysis
    return analysis


@router.get("/repositories/{repo_id}/webhooks", response_model=list[WebhookOut])
async def list_repository_webhooks(
    repo_id: str,
    current_user: User = Depends(_get_current_user),
    db=Depends(get_db),
) -> list[WebhookOut]:
    webhooks = _repo_webhooks.get(repo_id, [])
    return [
        WebhookOut(
            id=wh["id"],
            repository_id=repo_id,
            url=wh["url"],
            events=wh["events"],
            active=wh["active"],
            content_type=wh["content_type"],
            created_at=wh["created_at"],
            last_triggered_at=wh.get("last_triggered_at"),
            delivery_count=wh.get("delivery_count", 0),
        )
        for wh in webhooks
    ]


@router.post("/repositories/{repo_id}/webhooks", response_model=WebhookOut, status_code=status.HTTP_201_CREATED)
async def create_repository_webhook(
    repo_id: str,
    request: WebhookCreateRequest,
    current_user: User = Depends(_get_current_user),
    db=Depends(get_db),
) -> WebhookOut:
    client_host = current_user.id
    if not _check_rate_limit(f"webhook_create:{client_host}"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    webhook_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    webhook_data = {
        "id": webhook_id,
        "url": request.url,
        "events": request.events,
        "active": request.active,
        "content_type": request.content_type,
        "secret": request.secret,
        "created_at": now,
        "created_by": str(current_user.id),
        "last_triggered_at": None,
        "delivery_count": 0,
    }

    _repo_webhooks[repo_id].append(webhook_data)

    logger.info("Webhook created id=%s repo=%s url=%s user=%s", webhook_id, repo_id, request.url, current_user.username)

    return WebhookOut(
        id=webhook_id,
        repository_id=repo_id,
        url=request.url,
        events=request.events,
        active=request.active,
        content_type=request.content_type,
        created_at=now,
    )


@router.delete("/repositories/{repo_id}/webhooks/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_repository_webhook(
    repo_id: str,
    webhook_id: str,
    current_user: User = Depends(_get_current_user),
    db=Depends(get_db),
) -> None:
    webhooks = _repo_webhooks.get(repo_id, [])
    for i, wh in enumerate(webhooks):
        if wh["id"] == webhook_id:
            del webhooks[i]
            logger.info("Webhook deleted id=%s repo=%s user=%s", webhook_id, repo_id, current_user.username)
            return

    raise HTTPException(status_code=404, detail="Webhook not found")


@router.post("/ci/validate", response_model=CIValidationResponse)
async def validate_ci_config(
    request: CIValidationRequest,
    current_user: User = Depends(_get_current_user),
    db=Depends(get_db),
) -> CIValidationResponse:
    client_host = current_user.id
    if not _check_rate_limit(f"ci_validate:{client_host}"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    logger.info("Validating CI config repo=%s file=%s user=%s", request.repository_id, request.config_filename, current_user.username)

    result = _validate_novaforge_config(request.config_content)
    return result


@router.get("/ci/status/{run_id}", response_model=CISummary)
async def get_ci_status(
    run_id: str,
    current_user: User = Depends(_get_current_user),
    db=Depends(get_db),
) -> CISummary:
    client_host = current_user.id
    if not _check_rate_limit(f"ci_status_get:{client_host}"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    run_data = _ci_runs.get(run_id)
    if not run_data:
        raise HTTPException(status_code=404, detail=f"CI run {run_id} not found")

    return CISummary(
        run_id=run_id,
        status=run_data.get("status", "unknown"),
        conclusion=run_data.get("conclusion"),
        started_at=run_data.get("created_at", ""),
        completed_at=run_data.get("completed_at"),
        duration_ms=run_data.get("duration_ms"),
        steps=run_data.get("steps", []),
    )
