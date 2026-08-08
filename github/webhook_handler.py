"""
GitHub webhook handler for NovaForge AI.
Processes push, PR, issue events and triggers appropriate agents.
"""
import hmac
import hashlib
from fastapi import APIRouter, Request, HTTPException, Depends
from app.core.config import settings

router = APIRouter()

async def verify_webhook_signature(request: Request, payload: bytes):
    """Verify X-Hub-Signature-256"""
    signature = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(
        settings.github_webhook_secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(403, "Invalid signature")

@router.post("/webhooks/github")
async def handle_webhook(request: Request):
    payload = await request.body()
    await verify_webhook_signature(request, payload)
    event = request.headers.get("X-GitHub-Event", "")
    data = await request.json()
    
    if event == "push":
        return await handle_push(data)
    elif event == "pull_request":
        return await handle_pull_request(data)
    elif event == "issues":
        return await handle_issue(data)
    return {"status": "ignored", "event": event}

async def handle_push(data: dict):
    repo = data["repository"]["full_name"]
    branch = data["ref"].split("/")[-1]
    # Trigger indexing + analysis
    return {"status": "processing", "repo": repo, "branch": branch}

async def handle_pull_request(data: dict):
    action = data["action"]
    pr_number = data["pull_request"]["number"]
    repo = data["repository"]["full_name"]
    if action in ["opened", "synchronize"]:
        # Trigger code review agent
        return {"status": "review_scheduled", "repo": repo, "pr": pr_number}
    return {"status": "ignored", "action": action}

async def handle_issue(data: dict):
    action = data["action"]
    issue_number = data["issue"]["number"]
    if action == "opened":
        return {"status": "triage_scheduled", "issue": issue_number}
    return {"status": "ignored"}
