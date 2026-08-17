"""Unit tests for SDK devtools methods.

Tests the NovaForgeClient (sync) and AsyncNovaForgeClient devtools methods
from backend/sdk/client.py, plus the devtools dataclass models.
"""

import json
from unittest.mock import MagicMock, patch, AsyncMock

import httpx
import pytest

from backend.sdk.client import NovaForgeClient, AsyncNovaForgeClient
from backend.sdk.models import (
    DevSession,
    ContextResult,
    CodeActionResult,
    ReviewResult,
    SearchResultItem,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(status_code: int = 200, json_data: dict | None = None) -> MagicMock:
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    data = json_data if json_data is not None else {}
    resp.json.return_value = data
    resp.text = json.dumps(data)
    return resp


class TestSyncSDKDevTools:
    """Tests for NovaForgeClient devtools methods (synchronous)."""

    def _client(self) -> NovaForgeClient:
        return NovaForgeClient(
            base_url="https://api.example.com",
            api_key="test-key-999",
            max_retries=1,
        )

    # ------------------------------------------------------------------
    # test_create_devtools_session
    # ------------------------------------------------------------------
    def test_create_devtools_session(self):
        client = self._client()
        response_data = {
            "session_id": "sess-001",
            "client_type": "vscode",
            "client_version": "2.0.0",
            "organization_id": "org-xyz",
        }
        with patch.object(client, "post", return_value=response_data) as mock_post:
            result = client.create_devtools_session(
                client_type="vscode",
                client_version="2.0.0",
                org_id="org-xyz",
            )

        mock_post.assert_called_once_with(
            "/devtools/sessions",
            {
                "client_type": "vscode",
                "client_version": "2.0.0",
                "org_id": "org-xyz",
            },
        )
        assert isinstance(result, DevSession)
        assert result.session_id == "sess-001"
        assert result.client_type == "vscode"
        assert result.organization_id == "org-xyz"

    # ------------------------------------------------------------------
    # test_get_devtools_session
    # ------------------------------------------------------------------
    def test_get_devtools_session(self):
        client = self._client()
        response_data = {
            "session_id": "sess-002",
            "client_type": "cli",
            "client_version": "1.0.0",
        }
        with patch.object(client, "get", return_value=response_data) as mock_get:
            result = client.get_devtools_session("sess-002")

        mock_get.assert_called_once_with("/devtools/sessions/sess-002")
        assert isinstance(result, DevSession)
        assert result.session_id == "sess-002"
        assert result.client_type == "cli"

    # ------------------------------------------------------------------
    # test_delete_devtools_session
    # ------------------------------------------------------------------
    def test_delete_devtools_session(self):
        client = self._client()
        response_data = {"status": "deleted"}
        with patch.object(client, "delete", return_value=response_data) as mock_delete:
            result = client.delete_devtools_session("sess-003")

        mock_delete.assert_called_once_with("/devtools/sessions/sess-003")
        assert result == {"status": "deleted"}

    # ------------------------------------------------------------------
    # test_collect_context
    # ------------------------------------------------------------------
    def test_collect_context(self):
        client = self._client()
        response_data = {
            "context_id": "ctx-100",
            "file_context": {"language": "python", "path": "app/main.py"},
            "symbols": [{"name": "main", "type": "function"}],
            "rag_results": [],
            "graph_context": [],
            "total_tokens_estimate": 1234,
        }
        with patch.object(client, "post", return_value=response_data) as mock_post:
            result = client.collect_context(
                session_id="sess-001",
                file_path="app/main.py",
                language="python",
                selection="def main():",
                imports=["os", "sys"],
                max_context_tokens=8192,
            )

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "/devtools/context"
        payload = call_args[0][1]
        assert payload["session_id"] == "sess-001"
        assert payload["file_path"] == "app/main.py"
        assert payload["language"] == "python"
        assert payload["selection"] == "def main():"
        assert payload["imports"] == ["os", "sys"]
        assert payload["max_context_tokens"] == 8192
        assert isinstance(result, ContextResult)
        assert result.context_id == "ctx-100"
        assert result.total_tokens_estimate == 1234

    # ------------------------------------------------------------------
    # test_code_action
    # ------------------------------------------------------------------
    def test_code_action(self):
        client = self._client()
        response_data = {
            "action_id": "act-001",
            "action": "refactor",
            "file_path": "src/util.py",
            "original_code": "def old(): pass",
            "proposed_code": "def new(): pass",
            "explanation": "Renamed for clarity",
            "diff": "-def old(): pass\n+def new(): pass",
            "confidence": 0.92,
        }
        with patch.object(client, "post", return_value=response_data) as mock_post:
            result = client.code_action(
                action="refactor",
                file_path="src/util.py",
                language="python",
                code="def old(): pass",
                session_id="sess-010",
                start_line=1,
                end_line=5,
            )

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "/devtools/code-actions"
        payload = call_args[0][1]
        assert payload["action"] == "refactor"
        assert payload["file_path"] == "src/util.py"
        assert payload["session_id"] == "sess-010"
        assert payload["start_line"] == 1
        assert payload["end_line"] == 5
        assert isinstance(result, CodeActionResult)
        assert result.action_id == "act-001"
        assert result.confidence == 0.92

    # ------------------------------------------------------------------
    # test_review_code
    # ------------------------------------------------------------------
    def test_review_code(self):
        client = self._client()
        response_data = {
            "review_id": "rev-001",
            "summary": "Code looks solid.",
            "findings": [{"severity": "info", "message": "Consider adding docstrings"}],
            "score": 8.0,
            "files_reviewed": 1,
            "lines_reviewed": 45,
        }
        with patch.object(client, "post", return_value=response_data) as mock_post:
            result = client.review_code(
                session_id="sess-020",
                file_path="app/handler.py",
                code="def handle(): ...",
                review_type="standard",
            )

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "/devtools/review"
        payload = call_args[0][1]
        assert payload["session_id"] == "sess-020"
        assert payload["file_path"] == "app/handler.py"
        assert payload["review_type"] == "standard"
        assert isinstance(result, ReviewResult)
        assert result.review_id == "rev-001"
        assert result.score == 8.0
        assert len(result.findings) == 1

    # ------------------------------------------------------------------
    # test_run_agent_from_ide
    # ------------------------------------------------------------------
    def test_run_agent_from_ide(self):
        client = self._client()
        response_data = {"status": "completed", "output": "Agent done"}
        with patch.object(client, "post", return_value=response_data) as mock_post:
            result = client.run_agent_from_ide(
                session_id="sess-030",
                agent_name="reviewer",
                task="review all files",
                stream=False,
            )

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "/devtools/agents/run"
        payload = call_args[0][1]
        assert payload["session_id"] == "sess-030"
        assert payload["agent_name"] == "reviewer"
        assert payload["task"] == "review all files"
        assert payload["stream"] is False
        assert result == response_data

    # ------------------------------------------------------------------
    # test_search_code
    # ------------------------------------------------------------------
    def test_search_code(self):
        client = self._client()
        response_data = [
            {
                "id": "sr-1",
                "score": 0.95,
                "file_path": "src/auth.py",
                "line": 10,
                "content": "def login():",
                "symbol_type": "function",
                "symbol_name": "login",
            }
        ]
        with patch.object(client, "post", return_value=response_data) as mock_post:
            result = client.search_code(
                session_id="sess-040",
                query="login function",
                search_type="semantic",
                repository_id="repo-1",
                file_pattern="*.py",
                limit=5,
            )

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "/devtools/search"
        payload = call_args[0][1]
        assert payload["session_id"] == "sess-040"
        assert payload["query"] == "login function"
        assert payload["search_type"] == "semantic"
        assert payload["repository_id"] == "repo-1"
        assert payload["file_pattern"] == "*.py"
        assert payload["limit"] == 5
        assert len(result) == 1
        assert isinstance(result[0], SearchResultItem)
        assert result[0].file_path == "src/auth.py"

    # ------------------------------------------------------------------
    # test_run_workflow_from_ide
    # ------------------------------------------------------------------
    def test_run_workflow_from_ide(self):
        client = self._client()
        response_data = {"status": "completed", "result": "Workflow finished"}
        with patch.object(client, "post", return_value=response_data) as mock_post:
            result = client.run_workflow_from_ide(
                session_id="sess-050",
                workflow_id="wf-abc",
                inputs={"repo": "graphrag"},
                stream=True,
            )

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "/devtools/workflows/run"
        payload = call_args[0][1]
        assert payload["session_id"] == "sess-050"
        assert payload["workflow_id"] == "wf-abc"
        assert payload["inputs"] == {"repo": "graphrag"}
        assert payload["stream"] is True
        assert result == response_data

    # ------------------------------------------------------------------
    # test_get_capabilities
    # ------------------------------------------------------------------
    def test_get_capabilities(self):
        client = self._client()
        response_data = {"features": ["code_review", "chat", "search"], "max_tokens": 16384}
        with patch.object(client, "get", return_value=response_data) as mock_get:
            result = client.get_capabilities(client_type="vscode")

        mock_get.assert_called_once_with("/devtools/capabilities", params={"client_type": "vscode"})
        assert result["features"] == ["code_review", "chat", "search"]
        assert result["max_tokens"] == 16384

    # ------------------------------------------------------------------
    # test_get_git_status
    # ------------------------------------------------------------------
    def test_get_git_status(self):
        client = self._client()
        response_data = {"branch": "main", "dirty": False, "ahead": 0, "behind": 2}
        with patch.object(client, "get", return_value=response_data) as mock_get:
            result = client.get_git_status()

        mock_get.assert_called_once_with("/devtools/git/status")
        assert result["branch"] == "main"
        assert result["ahead"] == 0
        assert result["behind"] == 2

    # ------------------------------------------------------------------
    # test_get_git_diff
    # ------------------------------------------------------------------
    def test_get_git_diff(self):
        client = self._client()
        response_data = {"diff": "@@ -1,3 +1,4 @@\n+import os\n def main():\n     pass"}
        with patch.object(client, "get", return_value=response_data) as mock_get:
            result = client.get_git_diff(file_path="main.py", staged=True)

        mock_get.assert_called_once_with(
            "/devtools/git/diff",
            params={"file_path": "main.py", "staged": True},
        )
        assert "diff" in result

    # ------------------------------------------------------------------
    # test_get_git_context
    # ------------------------------------------------------------------
    def test_get_git_context(self):
        client = self._client()
        response_data = {"branch": "feature/x", "commit": "abc123", "recent_commits": []}
        with patch.object(client, "get", return_value=response_data) as mock_get:
            result = client.get_git_context()

        mock_get.assert_called_once_with("/devtools/git/context")
        assert result["branch"] == "feature/x"
        assert result["commit"] == "abc123"

    # ------------------------------------------------------------------
    # test_get_diagnostics
    # ------------------------------------------------------------------
    def test_get_diagnostics(self):
        client = self._client()
        response_data = {
            "diagnostics": [
                {"severity": "error", "message": "Undefined name 'x'", "line": 5},
            ],
            "file_path": "app.py",
        }
        with patch.object(client, "get", return_value=response_data) as mock_get:
            result = client.get_diagnostics(file_path="app.py")

        mock_get.assert_called_once_with("/devtools/diagnostics", params={"file_path": "app.py"})
        assert len(result["diagnostics"]) == 1
        assert result["diagnostics"][0]["severity"] == "error"


# ---------------------------------------------------------------------------
# Async SDK tests
# ---------------------------------------------------------------------------


class TestAsyncSDKDevTools:
    """Tests for AsyncNovaForgeClient devtools methods."""

    def _client(self) -> AsyncNovaForgeClient:
        return AsyncNovaForgeClient(
            base_url="https://api.example.com",
            api_key="test-key-999",
            max_retries=1,
        )

    # ------------------------------------------------------------------
    # test_create_devtools_session
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_create_devtools_session(self):
        client = self._client()
        response_data = {
            "session_id": "sess-a001",
            "client_type": "jetbrains",
            "client_version": "3.0.0",
            "organization_id": "org-a1",
            "repository_id": "repo-a1",
        }
        with patch.object(client, "post", new_callable=AsyncMock, return_value=response_data) as mock_post:
            result = await client.create_devtools_session(
                client_type="jetbrains",
                client_version="3.0.0",
                org_id="org-a1",
                repo_id="repo-a1",
            )

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "/devtools/sessions"
        payload = call_args[0][1]
        assert payload["client_type"] == "jetbrains"
        assert payload["client_version"] == "3.0.0"
        assert payload["org_id"] == "org-a1"
        assert payload["repo_id"] == "repo-a1"
        assert isinstance(result, DevSession)
        assert result.session_id == "sess-a001"

    # ------------------------------------------------------------------
    # test_get_devtools_session
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_devtools_session(self):
        client = self._client()
        response_data = {
            "session_id": "sess-a002",
            "client_type": "cli",
            "client_version": "1.0.0",
        }
        with patch.object(client, "get", new_callable=AsyncMock, return_value=response_data) as mock_get:
            result = await client.get_devtools_session("sess-a002")

        mock_get.assert_called_once_with("/devtools/sessions/sess-a002")
        assert isinstance(result, DevSession)
        assert result.session_id == "sess-a002"

    # ------------------------------------------------------------------
    # test_delete_devtools_session
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_delete_devtools_session(self):
        client = self._client()
        response_data = {"status": "deleted"}
        with patch.object(client, "delete", new_callable=AsyncMock, return_value=response_data) as mock_delete:
            result = await client.delete_devtools_session("sess-a003")

        mock_delete.assert_called_once_with("/devtools/sessions/sess-a003")
        assert result == {"status": "deleted"}

    # ------------------------------------------------------------------
    # test_collect_context
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_collect_context(self):
        client = self._client()
        response_data = {
            "context_id": "ctx-a100",
            "file_context": {"language": "typescript", "path": "src/index.ts"},
            "symbols": [{"name": "handleRequest", "type": "function"}],
            "rag_results": [],
            "graph_context": [],
            "total_tokens_estimate": 5678,
        }
        with patch.object(client, "post", new_callable=AsyncMock, return_value=response_data) as mock_post:
            result = await client.collect_context(
                session_id="sess-a001",
                file_path="src/index.ts",
                language="typescript",
                imports=["express", "cors"],
            )

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "/devtools/context"
        payload = call_args[0][1]
        assert payload["session_id"] == "sess-a001"
        assert payload["file_path"] == "src/index.ts"
        assert payload["language"] == "typescript"
        assert payload["imports"] == ["express", "cors"]
        assert isinstance(result, ContextResult)
        assert result.context_id == "ctx-a100"

    # ------------------------------------------------------------------
    # test_code_action
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_code_action(self):
        client = self._client()
        response_data = {
            "action_id": "act-a001",
            "action": "fix",
            "file_path": "src/api.ts",
            "original_code": "fetch(url)",
            "proposed_code": "await fetch(url)",
            "explanation": "Added await keyword",
            "diff": "-fetch(url)\n+await fetch(url)",
            "confidence": 0.99,
            "citations": ["MDN: async/await"],
        }
        with patch.object(client, "post", new_callable=AsyncMock, return_value=response_data) as mock_post:
            result = await client.code_action(
                action="fix",
                file_path="src/api.ts",
                language="typescript",
                code="fetch(url)",
                session_id="sess-a010",
            )

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "/devtools/code-actions"
        payload = call_args[0][1]
        assert payload["action"] == "fix"
        assert payload["session_id"] == "sess-a010"
        assert isinstance(result, CodeActionResult)
        assert result.action_id == "act-a001"
        assert result.confidence == 0.99

    # ------------------------------------------------------------------
    # test_review_code
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_review_code(self):
        client = self._client()
        response_data = {
            "review_id": "rev-a001",
            "summary": "Excellent code quality.",
            "findings": [],
            "score": 9.5,
            "files_reviewed": 3,
            "lines_reviewed": 200,
        }
        with patch.object(client, "post", new_callable=AsyncMock, return_value=response_data) as mock_post:
            result = await client.review_code(
                session_id="sess-a020",
                pr_number=42,
                review_type="architecture",
            )

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "/devtools/review"
        payload = call_args[0][1]
        assert payload["session_id"] == "sess-a020"
        assert payload["pr_number"] == 42
        assert payload["review_type"] == "architecture"
        assert isinstance(result, ReviewResult)
        assert result.score == 9.5

    # ------------------------------------------------------------------
    # test_run_agent_from_ide
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_run_agent_from_ide(self):
        client = self._client()
        response_data = {"status": "running", "output": "Agent started"}
        with patch.object(client, "post", new_callable=AsyncMock, return_value=response_data) as mock_post:
            result = await client.run_agent_from_ide(
                session_id="sess-a030",
                agent_name="coder",
                task="implement feature X",
                stream=True,
            )

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "/devtools/agents/run"
        payload = call_args[0][1]
        assert payload["agent_name"] == "coder"
        assert payload["task"] == "implement feature X"
        assert payload["stream"] is True
        assert result == response_data

    # ------------------------------------------------------------------
    # test_search_code
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_search_code(self):
        client = self._client()
        response_data = [
            {
                "id": "sr-a1",
                "score": 0.88,
                "file_path": "src/utils.ts",
                "line": 22,
                "content": "export function formatDate(): string",
                "symbol_type": "function",
                "symbol_name": "formatDate",
                "repository": "graphrag",
            }
        ]
        with patch.object(client, "post", new_callable=AsyncMock, return_value=response_data) as mock_post:
            result = await client.search_code(
                session_id="sess-a040",
                query="formatDate",
                search_type="symbol",
                repository_id="repo-ts",
                limit=10,
            )

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "/devtools/search"
        payload = call_args[0][1]
        assert payload["query"] == "formatDate"
        assert payload["search_type"] == "symbol"
        assert len(result) == 1
        assert isinstance(result[0], SearchResultItem)
        assert result[0].symbol_name == "formatDate"

    # ------------------------------------------------------------------
    # test_run_workflow_from_ide
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_run_workflow_from_ide(self):
        client = self._client()
        response_data = {"status": "completed", "result": "Done"}
        with patch.object(client, "post", new_callable=AsyncMock, return_value=response_data) as mock_post:
            result = await client.run_workflow_from_ide(
                session_id="sess-a050",
                workflow_id="wf-async-1",
                inputs={"task": "deploy"},
                stream=False,
            )

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "/devtools/workflows/run"
        payload = call_args[0][1]
        assert payload["workflow_id"] == "wf-async-1"
        assert payload["inputs"] == {"task": "deploy"}
        assert result == response_data

    # ------------------------------------------------------------------
    # test_get_capabilities
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_capabilities(self):
        client = self._client()
        response_data = {"features": ["chat", "review"], "max_tokens": 8192}
        with patch.object(client, "get", new_callable=AsyncMock, return_value=response_data) as mock_get:
            result = await client.get_capabilities(client_type="cli")

        mock_get.assert_called_once_with("/devtools/capabilities", params={"client_type": "cli"})
        assert result["features"] == ["chat", "review"]

    # ------------------------------------------------------------------
    # test_get_git_status
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_git_status(self):
        client = self._client()
        response_data = {"branch": "develop", "dirty": True, "ahead": 3, "behind": 1}
        with patch.object(client, "get", new_callable=AsyncMock, return_value=response_data) as mock_get:
            result = await client.get_git_status()

        mock_get.assert_called_once_with("/devtools/git/status")
        assert result["branch"] == "develop"
        assert result["dirty"] is True

    # ------------------------------------------------------------------
    # test_get_git_diff
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_git_diff(self):
        client = self._client()
        response_data = {"diff": "@@ -2,3 +2,5 @@\n+import json\n+print('hello')\n"}
        with patch.object(client, "get", new_callable=AsyncMock, return_value=response_data) as mock_get:
            result = await client.get_git_diff(file_path="main.py", staged=False)

        mock_get.assert_called_once_with(
            "/devtools/git/diff",
            params={"file_path": "main.py", "staged": False},
        )
        assert "diff" in result

    # ------------------------------------------------------------------
    # test_get_git_context
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_git_context(self):
        client = self._client()
        response_data = {"branch": "main", "commit": "def456", "recent_commits": []}
        with patch.object(client, "get", new_callable=AsyncMock, return_value=response_data) as mock_get:
            result = await client.get_git_context()

        mock_get.assert_called_once_with("/devtools/git/context")
        assert result["commit"] == "def456"

    # ------------------------------------------------------------------
    # test_get_diagnostics
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_diagnostics(self):
        client = self._client()
        response_data = {
            "diagnostics": [
                {"severity": "warning", "message": "Unused import", "line": 1},
            ]
        }
        with patch.object(client, "get", new_callable=AsyncMock, return_value=response_data) as mock_get:
            result = await client.get_diagnostics(file_path="mod.ts")

        mock_get.assert_called_once_with("/devtools/diagnostics", params={"file_path": "mod.ts"})
        assert result["diagnostics"][0]["message"] == "Unused import"


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestSDKModels:
    """Tests for the devtools dataclass models."""

    def test_dev_session_model(self):
        session = DevSession(
            session_id="s-1",
            client_type="vscode",
            client_version="2.1.0",
            organization_id="org-1",
            repository_id="repo-1",
        )
        assert session.session_id == "s-1"
        assert session.client_type == "vscode"
        assert session.client_version == "2.1.0"
        assert session.organization_id == "org-1"
        assert session.repository_id == "repo-1"
        assert session.capabilities == []
        assert session.created_at is None
        assert session.expires_at is None

    def test_context_result_model(self):
        ctx = ContextResult(
            context_id="ctx-1",
            file_context={"language": "python", "path": "app.py"},
            symbols=[{"name": "main", "type": "function"}],
            rag_results=[{"text": "relevant doc", "score": 0.9}],
            graph_context=[{"entity": "User", "relation": "has"}],
            total_tokens_estimate=2048,
        )
        assert ctx.context_id == "ctx-1"
        assert ctx.file_context == {"language": "python", "path": "app.py"}
        assert len(ctx.symbols) == 1
        assert ctx.symbols[0]["name"] == "main"
        assert len(ctx.rag_results) == 1
        assert ctx.rag_results[0]["score"] == 0.9
        assert len(ctx.graph_context) == 1
        assert ctx.total_tokens_estimate == 2048

    def test_code_action_result_model(self):
        action = CodeActionResult(
            action_id="act-1",
            action="explain",
            file_path="src/main.py",
            original_code="print('hello')",
            proposed_code="print('Hello, World!')",
            explanation="Capitalize greeting",
            diff="-print('hello')\n+print('Hello, World!')",
            confidence=0.85,
            citations=["PEP8"],
            warnings=["Style change only"],
        )
        assert action.action_id == "act-1"
        assert action.action == "explain"
        assert action.file_path == "src/main.py"
        assert action.original_code == "print('hello')"
        assert action.proposed_code == "print('Hello, World!')"
        assert action.explanation == "Capitalize greeting"
        assert action.confidence == 0.85
        assert action.citations == ["PEP8"]
        assert action.warnings == ["Style change only"]

    def test_review_result_model(self):
        review = ReviewResult(
            review_id="rev-1",
            summary="Good code with minor issues.",
            findings=[
                {"severity": "low", "message": "Add type hints", "file": "app.py", "line": 10},
                {"severity": "medium", "message": "Missing error handling", "file": "app.py", "line": 25},
            ],
            score=7.5,
            files_reviewed=2,
            lines_reviewed=150,
        )
        assert review.review_id == "rev-1"
        assert review.summary == "Good code with minor issues."
        assert len(review.findings) == 2
        assert review.findings[0]["severity"] == "low"
        assert review.findings[1]["severity"] == "medium"
        assert review.score == 7.5
        assert review.files_reviewed == 2
        assert review.lines_reviewed == 150

    def test_search_result_item_model(self):
        item = SearchResultItem(
            id="sr-1",
            score=0.92,
            file_path="src/auth.py",
            line=42,
            content="def authenticate(token): ...",
            symbol_type="function",
            symbol_name="authenticate",
            repository="graphrag",
        )
        assert item.id == "sr-1"
        assert item.score == 0.92
        assert item.file_path == "src/auth.py"
        assert item.line == 42
        assert item.content == "def authenticate(token): ..."
        assert item.symbol_type == "function"
        assert item.symbol_name == "authenticate"
        assert item.repository == "graphrag"
