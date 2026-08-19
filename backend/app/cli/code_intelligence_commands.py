"""Code Intelligence CLI Extension for NovaForge.

Provides CLI commands that interface with the /code-intelligence backend API,
including indexing, file analysis, symbol search, graph exploration,
code quality, security scanning, impact analysis, and search.

Usage:
    python -m app.cli.code_intelligence_commands <command> [args...]
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from datetime import datetime, timezone
from typing import Any, Optional

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


def _magenta(text: str) -> str:
    return f"{_MAGENTA}{text}{_RESET}"


def _blue(text: str) -> str:
    return f"{_BLUE}{text}{_RESET}"


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


def _severity_color(severity: str) -> Any:
    s = severity.lower()
    if s in ("critical", "high"):
        return _red
    if s in ("medium", "warning", "moderate"):
        return _yellow
    if s in ("low", "info"):
        return _cyan
    return _dim


# ---------------------------------------------------------------------------
# CodeIntelligenceCLICommands class
# ---------------------------------------------------------------------------


class CodeIntelligenceCLICommands:
    """CLI commands for the NovaForge /code-intelligence backend API."""

    def __init__(self, base_url: str, api_key: Optional[str] = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client_kwargs: dict[str, Any] = {
            "timeout": httpx.Timeout(30.0, connect=10.0),
        }
        if self.api_key:
            self._client_kwargs["headers"] = {"Authorization": f"Bearer {self.api_key}"}

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

    async def _get(
        self,
        path: str,
        params: Optional[dict[str, Any]] = None,
        verbose: bool = False,
    ) -> Any:
        self._log_verbose(f"GET {path} params={params}", verbose)
        try:
            async with httpx.AsyncClient(**self._client_kwargs) as client:
                response = await client.get(
                    self._url(path),
                    params=params,
                    headers=self._headers(),
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            _print_error(f"HTTP {exc.response.status_code}: {exc.response.text}")
            return None
        except httpx.ConnectError:
            _print_error(f"Cannot connect to server at {self.base_url}")
            return None
        except Exception as exc:
            _print_error(str(exc))
            return None

    async def _post(
        self,
        path: str,
        data: Optional[dict[str, Any]] = None,
        verbose: bool = False,
    ) -> Any:
        self._log_verbose(f"POST {path} body={data}", verbose)
        try:
            async with httpx.AsyncClient(**self._client_kwargs) as client:
                response = await client.post(
                    self._url(path),
                    json=data or {},
                    headers=self._headers(),
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            _print_error(f"HTTP {exc.response.status_code}: {exc.response.text}")
            return None
        except httpx.ConnectError:
            _print_error(f"Cannot connect to server at {self.base_url}")
            return None
        except Exception as exc:
            _print_error(str(exc))
            return None

    async def _get_and_print(
        self,
        path: str,
        label: str,
        verbose: bool = False,
        as_json: bool = False,
        params: Optional[dict[str, Any]] = None,
    ) -> Any:
        """Generic GET + print helper for simple endpoints."""
        _print_header(label)
        data = await self._get(path, params=params, verbose=verbose)
        if data is None:
            return None
        if as_json:
            _print_json(data)
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    name = item.get("name") or item.get("file_path") or item.get("symbol_name") or item.get("owner_email") or item.get("author_name") or item.get("event_type") or str(item)[:80]
                    _print_info(f"  {name}")
                else:
                    _print_info(f"  {item}")
            _print_info(f"\nTotal: {len(data)}")
        elif isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, (list, dict)):
                    _print_info(f"  {k}: ({type(v).__name__}, {len(v)} items)")
                else:
                    _print_info(f"  {k}: {v}")
        _print_success(f"{label} retrieved successfully")
        return data

    # -- API methods ----------------------------------------------------------

    async def index(
        self,
        repo_id: str,
        commit_sha: Optional[str] = None,
        incremental: bool = True,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Trigger code indexing for a repository."""
        _print_header(f"index/{repo_id}")
        self._log_verbose(f"commit={commit_sha} incremental={incremental}", verbose)

        payload: dict[str, Any] = {"incremental": incremental}
        if commit_sha:
            payload["commit_sha"] = commit_sha

        path = f"/code-intelligence/repositories/{repo_id}/index"
        data = await self._post(path, payload, verbose)
        if data is None:
            return None

        if as_json:
            _print_json(data)
        else:
            status = data.get("status", "unknown")
            color_fn = _green if status in ("completed", "started", "queued") else _yellow
            _print_success(f"Indexing triggered: {color_fn(status)}")
            for key in ("version_id", "commit_sha", "files_indexed", "symbols_extracted"):
                if key in data and data[key] is not None:
                    print(f"  {_bold(f'{key}:')} {data[key]}")
            print()
        return data

    async def status(
        self,
        repo_id: str,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Show index status for a repository."""
        _print_header(f"index-status/{repo_id}")

        path = f"/code-intelligence/repositories/{repo_id}/index/status"
        data = await self._get(path, verbose=verbose)
        if data is None:
            return None

        if as_json:
            _print_json(data)
        else:
            status = data.get("status", "unknown")
            color_fn = _green if status == "ready" else _yellow
            print(f"\n  {_bold('Status:')} {color_fn(status)}")
            for key in ("version_id", "commit_sha", "last_indexed_at", "files_indexed", "symbols_extracted"):
                if key in data and data[key] is not None:
                    print(f"  {_bold(f'{key.title()}:')} {data[key]}")
            print()
        return data

    async def files(
        self,
        repo_id: str,
        language: Optional[str] = None,
        limit: int = 50,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """List indexed files in a repository."""
        _print_header(f"files/{repo_id}")

        params: dict[str, Any] = {"limit": limit}
        if language:
            params["language"] = language

        path = f"/code-intelligence/repositories/{repo_id}/files"
        data = await self._get(path, params=params, verbose=verbose)
        if data is None:
            return None

        if as_json:
            _print_json(data)
        else:
            files_list = data if isinstance(data, list) else data.get("files", data.get("results", []))
            total = len(files_list)
            print(f"\n{_bold(f'Files ({total})')}\n")
            if not files_list:
                _print_info("No files found.")
                return data
            for i, f in enumerate(files_list, 1):
                if isinstance(f, dict):
                    path_str = f.get("path", f.get("file_path", f.get("name", "unknown")))
                    lang = f.get("language", "")
                    lines = f.get("line_count", f.get("lines", ""))
                    symbols = f.get("symbol_count", f.get("symbols", ""))
                    lang_str = f" {_magenta(lang)}" if lang else ""
                    line_str = f" {_dim(f'{lines}L')}" if lines else ""
                    sym_str = f" {_dim(f'{symbols} sym')}" if symbols else ""
                    print(f"  {_bold(f'{i}.')}{_cyan(str(path_str))}{lang_str}{line_str}{sym_str}")
                else:
                    print(f"  {i}. {f}")
            print()
        return data

    async def symbols(
        self,
        repo_id: str,
        query: Optional[str] = None,
        symbol_type: Optional[str] = None,
        limit: int = 50,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Search or list symbols in a repository."""
        _print_header(f"symbols/{repo_id}")
        self._log_verbose(f"query={query!r} type={symbol_type}", verbose)

        params: dict[str, Any] = {"limit": limit}
        if query:
            params["query"] = query
        if symbol_type:
            params["symbol_type"] = symbol_type

        path = f"/code-intelligence/repositories/{repo_id}/symbols"
        data = await self._get(path, params=params, verbose=verbose)
        if data is None:
            return None

        if as_json:
            _print_json(data)
        else:
            symbols_list = data if isinstance(data, list) else data.get("symbols", data.get("results", []))
            total = len(symbols_list)
            print(f"\n{_bold(f'Symbols ({total})')}\n")
            if not symbols_list:
                _print_info("No symbols found.")
                return data
            for i, s in enumerate(symbols_list, 1):
                if isinstance(s, dict):
                    name = s.get("name", "unknown")
                    stype = s.get("symbol_type", s.get("type", ""))
                    file_path = s.get("file_path", s.get("path", ""))
                    line = s.get("start_line", s.get("line", ""))
                    type_color = _magenta if stype in ("class", "interface") else _blue if stype == "function" else _dim
                    loc = f" {_dim(f'{file_path}:{line}')}" if file_path else ""
                    print(f"  {_bold(f'{i}.')}{type_color(str(stype))} {_cyan(str(name))}{loc}")
                else:
                    print(f"  {i}. {s}")
            print()
        return data

    async def symbol_detail(
        self,
        repo_id: str,
        symbol_id: str,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Show detailed information about a symbol."""
        _print_header(f"symbol/{repo_id}/{symbol_id}")

        path = f"/code-intelligence/repositories/{repo_id}/symbols/{symbol_id}"
        data = await self._get(path, verbose=verbose)
        if data is None:
            return None

        if as_json:
            _print_json(data)
        else:
            name = data.get("name", "unknown")
            stype = data.get("symbol_type", data.get("type", ""))
            print(f"\n  {_bold('Symbol:')} {_cyan(str(name))}")
            print(f"  {_bold('Type:')}   {_magenta(str(stype))}")
            for key in ("file_path", "start_line", "end_line", "signature", "return_type", "visibility", "docstring"):
                val = data.get(key)
                if val is not None and val != "" and val != 0:
                    label = key.replace("_", " ").title()
                    if key == "docstring":
                        wrapped = textwrap.indent(str(val), "     ")
                        print(f"  {_bold(f'{label}:')}\n{wrapped}")
                    else:
                        print(f"  {_bold(f'{label}:')} {val}")
            print()
        return data

    async def calls(
        self,
        repo_id: str,
        symbol_id: Optional[str] = None,
        file_id: Optional[str] = None,
        depth: int = 3,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Show call graph for a repository."""
        _print_header(f"calls/{repo_id}")

        params: dict[str, Any] = {"depth": depth}
        if symbol_id:
            params["symbol_id"] = symbol_id
        if file_id:
            params["file_id"] = file_id

        path = f"/code-intelligence/repositories/{repo_id}/graph/calls"
        data = await self._get(path, params=params, verbose=verbose)
        if data is None:
            return None

        if as_json:
            _print_json(data)
        else:
            self._print_graph("Call Graph", data)
        return data

    async def imports(
        self,
        repo_id: str,
        file_id: Optional[str] = None,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Show import graph for a repository."""
        _print_header(f"imports/{repo_id}")

        params: dict[str, Any] = {}
        if file_id:
            params["file_id"] = file_id

        path = f"/code-intelligence/repositories/{repo_id}/graph/imports"
        data = await self._get(path, params=params, verbose=verbose)
        if data is None:
            return None

        if as_json:
            _print_json(data)
        else:
            self._print_graph("Import Graph", data)
        return data

    async def deps(
        self,
        repo_id: str,
        symbol_id: Optional[str] = None,
        file_id: Optional[str] = None,
        depth: int = 3,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Show dependency graph for a repository."""
        _print_header(f"deps/{repo_id}")

        params: dict[str, Any] = {"depth": depth}
        if symbol_id:
            params["symbol_id"] = symbol_id
        if file_id:
            params["file_id"] = file_id

        path = f"/code-intelligence/repositories/{repo_id}/graph/dependencies"
        data = await self._get(path, params=params, verbose=verbose)
        if data is None:
            return None

        if as_json:
            _print_json(data)
        else:
            self._print_graph("Dependency Graph", data)
        return data

    async def metrics(
        self,
        repo_id: str,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Show repository metrics."""
        _print_header(f"metrics/{repo_id}")

        path = f"/code-intelligence/repositories/{repo_id}/metrics"
        data = await self._get(path, verbose=verbose)
        if data is None:
            return None

        if as_json:
            _print_json(data)
        else:
            print(f"\n  {_bold('Repository Metrics')}\n")
            for key in ("total_files", "total_lines", "total_symbols", "avg_complexity", "max_complexity",
                         "test_coverage", "duplication_ratio", "maintainability_index", "technical_debt_hours"):
                val = data.get(key)
                if val is not None:
                    label = key.replace("_", " ").title()
                    if "coverage" in key or "ratio" in key or "index" in key:
                        print(f"  {_bold(f'{label}:')} {val}%")
                    elif "hours" in key:
                        print(f"  {_bold(f'{label}:')} {val}h")
                    else:
                        print(f"  {_bold(f'{label}:')} {val}")
            languages = data.get("languages", {})
            if languages:
                print(f"\n  {_bold('Languages:')}")
                for lang, count in languages.items():
                    print(f"    {_cyan(lang)}: {count}")
            print()
        return data

    async def smells(
        self,
        repo_id: str,
        smell_type: Optional[str] = None,
        severity: Optional[str] = None,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Show code smells for a repository."""
        _print_header(f"smells/{repo_id}")

        params: dict[str, Any] = {}
        if smell_type:
            params["smell_type"] = smell_type
        if severity:
            params["severity"] = severity

        path = f"/code-intelligence/repositories/{repo_id}/smells"
        data = await self._get(path, params=params, verbose=verbose)
        if data is None:
            return None

        if as_json:
            _print_json(data)
        else:
            smells_list = data if isinstance(data, list) else data.get("smells", data.get("results", []))
            total = len(smells_list)
            print(f"\n{_bold(f'Code Smells ({total})')}\n")
            if not smells_list:
                _print_info("No code smells found.")
                return data
            for i, s in enumerate(smells_list, 1):
                if isinstance(s, dict):
                    stype = s.get("smell_type", s.get("type", "unknown"))
                    sev = s.get("severity", "info")
                    msg = s.get("message", "")
                    fpath = s.get("file_path", "")
                    line = s.get("line_start", s.get("line", ""))
                    sev_color = _severity_color(sev)
                    loc = f" {_dim(f'{fpath}:{line}')}" if fpath else ""
                    print(f"  {_bold(f'{i}.')}{sev_color(f'[{sev.upper()}]')} {_magenta(str(stype))}{loc}")
                    if msg:
                        print(f"     {_dim(str(msg))}")
                else:
                    print(f"  {i}. {s}")
            print()
        return data

    async def security(
        self,
        repo_id: str,
        severity: Optional[str] = None,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Show security findings for a repository."""
        _print_header(f"security/{repo_id}")

        params: dict[str, Any] = {}
        if severity:
            params["severity"] = severity

        path = f"/code-intelligence/repositories/{repo_id}/security"
        data = await self._get(path, params=params, verbose=verbose)
        if data is None:
            return None

        if as_json:
            _print_json(data)
        else:
            findings = data if isinstance(data, list) else data.get("findings", data.get("results", []))
            total = len(findings)
            print(f"\n{_bold(f'Security Findings ({total})')}\n")
            if not findings:
                _print_success("No security findings.")
                return data
            for i, f in enumerate(findings, 1):
                if isinstance(f, dict):
                    title = f.get("title", "Unknown")
                    sev = f.get("severity", "info")
                    cat = f.get("category", "")
                    fpath = f.get("file_path", "")
                    cwe = f.get("cwe_id", "")
                    desc = f.get("description", "")
                    sev_color = _severity_color(sev)
                    loc = f" {_dim(str(fpath))}" if fpath else ""
                    cwe_str = f" {_dim(f'({cwe})')}" if cwe else ""
                    print(f"  {_bold(f'{i}.')}{sev_color(f'[{sev.upper()}]')} {_cyan(str(title))}{cwe_str}{loc}")
                    if cat:
                        print(f"     {_dim(f'Category: {cat}')}")
                    if desc:
                        snippet = str(desc)[:150]
                        print(f"     {_dim(snippet)}")
                else:
                    print(f"  {i}. {f}")
            print()
        return data

    async def architecture(
        self,
        repo_id: str,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Show architecture overview for a repository."""
        _print_header(f"arch/{repo_id}")

        path = f"/code-intelligence/repositories/{repo_id}/architecture"
        data = await self._get(path, verbose=verbose)
        if data is None:
            return None

        if as_json:
            _print_json(data)
        else:
            print(f"\n  {_bold('Architecture Overview')}\n")
            summary = data.get("summary", "")
            if summary:
                print(f"  {summary}\n")
            modules = data.get("modules", [])
            if modules:
                print(f"  {_bold('Modules:')}")
                for m in modules:
                    if isinstance(m, dict):
                        name = m.get("name", "unknown")
                        desc = m.get("description", "")
                        sym_count = m.get("symbol_count", m.get("symbols", ""))
                        desc_str = f" {_dim(str(desc))}" if desc else ""
                        sym_str = f" {_dim(f'({sym_count} symbols)')}" if sym_count else ""
                        print(f"    {_cyan(str(name))}{desc_str}{sym_str}")
                    else:
                        print(f"    {m}")
                print()
            layers = data.get("layers", [])
            if layers:
                print(f"  {_bold('Layers:')}")
                for layer in layers:
                    if isinstance(layer, dict):
                        name = layer.get("name", "unknown")
                        deps = layer.get("dependencies", [])
                        dep_str = f" {_dim(f'-> {deps}')} " if deps else ""
                        print(f"    {_magenta(str(name))}{dep_str}")
                    else:
                        print(f"    {layer}")
                print()
            patterns = data.get("patterns", [])
            if patterns:
                print(f"  {_bold('Patterns:')}")
                for p in patterns:
                    print(f"    {_blue(str(p))}")
                print()
            entry_points = data.get("entry_points", [])
            if entry_points:
                print(f"  {_bold('Entry Points:')}")
                for ep in entry_points:
                    print(f"    {_green(str(ep))}")
                print()
        return data

    async def impact(
        self,
        repo_id: str,
        symbol_id: str,
        depth: int = 3,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Analyze impact of changing a symbol."""
        _print_header(f"impact/{repo_id}")
        self._log_verbose(f"symbol={symbol_id} depth={depth}", verbose)

        payload: dict[str, Any] = {
            "target_type": "symbol",
            "target_id": symbol_id,
            "depth": depth,
        }

        path = f"/code-intelligence/repositories/{repo_id}/impact/analyze"
        data = await self._post(path, payload, verbose)
        if data is None:
            return None

        if as_json:
            _print_json(data)
        else:
            score = data.get("impact_score", 0)
            affected_files = data.get("affected_files", [])
            affected_symbols = data.get("affected_symbols", [])
            chain = data.get("chain", [])

            score_color = _green if score < 0.3 else _yellow if score < 0.7 else _red
            print(f"\n  {_bold('Impact Score:')} {score_color(f'{score:.2f}')}")
            print(f"  {_bold('Affected Files:')} {len(affected_files)}")
            print(f"  {_bold('Affected Symbols:')} {len(affected_symbols)}")
            if chain:
                print(f"\n  {_bold('Impact Chain:')}")
                for node in chain:
                    if isinstance(node, dict):
                        name = node.get("name", node.get("symbol", ""))
                        ntype = node.get("type", "")
                        indent = "    " + "  " * node.get("depth", 0)
                        print(f"{indent}{_cyan(str(ntype))} {_bold(str(name))}")
                    else:
                        print(f"    {node}")
            recommendations = data.get("recommendations", [])
            if recommendations:
                print(f"\n  {_bold('Recommendations:')}")
                for rec in recommendations:
                    print(f"    {_yellow('!')} {rec}")
            print()
        return data

    async def unused(
        self,
        repo_id: str,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Find unused symbols in a repository."""
        _print_header(f"unused/{repo_id}")

        path = f"/code-intelligence/repositories/{repo_id}/impact/unused"
        data = await self._post(path, verbose=verbose)
        if data is None:
            return None

        if as_json:
            _print_json(data)
        else:
            symbols = data if isinstance(data, list) else data.get("symbols", data.get("results", []))
            total = len(symbols)
            print(f"\n{_bold(f'Unused Symbols ({total})')}\n")
            if not symbols:
                _print_success("No unused symbols found.")
                return data
            for i, s in enumerate(symbols, 1):
                if isinstance(s, dict):
                    name = s.get("name", "unknown")
                    stype = s.get("symbol_type", s.get("type", ""))
                    fpath = s.get("file_path", "")
                    loc = f" {_dim(str(fpath))}" if fpath else ""
                    print(f"  {_bold(f'{i}.')}{_magenta(str(stype))} {_cyan(str(name))}{loc}")
                else:
                    print(f"  {i}. {s}")
            print()
        return data

    async def search(
        self,
        repo_id: str,
        query: str,
        search_type: str = "hybrid",
        limit: int = 20,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Perform a code search across the repository."""
        _print_header(f"search/{repo_id}")
        self._log_verbose(f"query={query!r} type={search_type} limit={limit}", verbose)

        payload: dict[str, Any] = {
            "query": query,
            "search_type": search_type,
            "limit": limit,
        }

        path = f"/code-intelligence/repositories/{repo_id}/search"
        data = await self._post(path, payload, verbose)
        if data is None:
            return None

        if as_json:
            _print_json(data)
        else:
            results = data.get("results", data.get("matches", []))
            total = data.get("total", len(results))
            duration = data.get("duration_ms")
            duration_str = f" {_dim(f'({duration}ms)')}" if duration else ""
            print(f"\n{_bold(f'Search Results ({total})')}{duration_str}\n")
            if not results:
                _print_info("No results found.")
                return data
            for i, r in enumerate(results, 1):
                if isinstance(r, dict):
                    fpath = r.get("file_path", r.get("path", ""))
                    line = r.get("line", r.get("line_number", ""))
                    score = r.get("score", r.get("relevance", None))
                    content = r.get("content", r.get("text", r.get("snippet", "")))
                    mtype = r.get("match_type", r.get("symbol_type", ""))
                    line_str = f":{line}" if line else ""
                    score_str = f" {_dim(f'({score:.2f})')}" if score is not None else ""
                    type_str = f" {_dim('[%s]' % mtype)}" if mtype else ""
                    print(f"  {_bold(f'{i}.')}{_cyan(str(fpath))}{line_str}{score_str}{type_str}")
                    if content:
                        snippet = str(content).strip()
                        if len(snippet) > 200:
                            snippet = snippet[:200] + "..."
                        wrapped = textwrap.indent(snippet, "     ")
                        print(f"{_dim(wrapped)}")
                    print()
                else:
                    print(f"  {i}. {r}\n")
        return data

    async def health(
        self,
        repo_id: str,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Show index health for a repository."""
        _print_header(f"health/{repo_id}")

        path = f"/code-intelligence/repositories/{repo_id}/health"
        data = await self._get(path, verbose=verbose)
        if data is None:
            return None

        if as_json:
            _print_json(data)
        else:
            status = data.get("status", "unknown")
            health_score = data.get("health_score", 0)
            color_fn = _green if status == "healthy" else _yellow if status == "degraded" else _red
            score_color = _green if health_score >= 0.8 else _yellow if health_score >= 0.5 else _red

            print(f"\n  {_bold('Health Status:')} {color_fn(status)}")
            print(f"  {_bold('Health Score:')} {score_color(f'{health_score:.2f}')}")
            for key in ("current_version_id", "current_commit_sha", "last_indexed_at",
                         "stale_files", "pending_files", "error_count"):
                val = data.get(key)
                if val is not None:
                    label = key.replace("_", " ").title()
                    print(f"  {_bold(f'{label}:')} {val}")
            issues = data.get("issues", [])
            if issues:
                print(f"\n  {_bold('Issues:')}")
                for issue in issues:
                    print(f"    {_yellow('!')} {issue}")
            print()
        return data

    @staticmethod
    def _print_graph(title: str, data: Any) -> None:
        """Generic graph pretty-printer."""
        print(f"\n  {_bold(title)}\n")

        if isinstance(data, dict):
            nodes = data.get("nodes", data.get("symbols", []))
            edges = data.get("edges", data.get("calls", data.get("dependencies", data.get("imports", []))))
            summary = data.get("summary", "")

            if summary:
                print(f"  {summary}\n")

            if nodes:
                print(f"  {_bold(f'Nodes ({len(nodes)})')}")
                for node in nodes:
                    if isinstance(node, dict):
                        name = node.get("name", node.get("symbol", "unknown"))
                        ntype = node.get("type", node.get("symbol_type", ""))
                        fpath = node.get("file_path", node.get("path", ""))
                        type_str = f" {_magenta(str(ntype))}" if ntype else ""
                        loc = f" {_dim(str(fpath))}" if fpath else ""
                        print(f"    {_cyan(str(name))}{type_str}{loc}")
                    else:
                        print(f"    {node}")
                print()

            if edges:
                print(f"  {_bold(f'Edges ({len(edges)})')}")
                for edge in edges:
                    if isinstance(edge, dict):
                        caller = edge.get("caller", edge.get("source", edge.get("from", "")))
                        callee = edge.get("callee", edge.get("target", edge.get("to", "")))
                        etype = edge.get("type", edge.get("relation", ""))
                        type_str = f" {_dim(f'[{etype}]')}" if etype else ""
                        print(f"    {_cyan(str(caller))} {_bold('->')} {_cyan(str(callee))}{type_str}")
                    else:
                        print(f"    {edge}")
                print()
        elif isinstance(data, list):
            print(f"  {_bold(f'Items ({len(data)})')}")
            for item in data:
                print(f"    {item}")
            print()
        else:
            print(f"  {data}\n")


# ---------------------------------------------------------------------------
# CLI argument parser & dispatcher
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="code_intelligence_commands",
        description="NovaForge Code Intelligence CLI",
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

    # -- index --------------------------------------------------------------
    p_index = sub.add_parser("index", help="Trigger code indexing")
    p_index.add_argument("repo_id", help="Repository ID")
    p_index.add_argument("--commit", default=None, dest="commit_sha", help="Commit SHA to index")
    p_index.add_argument("--incremental", action="store_true", default=True, help="Incremental index (default)")
    p_index.add_argument("--full", action="store_true", help="Full re-index (not incremental)")

    # -- status -------------------------------------------------------------
    p_status = sub.add_parser("status", help="Show index status")
    p_status.add_argument("repo_id", help="Repository ID")

    # -- files --------------------------------------------------------------
    p_files = sub.add_parser("files", help="List indexed files")
    p_files.add_argument("repo_id", help="Repository ID")
    p_files.add_argument("--language", default=None, dest="language", help="Filter by language")
    p_files.add_argument("--limit", type=int, default=50, help="Max results")

    # -- symbols ------------------------------------------------------------
    p_symbols = sub.add_parser("symbols", help="Search/list symbols")
    p_symbols.add_argument("repo_id", help="Repository ID")
    p_symbols.add_argument("--query", default=None, help="Search query")
    p_symbols.add_argument("--type", default=None, dest="symbol_type", help="Symbol type filter")
    p_symbols.add_argument("--limit", type=int, default=50, help="Max results")

    # -- symbol -------------------------------------------------------------
    p_symbol = sub.add_parser("symbol", help="Show symbol details")
    p_symbol.add_argument("repo_id", help="Repository ID")
    p_symbol.add_argument("symbol_id", help="Symbol ID")

    # -- calls --------------------------------------------------------------
    p_calls = sub.add_parser("calls", help="Show call graph")
    p_calls.add_argument("repo_id", help="Repository ID")
    p_calls.add_argument("--symbol-id", default=None, dest="symbol_id", help="Root symbol ID")
    p_calls.add_argument("--file-id", default=None, dest="file_id", help="Root file ID")
    p_calls.add_argument("--depth", type=int, default=3, help="Graph depth")

    # -- imports ------------------------------------------------------------
    p_imports = sub.add_parser("imports", help="Show import graph")
    p_imports.add_argument("repo_id", help="Repository ID")
    p_imports.add_argument("--file-id", default=None, dest="file_id", help="File ID")

    # -- deps ---------------------------------------------------------------
    p_deps = sub.add_parser("deps", help="Show dependency graph")
    p_deps.add_argument("repo_id", help="Repository ID")
    p_deps.add_argument("--symbol-id", default=None, dest="symbol_id", help="Symbol ID")
    p_deps.add_argument("--file-id", default=None, dest="file_id", help="File ID")
    p_deps.add_argument("--depth", type=int, default=3, help="Graph depth")

    # -- metrics ------------------------------------------------------------
    p_metrics = sub.add_parser("metrics", help="Show repository metrics")
    p_metrics.add_argument("repo_id", help="Repository ID")

    # -- smells -------------------------------------------------------------
    p_smells = sub.add_parser("smells", help="Show code smells")
    p_smells.add_argument("repo_id", help="Repository ID")
    p_smells.add_argument("--type", default=None, dest="smell_type", help="Smell type filter")
    p_smells.add_argument("--severity", default=None, help="Severity filter")

    # -- security -----------------------------------------------------------
    p_security = sub.add_parser("security", help="Show security findings")
    p_security.add_argument("repo_id", help="Repository ID")
    p_security.add_argument("--severity", default=None, help="Severity filter")

    # -- arch ---------------------------------------------------------------
    p_arch = sub.add_parser("arch", help="Show architecture")
    p_arch.add_argument("repo_id", help="Repository ID")

    # -- impact -------------------------------------------------------------
    p_impact = sub.add_parser("impact", help="Analyze impact of a change")
    p_impact.add_argument("repo_id", help="Repository ID")
    p_impact.add_argument("symbol_id", help="Symbol ID to analyze")
    p_impact.add_argument("--depth", type=int, default=3, help="Analysis depth")

    # -- search -------------------------------------------------------------
    p_search = sub.add_parser("search", help="Code search")
    p_search.add_argument("repo_id", help="Repository ID")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument(
        "--type",
        dest="search_type",
        choices=["hybrid", "lexical", "semantic", "symbol", "file"],
        default="hybrid",
        help="Search type",
    )
    p_search.add_argument("--limit", type=int, default=20, help="Max results")

    # -- health -------------------------------------------------------------
    p_health = sub.add_parser("health", help="Show index health")
    p_health.add_argument("repo_id", help="Repository ID")

    # -- unused -------------------------------------------------------------
    p_unused = sub.add_parser("unused", help="Find unused symbols")
    p_unused.add_argument("repo_id", help="Repository ID")

    # -- tests --------------------------------------------------------------
    p_tests = sub.add_parser("tests", help="Show test intelligence summary")
    p_tests.add_argument("repo_id", help="Repository ID")

    # -- test-quality -------------------------------------------------------
    p_tq = sub.add_parser("test-quality", help="Show test quality metrics")
    p_tq.add_argument("repo_id", help="Repository ID")

    # -- test-gaps ----------------------------------------------------------
    p_tg = sub.add_parser("test-gaps", help="Find untested symbols")
    p_tg.add_argument("repo_id", help="Repository ID")

    # -- ownership ----------------------------------------------------------
    p_ownership = sub.add_parser("ownership", help="Show ownership summary")
    p_ownership.add_argument("repo_id", help="Repository ID")

    # -- contributors -------------------------------------------------------
    p_contrib = sub.add_parser("contributors", help="List contributors")
    p_contrib.add_argument("repo_id", help="Repository ID")

    # -- bus-risk -----------------------------------------------------------
    p_bus = sub.add_parser("bus-risk", help="Find bus risk files")
    p_bus.add_argument("repo_id", help="Repository ID")

    # -- hotspots -----------------------------------------------------------
    p_hot = sub.add_parser("hotspots", help="Show change hotspots")
    p_hot.add_argument("repo_id", help="Repository ID")
    p_hot.add_argument("--top-n", type=int, default=20, help="Number of hotspots")

    # -- churn --------------------------------------------------------------
    p_churn = sub.add_parser("churn", help="Show churn metrics")
    p_churn.add_argument("repo_id", help="Repository ID")

    # -- history ------------------------------------------------------------
    p_hist = sub.add_parser("history", help="Show change history summary")
    p_hist.add_argument("repo_id", help="Repository ID")

    # -- config -------------------------------------------------------------
    p_config = sub.add_parser("config", help="Show configuration analysis")
    p_config.add_argument("repo_id", help="Repository ID")

    # -- docs ---------------------------------------------------------------
    p_docs = sub.add_parser("docs", help="Show documentation summary")
    p_docs.add_argument("repo_id", help="Repository ID")

    # -- summary ------------------------------------------------------------
    p_summary = sub.add_parser("summary", help="Show repository summary")
    p_summary.add_argument("repo_id", help="Repository ID")

    # -- consistency --------------------------------------------------------
    p_consist = sub.add_parser("consistency", help="Show consistency health")
    p_consist.add_argument("repo_id", help="Repository ID")

    # -- events -------------------------------------------------------------
    p_events = sub.add_parser("events", help="Show recent events")
    p_events.add_argument("repo_id", help="Repository ID")
    p_events.add_argument("--type", default=None, dest="event_type", help="Event type filter")
    p_events.add_argument("--limit", type=int, default=50, help="Max results")

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

    cmds = CodeIntelligenceCLICommands(base_url=base_url, api_key=api_key)

    if args.command == "index":
        incremental = not args.full
        return await cmds.index(
            repo_id=args.repo_id,
            commit_sha=args.commit_sha,
            incremental=incremental,
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "status":
        return await cmds.status(
            repo_id=args.repo_id,
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "files":
        return await cmds.files(
            repo_id=args.repo_id,
            language=args.language,
            limit=args.limit,
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "symbols":
        return await cmds.symbols(
            repo_id=args.repo_id,
            query=args.query,
            symbol_type=args.symbol_type,
            limit=args.limit,
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "symbol":
        return await cmds.symbol_detail(
            repo_id=args.repo_id,
            symbol_id=args.symbol_id,
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "calls":
        return await cmds.calls(
            repo_id=args.repo_id,
            symbol_id=args.symbol_id,
            file_id=args.file_id,
            depth=args.depth,
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "imports":
        return await cmds.imports(
            repo_id=args.repo_id,
            file_id=args.file_id,
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "deps":
        return await cmds.deps(
            repo_id=args.repo_id,
            symbol_id=args.symbol_id,
            file_id=args.file_id,
            depth=args.depth,
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "metrics":
        return await cmds.metrics(
            repo_id=args.repo_id,
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "smells":
        return await cmds.smells(
            repo_id=args.repo_id,
            smell_type=args.smell_type,
            severity=args.severity,
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "security":
        return await cmds.security(
            repo_id=args.repo_id,
            severity=args.severity,
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "arch":
        return await cmds.architecture(
            repo_id=args.repo_id,
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "impact":
        return await cmds.impact(
            repo_id=args.repo_id,
            symbol_id=args.symbol_id,
            depth=args.depth,
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "search":
        return await cmds.search(
            repo_id=args.repo_id,
            query=args.query,
            search_type=args.search_type,
            limit=args.limit,
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "health":
        return await cmds.health(
            repo_id=args.repo_id,
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "unused":
        return await cmds.unused(
            repo_id=args.repo_id,
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "tests":
        return await cmds._get_and_print(
            f"/code-intelligence/{args.repo_id}/tests",
            label="Test Intelligence Summary",
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "test-quality":
        return await cmds._get_and_print(
            f"/code-intelligence/{args.repo_id}/tests/quality",
            label="Test Quality",
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "test-gaps":
        return await cmds._get_and_print(
            f"/code-intelligence/{args.repo_id}/tests/gaps",
            label="Test Gaps",
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "ownership":
        return await cmds._get_and_print(
            f"/code-intelligence/{args.repo_id}/ownership",
            label="Ownership Summary",
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "contributors":
        return await cmds._get_and_print(
            f"/code-intelligence/{args.repo_id}/ownership/contributors",
            label="Contributors",
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "bus-risk":
        return await cmds._get_and_print(
            f"/code-intelligence/{args.repo_id}/ownership/bus-risk",
            label="Bus Risk Files",
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "hotspots":
        return await cmds._get_and_print(
            f"/code-intelligence/{args.repo_id}/history/hotspots",
            label="Change Hotspots",
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "churn":
        return await cmds._get_and_print(
            f"/code-intelligence/{args.repo_id}/history/churn",
            label="Churn Metrics",
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "history":
        return await cmds._get_and_print(
            f"/code-intelligence/{args.repo_id}/history/summary",
            label="Change History Summary",
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "config":
        return await cmds._get_and_print(
            f"/code-intelligence/{args.repo_id}/config",
            label="Configuration Analysis",
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "docs":
        return await cmds._get_and_print(
            f"/code-intelligence/{args.repo_id}/docs",
            label="Documentation Summary",
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "summary":
        return await cmds._get_and_print(
            f"/code-intelligence/{args.repo_id}/summary",
            label="Repository Summary",
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "consistency":
        return await cmds._get_and_print(
            f"/code-intelligence/{args.repo_id}/consistency",
            label="Consistency Health",
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "events":
        return await cmds._get_and_print(
            f"/code-intelligence/{args.repo_id}/events",
            label="Recent Events",
            verbose=args.verbose,
            as_json=args.as_json,
        )

    _print_error(f"Unknown command: {args.command}")
    return None


def code_intelligence_cli_main(args: Optional[list[str]] = None) -> None:
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
# Entry point for `python -m app.cli.code_intelligence_commands`
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    code_intelligence_cli_main()
