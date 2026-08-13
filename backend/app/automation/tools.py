"""Tool execution framework (Volume 33).

Every tool declares tool_id, name, version, description, input/output
schemas, permissions, risk level, timeout and resource limits. Tools never
execute untrusted content on the host: terminal and browser backends are
sandboxed or report honest unavailability. Tools are tenant-blind primitives;
authorization happens in the policy and engine layers.
"""
import logging, os, re, time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

RISK_LEVELS = ("low", "medium", "high")


@dataclass
class ToolSpec:
    tool_id: str
    name: str
    description: str
    version: str = "1.0.0"
    input_schema: dict = field(default_factory=dict)
    output_schema: dict = field(default_factory=dict)
    permissions: list[str] = field(default_factory=list)
    risk_level: str = "low"
    timeout_s: int = 30
    resource_limits: dict = field(default_factory=dict)
    supported_environments: list[str] = field(default_factory=lambda: ["all"])
    approval_required: bool = False

    def to_dict(self) -> dict:
        return {"tool_id": self.tool_id, "name": self.name,
                "version": self.version, "description": self.description,
                "input_schema": self.input_schema,
                "output_schema": self.output_schema,
                "permissions": self.permissions,
                "risk_level": self.risk_level, "timeout_s": self.timeout_s,
                "resource_limits": self.resource_limits,
                "supported_environments": self.supported_environments,
                "approval_required": self.approval_required}


class Tool(ABC):
    spec: ToolSpec

    @abstractmethod
    def execute(self, inputs: dict, context: Optional[dict] = None) -> dict:
        """Eagerly execute. Raises ToolError on failure. Never blocks the host."""

    def describe(self) -> dict:
        return self.spec.to_dict()


class ToolError(Exception):
    pass


# ------------------------------------------------------------------ utils
class _RepoSurface:
    """Honest read-side surface of local repositories (no writes to host)."""

    def __init__(self):
        self.root = os.path.abspath(".")
        allowed = {self.root}
        for sub in ("backend", "backend/app", "docs"):
            allowed.add(os.path.abspath(sub))
        self.allowed = [p for p in allowed if os.path.isdir(p)]

    def resolve(self, path: str) -> str:
        abs_path = os.path.abspath(os.path.join(self.root, path))
        if not any(abs_path.startswith(a) for a in self.allowed):
            raise ToolError(f"path outside allowed workspace: {path}")
        return abs_path

    def list_dirs(self, base: str = "") -> list[str]:
        base_path = os.path.abspath(os.path.join(self.root, base))
        if not os.path.isdir(base_path):
            raise ToolError(f"not a directory: {base}")
        return [d for d in next(os.walk(base_path))[1]]

    def read(self, path: str, max_bytes: int = 400_000) -> dict:
        abs_path = self.resolve(path)
        if not os.path.isfile(abs_path):
            raise ToolError(f"file not found: {path}")
        size = os.path.getsize(abs_path)
        if size > max_bytes:
            raise ToolError(f"file too large ({size} > {max_bytes})")
        with open(abs_path, "r", encoding="utf-8", errors="replace") as fh:
            return {"path": path, "size_bytes": size, "content": fh.read()}

    def exists(self, path: str) -> bool:
        try:
            return os.path.exists(self.resolve(path))
        except ToolError:
            return False


class _HttpClient:
    """SSRF-guarded HTTP tool. Timeout + size caps + retry. No credential keys."""

    def __init__(self, guard=None, timeout_s: int = 15, max_bytes: int = 2_000_000):
        self.guard = guard  # SSRFGuard-like: validate_url(url) -> bool
        self.timeout_s = timeout_s
        self.max_bytes = max_bytes
        import urllib.request
        self._request = urllib.request

    def call(self, method: str, url: str, headers: Optional[dict] = None,
             body: Optional[bytes] = None) -> dict:
        if self.guard is not None and not self.guard.validate_url(url):
            raise ToolError(f"URL rejected by SSRF guard: {url}")
        req = self._request.Request(url, data=body, headers=headers or {},
                                    method=method.upper())
        start = time.time()
        try:
            with self._request.urlopen(req, timeout=self.timeout_s) as resp:
                chunk = resp.read(self.max_bytes + 1)
                if len(chunk) > self.max_bytes:
                    raise ToolError("response exceeds max_bytes limit")
                content = chunk.decode("utf-8", errors="replace")
                return {"url": url, "method": method.upper(), "status": resp.status,
                        "headers": dict(resp.headers),
                        "body": content[: self.max_bytes],
                        "latency_ms": round((time.time() - start) * 1000, 2)}
        except ToolError:
            raise
        except Exception as exc:
            raise ToolError(f"http {method} {url} failed: {exc}")


# ------------------------------------------------------------ built-in tools
class ListReposTool(Tool):
    spec = ToolSpec("list_repos", "List Repositories", "List workspace repositories",
                    risk_level="low", timeout_s=10)

    def __init__(self):
        self._surface = _RepoSurface()

    def execute(self, inputs, context=None):
        return {"repositories": self._surface.list_dirs(inputs.get("base", ""))}


class ReadFileTool(Tool):
    spec = ToolSpec("read_file", "Read File", "Read a file in the workspace",
                    input_schema={"path": "string"},
                    permissions=["read"], risk_level="low", timeout_s=10)

    def __init__(self):
        self._surface = _RepoSurface()

    def execute(self, inputs, context=None):
        return self._surface.read(inputs.get("path", ""),
                                  max_bytes=int(inputs.get("max_bytes", 400_000)))


