"""Unit tests for GitHub Integration — webhooks, PR review, CI/CD, webhook management."""

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.github_integration import (
    CIStatusUpdate,
    CIValidationRequest,
    CIWorkflowRun,
    PRCommentRequest,
    PRReviewRequest,
    WebhookCreateRequest,
    _check_rate_limit,
    _handle_check_run_event,
    _handle_issue_comment_event,
    _handle_pr_event,
    _handle_pr_review_event,
    _handle_push_event,
    _handle_workflow_run_event,
    _repo_webhooks,
    _validate_novaforge_config,
    _verify_webhook_signature,
    approve_pr,
    create_repository_webhook,
    delete_repository_webhook,
    get_ci_status,
    get_config,
    get_pr_analysis,
    list_repository_webhooks,
    post_pr_comment,
    receive_webhook,
    trigger_ci_workflow,
    trigger_pr_review,
    update_ci_status,
    validate_ci_config,
)

pytestmark = pytest.mark.asyncio


def _dummy_user():
    user = MagicMock()
    user.id = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    user.username = "testuser"
    user.email = "test@example.com"
    user.is_active = True
    return user


def _make_request(method="POST", body=b"{}", headers=None, client_host="127.0.0.1", parse_json=True):
    request = AsyncMock()
    request.body = AsyncMock(return_value=body)
    if parse_json:
        request.json = AsyncMock(return_value=json.loads(body))
    else:
        request.json = AsyncMock(side_effect=Exception("Invalid JSON"))
    request.client = MagicMock()
    request.client.host = client_host
    if headers is None:
        headers = {}
    request.headers = headers
    return request


def _make_db():
    return AsyncMock()


def _webhook_payload(event_type="push", action=None, extra=None):
    payload = {
        "repository": {"full_name": "org/repo", "id": 12345},
        "sender": {"login": "dev1"},
        "ref": "refs/heads/main",
        "head_commit": {"id": "abc123", "message": "fix: bug"},
        "pusher": {"name": "dev1"},
        "commits": [{"added": ["a.py"], "modified": ["b.py"], "removed": ["c.py"]}],
    }
    if event_type == "pull_request":
        payload["action"] = action or "opened"
        payload["pull_request"] = {
            "number": 42,
            "title": "Add feature",
            "head": {"sha": "head123"},
            "base": {"ref": "main"},
        }
    elif event_type == "pull_request_review":
        payload["action"] = action or "submitted"
        payload["pull_request"] = {"number": 42}
        payload["review"] = {
            "id": 999,
            "state": "approved",
            "user": {"login": "reviewer1"},
            "body": "LGTM",
        }
    elif event_type == "issue_comment":
        payload["action"] = action or "created"
        payload["issue"] = {"number": 10}
        payload["comment"] = {
            "user": {"login": "commenter1"},
            "body": extra.get("body", "nice work!") if extra else "nice work!",
        }
        if extra and extra.get("is_pr"):
            payload["issue"]["pull_request"] = {"url": "https://api.github.com/repos/org/repo/pulls/10"}
    elif event_type == "check_run":
        payload["action"] = action or "completed"
        payload["check_run"] = {
            "id": 555,
            "name": "ci/lint",
            "status": "completed",
            "conclusion": "success",
        }
    elif event_type == "workflow_run":
        payload["action"] = action or "completed"
        payload["workflow_run"] = {
            "id": 777,
            "name": "CI",
            "status": "completed",
            "conclusion": "success",
            "head_branch": "main",
            "head_sha": "abc123",
        }
    if extra:
        payload.update(extra)
    return payload


# ─── TestWebhookProcessing ─────────────────────────────────────────────────


