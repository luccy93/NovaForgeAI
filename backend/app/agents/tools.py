"""Tool system — executable capabilities for agents."""

import asyncio
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from app.agents.schemas import ToolResult


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, str]
    required_permissions: list[str] = field(default_factory=lambda: ["read"])
    func: Optional[Callable] = None


@dataclass
class ToolCall:
    name: str
    params: dict[str, Any]


class ToolRegistry:
    """Registry of all tools available to agents."""

    def __init__(self):
        self._tools: dict[str, ToolSpec] = {}
        self._register_core_tools()

    def _register_core_tools(self):
        tools = [
            ToolSpec("search_code", "Search repository code by pattern", {"pattern": "string", "path": "string?"}, ["read"], self._search_code),
            ToolSpec("read_file", "Read file contents", {"path": "string", "max_lines": "int?"}, ["read"], self._read_file),
            ToolSpec("list_files", "List files in a directory", {"path": "string", "pattern": "string?"}, ["read"], self._list_files),
            ToolSpec("dependency_graph", "Get dependency graph for a file", {"path": "string"}, ["read"], self._dependency_graph),
            ToolSpec("git_history", "Get git log for a file", {"path": "string", "max_count": "int?"}, ["read"], self._git_history),
            ToolSpec("run_terminal", "Execute a terminal command", {"command": "string", "timeout": "int?"}, ["write"], self._run_terminal),
            ToolSpec("query_database", "Execute a read-only database query", {"query": "string", "params": "dict?"}, ["read"], self._query_database),
            ToolSpec("github_api", "Call GitHub API", {"endpoint": "string", "method": "string?", "data": "dict?"}, ["read"], self._github_api),
            ToolSpec("web_search", "Search the web for information", {"query": "string", "max_results": "int?"}, ["read"], self._web_search),
            ToolSpec("doc_search", "Search project documentation", {"query": "string"}, ["read"], self._doc_search),
            ToolSpec("list_directory", "List top-level directory contents", {"path": "string?"}, ["read"], self._list_directory),
            ToolSpec("file_stat", "Get file metadata", {"path": "string"}, ["read"], self._file_stat),
        ]
        for t in tools:
            self.register(t)

    def register(self, tool: ToolSpec):
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[ToolSpec]:
        return self._tools.get(name)

    def describe(self, permissions: list[str]) -> str:
        lines = []
        for name, spec in self._tools.items():
            if not any(p in permissions for p in spec.required_permissions) and "*" not in permissions:
                continue
            params = ", ".join(f"{k}: {v}" for k, v in spec.parameters.items())
            lines.append(f"- {name}({params}): {spec.description}")
        return "\n".join(lines)

    def parse_calls(self, output: str) -> list[ToolCall]:
        calls = []
        for line in output.split("\n"):
            line = line.strip()
            if line.startswith("TOOL_CALL:") or line.startswith("!tool "):
                content = line.removeprefix("TOOL_CALL:").removeprefix("!tool ").strip()
                parts = content.split("(", 1)
                if len(parts) == 2:
                    name = parts[0].strip()
                    param_str = parts[1].rstrip(")")
                    params = {}
                    for p in param_str.split(","):
                        if "=" in p:
                            k, v = p.split("=", 1)
                            params[k.strip()] = v.strip().strip('"').strip("'")
                    calls.append(ToolCall(name=name, params=params))
        return calls

    async def execute(self, name: str, **params) -> ToolResult:
        spec = self._tools.get(name)
        if not spec:
            return ToolResult(success=False, output="", error=f"Unknown tool: {name}")
        if not spec.func:
            return ToolResult(success=False, output="", error=f"Tool {name} has no implementation")
        start = time.monotonic()
        try:
            result = await spec.func(**params)
            duration = int((time.monotonic() - start) * 1000)
            return ToolResult(success=True, output=str(result), duration_ms=duration, data=result)
        except Exception as e:
            duration = int((time.monotonic() - start) * 1000)
            return ToolResult(success=False, output="", error=str(e), duration_ms=duration)

    async def _search_code(self, pattern: str, path: Optional[str] = None) -> list[dict]:
        import subprocess
        search_path = path or "."
        cmd = ["rg", "--json", pattern, search_path]
        try:
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, _ = await proc.communicate()
            results = []
            for line in stdout.decode().strip().split("\n"):
                if line:
                    import json
                    results.append(json.loads(line))
            return results[:50]
        except Exception:
            return [{"error": "rg not available or search failed"}]

    async def _read_file(self, path: str, max_lines: Optional[int] = None) -> str:
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if max_lines:
                lines = lines[:max_lines]
            return "".join(lines)
        except Exception as e:
            return f"Error reading {path}: {e}"

    async def _list_files(self, path: str, pattern: Optional[str] = None) -> list[str]:
        import glob as glob_mod
        search = f"{path}/**/{pattern or '*'}"
        return glob_mod.glob(search, recursive=True)[:200]

    async def _dependency_graph(self, path: str) -> dict:
        ext = os.path.splitext(path)[1]
        if ext in (".py",):
            import ast
            try:
                with open(path) as f:
                    tree = ast.parse(f.read())
                imports = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            imports.append(alias.name)
                    elif isinstance(node, ast.ImportFrom):
                        module = node.module or ""
                        for alias in node.names:
                            imports.append(f"{module}.{alias.name}")
                return {"file": path, "imports": imports}
            except Exception as e:
                return {"file": path, "error": str(e)}
        return {"file": path, "note": "Unsupported file type for AST analysis"}

    async def _git_history(self, path: str, max_count: int = 20) -> list[dict]:
        import subprocess
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "log", f"--max-count={max_count}", "--format=%H|%an|%ad|%s", "--", path,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            results = []
            for line in stdout.decode().strip().split("\n"):
                if line:
                    parts = line.split("|", 3)
                    results.append({"commit": parts[0], "author": parts[1], "date": parts[2], "message": parts[3] if len(parts) > 3 else ""})
            return results
        except Exception as e:
            return [{"error": str(e)}]

    async def _run_terminal(self, command: str, timeout: int = 30) -> str:
        import subprocess
        # Terminal execution is deny-by-default: arbitrary shell commands
        # from agent output must be explicitly enabled by the operator.
        if os.environ.get("NOVAFORGE_ENABLE_AGENT_SHELL", "false").lower() != "true":
            return "Error: terminal execution is disabled by platform policy"
        try:
            proc = await asyncio.create_subprocess_shell(
                command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                output = stdout.decode()
                if stderr.decode():
                    output += f"\nSTDERR:\n{stderr.decode()}"
                return output[:5000]
            except asyncio.TimeoutError:
                proc.kill()
                return "Command timed out"
        except Exception as e:
            return f"Error: {e}"

    async def _query_database(self, query: str, params: Optional[dict] = None) -> list[dict]:
        return [{"note": "Database queries are only available in the API context"}]

    async def _github_api(self, endpoint: str, method: str = "GET", data: Optional[dict] = None) -> dict:
        import httpx
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        headers = {"Accept": "application/vnd.github.v3+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        url = f"https://api.github.com{endpoint}" if not endpoint.startswith("http") else endpoint
        try:
            from app.integrations.network_policy import validate_url
            validate_url(url, allowlist=["api.github.com"])
            async with httpx.AsyncClient(timeout=30.0) as client:
                if method.upper() == "GET":
                    resp = await client.get(url, headers=headers)
                elif method.upper() == "POST":
                    resp = await client.post(url, headers=headers, json=data or {})
                else:
                    resp = await client.request(method, url, headers=headers, json=data or {})
                return resp.json()
        except Exception as e:
            return {"error": str(e)}

    async def _web_search(self, query: str, max_results: int = 5) -> list[dict]:
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = []
                for r in ddgs.text(query, max_results=max_results):
                    results.append({"title": r.get("title", ""), "href": r.get("href", ""), "body": r.get("body", "")})
                return results
        except ImportError:
            return [{"note": "Web search requires duckduckgo_search"}]
        except Exception as e:
            return [{"error": str(e)}]

    async def _doc_search(self, query: str) -> list[dict]:
        import glob
        docs = []
        for f in glob.glob("**/*.md", recursive=True) + glob.glob("**/docs/**", recursive=True):
            if os.path.isfile(f):
                docs.append({"file": f, "size": os.path.getsize(f)})
        return docs[:20]

    async def _list_directory(self, path: Optional[str] = None) -> list[str]:
        target = path or "."
        try:
            return os.listdir(target)
        except Exception as e:
            return [f"Error: {e}"]

    async def _file_stat(self, path: str) -> dict:
        try:
            stat = os.stat(path)
            return {
                "path": path, "size": stat.st_size, "mode": stat.st_mode,
                "modified": stat.st_mtime, "is_dir": os.path.isdir(path),
            }
        except Exception as e:
            return {"error": str(e)}
