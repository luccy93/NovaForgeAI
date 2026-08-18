"""NovaForge SDK — Code Intelligence extensions.

Provides mixin classes for NovaForgeClient and AsyncNovaForgeClient
that add methods for code indexing, symbol search, graph analysis,
code quality, security scanning, impact analysis, and RAG context.

Usage:
    from backend.sdk import NovaForgeClient
    from backend.sdk.code_intelligence import CodeIntelligenceMixin

    class MyClient(CodeIntelligenceMixin, NovaForgeClient):
        pass

    # Or use standalone async/sync helpers:
    from backend.sdk.code_intelligence import CodeIntelligenceMixin
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Response dataclasses
# ---------------------------------------------------------------------------


@dataclass
class CodeIndexResult:
    repo_id: str
    status: str
    version_id: Optional[str] = None
    commit_sha: Optional[str] = None
    incremental: bool = False
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    files_indexed: int = 0
    symbols_extracted: int = 0
    duration_ms: Optional[int] = None
    error: Optional[str] = None


@dataclass
class FileDetail:
    file_id: str
    repo_id: str
    path: str
    language: Optional[str] = None
    size_bytes: int = 0
    line_count: int = 0
    symbol_count: int = 0
    complexity: float = 0.0
    last_modified: Optional[str] = None
    hash: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SymbolDetail:
    symbol_id: str
    repo_id: str
    name: str
    symbol_type: str
    file_id: Optional[str] = None
    file_path: Optional[str] = None
    start_line: int = 0
    end_line: int = 0
    signature: Optional[str] = None
    docstring: Optional[str] = None
    return_type: Optional[str] = None
    visibility: Optional[str] = None
    parent_symbol_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MetricsResult:
    repo_id: str
    total_files: int = 0
    total_lines: int = 0
    total_symbols: int = 0
    languages: dict[str, int] = field(default_factory=dict)
    avg_complexity: float = 0.0
    max_complexity: float = 0.0
    test_coverage: Optional[float] = None
    duplication_ratio: Optional[float] = None
    maintainability_index: Optional[float] = None
    technical_debt_hours: Optional[float] = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class SmellResult:
    smell_id: str
    smell_type: str
    severity: str
    file_id: Optional[str] = None
    file_path: Optional[str] = None
    line_start: int = 0
    line_end: int = 0
    message: str = ""
    suggestion: Optional[str] = None
    symbol_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SecurityFindingResult:
    finding_id: str
    severity: str
    category: str
    title: str
    description: str = ""
    file_path: Optional[str] = None
    line_start: int = 0
    line_end: int = 0
    cwe_id: Optional[str] = None
    recommendation: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ArchitectureResult:
    repo_id: str
    modules: list[dict[str, Any]] = field(default_factory=list)
    layers: list[dict[str, Any]] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ImpactResult:
    repo_id: str
    target_type: str
    target_id: str
    affected_files: list[str] = field(default_factory=list)
    affected_symbols: list[str] = field(default_factory=list)
    impact_score: float = 0.0
    depth: int = 0
    chain: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class SearchResultItem:
    id: str
    score: float
    file_path: str
    line: int
    content: str
    symbol_type: str = ""
    symbol_name: str = ""
    match_type: str = ""


@dataclass
class SearchResults:
    query: str
    results: list[SearchResultItem] = field(default_factory=list)
    total: int = 0
    search_type: str = "hybrid"
    duration_ms: Optional[int] = None


@dataclass
class RAGContextResult:
    repo_id: str
    query: str
    context: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    token_count: int = 0
    symbols_included: list[str] = field(default_factory=list)
    files_included: list[str] = field(default_factory=list)


@dataclass
class IndexHealthResult:
    repo_id: str
    status: str
    current_version_id: Optional[str] = None
    current_commit_sha: Optional[str] = None
    last_indexed_at: Optional[str] = None
    stale_files: int = 0
    pending_files: int = 0
    error_count: int = 0
    health_score: float = 0.0
    issues: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_code_index(data: dict) -> CodeIndexResult:
    return CodeIndexResult(**{k: v for k, v in data.items() if k in CodeIndexResult.__dataclass_fields__})


def _parse_file_detail(data: dict) -> FileDetail:
    return FileDetail(**{k: v for k, v in data.items() if k in FileDetail.__dataclass_fields__})


def _parse_symbol_detail(data: dict) -> SymbolDetail:
    return SymbolDetail(**{k: v for k, v in data.items() if k in SymbolDetail.__dataclass_fields__})


def _parse_metrics(data: dict) -> MetricsResult:
    return MetricsResult(**{k: v for k, v in data.items() if k in MetricsResult.__dataclass_fields__})


def _parse_smell(data: dict) -> SmellResult:
    return SmellResult(**{k: v for k, v in data.items() if k in SmellResult.__dataclass_fields__})


def _parse_security_finding(data: dict) -> SecurityFindingResult:
    return SecurityFindingResult(**{k: v for k, v in data.items() if k in SecurityFindingResult.__dataclass_fields__})


def _parse_architecture(data: dict) -> ArchitectureResult:
    return ArchitectureResult(**{k: v for k, v in data.items() if k in ArchitectureResult.__dataclass_fields__})


def _parse_impact(data: dict) -> ImpactResult:
    return ImpactResult(**{k: v for k, v in data.items() if k in ImpactResult.__dataclass_fields__})


def _parse_search_item(data: dict) -> SearchResultItem:
    return SearchResultItem(**{k: v for k, v in data.items() if k in SearchResultItem.__dataclass_fields__})


def _parse_search_results(data: dict) -> SearchResults:
    results = [_parse_search_item(r) for r in data.get("results", [])]
    return SearchResults(
        query=data.get("query", ""),
        results=results,
        total=data.get("total", len(results)),
        search_type=data.get("search_type", "hybrid"),
        duration_ms=data.get("duration_ms"),
    )


def _parse_rag_context(data: dict) -> RAGContextResult:
    return RAGContextResult(**{k: v for k, v in data.items() if k in RAGContextResult.__dataclass_fields__})


def _parse_index_health(data: dict) -> IndexHealthResult:
    return IndexHealthResult(**{k: v for k, v in data.items() if k in IndexHealthResult.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Sync mixin
# ---------------------------------------------------------------------------


class CodeIntelligenceMixin:
    """Mixin that adds code intelligence methods to NovaForgeClient.

    Expects the host class to provide ``self.get()``, ``self.post()``,
    and ``self._build_url()`` — all of which NovaForgeClient already has.
    """

    # ─── Index Management ──────────────────────────────────────────────

    def trigger_indexing(
        self,
        repo_id: str,
        commit_sha: Optional[str] = None,
        incremental: bool = True,
        force: bool = False,
    ) -> CodeIndexResult:
        """Trigger code indexing for a repository."""
        payload: dict[str, Any] = {
            "incremental": incremental,
            "force": force,
        }
        if commit_sha is not None:
            payload["commit_sha"] = commit_sha
        data = self.post(f"/code-intelligence/repositories/{repo_id}/index", data=payload)
        return _parse_code_index(data)

    def get_index_status(self, repo_id: str) -> dict:
        """Get the current indexing status for a repository."""
        return self.get(f"/code-intelligence/repositories/{repo_id}/index/status")

    def get_index_versions(self, repo_id: str) -> list[dict]:
        """Get all index versions for a repository."""
        return self.get(f"/code-intelligence/repositories/{repo_id}/index/versions")

    def activate_index_version(self, repo_id: str, version_id: str) -> dict:
        """Activate a specific index version."""
        return self.post(f"/code-intelligence/repositories/{repo_id}/index/activate/{version_id}")

    def rollback_index(self, repo_id: str) -> dict:
        """Rollback to the previous index version."""
        return self.post(f"/code-intelligence/repositories/{repo_id}/index/rollback")

    def cancel_index(self, repo_id: str) -> dict:
        """Cancel an in-progress indexing job."""
        return self.post(f"/code-intelligence/repositories/{repo_id}/index/cancel")

    # ─── File Intelligence ─────────────────────────────────────────────

    def list_files(
        self,
        repo_id: str,
        language: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[FileDetail]:
        """List indexed files in a repository."""
        params: dict[str, Any] = {"offset": offset, "limit": limit}
        if language is not None:
            params["language"] = language
        data = self.get(f"/code-intelligence/repositories/{repo_id}/files", params=params)
        return [_parse_file_detail(f) for f in data]

    def get_file_detail(self, repo_id: str, file_id: str) -> FileDetail:
        """Get detailed information about a specific file."""
        data = self.get(f"/code-intelligence/repositories/{repo_id}/files/{file_id}")
        return _parse_file_detail(data)

    def get_file_metrics(self, repo_id: str, file_id: str) -> MetricsResult:
        """Get code metrics for a specific file."""
        data = self.get(f"/code-intelligence/repositories/{repo_id}/files/{file_id}/metrics")
        return _parse_metrics(data)

    def get_file_symbols(self, repo_id: str, file_id: str) -> list[SymbolDetail]:
        """Get all symbols defined in a file."""
        data = self.get(f"/code-intelligence/repositories/{repo_id}/files/{file_id}/symbols")
        return [_parse_symbol_detail(s) for s in data]

    # ─── Symbol Intelligence ───────────────────────────────────────────

    def search_symbols(
        self,
        repo_id: str,
        query: str,
        symbol_type: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[SymbolDetail]:
        """Search symbols in a repository."""
        params: dict[str, Any] = {"query": query, "offset": offset, "limit": limit}
        if symbol_type is not None:
            params["symbol_type"] = symbol_type
        data = self.get(f"/code-intelligence/repositories/{repo_id}/symbols", params=params)
        return [_parse_symbol_detail(s) for s in data]

    def get_symbol_detail(self, repo_id: str, symbol_id: str) -> SymbolDetail:
        """Get detailed information about a specific symbol."""
        data = self.get(f"/code-intelligence/repositories/{repo_id}/symbols/{symbol_id}")
        return _parse_symbol_detail(data)

    def get_symbol_references(self, repo_id: str, symbol_id: str) -> list[dict]:
        """Get all references to a symbol."""
        return self.get(f"/code-intelligence/repositories/{repo_id}/symbols/{symbol_id}/references")

    def get_symbol_definition(self, repo_id: str, symbol_id: str) -> dict:
        """Get the definition location of a symbol."""
        return self.get(f"/code-intelligence/repositories/{repo_id}/symbols/{symbol_id}/definition")

    # ─── Graph Intelligence ────────────────────────────────────────────

    def get_call_graph(
        self,
        repo_id: str,
        symbol_id: Optional[str] = None,
        file_id: Optional[str] = None,
        depth: int = 3,
    ) -> dict:
        """Get the call graph for a repository, optionally rooted at a symbol or file."""
        params: dict[str, Any] = {"depth": depth}
        if symbol_id is not None:
            params["symbol_id"] = symbol_id
        if file_id is not None:
            params["file_id"] = file_id
        return self.get(f"/code-intelligence/repositories/{repo_id}/graph/calls", params=params)

    def get_import_graph(
        self,
        repo_id: str,
        file_id: Optional[str] = None,
        symbol_id: Optional[str] = None,
    ) -> dict:
        """Get the import graph for a repository."""
        params: dict[str, Any] = {}
        if file_id is not None:
            params["file_id"] = file_id
        if symbol_id is not None:
            params["symbol_id"] = symbol_id
        return self.get(f"/code-intelligence/repositories/{repo_id}/graph/imports", params=params)

    def get_dependency_graph(
        self,
        repo_id: str,
        file_id: Optional[str] = None,
        symbol_id: Optional[str] = None,
        depth: int = 3,
    ) -> dict:
        """Get the dependency graph for a repository."""
        params: dict[str, Any] = {"depth": depth}
        if file_id is not None:
            params["file_id"] = file_id
        if symbol_id is not None:
            params["symbol_id"] = symbol_id
        return self.get(f"/code-intelligence/repositories/{repo_id}/graph/dependencies", params=params)

    def get_inheritance_graph(
        self,
        repo_id: str,
        symbol_id: Optional[str] = None,
    ) -> dict:
        """Get the inheritance graph for a repository."""
        params: dict[str, Any] = {}
        if symbol_id is not None:
            params["symbol_id"] = symbol_id
        return self.get(f"/code-intelligence/repositories/{repo_id}/graph/inheritance", params=params)

    # ─── Code Quality ──────────────────────────────────────────────────

    def get_repo_metrics(self, repo_id: str) -> MetricsResult:
        """Get aggregate code metrics for a repository."""
        data = self.get(f"/code-intelligence/repositories/{repo_id}/metrics")
        return _parse_metrics(data)

    def get_code_smells(
        self,
        repo_id: str,
        smell_type: Optional[str] = None,
        severity: Optional[str] = None,
        file_id: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[SmellResult]:
        """Get code smells for a repository."""
        params: dict[str, Any] = {"offset": offset, "limit": limit}
        if smell_type is not None:
            params["smell_type"] = smell_type
        if severity is not None:
            params["severity"] = severity
        if file_id is not None:
            params["file_id"] = file_id
        data = self.get(f"/code-intelligence/repositories/{repo_id}/smells", params=params)
        return [_parse_smell(s) for s in data]

    def get_smell_summary(self, repo_id: str) -> dict:
        """Get a summary of code smells for a repository."""
        return self.get(f"/code-intelligence/repositories/{repo_id}/smells/summary")

    # ─── Security ──────────────────────────────────────────────────────

    def get_security_findings(
        self,
        repo_id: str,
        severity: Optional[str] = None,
        category: Optional[str] = None,
    ) -> list[SecurityFindingResult]:
        """Get security findings for a repository."""
        params: dict[str, Any] = {}
        if severity is not None:
            params["severity"] = severity
        if category is not None:
            params["category"] = category
        data = self.get(f"/code-intelligence/repositories/{repo_id}/security", params=params)
        return [_parse_security_finding(f) for f in data]

    def trigger_security_scan(self, repo_id: str) -> dict:
        """Trigger a security scan for a repository."""
        return self.post(f"/code-intelligence/repositories/{repo_id}/security/scan")

    # ─── Architecture ──────────────────────────────────────────────────

    def get_architecture(self, repo_id: str) -> ArchitectureResult:
        """Get architecture overview for a repository."""
        data = self.get(f"/code-intelligence/repositories/{repo_id}/architecture")
        return _parse_architecture(data)

    def get_repo_summary(self, repo_id: str) -> dict:
        """Get a high-level summary of a repository."""
        return self.get(f"/code-intelligence/repositories/{repo_id}/architecture/summary")

    # ─── Impact Analysis ───────────────────────────────────────────────

    def analyze_impact(
        self,
        repo_id: str,
        target_type: str,
        target_id: str,
        depth: int = 3,
    ) -> ImpactResult:
        """Analyze the impact of changing a symbol or file."""
        payload: dict[str, Any] = {
            "target_type": target_type,
            "target_id": target_id,
            "depth": depth,
        }
        data = self.post(f"/code-intelligence/repositories/{repo_id}/impact/analyze", data=payload)
        return _parse_impact(data)

    def detect_breaking_changes(
        self,
        repo_id: str,
        old_commit: str,
        new_commit: str,
    ) -> dict:
        """Detect breaking changes between two commits."""
        payload: dict[str, Any] = {
            "old_commit": old_commit,
            "new_commit": new_commit,
        }
        return self.post(f"/code-intelligence/repositories/{repo_id}/impact/breaking-changes", data=payload)

    def find_unused_symbols(self, repo_id: str) -> list[dict]:
        """Find symbols that are not referenced anywhere."""
        return self.post(f"/code-intelligence/repositories/{repo_id}/impact/unused")

    # ─── Search ────────────────────────────────────────────────────────

    def code_search(
        self,
        repo_id: str,
        query: str,
        search_type: str = "hybrid",
        limit: int = 20,
        filters: Optional[dict[str, Any]] = None,
    ) -> SearchResults:
        """Perform a code search across the repository."""
        payload: dict[str, Any] = {
            "query": query,
            "search_type": search_type,
            "limit": limit,
        }
        if filters is not None:
            payload["filters"] = filters
        data = self.post(f"/code-intelligence/repositories/{repo_id}/search", data=payload)
        return _parse_search_results(data)

    def search_suggest(self, repo_id: str, prefix: str) -> list[str]:
        """Get search suggestions for a given prefix."""
        return self.get(
            f"/code-intelligence/repositories/{repo_id}/search/suggest",
            params={"prefix": prefix},
        )

    # ─── RAG Context ───────────────────────────────────────────────────

    def build_rag_context(
        self,
        repo_id: str,
        query: str,
        max_tokens: int = 4096,
    ) -> RAGContextResult:
        """Build RAG context for a query against the codebase."""
        payload: dict[str, Any] = {
            "query": query,
            "max_tokens": max_tokens,
        }
        data = self.post(f"/code-intelligence/repositories/{repo_id}/rag/context", data=payload)
        return _parse_rag_context(data)

    # ─── Health ────────────────────────────────────────────────────────

    def get_index_health(self, repo_id: str) -> IndexHealthResult:
        """Get index health status for a repository."""
        data = self.get(f"/code-intelligence/repositories/{repo_id}/health")
        return _parse_index_health(data)


# ---------------------------------------------------------------------------
# Async mixin
# ---------------------------------------------------------------------------


class AsyncCodeIntelligenceMixin:
    """Mixin that adds code intelligence methods to AsyncNovaForgeClient.

    Expects the host class to provide ``self.get()``, ``self.post()``,
    and ``self._build_url()`` — all of which AsyncNovaForgeClient already has.
    """

    # ─── Index Management ──────────────────────────────────────────────

    async def trigger_indexing(
        self,
        repo_id: str,
        commit_sha: Optional[str] = None,
        incremental: bool = True,
        force: bool = False,
    ) -> CodeIndexResult:
        """Trigger code indexing for a repository."""
        payload: dict[str, Any] = {
            "incremental": incremental,
            "force": force,
        }
        if commit_sha is not None:
            payload["commit_sha"] = commit_sha
        data = await self.post(f"/code-intelligence/repositories/{repo_id}/index", data=payload)
        return _parse_code_index(data)

    async def get_index_status(self, repo_id: str) -> dict:
        """Get the current indexing status for a repository."""
        return await self.get(f"/code-intelligence/repositories/{repo_id}/index/status")

    async def get_index_versions(self, repo_id: str) -> list[dict]:
        """Get all index versions for a repository."""
        return await self.get(f"/code-intelligence/repositories/{repo_id}/index/versions")

    async def activate_index_version(self, repo_id: str, version_id: str) -> dict:
        """Activate a specific index version."""
        return await self.post(f"/code-intelligence/repositories/{repo_id}/index/activate/{version_id}")

    async def rollback_index(self, repo_id: str) -> dict:
        """Rollback to the previous index version."""
        return await self.post(f"/code-intelligence/repositories/{repo_id}/index/rollback")

    async def cancel_index(self, repo_id: str) -> dict:
        """Cancel an in-progress indexing job."""
        return await self.post(f"/code-intelligence/repositories/{repo_id}/index/cancel")

    # ─── File Intelligence ─────────────────────────────────────────────

    async def list_files(
        self,
        repo_id: str,
        language: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[FileDetail]:
        """List indexed files in a repository."""
        params: dict[str, Any] = {"offset": offset, "limit": limit}
        if language is not None:
            params["language"] = language
        data = await self.get(f"/code-intelligence/repositories/{repo_id}/files", params=params)
        return [_parse_file_detail(f) for f in data]

    async def get_file_detail(self, repo_id: str, file_id: str) -> FileDetail:
        """Get detailed information about a specific file."""
        data = await self.get(f"/code-intelligence/repositories/{repo_id}/files/{file_id}")
        return _parse_file_detail(data)

    async def get_file_metrics(self, repo_id: str, file_id: str) -> MetricsResult:
        """Get code metrics for a specific file."""
        data = await self.get(f"/code-intelligence/repositories/{repo_id}/files/{file_id}/metrics")
        return _parse_metrics(data)

    async def get_file_symbols(self, repo_id: str, file_id: str) -> list[SymbolDetail]:
        """Get all symbols defined in a file."""
        data = await self.get(f"/code-intelligence/repositories/{repo_id}/files/{file_id}/symbols")
        return [_parse_symbol_detail(s) for s in data]

    # ─── Symbol Intelligence ───────────────────────────────────────────

    async def search_symbols(
        self,
        repo_id: str,
        query: str,
        symbol_type: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[SymbolDetail]:
        """Search symbols in a repository."""
        params: dict[str, Any] = {"query": query, "offset": offset, "limit": limit}
        if symbol_type is not None:
            params["symbol_type"] = symbol_type
        data = await self.get(f"/code-intelligence/repositories/{repo_id}/symbols", params=params)
        return [_parse_symbol_detail(s) for s in data]

    async def get_symbol_detail(self, repo_id: str, symbol_id: str) -> SymbolDetail:
        """Get detailed information about a specific symbol."""
        data = await self.get(f"/code-intelligence/repositories/{repo_id}/symbols/{symbol_id}")
        return _parse_symbol_detail(data)

    async def get_symbol_references(self, repo_id: str, symbol_id: str) -> list[dict]:
        """Get all references to a symbol."""
        return await self.get(f"/code-intelligence/repositories/{repo_id}/symbols/{symbol_id}/references")

    async def get_symbol_definition(self, repo_id: str, symbol_id: str) -> dict:
        """Get the definition location of a symbol."""
        return await self.get(f"/code-intelligence/repositories/{repo_id}/symbols/{symbol_id}/definition")

    # ─── Graph Intelligence ────────────────────────────────────────────

    async def get_call_graph(
        self,
        repo_id: str,
        symbol_id: Optional[str] = None,
        file_id: Optional[str] = None,
        depth: int = 3,
    ) -> dict:
        """Get the call graph for a repository, optionally rooted at a symbol or file."""
        params: dict[str, Any] = {"depth": depth}
        if symbol_id is not None:
            params["symbol_id"] = symbol_id
        if file_id is not None:
            params["file_id"] = file_id
        return await self.get(f"/code-intelligence/repositories/{repo_id}/graph/calls", params=params)

    async def get_import_graph(
        self,
        repo_id: str,
        file_id: Optional[str] = None,
        symbol_id: Optional[str] = None,
    ) -> dict:
        """Get the import graph for a repository."""
        params: dict[str, Any] = {}
        if file_id is not None:
            params["file_id"] = file_id
        if symbol_id is not None:
            params["symbol_id"] = symbol_id
        return await self.get(f"/code-intelligence/repositories/{repo_id}/graph/imports", params=params)

    async def get_dependency_graph(
        self,
        repo_id: str,
        file_id: Optional[str] = None,
        symbol_id: Optional[str] = None,
        depth: int = 3,
    ) -> dict:
        """Get the dependency graph for a repository."""
        params: dict[str, Any] = {"depth": depth}
        if file_id is not None:
            params["file_id"] = file_id
        if symbol_id is not None:
            params["symbol_id"] = symbol_id
        return await self.get(f"/code-intelligence/repositories/{repo_id}/graph/dependencies", params=params)

    async def get_inheritance_graph(
        self,
        repo_id: str,
        symbol_id: Optional[str] = None,
    ) -> dict:
        """Get the inheritance graph for a repository."""
        params: dict[str, Any] = {}
        if symbol_id is not None:
            params["symbol_id"] = symbol_id
        return await self.get(f"/code-intelligence/repositories/{repo_id}/graph/inheritance", params=params)

    # ─── Code Quality ──────────────────────────────────────────────────

    async def get_repo_metrics(self, repo_id: str) -> MetricsResult:
        """Get aggregate code metrics for a repository."""
        data = await self.get(f"/code-intelligence/repositories/{repo_id}/metrics")
        return _parse_metrics(data)

    async def get_code_smells(
        self,
        repo_id: str,
        smell_type: Optional[str] = None,
        severity: Optional[str] = None,
        file_id: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[SmellResult]:
        """Get code smells for a repository."""
        params: dict[str, Any] = {"offset": offset, "limit": limit}
        if smell_type is not None:
            params["smell_type"] = smell_type
        if severity is not None:
            params["severity"] = severity
        if file_id is not None:
            params["file_id"] = file_id
        data = await self.get(f"/code-intelligence/repositories/{repo_id}/smells", params=params)
        return [_parse_smell(s) for s in data]

    async def get_smell_summary(self, repo_id: str) -> dict:
        """Get a summary of code smells for a repository."""
        return await self.get(f"/code-intelligence/repositories/{repo_id}/smells/summary")

    # ─── Security ──────────────────────────────────────────────────────

    async def get_security_findings(
        self,
        repo_id: str,
        severity: Optional[str] = None,
        category: Optional[str] = None,
    ) -> list[SecurityFindingResult]:
        """Get security findings for a repository."""
        params: dict[str, Any] = {}
        if severity is not None:
            params["severity"] = severity
        if category is not None:
            params["category"] = category
        data = await self.get(f"/code-intelligence/repositories/{repo_id}/security", params=params)
        return [_parse_security_finding(f) for f in data]

    async def trigger_security_scan(self, repo_id: str) -> dict:
        """Trigger a security scan for a repository."""
        return await self.post(f"/code-intelligence/repositories/{repo_id}/security/scan")

    # ─── Architecture ──────────────────────────────────────────────────

    async def get_architecture(self, repo_id: str) -> ArchitectureResult:
        """Get architecture overview for a repository."""
        data = await self.get(f"/code-intelligence/repositories/{repo_id}/architecture")
        return _parse_architecture(data)

    async def get_repo_summary(self, repo_id: str) -> dict:
        """Get a high-level summary of a repository."""
        return await self.get(f"/code-intelligence/repositories/{repo_id}/architecture/summary")

    # ─── Impact Analysis ───────────────────────────────────────────────

    async def analyze_impact(
        self,
        repo_id: str,
        target_type: str,
        target_id: str,
        depth: int = 3,
    ) -> ImpactResult:
        """Analyze the impact of changing a symbol or file."""
        payload: dict[str, Any] = {
            "target_type": target_type,
            "target_id": target_id,
            "depth": depth,
        }
        data = await self.post(f"/code-intelligence/repositories/{repo_id}/impact/analyze", data=payload)
        return _parse_impact(data)

    async def detect_breaking_changes(
        self,
        repo_id: str,
        old_commit: str,
        new_commit: str,
    ) -> dict:
        """Detect breaking changes between two commits."""
        payload: dict[str, Any] = {
            "old_commit": old_commit,
            "new_commit": new_commit,
        }
        return await self.post(f"/code-intelligence/repositories/{repo_id}/impact/breaking-changes", data=payload)

    async def find_unused_symbols(self, repo_id: str) -> list[dict]:
        """Find symbols that are not referenced anywhere."""
        return await self.post(f"/code-intelligence/repositories/{repo_id}/impact/unused")

    # ─── Search ────────────────────────────────────────────────────────

    async def code_search(
        self,
        repo_id: str,
        query: str,
        search_type: str = "hybrid",
        limit: int = 20,
        filters: Optional[dict[str, Any]] = None,
    ) -> SearchResults:
        """Perform a code search across the repository."""
        payload: dict[str, Any] = {
            "query": query,
            "search_type": search_type,
            "limit": limit,
        }
        if filters is not None:
            payload["filters"] = filters
        data = await self.post(f"/code-intelligence/repositories/{repo_id}/search", data=payload)
        return _parse_search_results(data)

    async def search_suggest(self, repo_id: str, prefix: str) -> list[str]:
        """Get search suggestions for a given prefix."""
        return await self.get(
            f"/code-intelligence/repositories/{repo_id}/search/suggest",
            params={"prefix": prefix},
        )

    # ─── RAG Context ───────────────────────────────────────────────────

    async def build_rag_context(
        self,
        repo_id: str,
        query: str,
        max_tokens: int = 4096,
    ) -> RAGContextResult:
        """Build RAG context for a query against the codebase."""
        payload: dict[str, Any] = {
            "query": query,
            "max_tokens": max_tokens,
        }
        data = await self.post(f"/code-intelligence/repositories/{repo_id}/rag/context", data=payload)
        return _parse_rag_context(data)

    # ─── Health ────────────────────────────────────────────────────────

    async def get_index_health(self, repo_id: str) -> IndexHealthResult:
        """Get index health status for a repository."""
        data = await self.get(f"/code-intelligence/repositories/{repo_id}/health")
        return _parse_index_health(data)