class TestWebhookProcessing:
    async def test_webhook_push_event(self):
        payload = _webhook_payload("push")
        result = await _handle_push_event(payload)
        assert result["event"] == "push"
        assert result["repo"] == "org/repo"
        assert result["ref"] == "refs/heads/main"
        assert result["sha"] == "abc123"
        assert result["pusher"] == "dev1"
        assert "a.py" in result["changed_files"]
        assert "b.py" in result["changed_files"]
        assert "c.py" in result["changed_files"]
        assert result["commits_count"] == 1

    async def test_webhook_pr_opened(self):
        payload = _webhook_payload("pull_request", action="opened")
        result = await _handle_pr_event(payload)
        assert result["event"] == "pull_request"
        assert result["action"] == "opened"
        assert result["pr_number"] == 42
        assert result["repo"] == "org/repo"
        assert result["title"] == "Add feature"
        assert result["base_branch"] == "main"
        assert result["triggered_review"] is True

    async def test_webhook_pr_review(self):
        payload = _webhook_payload("pull_request_review")
        result = await _handle_pr_review_event(payload)
        assert result["event"] == "pull_request_review"
        assert result["action"] == "submitted"
        assert result["pr_number"] == 42
        assert result["review_id"] == 999
        assert result["review_state"] == "approved"
        assert result["reviewer"] == "reviewer1"
        assert result["body"] == "LGTM"
        assert result["repo"] == "org/repo"

    async def test_webhook_issue_comment(self):
        payload = _webhook_payload("issue_comment", extra={"body": "looks good"})
        result = await _handle_issue_comment_event(payload)
        assert result["event"] == "issue_comment"
        assert result["action"] == "created"
        assert result["issue_number"] == 10
        assert result["commenter"] == "commenter1"
        assert result["comment_body"] == "looks good"
        assert result["novaforge_commands"] == []

    async def test_webhook_check_run(self):
        payload = _webhook_payload("check_run")
        result = await _handle_check_run_event(payload)
        assert result["event"] == "check_run"
        assert result["action"] == "completed"
        assert result["check_run_id"] == 555
        assert result["name"] == "ci/lint"
        assert result["status"] == "completed"
        assert result["conclusion"] == "success"
        assert result["repo"] == "org/repo"

    async def test_webhook_workflow_run(self):
        payload = _webhook_payload("workflow_run")
        result = await _handle_workflow_run_event(payload)
        assert result["event"] == "workflow_run"
        assert result["action"] == "completed"
        assert result["run_id"] == 777
        assert result["name"] == "CI"
        assert result["status"] == "completed"
        assert result["conclusion"] == "success"
        assert result["head_branch"] == "main"
        assert result["head_sha"] == "abc123"
        assert result["repo"] == "org/repo"


# ─── TestPRReview ──────────────────────────────────────────────────────────


class TestPRReview:
    async def test_pr_review_success(self):
        request = PRReviewRequest(pr_number=1, repository_id="repo-123")
        user = _dummy_user()
        db = _make_db()
        result = await trigger_pr_review(request, current_user=user, db=db)
        assert result.review_id is not None
        assert "standard review" in result.summary.lower()
        assert result.score == 0.0

    async def test_pr_review_with_type(self):
        request = PRReviewRequest(
            pr_number=7,
            repository_id="repo-456",
            review_type="security",
        )
        user = _dummy_user()
        db = _make_db()
        result = await trigger_pr_review(request, current_user=user, db=db)
        assert "security" in result.summary.lower()

    async def test_pr_review_auto_comment(self):
        request = PRReviewRequest(
            pr_number=3,
            repository_id="repo-789",
            auto_comment=True,
            post_as_bot=True,
        )
        user = _dummy_user()
        db = _make_db()
        result = await trigger_pr_review(request, current_user=user, db=db)
        assert result.review_id is not None
        assert isinstance(result.findings, list)

    async def test_pr_review_not_found(self):
        request = PRReviewRequest(
            pr_number=9999,
            repository_id="repo-nonexistent",
            review_type="standard",
        )
        user = _dummy_user()
        db = _make_db()
        result = await trigger_pr_review(request, current_user=user, db=db)
        assert result.review_id is not None
        assert "9999" in result.summary


# ─── TestPRComments ────────────────────────────────────────────────────────


