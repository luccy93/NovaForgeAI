"""Tests for Developer Tools API — sessions, context, code actions, reviews, agents, search, git."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app import create_app
from app.api.auth import _get_current_user
from app.api import devtools

app = create_app()
client = TestClient(app)

BASE = "/api/v1"
TEST_USER_ID = uuid.uuid4()
OTHER_USER_ID = uuid.uuid4()


def _fake_user():
    user = MagicMock()
    user.id = TEST_USER_ID
    user.is_active = True
    return user


def _other_user():
    user = MagicMock()
    user.id = OTHER_USER_ID
    user.is_active = True
    return user


@pytest.fixture(autouse=True)
def _setup():
    app.dependency_overrides[_get_current_user] = _fake_user
    devtools._sessions.clear()
    yield
    app.dependency_overrides.clear()
    devtools._sessions.clear()


def _auth_header():
    return {"Authorization": "Bearer test-token"}


# ═══════════════════════════════════════════════════════════════════════════════
# Sessions
# ═══════════════════════════════════════════════════════════════════════════════

class TestDevToolsSessions:
    def test_create_session_success(self):
        resp = client.post(
            "/api/v1/devtools/sessions",
            json={
                "client_type": "vscode",
                "client_version": "1.2.0",
                "organization_id": "org-1",
                "repository_id": "repo-1",
                "workspace_root": "/workspace/project",
            },
            headers=_auth_header(),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "session_id" in data
        assert data["client_type"] == "vscode"
        assert data["client_version"] == "1.2.0"
        assert data["organization_id"] == "org-1"
        assert data["repository_id"] == "repo-1"
        assert data["created_at"]
        assert data["expires_at"]
        assert isinstance(data["capabilities"], dict)
        assert data["capabilities"]["streaming"] is True
        assert data["capabilities"]["webview"] is True

    def test_create_session_cli_type(self):
        resp = client.post(
            "/api/v1/devtools/sessions",
            json={"client_type": "cli", "client_version": "0.5.0"},
            headers=_auth_header(),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["client_type"] == "cli"
        assert data["capabilities"]["json_output"] is True
        assert data["capabilities"]["ci_mode"] is True
        assert data["capabilities"]["offline_mode"] is True

    def test_get_session_success(self):
        create_resp = client.post(
            "/api/v1/devtools/sessions",
            json={"client_type": "vscode"},
            headers=_auth_header(),
        )
        sid = create_resp.json()["session_id"]

        resp = client.get(f"/api/v1/devtools/sessions/{sid}", headers=_auth_header())
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == sid
        assert data["client_type"] == "vscode"

    def test_get_session_not_found(self):
        resp = client.get(
            f"/api/v1/devtools/sessions/{uuid.uuid4()}", headers=_auth_header()
        )
        assert resp.status_code == 404

    def test_get_session_wrong_user(self):
        create_resp = client.post(
            "/api/v1/devtools/sessions",
            json={"client_type": "vscode"},
            headers=_auth_header(),
        )
        sid = create_resp.json()["session_id"]

        app.dependency_overrides[_get_current_user] = _other_user
        resp = client.get(f"/api/v1/devtools/sessions/{sid}", headers=_auth_header())
        assert resp.status_code == 403

    def test_delete_session_success(self):
        create_resp = client.post(
            "/api/v1/devtools/sessions",
            json={"client_type": "jetbrains"},
            headers=_auth_header(),
        )
        sid = create_resp.json()["session_id"]

        resp = client.delete(f"/api/v1/devtools/sessions/{sid}", headers=_auth_header())
        assert resp.status_code == 204

        get_resp = client.get(f"/api/v1/devtools/sessions/{sid}", headers=_auth_header())
        assert get_resp.status_code == 404

    def test_delete_session_not_found(self):
        resp = client.delete(
            f"/api/v1/devtools/sessions/{uuid.uuid4()}", headers=_auth_header()
        )
        assert resp.status_code == 404

    def test_session_expires_in_24_hours(self):
        from datetime import datetime, timezone, timedelta

        resp = client.post(
            "/api/v1/devtools/sessions",
            json={"client_type": "cli"},
            headers=_auth_header(),
        )
        data = resp.json()
        created = datetime.fromisoformat(data["created_at"])
        expires = datetime.fromisoformat(data["expires_at"])
        delta = expires - created
        assert delta == timedelta(hours=24)


# ═══════════════════════════════════════════════════════════════════════════════
# Context Collection
# ═══════════════════════════════════════════════════════════════════════════════

class TestDevToolsContext:
    def test_collect_context_success(self):
        resp = client.post(
            "/api/v1/devtools/context",
            json={
                "session_id": str(uuid.uuid4()),
                "file_path": "src/main.py",
                "language": "python",
                "imports": ["os", "sys"],
            },
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "context_id" in data
        assert data["file_context"] is not None
        assert data["file_context"]["path"] == "src/main.py"
        assert data["file_context"]["language"] == "python"
        assert data["file_context"]["imports"] == ["os", "sys"]

    def test_collect_context_no_file(self):
        resp = client.post(
            "/api/v1/devtools/context",
            json={"session_id": str(uuid.uuid4())},
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["file_context"] is None
        assert data["symbols"] == []
        assert data["graph_context"] is None

    def test_collect_context_with_selection(self):
        resp = client.post(
            "/api/v1/devtools/context",
            json={
                "session_id": str(uuid.uuid4()),
                "file_path": "src/utils.py",
                "language": "python",
                "selection": {"start_line": 10, "end_line": 20, "text": "selected code"},
            },
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["file_context"]["selection"]["start_line"] == 10
        assert data["file_context"]["selection"]["end_line"] == 20

    def test_collect_context_token_estimate(self):
        resp = client.post(
            "/api/v1/devtools/context",
            json={
                "session_id": str(uuid.uuid4()),
                "file_path": "src/app.py",
                "language": "python",
            },
            headers=_auth_header(),
        )
        data = resp.json()
        assert isinstance(data["total_tokens_estimate"], int)
        assert data["total_tokens_estimate"] >= 0
        assert data["total_tokens_estimate"] <= 4096

    def test_collect_context_max_tokens(self):
        resp = client.post(
            "/api/v1/devtools/context",
            json={
                "session_id": str(uuid.uuid4()),
                "file_path": "src/big.py",
                "max_context_tokens": 1000,
            },
            headers=_auth_header(),
        )
        data = resp.json()
        assert data["total_tokens_estimate"] <= 1000


# ═══════════════════════════════════════════════════════════════════════════════
# Code Actions
# ═══════════════════════════════════════════════════════════════════════════════

class TestCodeActions:
    def _run_action(self, action, stream=False):
        return client.post(
            "/api/v1/devtools/code-actions",
            json={
                "session_id": str(uuid.uuid4()),
                "action": action,
                "file_path": "src/main.py",
                "language": "python",
                "code": "def hello():\n    return 'world'\n",
                "stream": stream,
            },
            headers=_auth_header(),
        )

    def test_code_action_explain(self):
        resp = self._run_action("explain")
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "explain"
        assert data["explanation"] == "Code explanation"
        assert data["file_path"] == "src/main.py"

    def test_code_action_fix(self):
        resp = self._run_action("fix")
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "fix"
        assert data["explanation"] == "Bug fix suggestion"

    def test_code_action_refactor(self):
        resp = self._run_action("refactor")
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "refactor"
        assert data["explanation"] == "Refactoring suggestion"

    def test_code_action_optimize(self):
        resp = self._run_action("optimize")
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "optimize"
        assert data["explanation"] == "Performance optimization"

    def test_code_action_generate_tests(self):
        resp = self._run_action("generate_tests")
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "generate_tests"
        assert data["explanation"] == "Test generation"

    def test_code_action_generate_docs(self):
        resp = self._run_action("generate_docs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "generate_docs"
        assert data["explanation"] == "Documentation generation"

    def test_code_action_security_review(self):
        resp = self._run_action("security_review")
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "security_review"
        assert data["explanation"] == "Security analysis"


# ═══════════════════════════════════════════════════════════════════════════════
# Diff Preview & Apply
# ═══════════════════════════════════════════════════════════════════════════════

class TestDiffPreview:
    def test_diff_preview_success(self):
        action_id = str(uuid.uuid4())
        resp = client.post(
            f"/api/v1/devtools/code-actions/diff/{action_id}",
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["diff_id"] == action_id
        assert isinstance(data["hunks"], list)
        assert isinstance(data["stats"], dict)

    def test_apply_code_action_approve(self):
        action_id = str(uuid.uuid4())
        resp = client.post(
            f"/api/v1/devtools/code-actions/apply/{action_id}?approved=true",
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action_id"] == action_id
        assert data["status"] == "applied"
        assert "timestamp" in data

    def test_apply_code_action_reject(self):
        action_id = str(uuid.uuid4())
        resp = client.post(
            f"/api/v1/devtools/code-actions/apply/{action_id}?approved=false",
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action_id"] == action_id
        assert data["status"] == "rejected"


# ═══════════════════════════════════════════════════════════════════════════════
# Code Review
# ═══════════════════════════════════════════════════════════════════════════════

class TestCodeReview:
    def _run_review(self, review_type, stream=False):
        return client.post(
            "/api/v1/devtools/review",
            json={
                "session_id": str(uuid.uuid4()),
                "file_path": "src/main.py",
                "code": "def hello():\n    return 'world'\n",
                "review_type": review_type,
                "stream": stream,
            },
            headers=_auth_header(),
        )

    def test_review_standard(self):
        resp = self._run_review("standard")
        assert resp.status_code == 200
        data = resp.json()
        assert "review_id" in data
        assert data["summary"] == "Code review completed"
        assert isinstance(data["findings"], list)
        assert data["files_reviewed"] == 1

    def test_review_security(self):
        resp = self._run_review("security")
        assert resp.status_code == 200
        data = resp.json()
        assert "review_id" in data
        assert isinstance(data["findings"], list)

    def test_review_architecture(self):
        resp = self._run_review("architecture")
        assert resp.status_code == 200
        data = resp.json()
        assert "review_id" in data

    def test_review_performance(self):
        resp = self._run_review("performance")
        assert resp.status_code == 200
        data = resp.json()
        assert "review_id" in data
        assert isinstance(data["lines_reviewed"], int)


# ═══════════════════════════════════════════════════════════════════════════════
# Agent Run
# ═══════════════════════════════════════════════════════════════════════════════

class TestAgentRun:
    def test_run_agent_success(self):
        resp = client.post(
            "/api/v1/devtools/agents/run",
            json={
                "session_id": str(uuid.uuid4()),
                "agent_name": "code_reviewer",
                "task": "Review this file for bugs",
                "stream": False,
            },
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "run_id" in data
        assert data["agent_name"] == "code_reviewer"
        assert data["status"] == "completed"
        assert isinstance(data["artifacts"], list)

    def test_run_agent_with_context(self):
        resp = client.post(
            "/api/v1/devtools/agents/run",
            json={
                "session_id": str(uuid.uuid4()),
                "agent_name": "tester",
                "task": "Generate unit tests",
                "context": {"file_path": "src/utils.py", "language": "python"},
                "stream": False,
            },
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_name"] == "tester"
        assert data["status"] == "completed"

    def test_run_agent_stream(self):
        resp = client.post(
            "/api/v1/devtools/agents/run",
            json={
                "session_id": str(uuid.uuid4()),
                "agent_name": "documenter",
                "task": "Generate docs",
                "stream": True,
            },
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/event-stream; charset=utf-8"
        assert "X-Run-ID" in resp.headers


# ═══════════════════════════════════════════════════════════════════════════════
# Search
# ═══════════════════════════════════════════════════════════════════════════════

class TestSearch:
    def _search(self, search_type, query="test function"):
        return client.post(
            "/api/v1/devtools/search",
            json={
                "session_id": str(uuid.uuid4()),
                "query": query,
                "search_type": search_type,
            },
            headers=_auth_header(),
        )

    def test_search_semantic(self):
        resp = self._search("semantic")
        assert resp.status_code == 200
        data = resp.json()
        assert data["search_type"] == "semantic"
        assert isinstance(data["results"], list)
        assert isinstance(data["total"], int)
        assert isinstance(data["duration_ms"], int)

    def test_search_symbol(self):
        resp = self._search("symbol", query="MyClass")
        assert resp.status_code == 200
        data = resp.json()
        assert data["search_type"] == "symbol"
        assert data["query"] == "MyClass"

    def test_search_file(self):
        resp = self._search("file", query="main.py")
        assert resp.status_code == 200
        data = resp.json()
        assert data["search_type"] == "file"
        assert data["query"] == "main.py"

    def test_search_repository(self):
        resp = self._search("repository", query="authentication flow")
        assert resp.status_code == 200
        data = resp.json()
        assert data["search_type"] == "repository"
        assert isinstance(data["results"], list)


# ═══════════════════════════════════════════════════════════════════════════════
# Client Capabilities
# ═══════════════════════════════════════════════════════════════════════════════

class TestCapabilities:
    def test_capabilities_vscode(self):
        resp = client.get(
            "/api/v1/devtools/capabilities?client_type=vscode", headers=_auth_header()
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["streaming"] is True
        assert data["webview"] is True
        assert data["diagnostics"] is True
        assert data["code_lens"] is True
        assert data["inline_completion"] is True

    def test_capabilities_jetbrains(self):
        resp = client.get(
            "/api/v1/devtools/capabilities?client_type=jetbrains", headers=_auth_header()
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["editor_integration"] is True
        assert data["tool_window"] is True
        assert data["psi_navigation"] is True

    def test_capabilities_cli(self):
        resp = client.get(
            "/api/v1/devtools/capabilities?client_type=cli", headers=_auth_header()
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["json_output"] is True
        assert data["ci_mode"] is True
        assert data["non_interactive"] is True
        assert data["offline_mode"] is True

    def test_capabilities_ci(self):
        resp = client.get(
            "/api/v1/devtools/capabilities?client_type=ci", headers=_auth_header()
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ci_mode"] is True
        assert data["non_interactive"] is True
        assert data["json_output"] is True
        assert data["machine_output"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# Git Integration
# ═══════════════════════════════════════════════════════════════════════════════

class TestGitIntegration:
    def test_git_status(self):
        resp = client.get("/api/v1/devtools/git/status", headers=_auth_header())
        assert resp.status_code == 200
        data = resp.json()
        assert data["branch"] == "main"
        assert data["remote"] == "origin"
        assert isinstance(data["staged_files"], list)
        assert isinstance(data["unstaged_files"], list)
        assert isinstance(data["untracked_files"], list)
        assert data["is_clean"] is True

    def test_git_diff_all(self):
        resp = client.get("/api/v1/devtools/git/diff", headers=_auth_header())
        assert resp.status_code == 200
        data = resp.json()
        assert data["file_path"] is None
        assert data["staged"] is False
        assert isinstance(data["diff"], str)
        assert isinstance(data["stats"], dict)
        assert "insertions" in data["stats"]
        assert "deletions" in data["stats"]

    def test_git_diff_file(self):
        resp = client.get(
            "/api/v1/devtools/git/diff?file_path=src/main.py&staged=true",
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["file_path"] == "src/main.py"
        assert data["staged"] is True

    def test_git_context(self):
        resp = client.get("/api/v1/devtools/git/context", headers=_auth_header())
        assert resp.status_code == 200
        data = resp.json()
        assert data["branch"] == "main"
        assert data["is_dirty"] is False
        assert data["commit_sha"] is None
        assert data["pr_number"] is None


# ═══════════════════════════════════════════════════════════════════════════════
# Diagnostics
# ═══════════════════════════════════════════════════════════════════════════════

class TestDiagnostics:
    def test_diagnostics_empty(self):
        resp = client.get("/api/v1/devtools/diagnostics", headers=_auth_header())
        assert resp.status_code == 200
        data = resp.json()
        assert data["file_path"] is None
        assert data["diagnostics"] == []
        assert data["summary"]["errors"] == 0
        assert data["summary"]["warnings"] == 0
        assert data["summary"]["info"] == 0

    def test_diagnostics_for_file(self):
        resp = client.get(
            "/api/v1/devtools/diagnostics?file_path=src/main.py", headers=_auth_header()
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["file_path"] == "src/main.py"
        assert isinstance(data["diagnostics"], list)
        assert isinstance(data["summary"], dict)


# ═══════════════════════════════════════════════════════════════════════════════
# Workflow Run
# ═══════════════════════════════════════════════════════════════════════════════

class TestWorkflowRun:
    def test_workflow_run_success(self):
        resp = client.post(
            "/api/v1/devtools/workflows/run",
            json={
                "session_id": str(uuid.uuid4()),
                "workflow_id": "wf-deploy-001",
            },
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "execution_id" in data
        assert data["workflow_id"] == "wf-deploy-001"
        assert data["status"] == "pending"

    def test_workflow_run_with_inputs(self):
        resp = client.post(
            "/api/v1/devtools/workflows/run",
            json={
                "session_id": str(uuid.uuid4()),
                "workflow_id": "wf-test-002",
                "inputs": {"branch": "main", "environment": "staging"},
            },
            headers=_auth_header(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["workflow_id"] == "wf-test-002"
        assert data["status"] == "pending"
        assert "message" in data


# ═══════════════════════════════════════════════════════════════════════════════
# Cross-Cutting Capabilities
# ═══════════════════════════════════════════════════════════════════════════════

class TestClientCapabilities:
    def test_capabilities_all_client_types(self):
        for ctype in ("vscode", "jetbrains", "cli", "browser", "ci"):
            resp = client.get(
                f"/api/v1/devtools/capabilities?client_type={ctype}", headers=_auth_header()
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["streaming"] is True
            assert data["cancellation"] is True
            assert data["diff_preview"] is True
            assert data["code_actions"] is True
            assert data["review"] is True
            assert data["search"] is True
            assert data["agent_execution"] is True
            assert data["workflow_execution"] is True
            assert data["git_integration"] is True

        unknown_resp = client.get(
            "/api/v1/devtools/capabilities?client_type=unknown", headers=_auth_header()
        )
        assert unknown_resp.status_code == 200
        data = unknown_resp.json()
        assert data["streaming"] is True
        assert data.get("webview") is None
        assert data.get("json_output") is None
