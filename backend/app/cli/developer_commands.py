"""Developer Tools CLI Extension for NovaForge.

Provides CLI commands that interface with the /devtools backend API,
including sessions, context, code actions, reviews, search, agents,
and workflows.

Usage:
    python -m app.cli.developer_commands <command> [args...]
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
import time
from datetime import datetime, timezone
from typing import Any, Generator, Optional

import httpx


# ---------------------------------------------------------------------------
# Terminal formatting helpers
# ---------------------------------------------------------------------------

_RESET = "\033[0m"
_BOLD = "\033[1m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_BLUE = "\033[34m"
_MAGENTA = "\033[35m"
_CYAN = "\033[36m"
_DIM = "\033[2m"


def _red(text: str) -> str:
    return f"{_RED}{text}{_RESET}"


def _green(text: str) -> str:
    return f"{_GREEN}{text}{_RESET}"


def _yellow(text: str) -> str:
    return f"{_YELLOW}{text}{_RESET}"


def _cyan(text: str) -> str:
    return f"{_CYAN}{text}{_RESET}"


def _bold(text: str) -> str:
    return f"{_BOLD}{text}{_RESET}"


def _dim(text: str) -> str:
    return f"{_DIM}{text}{_RESET}"


def _header(command: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"{_bold(_cyan(f'[{command}]'))} {_dim(now)}"


def _print_header(command: str) -> None:
    print(_header(command))


def _print_error(message: str) -> None:
    print(_red(f"Error: {message}"), file=sys.stderr)


def _print_success(message: str) -> None:
    print(_green(message))


def _print_warning(message: str) -> None:
    print(_yellow(f"Warning: {message}"))


def _print_info(message: str) -> None:
    print(_cyan(message))


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, default=str))


def _print_sse_event(event_data: dict[str, Any]) -> None:
    event_type = event_data.get("type", "message")
    content = event_data.get("content", event_data.get("data", ""))
    if isinstance(content, dict):
        content = json.dumps(content, default=str)
    if event_type == "token" or event_type == "delta":
        sys.stdout.write(str(content))
        sys.stdout.flush()
    elif event_type == "error":
        sys.stdout.write(_red(str(content)))
        sys.stdout.flush()
    elif event_type == "done":
        sys.stdout.write("\n")
        sys.stdout.flush()
    else:
        print(content)


# ---------------------------------------------------------------------------
# SSE stream parser
# ---------------------------------------------------------------------------


def _parse_sse_lines(raw: str) -> Generator[dict[str, Any], None, None]:
    """Parse raw SSE text into event dictionaries."""
    for block in raw.split("\n\n"):
        if not block.strip():
            continue
        event: dict[str, Any] = {}
        data_lines: list[str] = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event["type"] = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:") :].strip())
            elif line.startswith("id:"):
                event["id"] = line[len("id:") :].strip()
        if data_lines:
            raw_data = "\n".join(data_lines)
            try:
                event["data"] = json.loads(raw_data)
            except json.JSONDecodeError:
                event["data"] = raw_data
        if event:
            yield event


def _consume_sse_response(response: httpx.Response) -> Any:
    """Consume an SSE streaming response and print/return results."""
    accumulated: list[str] = []
    event_count = 0
    for line in response.iter_lines():
        if not line:
            continue
        if line.startswith("data:"):
            payload_str = line[len("data:") :].strip()
            if payload_str == "[DONE]":
                print()
                break
            try:
                payload = json.loads(payload_str)
            except json.JSONDecodeError:
                print(payload_str)
                accumulated.append(payload_str)
                continue
            event_count += 1
            event_type = payload.get("type", "message")
            content = payload.get("content", payload.get("data", payload.get("text", "")))
            if isinstance(content, dict):
                content = json.dumps(content, default=str)
            if event_type in ("token", "delta", "text"):
                sys.stdout.write(str(content))
                sys.stdout.flush()
                accumulated.append(str(content))
            elif event_type == "error":
                sys.stdout.write(_red(str(content)))
                sys.stdout.flush()
            elif event_type == "done":
                print()
            else:
                print(content)
                accumulated.append(str(content))
    if event_count == 0:
        try:
            return response.json()
        except Exception:
            text = response.text.strip()
            if text:
                print(text)
            return text
    full_text = "".join(accumulated)
    try:
        return json.loads(full_text)
    except (json.JSONDecodeError, ValueError):
        return full_text


# ---------------------------------------------------------------------------
# DeveloperCommands class
# ---------------------------------------------------------------------------


class DeveloperCommands:
    """CLI commands for the NovaForge /devtools backend API."""

    def __init__(self, base_url: str, api_key: Optional[str] = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client_kwargs: dict[str, Any] = {
            "timeout": httpx.Timeout(30.0, connect=10.0),
        }
        if self.api_key:
            self._client_kwargs["headers"] = {"Authorization": f"Bearer {self.api_key}"}

    # -- helpers --------------------------------------------------------------

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _headers(self, extra: Optional[dict[str, str]] = None) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        if extra:
            h.update(extra)
        return h

    def _log_verbose(self, message: str, verbose: bool) -> None:
        if verbose:
            print(_dim(f"[verbose] {message}"), file=sys.stderr)

    # -- API methods ----------------------------------------------------------

    async def chat(
        self,
        message: str,
        session_id: Optional[str] = None,
        repo_id: Optional[str] = None,
        stream: bool = False,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Chat with AI assistant."""
        _print_header("chat")
        self._log_verbose(f"message={message!r} session={session_id} repo={repo_id} stream={stream}", verbose)

        payload: dict[str, Any] = {"message": message}
        if session_id:
            payload["session_id"] = session_id
        if repo_id:
            payload["repo_id"] = repo_id
        if stream:
            payload["stream"] = True

        path = "/chat" if not session_id else "/devtools/chat"
        self._log_verbose(f"POST {path}", verbose)

        try:
            async with httpx.AsyncClient(**self._client_kwargs) as client:
                if stream:
                    response = await client.post(
                        self._url(path),
                        json=payload,
                        headers=self._headers(),
                        timeout=httpx.Timeout(120.0, connect=10.0),
                    )
                    response.raise_for_status()
                    result = _consume_sse_response(response)
                    if as_json:
                        _print_json(result)
                    return result
                else:
                    response = await client.post(
                        self._url(path),
                        json=payload,
                        headers=self._headers(),
                    )
                    response.raise_for_status()
                    data = response.json()
                    if as_json:
                        _print_json(data)
                    else:
                        content = data.get("content", data.get("response", data.get("message", data)))
                        if isinstance(content, dict):
                            _print_json(content)
                        else:
                            print(content)
                    return data
        except httpx.HTTPStatusError as exc:
            _print_error(f"HTTP {exc.response.status_code}: {exc.response.text}")
            return None
        except httpx.ConnectError:
            _print_error(f"Cannot connect to server at {self.base_url}")
            return None
        except Exception as exc:
            _print_error(str(exc))
            return None

    async def agent(
        self,
        agent_name: str,
        task: str,
        session_id: Optional[str] = None,
        stream: bool = False,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Run an agent with a given task."""
        _print_header(f"agent/{agent_name}")
        self._log_verbose(f"agent={agent_name} task={task!r} session={session_id} stream={stream}", verbose)

        payload: dict[str, Any] = {"agent_name": agent_name, "task": task}
        if session_id:
            payload["session_id"] = session_id
        if stream:
            payload["stream"] = True

        path = "/devtools/agents/run"
        self._log_verbose(f"POST {path}", verbose)

        try:
            async with httpx.AsyncClient(**self._client_kwargs) as client:
                if stream:
                    response = await client.post(
                        self._url(path),
                        json=payload,
                        headers=self._headers(),
                        timeout=httpx.Timeout(120.0, connect=10.0),
                    )
                    response.raise_for_status()
                    result = _consume_sse_response(response)
                    if as_json:
                        _print_json(result)
                    return result
                else:
                    response = await client.post(
                        self._url(path),
                        json=payload,
                        headers=self._headers(),
                    )
                    response.raise_for_status()
                    data = response.json()
                    if as_json:
                        _print_json(data)
                    else:
                        result_content = data.get("result", data.get("content", data.get("output", data)))
                        if isinstance(result_content, dict):
                            _print_json(result_content)
                        else:
                            print(result_content)
                    return data
        except httpx.HTTPStatusError as exc:
            _print_error(f"HTTP {exc.response.status_code}: {exc.response.text}")
            return None
        except httpx.ConnectError:
            _print_error(f"Cannot connect to server at {self.base_url}")
            return None
        except Exception as exc:
            _print_error(str(exc))
            return None

    async def review(
        self,
        file_path: Optional[str] = None,
        code: Optional[str] = None,
        review_type: str = "standard",
        session_id: Optional[str] = None,
        stream: bool = False,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Perform a code review."""
        _print_header("review")
        self._log_verbose(
            f"file={file_path} type={review_type} stream={stream} session={session_id}",
            verbose,
        )

        payload: dict[str, Any] = {"review_type": review_type}
        if file_path:
            payload["file_path"] = file_path
        if code:
            payload["code"] = code
        if session_id:
            payload["session_id"] = session_id
        if stream:
            payload["stream"] = True

        path = "/devtools/review"
        self._log_verbose(f"POST {path}", verbose)

        try:
            async with httpx.AsyncClient(**self._client_kwargs) as client:
                if stream:
                    response = await client.post(
                        self._url(path),
                        json=payload,
                        headers=self._headers(),
                        timeout=httpx.Timeout(120.0, connect=10.0),
                    )
                    response.raise_for_status()
                    result = _consume_sse_response(response)
                    if as_json:
                        _print_json(result)
                    return result
                else:
                    response = await client.post(
                        self._url(path),
                        json=payload,
                        headers=self._headers(),
                    )
                    response.raise_for_status()
                    data = response.json()
                    if as_json:
                        _print_json(data)
                    else:
                        self._print_review_result(data)
                    return data
        except httpx.HTTPStatusError as exc:
            _print_error(f"HTTP {exc.response.status_code}: {exc.response.text}")
            return None
        except httpx.ConnectError:
            _print_error(f"Cannot connect to server at {self.base_url}")
            return None
        except Exception as exc:
            _print_error(str(exc))
            return None

    @staticmethod
    def _print_review_result(data: dict[str, Any]) -> None:
        summary = data.get("summary", "")
        issues = data.get("issues", data.get("findings", []))
        score = data.get("score", data.get("rating", None))

        if score is not None:
            print(f"\n{_bold('Score:')} {score}")

        if summary:
            print(f"\n{_bold('Summary:')}\n{summary}\n")

        if issues and isinstance(issues, list):
            print(f"{_bold('Issues found:')}\n")
            for i, issue in enumerate(issues, 1):
                if isinstance(issue, dict):
                    severity = issue.get("severity", "info")
                    message = issue.get("message", issue.get("description", str(issue)))
                    location = issue.get("location", issue.get("file", ""))
                    line = issue.get("line", issue.get("line_number", ""))

                    color_fn = _dim
                    if severity in ("high", "critical", "error"):
                        color_fn = _red
                    elif severity in ("medium", "warning"):
                        color_fn = _yellow
                    elif severity in ("low", "info"):
                        color_fn = _cyan

                    loc = f" @ {location}:{line}" if location else ""
                    print(f"  {color_fn(f'{i}. [{severity.upper()}]')}{loc}")
                    print(f"     {message}\n")
                else:
                    print(f"  {i}. {issue}\n")
        elif not summary:
            _print_success("No issues found.")

    async def security(
        self,
        file_path: str,
        code: str,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Run a security review on code."""
        _print_header("security-review")
        self._log_verbose(f"file={file_path}", verbose)

        payload: dict[str, Any] = {
            "action": "security_review",
            "file_path": file_path,
            "code": code,
        }
        path = "/devtools/code-actions"
        self._log_verbose(f"POST {path}", verbose)

        try:
            async with httpx.AsyncClient(**self._client_kwargs) as client:
                response = await client.post(
                    self._url(path),
                    json=payload,
                    headers=self._headers(),
                    timeout=httpx.Timeout(60.0, connect=10.0),
                )
                response.raise_for_status()
                data = response.json()
                if as_json:
                    _print_json(data)
                else:
                    result = data.get("result", data.get("content", data))
                    if isinstance(result, dict):
                        _print_json(result)
                    else:
                        print(result)
                return data
        except httpx.HTTPStatusError as exc:
            _print_error(f"HTTP {exc.response.status_code}: {exc.response.text}")
            return None
        except httpx.ConnectError:
            _print_error(f"Cannot connect to server at {self.base_url}")
            return None
        except Exception as exc:
            _print_error(str(exc))
            return None

    async def test_gen(
        self,
        file_path: str,
        code: str,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Generate tests for code."""
        _print_header("test-gen")
        self._log_verbose(f"file={file_path}", verbose)

        payload: dict[str, Any] = {
            "action": "generate_tests",
            "file_path": file_path,
            "code": code,
        }
        path = "/devtools/code-actions"
        self._log_verbose(f"POST {path}", verbose)

        try:
            async with httpx.AsyncClient(**self._client_kwargs) as client:
                response = await client.post(
                    self._url(path),
                    json=payload,
                    headers=self._headers(),
                    timeout=httpx.Timeout(60.0, connect=10.0),
                )
                response.raise_for_status()
                data = response.json()
                if as_json:
                    _print_json(data)
                else:
                    result = data.get("result", data.get("content", data))
                    if isinstance(result, dict):
                        _print_json(result)
                    else:
                        print(result)
                return data
        except httpx.HTTPStatusError as exc:
            _print_error(f"HTTP {exc.response.status_code}: {exc.response.text}")
            return None
        except httpx.ConnectError:
            _print_error(f"Cannot connect to server at {self.base_url}")
            return None
        except Exception as exc:
            _print_error(str(exc))
            return None

    async def explain(
        self,
        file_path: str,
        code: str,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Explain code."""
        _print_header("explain")
        self._log_verbose(f"file={file_path}", verbose)

        payload: dict[str, Any] = {
            "action": "explain",
            "file_path": file_path,
            "code": code,
        }
        path = "/devtools/code-actions"
        self._log_verbose(f"POST {path}", verbose)

        try:
            async with httpx.AsyncClient(**self._client_kwargs) as client:
                response = await client.post(
                    self._url(path),
                    json=payload,
                    headers=self._headers(),
                    timeout=httpx.Timeout(60.0, connect=10.0),
                )
                response.raise_for_status()
                data = response.json()
                if as_json:
                    _print_json(data)
                else:
                    result = data.get("result", data.get("content", data))
                    if isinstance(result, dict):
                        _print_json(result)
                    else:
                        print(result)
                return data
        except httpx.HTTPStatusError as exc:
            _print_error(f"HTTP {exc.response.status_code}: {exc.response.text}")
            return None
        except httpx.ConnectError:
            _print_error(f"Cannot connect to server at {self.base_url}")
            return None
        except Exception as exc:
            _print_error(str(exc))
            return None

    async def fix(
        self,
        file_path: str,
        code: str,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Fix code issues."""
        _print_header("fix")
        self._log_verbose(f"file={file_path}", verbose)

        payload: dict[str, Any] = {
            "action": "fix",
            "file_path": file_path,
            "code": code,
        }
        path = "/devtools/code-actions"
        self._log_verbose(f"POST {path}", verbose)

        try:
            async with httpx.AsyncClient(**self._client_kwargs) as client:
                response = await client.post(
                    self._url(path),
                    json=payload,
                    headers=self._headers(),
                    timeout=httpx.Timeout(60.0, connect=10.0),
                )
                response.raise_for_status()
                data = response.json()
                if as_json:
                    _print_json(data)
                else:
                    result = data.get("result", data.get("content", data))
                    if isinstance(result, dict):
                        _print_json(result)
                    else:
                        print(result)
                return data
        except httpx.HTTPStatusError as exc:
            _print_error(f"HTTP {exc.response.status_code}: {exc.response.text}")
            return None
        except httpx.ConnectError:
            _print_error(f"Cannot connect to server at {self.base_url}")
            return None
        except Exception as exc:
            _print_error(str(exc))
            return None

    async def search(
        self,
        query: str,
        search_type: str = "semantic",
        repo_id: Optional[str] = None,
        limit: int = 10,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Search repository content."""
        _print_header("search")
        self._log_verbose(f"query={query!r} type={search_type} limit={limit}", verbose)

        payload: dict[str, Any] = {
            "query": query,
            "search_type": search_type,
            "limit": limit,
        }
        if repo_id:
            payload["repo_id"] = repo_id

        path = "/devtools/search"
        self._log_verbose(f"POST {path}", verbose)

        try:
            async with httpx.AsyncClient(**self._client_kwargs) as client:
                response = await client.post(
                    self._url(path),
                    json=payload,
                    headers=self._headers(),
                )
                response.raise_for_status()
                data = response.json()
                if as_json:
                    _print_json(data)
                else:
                    self._print_search_results(data)
                return data
        except httpx.HTTPStatusError as exc:
            _print_error(f"HTTP {exc.response.status_code}: {exc.response.text}")
            return None
        except httpx.ConnectError:
            _print_error(f"Cannot connect to server at {self.base_url}")
            return None
        except Exception as exc:
            _print_error(str(exc))
            return None

    @staticmethod
    def _print_search_results(data: dict[str, Any]) -> None:
        results = data.get("results", data.get("matches", []))
        total = data.get("total", len(results))
        print(f"\n{_bold(f'Results ({total})')}\n")

        if not results:
            _print_info("No results found.")
            return

        for i, result in enumerate(results, 1):
            if isinstance(result, dict):
                title = result.get("title", result.get("file_path", result.get("path", f"Result {i}")))
                score = result.get("score", result.get("relevance", None))
                content = result.get("content", result.get("text", result.get("snippet", "")))
                line_num = result.get("line", result.get("line_number", ""))

                score_str = f" {_dim(f'({score:.2f})')}" if score is not None else ""
                line_str = f":{line_num}" if line_num else ""
                print(f"  {_bold(f'{i}.')}{_cyan(str(title))}{line_str}{score_str}")
                if content:
                    snippet = content.strip()
                    if len(snippet) > 200:
                        snippet = snippet[:200] + "..."
                    wrapped = textwrap.indent(snippet, "     ")
                    print(f"{_dim(wrapped)}")
                print()
            else:
                print(f"  {i}. {result}\n")

    async def workflow(
        self,
        workflow_id: str,
        inputs: Optional[dict[str, Any]] = None,
        stream: bool = False,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Run a workflow."""
        _print_header(f"workflow/{workflow_id}")
        self._log_verbose(f"workflow={workflow_id} stream={stream}", verbose)

        payload: dict[str, Any] = {"workflow_id": workflow_id}
        if inputs:
            payload["inputs"] = inputs
        if stream:
            payload["stream"] = True

        path = "/devtools/workflows/run"
        self._log_verbose(f"POST {path}", verbose)

        try:
            async with httpx.AsyncClient(**self._client_kwargs) as client:
                if stream:
                    response = await client.post(
                        self._url(path),
                        json=payload,
                        headers=self._headers(),
                        timeout=httpx.Timeout(120.0, connect=10.0),
                    )
                    response.raise_for_status()
                    result = _consume_sse_response(response)
                    if as_json:
                        _print_json(result)
                    return result
                else:
                    response = await client.post(
                        self._url(path),
                        json=payload,
                        headers=self._headers(),
                    )
                    response.raise_for_status()
                    data = response.json()
                    if as_json:
                        _print_json(data)
                    else:
                        status = data.get("status", "completed")
                        output = data.get("output", data.get("result", data))
                        if status == "completed":
                            _print_success(f"Workflow {workflow_id} completed.")
                        else:
                            _print_info(f"Workflow {workflow_id} status: {status}")
                        if isinstance(output, dict):
                            _print_json(output)
                        elif output:
                            print(output)
                    return data
        except httpx.HTTPStatusError as exc:
            _print_error(f"HTTP {exc.response.status_code}: {exc.response.text}")
            return None
        except httpx.ConnectError:
            _print_error(f"Cannot connect to server at {self.base_url}")
            return None
        except Exception as exc:
            _print_error(str(exc))
            return None

    async def status(
        self,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Get server status."""
        _print_header("status")
        path = "/auth/status"
        self._log_verbose(f"GET {path}", verbose)

        try:
            async with httpx.AsyncClient(**self._client_kwargs) as client:
                response = await client.get(
                    self._url(path),
                    headers=self._headers(),
                )
                response.raise_for_status()
                data = response.json()
                if as_json:
                    _print_json(data)
                else:
                    server_status = data.get("status", "unknown")
                    color_fn = _green if server_status == "ok" else _yellow
                    print(f"\n  {_bold('Server:')} {color_fn(server_status)}")
                    for key in ("version", "uptime", "environment", "region"):
                        if key in data:
                            print(f"  {_bold(f'{key.title()}:')} {data[key]}")
                    print()
                return data
        except httpx.HTTPStatusError as exc:
            _print_error(f"HTTP {exc.response.status_code}: {exc.response.text}")
            return None
        except httpx.ConnectError:
            _print_error(f"Cannot connect to server at {self.base_url}")
            return None
        except Exception as exc:
            _print_error(str(exc))
            return None

    async def login(
        self,
        email: str,
        password: str,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Login via token exchange."""
        _print_header("login")
        self._log_verbose(f"email={email}", verbose)

        payload: dict[str, Any] = {"email": email, "password": password}
        path = "/auth/token-exchange"
        self._log_verbose(f"POST {path}", verbose)

        try:
            async with httpx.AsyncClient(**self._client_kwargs) as client:
                response = await client.post(
                    self._url(path),
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                data = response.json()
                if as_json:
                    _print_json(data)
                else:
                    token = data.get("access_token", data.get("token", ""))
                    user = data.get("user", data.get("email", ""))
                    if token:
                        _print_success("Login successful.")
                        if user:
                            print(f"  {_bold('User:')} {user}")
                        print(f"  {_bold('Token:')} {token[:16]}...{_dim('(truncated)')}")
                        print(f"\n  {_dim('Set your API key with: export NOVAFORGE_API_KEY=<token>')}")
                    else:
                        _print_info("Login response:")
                        _print_json(data)
                return data
        except httpx.HTTPStatusError as exc:
            _print_error(f"HTTP {exc.response.status_code}: {exc.response.text}")
            return None
        except httpx.ConnectError:
            _print_error(f"Cannot connect to server at {self.base_url}")
            return None
        except Exception as exc:
            _print_error(str(exc))
            return None

    async def create_session(
        self,
        client_type: str = "cli",
        org_id: Optional[str] = None,
        repo_id: Optional[str] = None,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Create a devtools session."""
        _print_header("session")
        self._log_verbose(f"client={client_type} org={org_id} repo={repo_id}", verbose)

        payload: dict[str, Any] = {"client_type": client_type}
        if org_id:
            payload["org_id"] = org_id
        if repo_id:
            payload["repo_id"] = repo_id

        path = "/devtools/sessions"
        self._log_verbose(f"POST {path}", verbose)

        try:
            async with httpx.AsyncClient(**self._client_kwargs) as client:
                response = await client.post(
                    self._url(path),
                    json=payload,
                    headers=self._headers(),
                )
                response.raise_for_status()
                data = response.json()
                if as_json:
                    _print_json(data)
                else:
                    session_id = data.get("session_id", data.get("id", "unknown"))
                    _print_success(f"Session created: {session_id}")
                    for key in ("org_id", "repo_id", "client_type", "created_at"):
                        if key in data:
                            print(f"  {_bold(f'{key}:')} {data[key]}")
                    print()
                return data
        except httpx.HTTPStatusError as exc:
            _print_error(f"HTTP {exc.response.status_code}: {exc.response.text}")
            return None
        except httpx.ConnectError:
            _print_error(f"Cannot connect to server at {self.base_url}")
            return None
        except Exception as exc:
            _print_error(str(exc))
            return None

    async def whoami(
        self,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Show current authenticated user."""
        _print_header("whoami")

        try:
            async with httpx.AsyncClient(**self._client_kwargs) as client:
                response = await client.get(
                    self._url("/auth/me"),
                    headers=self._headers(),
                )
                response.raise_for_status()
                data = response.json()
                if as_json:
                    _print_json(data)
                else:
                    name = data.get("name", data.get("display_name", "unknown"))
                    email = data.get("email", "unknown")
                    user_id = data.get("id", data.get("user_id", ""))
                    print(f"\n  {_bold('Name:')}  {name}")
                    print(f"  {_bold('Email:')} {email}")
                    if user_id:
                        print(f"  {_bold('ID:')}    {user_id}")
                    for key in ("org", "org_id", "role", "teams"):
                        if key in data:
                            print(f"  {_bold(f'{key.title()}:')} {data[key]}")
                    print()
                return data
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401:
                _print_error("Not authenticated. Run: python -m app.cli.developer_commands login <email> <password>")
            else:
                _print_error(f"HTTP {exc.response.status_code}: {exc.response.text}")
            return None
        except httpx.ConnectError:
            _print_error(f"Cannot connect to server at {self.base_url}")
            return None
        except Exception as exc:
            _print_error(str(exc))
            return None


# ---------------------------------------------------------------------------
# CLI argument parser & dispatcher
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="developer_commands",
        description="NovaForge Developer Tools CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Backend server URL (default: NOVAFORGE_BASE_URL env var)",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="API key for authentication (default: NOVAFORGE_API_KEY env var)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose/debug output",
    )

    sub = parser.add_subparsers(dest="command", help="Available commands")

    # -- chat ---------------------------------------------------------------
    p_chat = sub.add_parser("chat", help="Chat with AI assistant")
    p_chat.add_argument("message", help="Message to send")
    p_chat.add_argument("--session-id", default=None, help="Session ID")
    p_chat.add_argument("--repo-id", default=None, help="Repository ID")
    p_chat.add_argument("--stream", action="store_true", help="Stream response")

    # -- agent --------------------------------------------------------------
    p_agent = sub.add_parser("agent", help="Run an agent")
    p_agent.add_argument("agent_name", help="Name of the agent to run")
    p_agent.add_argument("task", help="Task description for the agent")
    p_agent.add_argument("--session-id", default=None, help="Session ID")
    p_agent.add_argument("--stream", action="store_true", help="Stream response")

    # -- review -------------------------------------------------------------
    p_review = sub.add_parser("review", help="Code review")
    p_review.add_argument("--file", default=None, dest="file_path", help="File to review")
    p_review.add_argument("--code", default=None, help="Code snippet to review")
    p_review.add_argument(
        "--type",
        dest="review_type",
        choices=["standard", "security", "architecture", "performance"],
        default="standard",
        help="Review type",
    )
    p_review.add_argument("--session-id", default=None, help="Session ID")
    p_review.add_argument("--stream", action="store_true", help="Stream response")

    # -- security -----------------------------------------------------------
    p_security = sub.add_parser("security", help="Security review")
    p_security.add_argument("file_path", help="File path")
    p_security.add_argument("code", help="Code to review")

    # -- test-gen -----------------------------------------------------------
    p_test = sub.add_parser("test-gen", help="Generate tests")
    p_test.add_argument("file_path", help="File path")
    p_test.add_argument("code", help="Code to generate tests for")

    # -- explain ------------------------------------------------------------
    p_explain = sub.add_parser("explain", help="Explain code")
    p_explain.add_argument("file_path", help="File path")
    p_explain.add_argument("code", help="Code to explain")

    # -- fix ----------------------------------------------------------------
    p_fix = sub.add_parser("fix", help="Fix code issues")
    p_fix.add_argument("file_path", help="File path")
    p_fix.add_argument("code", help="Code to fix")

    # -- search -------------------------------------------------------------
    p_search = sub.add_parser("search", help="Search repository")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument(
        "--type",
        dest="search_type",
        choices=["semantic", "symbol", "file", "repository"],
        default="semantic",
        help="Search type",
    )
    p_search.add_argument("--repo-id", default=None, help="Repository ID")
    p_search.add_argument("--limit", type=int, default=10, help="Max results")

    # -- workflow -----------------------------------------------------------
    p_workflow = sub.add_parser("workflow", help="Run a workflow")
    p_workflow.add_argument("workflow_id", help="Workflow ID")
    p_workflow.add_argument("--inputs", default=None, help="JSON inputs")
    p_workflow.add_argument("--stream", action="store_true", help="Stream response")

    # -- status -------------------------------------------------------------
    sub.add_parser("status", help="Check server status")

    # -- login --------------------------------------------------------------
    p_login = sub.add_parser("login", help="Login to server")
    p_login.add_argument("email", help="Email address")
    p_login.add_argument("password", help="Password")

    # -- session ------------------------------------------------------------
    p_session = sub.add_parser("session", help="Create a devtools session")
    p_session.add_argument(
        "--client-type",
        choices=["vscode", "jetbrains", "cli"],
        default="cli",
        help="Client type",
    )
    p_session.add_argument("--org-id", default=None, help="Organization ID")
    p_session.add_argument("--repo-id", default=None, help="Repository ID")

    # -- whoami -------------------------------------------------------------
    sub.add_parser("whoami", help="Show current user")

    return parser


def _resolve_base_url(provided: Optional[str]) -> str:
    import os

    url = provided or os.environ.get("NOVAFORGE_BASE_URL") or os.environ.get("BACKEND_URL")
    if not url:
        _print_error(
            "No server URL provided. Set --base-url or NOVAFORGE_BASE_URL environment variable."
        )
        sys.exit(1)
    return url


def _resolve_api_key(provided: Optional[str]) -> Optional[str]:
    import os

    return provided or os.environ.get("NOVAFORGE_API_KEY")


async def _dispatch(args: argparse.Namespace) -> Any:
    base_url = _resolve_base_url(args.base_url)
    api_key = _resolve_api_key(args.api_key)

    if args.verbose:
        _print_info(f"Server: {base_url}")
        _print_info(f"Command: {args.command}")

    cmds = DeveloperCommands(base_url=base_url, api_key=api_key)

    if args.command == "chat":
        return await cmds.chat(
            message=args.message,
            session_id=args.session_id,
            repo_id=args.repo_id,
            stream=args.stream,
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "agent":
        return await cmds.agent(
            agent_name=args.agent_name,
            task=args.task,
            session_id=args.session_id,
            stream=args.stream,
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "review":
        return await cmds.review(
            file_path=args.file_path,
            code=args.code,
            review_type=args.review_type,
            session_id=args.session_id,
            stream=args.stream,
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "security":
        return await cmds.security(
            file_path=args.file_path,
            code=args.code,
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "test-gen":
        return await cmds.test_gen(
            file_path=args.file_path,
            code=args.code,
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "explain":
        return await cmds.explain(
            file_path=args.file_path,
            code=args.code,
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "fix":
        return await cmds.fix(
            file_path=args.file_path,
            code=args.code,
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "search":
        return await cmds.search(
            query=args.query,
            search_type=args.search_type,
            repo_id=args.repo_id,
            limit=args.limit,
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "workflow":
        inputs = None
        if args.inputs:
            try:
                inputs = json.loads(args.inputs)
            except json.JSONDecodeError as exc:
                _print_error(f"Invalid JSON for --inputs: {exc}")
                return None
        return await cmds.workflow(
            workflow_id=args.workflow_id,
            inputs=inputs,
            stream=args.stream,
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "status":
        return await cmds.status(
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "login":
        return await cmds.login(
            email=args.email,
            password=args.password,
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "session":
        return await cmds.create_session(
            client_type=args.client_type,
            org_id=args.org_id,
            repo_id=args.repo_id,
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "whoami":
        return await cmds.whoami(
            verbose=args.verbose,
            as_json=args.as_json,
        )

    _print_error(f"Unknown command: {args.command}")
    return None


def cli_main(args: Optional[list[str]] = None) -> None:
    """Parse CLI arguments and dispatch to the appropriate command method.

    Args:
        args: Command-line arguments. Defaults to sys.argv[1:].
    """
    parser = _build_parser()
    namespace = parser.parse_args(args)

    if not namespace.command:
        parser.print_help()
        sys.exit(1)

    try:
        import asyncio

        result = asyncio.run(_dispatch(namespace))
        if result is None:
            sys.exit(1)
    except KeyboardInterrupt:
        print(f"\n{_yellow('Interrupted.')}")
        sys.exit(130)


# ---------------------------------------------------------------------------
# Entry point for `python -m app.cli.developer_commands`
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cli_main()