class TestPRComments:
    async def test_pr_comment_success(self):
        request = PRCommentRequest(
            pr_number=10,
            repository_id="repo-100",
            comment_body="All checks passed.",
            comment_type="review",
        )
        user = _dummy_user()
        db = _make_db()
        result = await post_pr_comment(request, current_user=user, db=db)
        assert "comment_id" in result
        assert result["pr_number"] == 10
        assert result["repository_id"] == "repo-100"
        assert result["body"] == "All checks passed."
        assert result["comment_type"] == "review"
        assert "created_at" in result
        assert "html_url" in result

    async def test_pr_approve_success(self):
        user = _dummy_user()
        db = _make_db()
        result = await approve_pr(
            pr_number=5,
            repository_id="repo-200",
            current_user=user,
            db=db,
        )
        assert result["pr_number"] == 5
        assert result["repository_id"] == "repo-200"
        assert result["state"] == "approved"
        assert result["body"] == "Automated approval by NovaForge AI."
        assert "submitted_at" in result

    async def test_pr_analysis(self):
        user = _dummy_user()
        db = _make_db()
        result = await get_pr_analysis(
            pr_number=15,
            repository_id="repo-300",
            current_user=user,
            db=db,
        )
        assert result.pr_number == 15
        assert result.repository_id == "repo-300"
        assert result.score == 0.0
        assert isinstance(result.findings, list)
        assert result.files_changed == 0


# ─── TestCIIntegration ─────────────────────────────────────────────────────


class TestCIIntegration:
    async def test_ci_update_status(self):
        request = CIStatusUpdate(
            check_run_id=111,
            status="completed",
            conclusion="success",
            output={"title": "All checks passed", "summary": "No issues"},
        )
        user = _dummy_user()
        db = _make_db()
        result = await update_ci_status(request, current_user=user, db=db)
        assert result["check_run_id"] == 111
        assert result["status"] == "completed"
        assert result["conclusion"] == "success"
        assert "updated_at" in result
        assert result["duration_ms"] is not None

    async def test_ci_trigger_workflow(self):
        request = CIWorkflowRun(
            workflow_id="build-and-test",
            trigger_event="push",
            ref="main",
            sha="deadbeef",
            inputs={"environment": "staging"},
        )
        user = _dummy_user()
        db = _make_db()
        result = await trigger_ci_workflow(request, current_user=user, db=db)
        assert "run_id" in result
        assert result["workflow_id"] == "build-and-test"
        assert result["status"] == "queued"
        assert result["trigger_event"] == "push"
        assert result["ref"] == "main"
        assert result["sha"] == "deadbeef"
        assert result["message"] == "Workflow triggered successfully"

    async def test_ci_get_status(self):
        request = CIWorkflowRun(
            workflow_id="deploy",
            status="queued",
            ref="main",
        )
        user = _dummy_user()
        db = _make_db()
        trigger_result = await trigger_ci_workflow(request, current_user=user, db=db)
        run_id = trigger_result["run_id"]

        from app.api.github_integration import _ci_runs
        _ci_runs[run_id]["status"] = "completed"
        _ci_runs[run_id]["conclusion"] = "success"
        _ci_runs[run_id]["completed_at"] = datetime.now(timezone.utc).isoformat()

        result = await get_ci_status(run_id, current_user=user, db=db)
        assert result.run_id == run_id
        assert result.status == "completed"
        assert result.conclusion == "success"

    async def test_ci_validate_config_valid(self):
        config_content = json.dumps({
            "version": 1,
            "pipeline": [
                {"name": "lint", "run": "flake8 ."},
                {"name": "test", "run": "pytest"},
            ],
        })
        request = CIValidationRequest(
            repository_id="repo-500",
            config_content=config_content,
        )
        user = _dummy_user()
        db = _make_db()
        result = await validate_ci_config(request, current_user=user, db=db)
        assert result.valid is True
        assert len(result.errors) == 0
        assert result.parsed["version"] == 1

    async def test_ci_validate_config_invalid(self):
        config_content = json.dumps({
            "version": 1,
        })
        request = CIValidationRequest(
            repository_id="repo-501",
            config_content=config_content,
        )
        user = _dummy_user()
        db = _make_db()
        result = await validate_ci_config(request, current_user=user, db=db)
        assert result.valid is False
        assert len(result.errors) > 0


# ─── TestWebhookManagement ─────────────────────────────────────────────────


