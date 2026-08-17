"""Unit tests for Developer Tools CLI commands.

Tests the DeveloperCommands class from backend/app/cli/developer_commands.py,
mocking all HTTP calls via unittest.mock.
"""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

_backend_dir = str(Path(__file__).resolve().parent.parent.parent / "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from app.cli.developer_commands import DeveloperCommands


BASE_URL = "https://novaforge.example.com"
API_KEY = "test-api-key-12345"


def _make_response(status_code: int = 200, json_data: dict | None = None) -> MagicMock:
    """Create a mock httpx.Response with the given status code and JSON body."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = json.dumps(json_data or {})
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        http_err = httpx.HTTPStatusError(
            message=f"HTTP {status_code}",
            request=MagicMock(),
            response=resp,
        )
        resp.raise_for_status.side_effect = http_err
    return resp


def _patch_async_client(return_response: MagicMock | None = None, side_effect: Exception | None = None):
    """Return a context-manager patch for httpx.AsyncClient."""
    mock_client = AsyncMock()
    if side_effect:
        mock_client.post.side_effect = side_effect
        mock_client.get.side_effect = side_effect
    elif return_response is not None:
        mock_client.post.return_value = return_response
        mock_client.get.return_value = return_response

    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_client
    mock_cm.__aexit__.return_value = False
    return patch("httpx.AsyncClient", return_value=mock_cm), mock_client


class TestDeveloperCLICommands:
    """Tests for the DeveloperCommands async CLI methods."""

    # ------------------------------------------------------------------
    # test_chat_command
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_chat_command(self, capsys):
        response_data = {"content": "Hello from the assistant!"}
        resp = _make_response(200, response_data)
        patcher, mock_client = _patch_async_client(return_response=resp)

        with patcher:
            cmds = DeveloperCommands(base_url=BASE_URL, api_key=API_KEY)
            result = await cmds.chat(message="Hi there!")

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "/chat" in call_args[0][0]
        assert call_args[1]["json"]["message"] == "Hi there!"
        assert result == response_data
        captured = capsys.readouterr()
        assert "Hello from the assistant!" in captured.out

    # ------------------------------------------------------------------
    # test_agent_command
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_agent_command(self, capsys):
        response_data = {"result": "Agent finished task."}
        resp = _make_response(200, response_data)
        patcher, mock_client = _patch_async_client(return_response=resp)

        with patcher:
            cmds = DeveloperCommands(base_url=BASE_URL, api_key=API_KEY)
            result = await cmds.agent(agent_name="coder", task="write a parser")

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "/devtools/agents/run" in call_args[0][0]
        payload = call_args[1]["json"]
        assert payload["agent_name"] == "coder"
        assert payload["task"] == "write a parser"
        assert result == response_data
        captured = capsys.readouterr()
        assert "Agent finished task." in captured.out

    # ------------------------------------------------------------------
    # test_review_command
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_review_command(self, capsys):
        response_data = {
            "summary": "Looks good overall.",
            "issues": [
                {"severity": "low", "message": "Consider renaming variable", "file": "app.py", "line": 12},
            ],
            "score": 8.5,
        }
        resp = _make_response(200, response_data)
        patcher, mock_client = _patch_async_client(return_response=resp)

        with patcher:
            cmds = DeveloperCommands(base_url=BASE_URL, api_key=API_KEY)
            result = await cmds.review(file_path="app.py", code="x = 1")

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "/devtools/review" in call_args[0][0]
        payload = call_args[1]["json"]
        assert payload["review_type"] == "standard"
        assert payload["file_path"] == "app.py"
        assert result == response_data

    # ------------------------------------------------------------------
    # test_security_command
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_security_command(self, capsys):
        response_data = {
            "result": {"vulnerabilities": [{"type": "sql_injection", "severity": "high"}]}
        }
        resp = _make_response(200, response_data)
        patcher, mock_client = _patch_async_client(return_response=resp)

        with patcher:
            cmds = DeveloperCommands(base_url=BASE_URL, api_key=API_KEY)
            result = await cmds.security(file_path="db.py", code="cursor.execute(q)")

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "/devtools/code-actions" in call_args[0][0]
        payload = call_args[1]["json"]
        assert payload["action"] == "security_review"
        assert payload["file_path"] == "db.py"
        assert payload["code"] == "cursor.execute(q)"
        assert result == response_data

    # ------------------------------------------------------------------
    # test_test_gen_command
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_test_gen_command(self, capsys):
        response_data = {"result": "import pytest\ndef test_add(): assert 1+1==2"}
        resp = _make_response(200, response_data)
        patcher, mock_client = _patch_async_client(return_response=resp)

        with patcher:
            cmds = DeveloperCommands(base_url=BASE_URL, api_key=API_KEY)
            result = await cmds.test_gen(file_path="math.py", code="def add(a,b): return a+b")

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "/devtools/code-actions" in call_args[0][0]
        payload = call_args[1]["json"]
        assert payload["action"] == "generate_tests"
        assert payload["file_path"] == "math.py"
        assert result == response_data
        captured = capsys.readouterr()
        assert "pytest" in captured.out or "test_add" in captured.out

    # ------------------------------------------------------------------
    # test_explain_command
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_explain_command(self, capsys):
        response_data = {"result": "This function adds two numbers together."}
        resp = _make_response(200, response_data)
        patcher, mock_client = _patch_async_client(return_response=resp)

        with patcher:
            cmds = DeveloperCommands(base_url=BASE_URL, api_key=API_KEY)
            result = await cmds.explain(file_path="math.py", code="def add(a,b): return a+b")

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "/devtools/code-actions" in call_args[0][0]
        payload = call_args[1]["json"]
        assert payload["action"] == "explain"
        assert result == response_data
        captured = capsys.readouterr()
        assert "adds two numbers" in captured.out

    # ------------------------------------------------------------------
    # test_fix_command
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_fix_command(self, capsys):
        response_data = {
            "result": {
                "original_code": "x = divide(1,0)",
                "proposed_code": "x = safe_divide(1,0)",
                "explanation": "Added zero-division guard.",
            }
        }
        resp = _make_response(200, response_data)
        patcher, mock_client = _patch_async_client(return_response=resp)

        with patcher:
            cmds = DeveloperCommands(base_url=BASE_URL, api_key=API_KEY)
            result = await cmds.fix(file_path="utils.py", code="x = divide(1,0)")

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "/devtools/code-actions" in call_args[0][0]
        payload = call_args[1]["json"]
        assert payload["action"] == "fix"
        assert payload["code"] == "x = divide(1,0)"
        assert result == response_data

    # ------------------------------------------------------------------
    # test_search_command
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_search_command(self, capsys):
        response_data = {
            "results": [
                {"title": "auth.py", "score": 0.95, "content": "def authenticate(): ...", "line": 42},
            ],
            "total": 1,
        }
        resp = _make_response(200, response_data)
        patcher, mock_client = _patch_async_client(return_response=resp)

        with patcher:
            cmds = DeveloperCommands(base_url=BASE_URL, api_key=API_KEY)
            result = await cmds.search(query="authenticate", search_type="semantic", limit=5)

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "/devtools/search" in call_args[0][0]
        payload = call_args[1]["json"]
        assert payload["query"] == "authenticate"
        assert payload["search_type"] == "semantic"
        assert payload["limit"] == 5
        assert result == response_data

    # ------------------------------------------------------------------
    # test_workflow_command
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_workflow_command(self, capsys):
        response_data = {"status": "completed", "output": {"summary": "Done"}}
        resp = _make_response(200, response_data)
        patcher, mock_client = _patch_async_client(return_response=resp)

        with patcher:
            cmds = DeveloperCommands(base_url=BASE_URL, api_key=API_KEY)
            result = await cmds.workflow(
                workflow_id="wf-123",
                inputs={"key": "value"},
            )

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "/devtools/workflows/run" in call_args[0][0]
        payload = call_args[1]["json"]
        assert payload["workflow_id"] == "wf-123"
        assert payload["inputs"] == {"key": "value"}
        assert result == response_data

    # ------------------------------------------------------------------
    # test_status_command
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_status_command(self, capsys):
        response_data = {"status": "ok", "version": "2.1.0", "environment": "prod"}
        resp = _make_response(200, response_data)
        patcher, mock_client = _patch_async_client(return_response=resp)

        with patcher:
            cmds = DeveloperCommands(base_url=BASE_URL, api_key=API_KEY)
            result = await cmds.status()

        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        assert "/auth/status" in call_args[0][0]
        assert result == response_data
        captured = capsys.readouterr()
        assert "2.1.0" in captured.out

    # ------------------------------------------------------------------
    # test_login_command
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_login_command(self, capsys):
        response_data = {"access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.signature", "user": "dev@example.com"}
        resp = _make_response(200, response_data)
        patcher, mock_client = _patch_async_client(return_response=resp)

        with patcher:
            cmds = DeveloperCommands(base_url=BASE_URL, api_key=API_KEY)
            result = await cmds.login(email="dev@example.com", password="s3cret!")

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "/auth/token-exchange" in call_args[0][0]
        payload = call_args[1]["json"]
        assert payload["email"] == "dev@example.com"
        assert payload["password"] == "s3cret!"
        assert result == response_data
        captured = capsys.readouterr()
        assert "Login successful" in captured.out

    # ------------------------------------------------------------------
    # test_session_command
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_session_command(self, capsys):
        response_data = {
            "session_id": "sess-abc-123",
            "client_type": "cli",
            "org_id": "org-1",
            "created_at": "2025-01-01T00:00:00Z",
        }
        resp = _make_response(200, response_data)
        patcher, mock_client = _patch_async_client(return_response=resp)

        with patcher:
            cmds = DeveloperCommands(base_url=BASE_URL, api_key=API_KEY)
            result = await cmds.create_session(client_type="cli", org_id="org-1")

        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "/devtools/sessions" in call_args[0][0]
        payload = call_args[1]["json"]
        assert payload["client_type"] == "cli"
        assert payload["org_id"] == "org-1"
        assert result == response_data
        captured = capsys.readouterr()
        assert "sess-abc-123" in captured.out

    # ------------------------------------------------------------------
    # test_json_output
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_json_output(self, capsys):
        response_data = {"content": "Test JSON output mode"}
        resp = _make_response(200, response_data)
        patcher, mock_client = _patch_async_client(return_response=resp)

        with patcher:
            cmds = DeveloperCommands(base_url=BASE_URL, api_key=API_KEY)
            result = await cmds.chat(message="hello", as_json=True)

        assert result == response_data
        captured = capsys.readouterr()
        output = captured.out
        brace_idx = output.index("{")
        json_part = output[brace_idx:]
        parsed = json.loads(json_part)
        assert parsed["content"] == "Test JSON output mode"

    # ------------------------------------------------------------------
    # test_error_handling
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_error_handling(self, capsys):
        resp = _make_response(500, {"detail": "Internal Server Error"})
        patcher, mock_client = _patch_async_client(return_response=resp)

        with patcher:
            cmds = DeveloperCommands(base_url=BASE_URL, api_key=API_KEY)
            result = await cmds.chat(message="trigger error")

        assert result is None
        captured = capsys.readouterr()
        assert "Error:" in captured.err

    # ------------------------------------------------------------------
    # test_verbose_output
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_verbose_output(self, capsys):
        response_data = {"content": "Verbose test"}
        resp = _make_response(200, response_data)
        patcher, mock_client = _patch_async_client(return_response=resp)

        with patcher:
            cmds = DeveloperCommands(base_url=BASE_URL, api_key=API_KEY)
            result = await cmds.chat(message="hi", verbose=True)

        assert result == response_data
        captured = capsys.readouterr()
        assert "[verbose]" in captured.err