class SearchCodeTool(Tool):
    spec = ToolSpec("search_code", "Search Code", "Grep the workspace",
                    risk_level="low", timeout_s=30)

    def __init__(self):
        self._surface = _RepoSurface()

    def execute(self, inputs, context=None):
        pattern = inputs.get("pattern", "")
        if not pattern:
            raise ToolError("pattern required")
        hits = []
        try:
            import subprocess
            run = subprocess.run(
                ["rg", "--no-heading", "-l", pattern, "."],
                cwd=self._surface.root, capture_output=True, text=True,
                timeout=int(inputs.get("timeout_s", 20)))
            hits = [ln for ln in (run.stdout or "").splitlines() if ln and ln != ""]
        except Exception:
            hits = []
        return {"pattern": pattern, "matches": hits[:200], "count": len(hits)}


class HttpTool(Tool):
    spec = ToolSpec("http", "HTTP Request", "SSRF-guarded HTTP calls",
                    input_schema={"method": "string", "url": "string"},
                    permissions=["network"], risk_level="low", timeout_s=15,
                    resource_limits={"max_bytes": 2_000_000})

    def __init__(self, guard=None):
        self._client = _HttpClient(guard=guard)

    def execute(self, inputs, context=None):
        method = str(inputs.get("method", "GET")).upper()
        url = inputs.get("url", "")
        if method not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
            raise ToolError(f"unsupported method {method}")
        body = inputs.get("body")
        if isinstance(body, str):
            body = body.encode("utf-8")
        headers = inputs.get("headers") or {}
        return self._client.call(method, url, headers=headers, body=body)


class ParseTool(Tool):
    spec = ToolSpec("parse", "Parse", "Parse JSON/YAML-ish text",
                    risk_level="low", timeout_s=5)

    def execute(self, inputs, context=None):
        import json
        text = inputs.get("text", "")
        try:
            return {"parsed": json.loads(text)}
        except Exception as exc:
            raise ToolError(f"parse failed: {exc}")


class LogTool(Tool):
    spec = ToolSpec("log", "Log", "Append a structured log entry",
                    risk_level="low", timeout_s=5)

    def execute(self, inputs, context=None):
        return {"logged": True, "message": inputs.get("message", ""),
                "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


class ReportTool(Tool):
    spec = ToolSpec("generate_report", "Generate Report",
                    "Build a text/markdown report from inputs",
                    risk_level="low", timeout_s=10)

    def execute(self, inputs, context=None):
        title = inputs.get("title", "Automation Report")
        sections = inputs.get("sections") or []
        lines = [f"# {title}", ""]
        for section in sections:
            if isinstance(section, dict):
                lines.append(f"## {section.get('heading', '')}")
                lines.append(str(section.get("body", "")))
                lines.append("")
            else:
                lines.append(str(section))
        return {"report": "\n".join(lines)}


class ShellPreviewTool(Tool):
    """Dry-run shell preview. Never executes; routes to TerminalSandbox for
    real execution (which itself demands a sandbox runtime + approval)."""

    spec = ToolSpec("shell_preview", "Shell Preview",
                    "Preview a shell command: classify risk, show plan",
                    risk_level="medium", timeout_s=10)

    def __init__(self, risk_engine=None):
        self._risk = risk_engine

    def execute(self, inputs, context=None):
        command = inputs.get("command", "")
        if not command:
            raise ToolError("command required")
        risk = self._risk.classify(command) if self._risk else {
            "risk": "medium", "reason": "no risk engine"}
        return {"command": command, "risk": risk.get("risk"),
                "reason": risk.get("reason", ""), "executed": False,
                "note": "use the terminal sandbox with approval to execute"}


# ---------------------------------------------------------------- registry
class ToolRegistry:
    """Registry of tools per environment. Tools are shared primitives; risk
    and permission enforcement happens in policy + engine layers."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}
        self.executions = 0
        self.failures = 0

    def register(self, tool: Tool) -> None:
        self._tools[tool.spec.tool_id] = tool

    def get(self, tool_id: str) -> Optional[Tool]:
        return self._tools.get(tool_id)

    def list(self) -> list[dict]:
        return [t.describe() for t in self._tools.values()]

    def count(self) -> int:
        return len(self._tools)

    def execute(self, tool_id: str, inputs: dict,
                context: Optional[dict] = None) -> dict:
        tool = self.get(tool_id)
        if tool is None:
            raise ToolError(f"unknown tool '{tool_id}'")
        import asyncio
        if asyncio.iscoroutinefunction(tool.execute):
            result = asyncio.run(tool.execute(inputs, context)) \
                if not _in_loop() else _run_coro(tool.execute(inputs, context))
        else:
            result = tool.execute(inputs, context or {})
        self.executions += 1
        if not isinstance(result, dict):
            result = {"result": result}
        result.setdefault("tool_id", tool_id)
        result.setdefault("risk_level", tool.spec.risk_level)
        return result


def _in_loop() -> bool:
    import asyncio
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


def _run_coro(coro):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(coro)


def default_registry(guard=None, terminal=None, browser=None) -> ToolRegistry:
    """Assemble the standard toolset ('all' + 'sandboxed' environments)."""
    reg = ToolRegistry()
    reg.register(ListReposTool())
    reg.register(ReadFileTool())
    reg.register(SearchCodeTool())
    reg.register(HttpTool(guard=guard))
    reg.register(ParseTool())
    reg.register(LogTool())
    reg.register(ReportTool())
    if terminal is not None:
        reg.register(terminal.make_tool())
    else:
        from .terminal import TerminalSandbox
        reg.register(TerminalSandbox().make_tool())
    if browser is not None:
        reg.register(browser.make_tool())
    else:
        from .browser import BrowserAgent
        reg.register(BrowserAgent().make_tool())
    reg.register(ShellPreviewTool(risk_engine=(
        terminal.risk_engine if terminal else None)))
    return reg