class TestWebhookManagement:
    async def test_list_webhooks(self):
        from app.api.github_integration import _repo_webhooks

        _repo_webhooks["repo-list-test"] = [
            {
                "id": "wh-1",
                "url": "https://example.com/hook",
                "events": ["push"],
                "active": True,
                "content_type": "json",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "last_triggered_at": None,
                "delivery_count": 0,
            }
        ]

        user = _dummy_user()
        db = _make_db()
        result = await list_repository_webhooks("repo-list-test", current_user=user, db=db)
        assert len(result) == 1
        assert result[0].id == "wh-1"
        assert result[0].url == "https://example.com/hook"
        assert result[0].events == ["push"]
        assert result[0].active is True

        _repo_webhooks.pop("repo-list-test", None)

    async def test_create_webhook(self):
        request = WebhookCreateRequest(
            url="https://example.com/hook",
            events=["push", "pull_request"],
            secret="my-secret",
            content_type="json",
            active=True,
        )
        user = _dummy_user()
        db = _make_db()
        result = await create_repository_webhook("repo-create-test", request, current_user=user, db=db)
        assert result.id is not None
        assert result.url == "https://example.com/hook"
        assert result.events == ["push", "pull_request"]
        assert result.repository_id == "repo-create-test"
        assert result.active is True
        assert result.content_type == "json"
        assert result.created_at is not None

    async def test_delete_webhook(self):
        from app.api.github_integration import _repo_webhooks

        webhook_id = str(uuid.uuid4())
        _repo_webhooks["repo-delete-test"] = [
            {
                "id": webhook_id,
                "url": "https://example.com/delete-me",
                "events": ["push"],
                "active": True,
                "content_type": "json",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ]

        user = _dummy_user()
        db = _make_db()
        await delete_repository_webhook("repo-delete-test", webhook_id, current_user=user, db=db)
        assert len(_repo_webhooks["repo-delete-test"]) == 0

        _repo_webhooks.pop("repo-delete-test", None)

    async def test_webhook_signature_verification(self):
        secret = "test-webhook-secret-123"
        payload = b'{"action":"opened"}'
        expected = "sha256=" + hmac.new(
            secret.encode("utf-8"), payload, hashlib.sha256
        ).hexdigest()
        assert _verify_webhook_signature(payload, expected, secret) is True

        tampered = "sha256=" + hmac.new(
            secret.encode("utf-8"), b'{"action":"closed"}', hashlib.sha256
        ).hexdigest()
        assert _verify_webhook_signature(payload, tampered, secret) is False


# ─── TestEventHandlers ─────────────────────────────────────────────────────


class TestEventHandlers:
    async def test_handle_push_updates_knowledge(self):
        payload = {
            "repository": {"full_name": "org/knowledge-repo", "id": 111},
            "ref": "refs/heads/main",
            "head_commit": {"id": "sha-new", "message": "update docs"},
            "pusher": {"name": "doc-writer"},
            "commits": [
                {
                    "added": ["docs/new.md"],
                    "modified": ["README.md"],
                    "removed": [],
                }
            ],
        }
        result = await _handle_push_event(payload)
        assert result["event"] == "push"
        assert result["repo"] == "org/knowledge-repo"
        assert "docs/new.md" in result["changed_files"]
        assert "README.md" in result["changed_files"]
        assert result["commits_count"] == 1

    async def test_handle_pr_creates_review(self):
        payload = {
            "action": "opened",
            "repository": {"full_name": "org/app", "id": 222},
            "sender": {"login": "author1"},
            "pull_request": {
                "number": 99,
                "title": "Refactor auth module",
                "head": {"sha": "pr-sha"},
                "base": {"ref": "develop"},
            },
        }
        result = await _handle_pr_event(payload)
        assert result["event"] == "pull_request"
        assert result["action"] == "opened"
        assert result["pr_number"] == 99
        assert result["triggered_review"] is True
        assert "review_request" in result

    async def test_handle_comment_triggers_action(self):
        payload = {
            "action": "created",
            "repository": {"full_name": "org/bot-test", "id": 333},
            "sender": {"login": "admin1"},
            "issue": {
                "number": 7,
                "pull_request": {"url": "https://api.github.com/repos/org/bot-test/pulls/7"},
            },
            "comment": {
                "user": {"login": "admin1"},
                "body": "/novaforge review\nPlease review the latest changes.",
            },
        }
        result = await _handle_issue_comment_event(payload)
        assert result["event"] == "issue_comment"
        assert result["is_pull_request"] is True
        assert "/novaforge review" in result["novaforge_commands"]
        assert len(result["novaforge_commands"]) == 1

    async def test_handle_check_run_updates_status(self):
        payload = {
            "action": "completed",
            "repository": {"full_name": "org/ci-test", "id": 444},
            "sender": {"login": "ci-bot"},
            "check_run": {
                "id": 888,
                "name": "test/build",
                "status": "completed",
                "conclusion": "failure",
            },
        }
        result = await _handle_check_run_event(payload)
        assert result["event"] == "check_run"
        assert result["action"] == "completed"
        assert result["check_run_id"] == 888
        assert result["name"] == "test/build"
        assert result["conclusion"] == "failure"

    async def test_handle_workflow_run_notifies(self):
        payload = {
            "action": "completed",
            "repository": {"full_name": "org/deploy", "id": 555},
            "sender": {"login": "ci-bot"},
            "workflow_run": {
                "id": 1010,
                "name": "Deploy Production",
                "status": "completed",
                "conclusion": "success",
                "head_branch": "main",
                "head_sha": "deploy-sha",
            },
        }
        result = await _handle_workflow_run_event(payload)
        assert result["event"] == "workflow_run"
        assert result["action"] == "completed"
        assert result["run_id"] == 1010
        assert result["name"] == "Deploy Production"
        assert result["conclusion"] == "success"
        assert result["head_branch"] == "main"

    async def test_handle_review_event_processes(self):
        payload = {
            "action": "submitted",
            "repository": {"full_name": "org/review-test", "id": 666},
            "sender": {"login": "reviewer2"},
            "pull_request": {"number": 25},
            "review": {
                "id": 4444,
                "state": "changes_requested",
                "user": {"login": "reviewer2"},
                "body": "Please fix the null check on line 42.",
            },
        }
        result = await _handle_pr_review_event(payload)
        assert result["event"] == "pull_request_review"
        assert result["action"] == "submitted"
        assert result["pr_number"] == 25
        assert result["review_id"] == 4444
        assert result["review_state"] == "changes_requested"
        assert result["reviewer"] == "reviewer2"
        assert "null check" in result["body"]


# ─── TestSecurity ──────────────────────────────────────────────────────────


class TestSecurity:
    async def test_webhook_valid_signature(self):
        secret = "hmac-test-secret"
        payload = b'{"event":"push","repo":"test"}'
        sig = "sha256=" + hmac.new(
            secret.encode("utf-8"), payload, hashlib.sha256
        ).hexdigest()
        assert _verify_webhook_signature(payload, sig, secret) is True

    async def test_webhook_invalid_signature(self):
        secret = "hmac-test-secret"
        payload = b'{"event":"push","repo":"test"}'
        bad_sig = "sha256=" + hmac.new(
            "wrong-key".encode("utf-8"), payload, hashlib.sha256
        ).hexdigest()
        assert _verify_webhook_signature(payload, bad_sig, secret) is False

    async def test_webhook_missing_signature(self):
        secret = "hmac-test-secret"
        payload = b'{"event":"push"}'
        assert _verify_webhook_signature(payload, None, secret) is False


# ─── TestWebhookEndpointIntegration ────────────────────────────────────────


class TestWebhookEndpointIntegration:
    async def test_receive_webhook_push_returns_processed(self):
        payload = _webhook_payload("push")
        body = json.dumps(payload).encode("utf-8")
        request = _make_request(body=body)

        with patch("app.api.github_integration._verify_webhook_signature", return_value=True), \
             patch("app.api.github_integration._check_rate_limit", return_value=True):
            result = await receive_webhook(
                request,
                x_github_event="push",
                x_hub_signature_256=None,
                x_github_delivery="delivery-1",
            )
        assert result["status"] == "processed"
        assert result["event_type"] == "push"
        assert result["result"]["event"] == "push"
        assert result["delivery_id"] == "delivery-1"

    async def test_receive_webhook_unknown_event_ignored(self):
        payload = {"action": "opened", "repository": {"full_name": "org/x"}}
        body = json.dumps(payload).encode("utf-8")
        request = _make_request(body=body)

        with patch("app.api.github_integration._verify_webhook_signature", return_value=True), \
             patch("app.api.github_integration._check_rate_limit", return_value=True):
            result = await receive_webhook(
                request,
                x_github_event="unknown_event_type",
                x_hub_signature_256=None,
                x_github_delivery="delivery-2",
            )
        assert result["status"] == "ignored"
        assert "No handler registered" in result["message"]

    async def test_receive_webhook_invalid_signature_rejected(self):
        from fastapi import HTTPException
        payload = _webhook_payload("push")
        body = json.dumps(payload).encode("utf-8")
        request = _make_request(body=body)

        with patch("app.api.github_integration._verify_webhook_signature", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                await receive_webhook(
                    request,
                    x_github_event="push",
                    x_hub_signature_256="sha256=badsig",
                    x_github_delivery="delivery-3",
                )
            assert exc_info.value.status_code == 403

    async def test_receive_webhook_rate_limited(self):
        from fastapi import HTTPException
        payload = _webhook_payload("push")
        body = json.dumps(payload).encode("utf-8")
        request = _make_request(body=body)

        with patch("app.api.github_integration._verify_webhook_signature", return_value=True), \
             patch("app.api.github_integration._check_rate_limit", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                await receive_webhook(
                    request,
                    x_github_event="push",
                    x_hub_signature_256=None,
                    x_github_delivery="delivery-4",
                )
            assert exc_info.value.status_code == 429

    async def test_receive_webhook_invalid_json_rejected(self):
        from fastapi import HTTPException
        request = _make_request(body=b"not-json-at-all", parse_json=False)

        with patch("app.api.github_integration._verify_webhook_signature", return_value=True), \
             patch("app.api.github_integration._check_rate_limit", return_value=True):
            with pytest.raises(HTTPException) as exc_info:
                await receive_webhook(
                    request,
                    x_github_event="push",
                    x_hub_signature_256=None,
                    x_github_delivery="delivery-5",
                )
            assert exc_info.value.status_code == 400


# ─── TestRateLimiting ──────────────────────────────────────────────────────


class TestRateLimiting:
    def test_rate_limit_allows_within_window(self):
        identifier = f"test_rate_{uuid.uuid4()}"
        for _ in range(5):
            assert _check_rate_limit(identifier) is True

    def test_rate_limit_blocks_when_exceeded(self):
        identifier = f"test_rate_exhaust_{uuid.uuid4()}"
        for _ in range(60):
            result = _check_rate_limit(identifier)
            assert result is True
        assert _check_rate_limit(identifier) is False


# ─── TestCIValidationLogic ─────────────────────────────────────────────────


class TestCIValidationLogic:
    def test_valid_pipeline_config(self):
        content = json.dumps({
            "version": 1,
            "pipeline": [
                {"name": "build", "run": "make build"},
                {"name": "test", "run": "pytest"},
            ],
        })
        result = _validate_novaforge_config(content)
        assert result.valid is True
        assert len(result.errors) == 0

    def test_valid_jobs_config(self):
        content = json.dumps({
            "version": 1,
            "jobs": {
                "build": {"steps": [{"name": "compile", "run": "gcc main.c"}]},
                "test": {"steps": [{"name": "unit-test", "run": "make test"}]},
            },
        })
        result = _validate_novaforge_config(content)
        assert result.valid is True
        assert len(result.errors) == 0

    def test_missing_pipeline_and_steps_and_jobs(self):
        content = json.dumps({"version": 1})
        result = _validate_novaforge_config(content)
        assert result.valid is False
        assert any("pipeline" in e for e in result.errors)

    def test_missing_version_warns(self):
        content = json.dumps({"pipeline": [{"name": "lint", "run": "flake8"}]})
        result = _validate_novaforge_config(content)
        assert result.valid is True
        assert any("version" in w for w in result.warnings)

    def test_invalid_yaml_syntax(self):
        content = "pipeline:\n  - name: build\n  run: make\n    invalid: [{"
        import sys
        with patch.dict(sys.modules, {"yaml": None}):
            result = _validate_novaforge_config(content)
            assert result.valid is False
            assert any("YAML" in e or "JSON" in e for e in result.errors)

    def test_pipeline_step_missing_run_or_uses(self):
        content = json.dumps({
            "pipeline": [{"name": "mystery-step"}],
        })
        result = _validate_novaforge_config(content)
        assert result.valid is False
        assert any("'run' or 'uses'" in e for e in result.errors)

    def test_pipeline_step_not_mapping(self):
        content = json.dumps({
            "pipeline": ["not-a-mapping"],
        })
        result = _validate_novaforge_config(content)
        assert result.valid is False
        assert any("mapping" in e for e in result.errors)

    def test_steps_not_list(self):
        content = json.dumps({"steps": "not-a-list"})
        result = _validate_novaforge_config(content)
        assert result.valid is False
        assert any("'steps' must be a list" in e for e in result.errors)

    def test_jobs_not_mapping(self):
        content = json.dumps({"jobs": ["not-a-mapping"]})
        result = _validate_novaforge_config(content)
        assert result.valid is False
        assert any("'jobs' must be a mapping" in e for e in result.errors)

    def test_unknown_trigger_warns(self):
        content = json.dumps({
            "pipeline": [{"name": "ci", "run": "echo ok"}],
            "triggers": ["push", "banana_event"],
        })
        result = _validate_novaforge_config(content)
        assert result.valid is True
        assert any("banana_event" in w for w in result.warnings)

    def test_secret_reference_warns(self):
        content = json.dumps({
            "pipeline": [{"name": "deploy", "run": "echo ok"}],
            "environment": {"API_KEY": "secret:my-api-key"},
        })
        result = _validate_novaforge_config(content)
        assert result.valid is True
        assert any("API_KEY" in w for w in result.warnings)

    def test_non_dict_root_rejected(self):
        content = json.dumps([1, 2, 3])
        result = _validate_novaforge_config(content)
        assert result.valid is False
        assert any("mapping" in e for e in result.errors)

    def test_invalid_content_format(self):
        import sys
        with patch.dict(sys.modules, {"yaml": None}):
            result = _validate_novaforge_config("{{{not valid yaml or json}}}")
            assert result.valid is False
            assert any("YAML" in e or "JSON" in e for e in result.errors)


# ─── TestConfig ────────────────────────────────────────────────────────────


class TestConfig:
    def test_get_config_returns_singleton(self):
        cfg1 = get_config()
        cfg2 = get_config()
        assert cfg1 is cfg2

    def test_config_default_bot_username(self):
        cfg = get_config()
        assert cfg.bot_username == "novaforge-bot"

    def test_config_auto_review_enabled(self):
        cfg = get_config()
        assert isinstance(cfg.auto_review_enabled, bool)
        assert isinstance(cfg.review_on_pr, bool)


# ─── TestPRValidation ─────────────────────────────────────────────────────


class TestPRValidation:
    def test_pr_review_request_validation(self):
        req = PRReviewRequest(pr_number=1, repository_id="r1", review_type="performance")
        assert req.review_type == "performance"
        assert req.auto_comment is True
        assert req.post_as_bot is True

    def test_pr_review_request_invalid_type(self):
        with pytest.raises(Exception):
            PRReviewRequest(pr_number=1, repository_id="r1", review_type="invalid_type")

    def test_pr_comment_request_validation(self):
        req = PRCommentRequest(
            pr_number=1,
            repository_id="r1",
            comment_body="test comment",
            comment_type="suggestion",
        )
        assert req.comment_type == "suggestion"

    def test_pr_comment_request_empty_body_rejected(self):
        with pytest.raises(Exception):
            PRCommentRequest(pr_number=1, repository_id="r1", comment_body="", comment_type="review")

    def test_ci_status_update_validation(self):
        req = CIStatusUpdate(check_run_id=1, status="in_progress")
        assert req.status == "in_progress"
        assert req.conclusion is None

    def test_ci_status_update_invalid_status(self):
        with pytest.raises(Exception):
            CIStatusUpdate(check_run_id=1, status="unknown_status")

    def test_ci_workflow_run_validation(self):
        req = CIWorkflowRun(workflow_id="wf-1", ref="main", sha="abc123")
        assert req.trigger_event == "push"
        assert req.status == "queued"

    def test_webhook_create_request_validation(self):
        req = WebhookCreateRequest(url="https://hook.example.com", events=["push", "pull_request"])
        assert req.active is True
        assert req.content_type == "json"

    def test_webhook_create_request_empty_events_rejected(self):
        with pytest.raises(Exception):
            WebhookCreateRequest(url="https://hook.example.com", events=[])
