"""Knowledge & Retrieval (RAG) CLI Extension for NovaForge.

Provides CLI commands that interface with the /api/v1/rag backend API,
including knowledge-source management, hybrid retrieval, source status,
indexing, evaluation, and knowledge health.

Usage:
    python -m app.cli.rag_commands <command> [args...]

Examples:
    python -m app.cli.rag_commands search "how do I rotate tokens?" --repo-id 42
    python -m app.cli.rag_commands sources --repo-id 42 --source-type doc
    python -m app.cli.rag_commands create-source "Runbook" --source-type doc --uri file:///runbook.md
    python -m app.cli.rag_commands health
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
from datetime import datetime, timezone
from typing import Any, Optional

import httpx


# ---------------------------------------------------------------------------
# Terminal formatting helpers (mirrors code_intelligence_commands.py)
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


# ---------------------------------------------------------------------------
# RagCLICommands class
# ---------------------------------------------------------------------------


class RagCLICommands:
    """CLI commands for the NovaForge /api/v1/rag backend API."""

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

    async def _request(
        self,
        method: str,
        path: str,
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
        verbose: bool = False,
    ) -> Any:
        self._log_verbose(f"{method} {path} json={json} params={params}", verbose)
        try:
            async with httpx.AsyncClient(**self._client_kwargs) as client:
                response = await client.request(
                    method,
                    self._url(path),
                    json=json,
                    params=params,
                    headers=self._headers(),
                )
                response.raise_for_status()
                if response.status_code == 204:
                    return {"status": "ok"}
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
        method: str,
        path: str,
        label: str,
        verbose: bool = False,
        as_json: bool = False,
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> Any:
        """Generic request + print helper for simple endpoints.

        Mirrors the ``_get_and_print`` helper in
        ``code_intelligence_commands.py`` but additionally supports POST/DELETE
        via the ``method`` argument.
        """
        _print_header(label)
        data = await self._request(
            method, path, json=json, params=params, verbose=verbose
        )
        if data is None:
            return None
        if as_json:
            _print_json(data)
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    name = (
                        item.get("name")
                        or item.get("title")
                        or item.get("source_id")
                        or item.get("source_type")
                        or item.get("status")
                        or str(item)[:80]
                    )
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

    # -- search --------------------------------------------------------------

    async def search(
        self,
        query: str,
        repository_id: Optional[str] = None,
        limit: int = 10,
        rerank_strategy: Optional[str] = None,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Run hybrid retrieval and print context, answerability and citations."""
        _print_header(f"search/{query!r}")

        payload: dict[str, Any] = {"query": query, "limit": limit}
        if repository_id is not None:
            payload["repository_id"] = repository_id
        if rerank_strategy is not None:
            payload["rerank_strategy"] = rerank_strategy

        data = await self._request(
            "POST", "/api/v1/rag/search", json=payload, verbose=verbose
        )
        if data is None:
            return None

        if as_json:
            _print_json(data)
            return data

        context = data.get("context", [])
        answerability = data.get("answerability", data.get("answerable"))
        citations = data.get("citations", [])

        print(f"\n  {_bold('Answerability:')} {_cyan(str(answerability))}")
        print(f"  {_bold('Context chunks:')} {len(context)}")
        print(f"  {_bold('Citations:')} {len(citations)}\n")

        if context:
            print(f"  {_bold('Context')}\n")
            for i, chunk in enumerate(context, 1):
                if isinstance(chunk, dict):
                    cid = chunk.get("chunk_id", chunk.get("id", i))
                    src = chunk.get("source", chunk.get("source_id", ""))
                    text = chunk.get("text", chunk.get("content", ""))
                    score = chunk.get("score", chunk.get("relevance"))
                    src_str = f" {_dim(f'[{src}]')}" if src else ""
                    score_str = f" {_dim(f'({score})')}" if score is not None else ""
                    print(f"  {_bold(f'{i}.')}{_cyan(str(cid))}{src_str}{score_str}")
                    if text:
                        snippet = str(text).strip()
                        if len(snippet) > 240:
                            snippet = snippet[:240] + "..."
                        print(f"{_dim(textwrap.indent(snippet, '     '))}")
                else:
                    print(f"  {i}. {chunk}")
            print()

        if citations:
            print(f"  {_bold('Citations')}\n")
            for i, cit in enumerate(citations, 1):
                if isinstance(cit, dict):
                    label = cit.get("label", cit.get("citation", str(i)))
                    valid = cit.get("valid", cit.get("is_valid"))
                    valid_str = (
                        f" {_green('[valid]')}"
                        if valid
                        else (f" {_red('[invalid]')}" if valid is not None else "")
                    )
                    print(f"  {_bold(f'{i}.')} {_yellow(str(label))}{valid_str}")
                else:
                    print(f"  {i}. {cit}")
            print()

        _print_success("Search complete")
        return data

    # -- status --------------------------------------------------------------

    async def status(
        self,
        source_id: Optional[str] = None,
        repository_id: Optional[str] = None,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Show indexing status for a source (or all sources in a repo)."""
        if source_id:
            _print_header(f"status/{source_id}")
            path = f"/api/v1/rag/sources/{source_id}/status"
            data = await self._request("GET", path, verbose=verbose)
        else:
            _print_header(f"status/{repository_id or 'all'}")
            path = "/api/v1/rag/sources"
            params: dict[str, Any] = {}
            if repository_id is not None:
                params["repository_id"] = repository_id
            data = await self._request("GET", path, params=params, verbose=verbose)

        if data is None:
            return None

        if as_json:
            _print_json(data)
            return data

        if isinstance(data, list):
            print(f"\n  {_bold(f'Sources ({len(data)})')}\n")
            for i, item in enumerate(data, 1):
                if isinstance(item, dict):
                    name = item.get("name", "unknown")
                    sid = item.get("source_id", item.get("id", ""))
                    st = item.get("status", item.get("index_status", "unknown"))
                    color_fn = _green if st in ("ready", "indexed", "healthy") else _yellow
                    print(f"  {_bold(f'{i}.')} {_cyan(str(name))} {_dim(str(sid))} {color_fn(str(st))}")
                else:
                    print(f"  {i}. {item}")
            print()
        elif isinstance(data, dict):
            status = data.get("status", data.get("index_status", "unknown"))
            color_fn = _green if status in ("ready", "indexed", "healthy") else _yellow
            print(f"\n  {_bold('Status:')} {color_fn(str(status))}")
            for key in (
                "version_id",
                "source_id",
                "name",
                "staleness",
                "last_indexed_at",
                "chunk_count",
                "error",
            ):
                val = data.get(key)
                if val is not None:
                    label = key.replace("_", " ").title()
                    print(f"  {_bold(f'{label}:')} {val}")
            print()
        _print_success("Status retrieved")
        return data

    # -- sources -------------------------------------------------------------

    async def sources(
        self,
        repository_id: Optional[str] = None,
        source_type: Optional[str] = None,
        status: Optional[str] = None,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """List knowledge sources, optionally filtered."""
        _print_header("sources")

        params: dict[str, Any] = {}
        if repository_id is not None:
            params["repository_id"] = repository_id
        if source_type is not None:
            params["source_type"] = source_type
        if status is not None:
            params["status"] = status

        data = await self._request(
            "GET", "/api/v1/rag/sources", params=params, verbose=verbose
        )
        if data is None:
            return None

        sources_list = data if isinstance(data, list) else data.get(
            "sources", data.get("results", [])
        )

        if as_json:
            _print_json(sources_list)
            return data

        total = len(sources_list)
        print(f"\n{_bold(f'Sources ({total})')}\n")
        if not sources_list:
            _print_info("No sources found.")
            return data
        for i, s in enumerate(sources_list, 1):
            if isinstance(s, dict):
                name = s.get("name", "unknown")
                sid = s.get("source_id", s.get("id", ""))
                stype = s.get("source_type", s.get("type", ""))
                st = s.get("status", s.get("index_status", ""))
                type_str = f" {_magenta(str(stype))}" if stype else ""
                st_str = f" {_dim(str(st))}" if st else ""
                print(f"  {_bold(f'{i}.')} {_cyan(str(name))} {_dim(str(sid))}{type_str}{st_str}")
            else:
                print(f"  {i}. {s}")
        print()
        return data

    # -- index ---------------------------------------------------------------

    async def index(
        self,
        source_id: str,
        content: Optional[str] = None,
        repository_id: Optional[str] = None,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Trigger indexing of a knowledge source."""
        _print_header(f"index/{source_id}")

        payload: dict[str, Any] = {}
        if content is not None:
            payload["content"] = content
        if repository_id is not None:
            payload["repository_id"] = repository_id

        data = await self._request(
            "POST",
            f"/api/v1/rag/sources/{source_id}/index",
            json=payload,
            verbose=verbose,
        )
        if data is None:
            return None

        if as_json:
            _print_json(data)
            return data

        status = data.get("status", data.get("index_status", "unknown"))
        color_fn = _green if status in ("queued", "started", "indexing", "completed", "ready") else _yellow
        _print_success(f"Indexing triggered: {color_fn(str(status))}")
        for key in ("version_id", "chunk_count", "message", "source_id"):
            if key in data and data[key] is not None:
                print(f"  {_bold(f'{key}:')} {data[key]}")
        print()
        return data

    # -- evaluate ------------------------------------------------------------

    async def evaluate(
        self,
        dataset_name: str,
        queries: list[str],
        expected_chunk_ids: list[list[str]],
        rerank_strategy: Optional[str] = None,
        query_type: Optional[str] = None,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Run a retrieval evaluation and print the computed metrics."""
        _print_header(f"evaluate/{dataset_name}")

        payload: dict[str, Any] = {
            "dataset_name": dataset_name,
            "queries": queries,
            "expected_chunk_ids": expected_chunk_ids,
        }
        if rerank_strategy is not None:
            payload["rerank_strategy"] = rerank_strategy
        if query_type is not None:
            payload["query_type"] = query_type

        data = await self._request(
            "POST", "/api/v1/rag/evaluate", json=payload, verbose=verbose
        )
        if data is None:
            return None

        if as_json:
            _print_json(data)
            return data

        metrics = data.get("metrics", data.get("results", data))
        _print_success(f"Evaluation '{dataset_name}' complete")
        if isinstance(metrics, dict):
            for key, val in metrics.items():
                if isinstance(val, (list, dict)):
                    _print_info(f"  {key}: ({type(val).__name__}, {len(val)} items)")
                else:
                    _print_info(f"  {key}: {val}")
        else:
            _print_json(metrics)
        print()
        return data

    # -- health --------------------------------------------------------------

    async def health(
        self,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Show knowledge health metrics."""
        _print_header("health")

        data = await self._request("GET", "/api/v1/rag/health", verbose=verbose)
        if data is None:
            return None

        if as_json:
            _print_json(data)
            return data

        status = data.get("status", "unknown")
        color_fn = _green if status == "healthy" else _yellow if status in ("degraded", "warning") else _red
        print(f"\n  {_bold('Health Status:')} {color_fn(str(status))}")
        for key in (
            "source_count",
            "indexed_source_count",
            "chunk_count",
            "stale_source_count",
            "health_score",
            "last_indexed_at",
            "error_count",
        ):
            val = data.get(key)
            if val is not None:
                label = key.replace("_", " ").title()
                if "score" in key and isinstance(val, (int, float)):
                    score_color = _green if val >= 0.8 else _yellow if val >= 0.5 else _red
                    print(f"  {_bold(f'{label}:')} {score_color(f'{val:.2f}')}")
                else:
                    print(f"  {_bold(f'{label}:')} {val}")
        issues = data.get("issues", [])
        if issues:
            print(f"\n  {_bold('Issues:')}")
            for issue in issues:
                print(f"    {_yellow('!')} {issue}")
        print()
        return data

    # -- create-source ------------------------------------------------------

    async def create_source(
        self,
        name: str,
        source_type: str,
        repository_id: Optional[str] = None,
        source_uri: Optional[str] = None,
        content: Optional[str] = None,
        classification: str = "internal",
        permissions: Optional[dict] = None,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Register a new knowledge source."""
        _print_header(f"create-source/{name}")

        payload: dict[str, Any] = {
            "name": name,
            "source_type": source_type,
            "classification": classification,
        }
        if repository_id is not None:
            payload["repository_id"] = repository_id
        if source_uri is not None:
            payload["source_uri"] = source_uri
        if content is not None:
            payload["content"] = content
        if permissions is not None:
            payload["permissions"] = permissions

        data = await self._request(
            "POST", "/api/v1/rag/sources", json=payload, verbose=verbose
        )
        if data is None:
            return None

        if as_json:
            _print_json(data)
            return data

        sid = data.get("source_id", data.get("id", ""))
        _print_success(f"Source created: {_cyan(str(name))} {_dim(str(sid))}")
        for key in ("status", "source_type", "classification", "version_id"):
            if key in data and data[key] is not None:
                print(f"  {_bold(f'{key}:')} {data[key]}")
        print()
        return data

    # -- delete-source ------------------------------------------------------

    async def delete_source(
        self,
        source_id: str,
        verbose: bool = False,
        as_json: bool = False,
    ) -> Any:
        """Delete a knowledge source."""
        _print_header(f"delete-source/{source_id}")

        data = await self._request(
            "DELETE", f"/api/v1/rag/sources/{source_id}", verbose=verbose
        )
        if data is None:
            return None

        if as_json:
            _print_json(data)
            return data

        _print_success(f"Source deleted: {_dim(source_id)}")
        if isinstance(data, dict):
            for key, val in data.items():
                if key in ("detail", "status", "deleted", "source_id"):
                    _print_info(f"  {key}: {val}")
        print()
        return data


# ---------------------------------------------------------------------------
# CLI argument parser & dispatcher
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rag_commands",
        description="NovaForge Knowledge & Retrieval (RAG) CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Backend server URL (default: NOVAFORGE_API_URL env var or http://localhost:8000)",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Bearer auth token (default: NOVAFORGE_TOKEN env var)",
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

    # -- search -------------------------------------------------------------
    p_search = sub.add_parser("search", help="Hybrid retrieval over knowledge sources")
    p_search.add_argument("query", help="Natural-language query")
    p_search.add_argument("--repo-id", default=None, dest="repository_id", help="Repository ID filter")
    p_search.add_argument("--limit", type=int, default=10, help="Max results")
    p_search.add_argument("--rerank", default=None, dest="rerank_strategy", help="Rerank strategy")

    # -- status -------------------------------------------------------------
    p_status = sub.add_parser("status", help="Show source indexing status")
    p_status.add_argument("--source-id", default=None, dest="source_id", help="Specific source ID")
    p_status.add_argument("--repo-id", default=None, dest="repository_id", help="Filter by repository ID")

    # -- sources ------------------------------------------------------------
    p_sources = sub.add_parser("sources", help="List knowledge sources")
    p_sources.add_argument("--repo-id", default=None, dest="repository_id", help="Filter by repository ID")
    p_sources.add_argument("--source-type", default=None, dest="source_type", help="Filter by source type")
    p_sources.add_argument("--status", default=None, dest="status", help="Filter by status")

    # -- index --------------------------------------------------------------
    p_index = sub.add_parser("index", help="Trigger indexing of a knowledge source")
    p_index.add_argument("source_id", help="Source ID to index")
    p_index.add_argument("--content", default=None, help="Path to file whose content to send for indexing")
    p_index.add_argument("--repo-id", default=None, dest="repository_id", help="Repository ID")

    # -- evaluate -----------------------------------------------------------
    p_eval = sub.add_parser("evaluate", help="Run a RAG evaluation")
    p_eval.add_argument("--dataset", required=True, dest="dataset_name", help="Dataset name")
    p_eval.add_argument(
        "--queries",
        required=True,
        dest="queries",
        help="Comma-separated queries OR path to a JSON file with a list of strings",
    )
    p_eval.add_argument(
        "--expected",
        required=True,
        dest="expected",
        help="Path to a JSON file with a list of lists of expected chunk ids",
    )
    p_eval.add_argument("--rerank", default=None, dest="rerank_strategy", help="Rerank strategy")
    p_eval.add_argument("--query-type", default=None, dest="query_type", help="Query type")

    # -- health -------------------------------------------------------------
    p_health = sub.add_parser("health", help="Show knowledge health")
    p_health.set_defaults(command="health")

    # -- create-source ------------------------------------------------------
    p_create = sub.add_parser("create-source", help="Register a new knowledge source")
    p_create.add_argument("name", help="Source name")
    p_create.add_argument("--source-type", required=True, dest="source_type", help="Source type (e.g. doc, repo, web)")
    p_create.add_argument("--repo-id", default=None, dest="repository_id", help="Repository ID")
    p_create.add_argument("--uri", default=None, dest="source_uri", help="Source URI")
    p_create.add_argument("--content", default=None, help="Path to a file whose content to attach")
    p_create.add_argument("--classification", default="internal", dest="classification", help="Classification (default: internal)")
    p_create.add_argument("--permissions", default=None, help="JSON string of permissions object")

    # -- delete-source ------------------------------------------------------
    p_delete = sub.add_parser("delete-source", help="Delete a knowledge source")
    p_delete.add_argument("source_id", help="Source ID to delete")

    return parser


def _resolve_base_url(provided: Optional[str]) -> str:
    url = (
        provided
        or os.environ.get("NOVAFORGE_API_URL")
        or os.environ.get("NOVAFORGE_BASE_URL")
        or "http://localhost:8000"
    )
    return url.rstrip("/")


def _resolve_token(provided: Optional[str]) -> Optional[str]:
    return provided or os.environ.get("NOVAFORGE_TOKEN")


def _read_file_or_none(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _parse_queries(value: str) -> list[str]:
    """Accept comma-separated queries or a path to a JSON list file."""
    candidate = value.strip()
    if candidate.startswith("[") or candidate.endswith(".json") or os.path.isfile(candidate):
        try:
            if os.path.isfile(candidate):
                with open(candidate, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            else:
                data = json.loads(candidate)
            if isinstance(data, list):
                return [str(q) for q in data]
        except (json.JSONDecodeError, OSError):
            pass
    return [q.strip() for q in candidate.split(",") if q.strip()]


def _parse_expected(value: str) -> list[list[str]]:
    """Expected chunk ids: path to a JSON file with a list of lists."""
    if os.path.isfile(value):
        with open(value, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    else:
        data = json.loads(value)
    return [[str(c) for c in group] for group in data]


async def _dispatch(args: argparse.Namespace) -> Any:
    base_url = _resolve_base_url(args.base_url)
    token = _resolve_token(args.token)

    if args.verbose:
        _print_info(f"Server: {base_url}")
        _print_info(f"Command: {args.command}")

    cmds = RagCLICommands(base_url=base_url, api_key=token)

    if args.command == "search":
        return await cmds.search(
            query=args.query,
            repository_id=args.repository_id,
            limit=args.limit,
            rerank_strategy=args.rerank_strategy,
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "status":
        return await cmds.status(
            source_id=args.source_id,
            repository_id=args.repository_id,
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "sources":
        return await cmds.sources(
            repository_id=args.repository_id,
            source_type=args.source_type,
            status=args.status,
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "index":
        content = _read_file_or_none(args.content)
        return await cmds.index(
            source_id=args.source_id,
            content=content,
            repository_id=args.repository_id,
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "evaluate":
        queries = _parse_queries(args.queries)
        expected = _parse_expected(args.expected)
        return await cmds.evaluate(
            dataset_name=args.dataset_name,
            queries=queries,
            expected_chunk_ids=expected,
            rerank_strategy=args.rerank_strategy,
            query_type=args.query_type,
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "health":
        return await cmds.health(
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "create-source":
        content = _read_file_or_none(args.content)
        permissions = None
        if args.permissions:
            permissions = json.loads(args.permissions)
        return await cmds.create_source(
            name=args.name,
            source_type=args.source_type,
            repository_id=args.repository_id,
            source_uri=args.source_uri,
            content=content,
            classification=args.classification,
            permissions=permissions,
            verbose=args.verbose,
            as_json=args.as_json,
        )

    if args.command == "delete-source":
        return await cmds.delete_source(
            source_id=args.source_id,
            verbose=args.verbose,
            as_json=args.as_json,
        )

    _print_error(f"Unknown command: {args.command}")
    return None


def rag_cli_main(args: Optional[list[str]] = None) -> None:
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
# Entry point for `python -m app.cli.rag_commands`
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    rag_cli_main()
