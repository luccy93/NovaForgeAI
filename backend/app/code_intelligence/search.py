"""Hybrid Search Engine — combines BM25 + vector + symbol + graph + metadata.

Provides a unified search API over multiple retrieval strategies with
Reciprocal Rank Fusion, multi-factor ranking, and explainable scoring.
"""

import logging
import math
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select, func, and_, or_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.code_intelligence.models import (
    CodeCall,
    CodeFile,
    CodeHistory,
    CodeImport,
    CodeReference,
    CodeSymbol,
    SymbolType,
)

logger = logging.getLogger(__name__)

# ─── Constants ─────────────────────────────────────────────────────────

EMBEDDING_COLLECTION = "repository_chunks"
DOC_EMBEDDING_COLLECTION = "documentation_chunks"

# Ranking weights for composite scoring
WEIGHT_LEXICAL = 0.25
WEIGHT_SEMANTIC = 0.30
WEIGHT_SYMBOL = 0.20
WEIGHT_PATH = 0.10
WEIGHT_RECENCY = 0.08
WEIGHT_DEPENDENCY = 0.07

# Dangerous regex patterns that can cause catastrophic backtracking
_DANGEROUS_PATTERNS = frozenset({
    r"(a+)+$",
    r"(a|a)+$",
    r"(.*a){x}$",
    r"([a-zA-Z]+)*$",
    r"(a|b|c|d|e|f|g|h|i|j)+$",
})


# ─── Dataclasses ───────────────────────────────────────────────────────


@dataclass
class SearchResult:
    """Single search result with multi-factor scoring."""

    id: str = ""
    score: float = 0.0
    type: str = "symbol"  # symbol | file | chunk | graph
    name: str = ""
    file_path: str = ""
    line: int = 0
    end_line: int = 0
    content: str = ""
    snippet: str = ""
    language: str = ""
    symbol_type: str = ""
    repository: str = ""
    commit: str = ""
    metadata: dict = field(default_factory=dict)
    highlights: list[str] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)
    retrieval_source: str = ""  # lexical | semantic | symbol | graph | metadata | hybrid


@dataclass
class SearchResults:
    """Complete search response with facets and timing."""

    query: str = ""
    results: list[SearchResult] = field(default_factory=list)
    total: int = 0
    search_type: str = "hybrid"
    duration_ms: float = 0.0
    facets: dict = field(default_factory=dict)


# ─── HybridSearchEngine ───────────────────────────────────────────────


class HybridSearchEngine:
    """Unified search engine combining lexical, semantic, symbol, graph,
    dependency, path, and regex search strategies."""

    def __init__(
        self,
        db_session: AsyncSession,
        embedding_service: Any | None = None,
        vector_store: Any | None = None,
        graph_store: Any | None = None,
    ) -> None:
        self._db = db_session
        self._embedding = embedding_service
        self._vector_store = vector_store
        self._graph_store = graph_store

    # ── Main Search Entry ─────────────────────────────────────────────

    async def search(
        self,
        query: str,
        repo_id: str,
        search_type: str = "hybrid",
        limit: int = 20,
        filters: dict | None = None,
    ) -> SearchResults:
        """Main search entry point.

        Parameters
        ----------
        query : str
            Natural language or keyword query.
        repo_id : str
            Repository UUID string to search within.
        search_type : str
            One of: ``hybrid``, ``lexical``, ``semantic``, ``symbol``,
            ``file``, ``graph``, ``dependency``, ``path``, ``regex``.
        limit : int
            Maximum number of results.
        filters : dict | None
            Optional filters: ``{"language": "python", "type": "function",
            "severity": "high"}``.

        Returns
        -------
        SearchResults
            Ranked results with facets, timing, and total count.
        """
        if isinstance(repo_id, str):
            repo_id = UUID(repo_id)
        start = time.perf_counter()
        result_lists: list[list[SearchResult]] = []

        if search_type in ("hybrid", "lexical"):
            lexical = await self.lexical_search(query, repo_id, limit=limit * 2)
            result_lists.append(lexical)

        if search_type in ("hybrid", "semantic"):
            semantic = await self.semantic_search(query, repo_id, limit=limit * 2)
            result_lists.append(semantic)

        if search_type in ("hybrid", "symbol"):
            symbol = await self.symbol_search(query, repo_id, limit=limit * 2)
            result_lists.append(symbol)

        if search_type in ("file",):
            file_results = await self.file_search(query, repo_id, limit=limit * 2)
            result_lists.append(file_results)

        if search_type in ("hybrid", "graph"):
            graph = await self.graph_search(query, repo_id, limit=limit * 2)
            result_lists.append(graph)

        if search_type in ("dependency",):
            symbol_id = filters.pop("symbol_id", "") if filters else ""
            if symbol_id:
                dep = await self.dependency_search(symbol_id, repo_id, limit=limit * 2)
                result_lists.append(dep)

        if search_type in ("path",):
            path_results = await self.path_search(query, repo_id, limit=limit * 2)
            result_lists.append(path_results)

        if search_type in ("regex",):
            regex_results = await self.regex_search(query, repo_id, limit=limit * 2)
            result_lists.append(regex_results)

        if result_lists:
            if len(result_lists) == 1:
                combined = result_lists[0]
            else:
                combined = self._combine_results(result_lists, method="rrf")
        else:
            combined = []

        if filters:
            combined = self._apply_filters(combined, filters)

        combined = self._rank_by_relevance(combined, query)
        combined = combined[:limit]

        elapsed = (time.perf_counter() - start) * 1000
        facets = self._compute_facets(combined)

        return SearchResults(
            query=query,
            results=combined,
            total=len(combined),
            search_type=search_type,
            duration_ms=round(elapsed, 2),
            facets=facets,
        )

    # ── Individual Search Strategies ──────────────────────────────────

    async def lexical_search(
        self, query: str, repo_id: str, limit: int = 50
    ) -> list[SearchResult]:
        """BM25-style keyword search across code content, names, and docs."""
        keywords = [w.strip() for w in query.split() if len(w.strip()) > 1]
        if not keywords:
            return []

        results: list[SearchResult] = []

        conditions = [CodeSymbol.repository_id == repo_id]
        sym_or_conditions = []
        for kw in keywords:
            sym_or_conditions.append(
                or_(
                    CodeSymbol.name.ilike(f"%{kw}%"),
                    CodeSymbol.qualified_name.ilike(f"%{kw}%"),
                    CodeSymbol.signature.ilike(f"%{kw}%"),
                    CodeSymbol.docstring.ilike(f"%{kw}%"),
                )
            )
        if sym_or_conditions:
            conditions.append(or_(*sym_or_conditions))

        stmt = (
            select(CodeSymbol, CodeFile.file_path)
            .join(CodeFile, CodeSymbol.file_id == CodeFile.id)
            .where(and_(*conditions))
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        for sym, file_path in result.all():
            content_parts = [
                sym.name or "",
                sym.qualified_name or "",
                sym.signature or "",
                sym.docstring or "",
            ]
            content = " ".join(content_parts)
            score = self._bm25_score(query, keywords, content)
            highlights = self._extract_highlights(content, keywords)

            results.append(SearchResult(
                id=sym.symbol_id,
                score=score,
                type="symbol",
                name=sym.name,
                file_path=file_path,
                line=sym.start_line or 0,
                end_line=sym.end_line or 0,
                content=sym.docstring or "",
                snippet=sym.signature or "",
                language=sym.language or "",
                symbol_type=sym.symbol_type,
                repository=repo_id,
                highlights=highlights,
                retrieval_source="lexical",
                metadata={
                    "qualified_name": sym.qualified_name,
                    "visibility": sym.visibility or "",
                },
            ))

        file_conditions = [CodeFile.repository_id == repo_id]
        file_or_conditions = []
        for kw in keywords:
            file_or_conditions.append(
                or_(
                    CodeFile.file_path.ilike(f"%{kw}%"),
                    CodeFile.file_name.ilike(f"%{kw}%"),
                )
            )
        if file_or_conditions:
            file_conditions.append(or_(*file_or_conditions))

        file_stmt = (
            select(CodeFile)
            .where(and_(*file_conditions))
            .limit(limit)
        )
        file_result = await self._db.execute(file_stmt)
        for f in file_result.scalars().all():
            score = self._bm25_score(query, keywords, f"{f.file_path} {f.file_name}")
            highlights = self._extract_highlights(f"{f.file_path} {f.file_name}", keywords)

            results.append(SearchResult(
                id=str(f.id),
                score=score,
                type="file",
                name=f.file_name,
                file_path=f.file_path,
                language=f.language or "",
                repository=repo_id,
                highlights=highlights,
                retrieval_source="lexical",
                metadata={
                    "line_count": f.line_count or 0,
                    "symbol_count": f.symbol_count or 0,
                },
            ))

        return results

    async def semantic_search(
        self, query: str, repo_id: str, limit: int = 50
    ) -> list[SearchResult]:
        """Vector similarity search over embedded code chunks."""
        if not self._vector_store or not self._embedding:
            return []

        try:
            vector = await self._embedding.embed(query)

            search_result = await self._vector_store.search(
                collection=EMBEDDING_COLLECTION,
                query_vector=vector,
                limit=limit,
                query_filter={"must": [
                    {"key": "repository_id", "match": {"value": str(repo_id)}},
                ]},
            )

            results: list[SearchResult] = []
            for point in (search_result or []):
                payload = getattr(point, "payload", None) or {}
                score = getattr(point, "score", 0.0)
                chunk_id = payload.get("chunk_id", str(getattr(point, "id", "")))

                results.append(SearchResult(
                    id=chunk_id,
                    score=score,
                    type="chunk",
                    name=payload.get("file_path", ""),
                    file_path=payload.get("file_path", ""),
                    line=payload.get("start_line", 0),
                    end_line=payload.get("end_line", 0),
                    content=payload.get("content_preview", ""),
                    snippet=payload.get("content_preview", ""),
                    language=payload.get("language", ""),
                    repository=repo_id,
                    retrieval_source="semantic",
                    metadata={
                        "chunk_type": payload.get("chunk_type", ""),
                        "token_count": payload.get("token_count", 0),
                    },
                ))
            return results
        except Exception as exc:
            logger.warning("Semantic search failed: %s", exc)
            return []

    async def symbol_search(
        self,
        query: str,
        repo_id: str,
        symbol_type: str | None = None,
        limit: int = 50,
    ) -> list[SearchResult]:
        """Symbol name and qualified_name search."""
        keywords = [w.strip() for w in query.split() if len(w.strip()) > 1]
        if not keywords:
            return []

        conditions = [CodeSymbol.repository_id == repo_id]
        or_conditions = []
        for kw in keywords:
            or_conditions.append(CodeSymbol.name.ilike(f"%{kw}%"))
            or_conditions.append(CodeSymbol.qualified_name.ilike(f"%{kw}%"))
        if or_conditions:
            conditions.append(or_(*or_conditions))

        stmt = (
            select(CodeSymbol, CodeFile.file_path)
            .join(CodeFile, CodeSymbol.file_id == CodeFile.id)
            .where(and_(*conditions))
            .limit(limit)
        )

        if symbol_type:
            stmt = stmt.where(CodeSymbol.symbol_type == symbol_type)

        result = await self._db.execute(stmt)
        results: list[SearchResult] = []

        for sym, file_path in result.all():
            name_score = self._symbol_name_score(query, sym.name or "")
            qname_score = self._symbol_name_score(query, sym.qualified_name or "")
            score = max(name_score, qname_score)

            highlights: list[str] = []
            if sym.signature:
                highlights.append(sym.signature)
            if sym.docstring:
                highlights.append(sym.docstring[:200])

            results.append(SearchResult(
                id=sym.symbol_id,
                score=score,
                type="symbol",
                name=sym.name,
                file_path=file_path,
                line=sym.start_line or 0,
                end_line=sym.end_line or 0,
                content=sym.docstring or "",
                snippet=sym.signature or "",
                language=sym.language or "",
                symbol_type=sym.symbol_type,
                repository=repo_id,
                highlights=highlights,
                retrieval_source="symbol",
                metadata={
                    "qualified_name": sym.qualified_name,
                    "parent_symbol_id": sym.parent_symbol_id or "",
                    "is_async": sym.is_async,
                    "visibility": sym.visibility or "",
                },
            ))

        return results

    async def file_search(
        self, query: str, repo_id: str, limit: int = 50
    ) -> list[SearchResult]:
        """File path and name search."""
        keywords = [w.strip() for w in query.split() if len(w.strip()) > 1]
        if not keywords:
            return []

        conditions = [CodeFile.repository_id == repo_id]
        or_conditions = []
        for kw in keywords:
            or_conditions.append(CodeFile.file_path.ilike(f"%{kw}%"))
            or_conditions.append(CodeFile.file_name.ilike(f"%{kw}%"))
        if or_conditions:
            conditions.append(or_(*or_conditions))

        stmt = (
            select(CodeFile)
            .where(and_(*conditions))
            .order_by(CodeFile.file_path)
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        results: list[SearchResult] = []

        for f in result.scalars().all():
            path_lower = (f.file_path or "").lower()
            score = 0.0
            for kw in keywords:
                kw_lower = kw.lower()
                if kw_lower in path_lower:
                    score += 0.5
                if kw_lower in (f.file_name or "").lower():
                    score += 0.3
            score = min(1.0, score)

            results.append(SearchResult(
                id=str(f.id),
                score=score,
                type="file",
                name=f.file_name,
                file_path=f.file_path,
                language=f.language or "",
                repository=repo_id,
                highlights=[f.file_path],
                retrieval_source="metadata",
                metadata={
                    "line_count": f.line_count or 0,
                    "symbol_count": f.symbol_count or 0,
                    "is_test_file": f.is_test_file,
                    "is_config_file": f.is_config_file,
                    "is_documentation": f.is_documentation,
                },
            ))

        return results

    async def graph_search(
        self, query: str, repo_id: str, limit: int = 50
    ) -> list[SearchResult]:
        """Graph traversal search using Neo4j for relationship-aware results."""
        if not self._graph_store:
            return []

        results: list[SearchResult] = []
        keywords = [w.strip() for w in query.split() if len(w.strip()) > 1]
        if not keywords:
            return []

        try:
            name_conditions = " OR ".join(
                [f"toLower(n.name) CONTAINS toLower($kw{i})" for i in range(len(keywords))]
            )
            params = {f"kw{i}": kw for i, kw in enumerate(keywords)}
            params["repo_id"] = str(repo_id)
            params["limit"] = limit

            query_cypher = f"""
            MATCH (r:Repository {{id: $repo_id}})-[:CONTAINS*0..5]->(n)
            WHERE {name_conditions}
            OPTIONAL MATCH (n)-[rel]-(m)
            RETURN n.id AS id, n.name AS name, labels(n) AS labels,
                   n.file_path AS file_path, n.start_line AS start_line,
                   n.end_line AS end_line, n.language AS language,
                   collect(DISTINCT {{
                       rel_type: type(rel),
                       target_name: m.name,
                       target_id: m.id
                   }})[..10] AS relationships
            LIMIT $limit
            """

            result = await self._graph_store.run(query_cypher, **params)
            async for record in result:
                node_id = record.get("id", "")
                name = record.get("name", "")
                labels = record.get("labels", [])
                file_path = record.get("file_path", "")
                rels = record.get("relationships", [])

                node_type = labels[0].lower() if labels else "unknown"
                rel_score = min(1.0, len(rels) / 5.0) if rels else 0.0
                name_match = any(
                    kw.lower() in (name or "").lower() for kw in keywords
                )
                score = (0.6 if name_match else 0.2) + rel_score * 0.4

                highlights = [
                    f"{r['rel_type']} -> {r['target_name']}"
                    for r in rels
                    if r.get("target_name")
                ][:5]

                results.append(SearchResult(
                    id=node_id,
                    score=score,
                    type="graph",
                    name=name,
                    file_path=file_path or "",
                    line=record.get("start_line", 0) or 0,
                    end_line=record.get("end_line", 0) or 0,
                    language=record.get("language", "") or "",
                    repository=repo_id,
                    highlights=highlights,
                    retrieval_source="graph",
                    metadata={"node_labels": labels, "relationships": rels[:10]},
                ))

        except Exception as exc:
            logger.warning("Graph search failed: %s", exc)

        return results

    async def dependency_search(
        self,
        symbol_id: str,
        repo_id: str,
        direction: str = "both",
        limit: int = 50,
    ) -> list[SearchResult]:
        """Dependency-based search: find symbols connected via imports/calls."""
        sym = await self._resolve_symbol(symbol_id)
        if sym is None:
            return []

        results: list[SearchResult] = []
        visited: set[str] = set()

        if direction in ("outgoing", "both"):
            callees = await self._get_transitive_callees(sym.id, depth=2, max_results=limit)
            for callee_id, depth_level in callees:
                if str(callee_id) in visited:
                    continue
                visited.add(str(callee_id))
                callee_sym = await self._resolve_symbol_by_db_id(callee_id)
                if callee_sym is None:
                    continue
                file_path = await self._get_file_path(callee_sym.file_id)
                score = max(0.1, 1.0 - depth_level * 0.25)
                results.append(SearchResult(
                    id=callee_sym.symbol_id,
                    score=score,
                    type="symbol",
                    name=callee_sym.name,
                    file_path=file_path,
                    line=callee_sym.start_line or 0,
                    end_line=callee_sym.end_line or 0,
                    content=callee_sym.docstring or "",
                    snippet=callee_sym.signature or "",
                    language=callee_sym.language or "",
                    symbol_type=callee_sym.symbol_type,
                    repository=repo_id,
                    retrieval_source="dependency",
                    metadata={
                        "dependency_direction": "outgoing",
                        "depth": depth_level,
                        "source_symbol": sym.symbol_id,
                    },
                ))

        if direction in ("incoming", "both"):
            callers = await self._get_transitive_callers(sym.id, depth=1, max_results=limit)
            for caller_id, depth_level in callers:
                if str(caller_id) in visited:
                    continue
                visited.add(str(caller_id))
                caller_sym = await self._resolve_symbol_by_db_id(caller_id)
                if caller_sym is None:
                    continue
                file_path = await self._get_file_path(caller_sym.file_id)
                score = max(0.1, 1.0 - depth_level * 0.3)
                results.append(SearchResult(
                    id=caller_sym.symbol_id,
                    score=score,
                    type="symbol",
                    name=caller_sym.name,
                    file_path=file_path,
                    line=caller_sym.start_line or 0,
                    end_line=caller_sym.end_line or 0,
                    content=caller_sym.docstring or "",
                    snippet=caller_sym.signature or "",
                    language=caller_sym.language or "",
                    symbol_type=caller_sym.symbol_type,
                    repository=repo_id,
                    retrieval_source="dependency",
                    metadata={
                        "dependency_direction": "incoming",
                        "depth": depth_level,
                        "target_symbol": sym.symbol_id,
                    },
                ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    async def path_search(
        self, pattern: str, repo_id: str, limit: int = 50
    ) -> list[SearchResult]:
        """Glob/regex pattern search over file paths."""
        conditions = [CodeFile.repository_id == repo_id]

        regex_pattern = self._glob_to_regex(pattern)
        try:
            re.compile(regex_pattern)
        except re.error:
            regex_pattern = re.escape(pattern)

        conditions.append(CodeFile.file_path.ilike(f"%{pattern.replace('*', '%')}%"))

        stmt = (
            select(CodeFile)
            .where(and_(*conditions))
            .order_by(CodeFile.file_path)
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        results: list[SearchResult] = []

        compiled = re.compile(regex_pattern, re.IGNORECASE)
        for f in result.scalars().all():
            path = f.file_path or ""
            if compiled.search(path):
                score = 1.0
            else:
                score = 0.5

            results.append(SearchResult(
                id=str(f.id),
                score=score,
                type="file",
                name=f.file_name,
                file_path=f.file_path,
                language=f.language or "",
                repository=repo_id,
                highlights=[f.file_path],
                retrieval_source="metadata",
                metadata={
                    "line_count": f.line_count or 0,
                    "pattern": pattern,
                },
            ))

        return results

    async def regex_search(
        self, pattern: str, repo_id: str, limit: int = 50
    ) -> list[SearchResult]:
        """Safe content regex search. Rejects patterns that may cause
        catastrophic backtracking."""
        if not self._safe_regex(pattern):
            logger.warning("Rejected unsafe regex pattern: %s", pattern)
            return []

        try:
            compiled = re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            logger.warning("Invalid regex pattern %s: %s", pattern, exc)
            return []

        keyword = self._extract_keyword_from_regex(pattern)
        conditions = [CodeSymbol.repository_id == repo_id]
        if keyword:
            conditions.append(CodeSymbol.docstring.ilike(f"%{keyword}%"))

        stmt = (
            select(CodeSymbol, CodeFile.file_path)
            .join(CodeFile, CodeSymbol.file_id == CodeFile.id)
            .where(and_(*conditions))
            .limit(limit * 5)
        )
        result = await self._db.execute(stmt)
        results: list[SearchResult] = []

        for sym, file_path in result.all():
            searchable = " ".join(filter(None, [
                sym.name or "",
                sym.qualified_name or "",
                sym.signature or "",
                sym.docstring or "",
            ]))
            matches = compiled.findall(searchable)
            if not matches:
                continue

            score = min(1.0, len(matches) * 0.2 + 0.3)
            highlights = [str(m)[:200] for m in matches[:5]]

            results.append(SearchResult(
                id=sym.symbol_id,
                score=score,
                type="symbol",
                name=sym.name,
                file_path=file_path,
                line=sym.start_line or 0,
                end_line=sym.end_line or 0,
                content=sym.docstring or "",
                snippet=sym.signature or "",
                language=sym.language or "",
                symbol_type=sym.symbol_type,
                repository=repo_id,
                highlights=highlights,
                retrieval_source="lexical",
                metadata={"regex_pattern": pattern, "match_count": len(matches)},
            ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    # ── Result Combination ────────────────────────────────────────────

    def _combine_results(
        self, result_sets: list[list[SearchResult]], method: str = "rrf"
    ) -> list[SearchResult]:
        """Combine multiple result lists using Reciprocal Rank Fusion or
        weighted merge."""
        if method == "rrf":
            return self._reciprocal_rank_fusion(result_sets)
        return self._weighted_merge(result_sets)

    def _reciprocal_rank_fusion(
        self, result_lists: list[list[SearchResult]], k: int = 60
    ) -> list[SearchResult]:
        """Reciprocal Rank Fusion across multiple ranked lists.

        RRF score = sum(1 / (k + rank_i)) for each list i.
        """
        score_map: dict[str, float] = {}
        result_map: dict[str, SearchResult] = {}
        source_map: dict[str, set[str]] = defaultdict(set)

        for result_list in result_lists:
            for rank, result in enumerate(result_list):
                rid = result.id
                rrf_score = 1.0 / (k + rank + 1)

                if rid in score_map:
                    score_map[rid] += rrf_score
                else:
                    score_map[rid] = rrf_score
                    result_map[rid] = result

                source_map[rid].add(result.retrieval_source)

        combined: list[SearchResult] = []
        for rid, score in score_map.items():
            result = result_map[rid]
            if len(source_map[rid]) > 1:
                result.retrieval_source = "hybrid"
            result.score = score
            combined.append(result)

        combined.sort(key=lambda r: r.score, reverse=True)
        return combined

    def _weighted_merge(self, result_lists: list[list[SearchResult]]) -> list[SearchResult]:
        """Weighted score merge across result lists."""
        source_weights = {
            "lexical": 0.25,
            "semantic": 0.30,
            "symbol": 0.20,
            "graph": 0.15,
            "metadata": 0.10,
            "dependency": 0.15,
            "hybrid": 0.25,
        }

        score_map: dict[str, float] = {}
        result_map: dict[str, SearchResult] = {}
        source_count: dict[str, int] = defaultdict(int)

        for result_list in result_lists:
            for result in result_list:
                rid = result.id
                weight = source_weights.get(result.retrieval_source, 0.1)
                weighted_score = result.score * weight

                if rid in score_map:
                    score_map[rid] += weighted_score
                else:
                    score_map[rid] = weighted_score
                    result_map[rid] = result

                source_count[rid] += 1

        combined: list[SearchResult] = []
        for rid, score in score_map.items():
            result = result_map[rid]
            boost = min(0.3, source_count[rid] * 0.1)
            result.score = score + boost
            if source_count[rid] > 1:
                result.retrieval_source = "hybrid"
            combined.append(result)

        combined.sort(key=lambda r: r.score, reverse=True)
        return combined

    # ── Filtering ─────────────────────────────────────────────────────

    def _apply_filters(
        self, results: list[SearchResult], filters: dict
    ) -> list[SearchResult]:
        """Apply language, type, severity, and other metadata filters."""
        filtered: list[SearchResult] = []

        for r in results:
            passed = True

            lang_filter = filters.get("language")
            if lang_filter:
                if r.language.lower() != lang_filter.lower():
                    passed = False

            type_filter = filters.get("type")
            if type_filter and passed:
                if type_filter == "function":
                    if r.symbol_type not in (SymbolType.FUNCTION.value, SymbolType.METHOD.value):
                        if r.type != "chunk":
                            passed = False
                elif type_filter == "class":
                    if r.symbol_type not in (
                        SymbolType.CLASS.value, SymbolType.INTERFACE.value,
                        SymbolType.STRUCT.value, SymbolType.ENUM.value,
                    ):
                        if r.type != "chunk":
                            passed = False
                elif type_filter == "file":
                    if r.type != "file":
                        passed = False
                elif type_filter == "method":
                    if r.symbol_type != SymbolType.METHOD.value:
                        if r.type != "chunk":
                            passed = False

            severity_filter = filters.get("severity")
            if severity_filter and passed:
                sev = r.metadata.get("severity", "")
                if sev and sev.lower() != severity_filter.lower():
                    passed = False

            path_filter = filters.get("path_pattern")
            if path_filter and passed:
                if r.file_path:
                    pattern = path_filter.replace("*", ".*")
                    if not re.search(pattern, r.file_path, re.IGNORECASE):
                        passed = False

            if passed:
                filtered.append(r)

        return filtered

    # ── Ranking ───────────────────────────────────────────────────────

    def _rank_by_relevance(
        self, results: list[SearchResult], query: str
    ) -> list[SearchResult]:
        """Multi-factor ranking combining lexical, semantic, symbol, path,
        recency, and dependency relevance."""
        query_lower = query.lower()
        query_tokens = set(query_lower.split())

        for r in results:
            r.score = self._score_result(r, query)

        results.sort(key=lambda r: r.score, reverse=True)
        return results

    def _score_result(self, result: SearchResult, query: str) -> float:
        """Calculate composite score for a single result.

        Factors: lexical relevance, symbol relevance, semantic relevance,
        path relevance, recency, dependency relevance.
        """
        query_lower = query.lower()
        query_tokens = set(query_lower.split())

        # Lexical relevance: keyword overlap in name/content/snippet
        lexical = self._lexical_relevance(result, query_tokens)

        # Symbol relevance: name match quality
        symbol = self._symbol_relevance(result, query_tokens)

        # Semantic relevance: already scored by embedding similarity
        semantic = result.score if result.retrieval_source in ("semantic", "hybrid") else 0.0

        # Path relevance: query tokens in file path
        path = self._path_relevance(result, query_tokens)

        # Recency: boost recently changed files
        recency = self._recency_score(result)

        # Dependency relevance: boost results from dependency search
        dependency = 1.0 if result.retrieval_source == "dependency" else 0.0

        # Source strategy bonus
        source_bonus = 0.0
        if result.retrieval_source == "hybrid":
            source_bonus = 0.15
        elif result.retrieval_source in ("semantic", "symbol"):
            source_bonus = 0.05

        composite = (
            lexical * WEIGHT_LEXICAL
            + symbol * WEIGHT_SYMBOL
            + semantic * WEIGHT_SEMANTIC
            + path * WEIGHT_PATH
            + recency * WEIGHT_RECENCY
            + dependency * WEIGHT_DEPENDENCY
            + source_bonus
        )

        return round(min(1.0, composite), 6)

    def _lexical_relevance(
        self, result: SearchResult, query_tokens: set[str]
    ) -> float:
        """Score based on keyword overlap in content fields."""
        searchable_parts = [
            result.name.lower(),
            result.snippet.lower(),
            result.content.lower(),
            result.file_path.lower(),
        ]
        searchable = " ".join(searchable_parts)
        searchable_tokens = set(searchable.split())

        if not query_tokens:
            return 0.0

        overlap = len(query_tokens & searchable_tokens)
        return min(1.0, overlap / len(query_tokens))

    def _symbol_relevance(
        self, result: SearchResult, query_tokens: set[str]
    ) -> float:
        """Score based on name/qualified_name match quality."""
        if not query_tokens:
            return 0.0

        name = result.name.lower()
        if not name:
            return 0.0

        exact_match = 1.0 if query_tokens == {name} else 0.0
        contains_match = 0.8 if all(t in name for t in query_tokens) else 0.0
        partial_match = len(query_tokens & set(name.split())) / len(query_tokens) * 0.6

        return max(exact_match, contains_match, partial_match)

    def _path_relevance(
        self, result: SearchResult, query_tokens: set[str]
    ) -> float:
        """Score based on file path matching query tokens."""
        if not query_tokens or not result.file_path:
            return 0.0

        path_parts = set(
            result.file_path.lower()
            .replace("/", " ")
            .replace("\\", " ")
            .replace(".", " ")
            .replace("_", " ")
            .replace("-", " ")
            .split()
        )

        overlap = len(query_tokens & path_parts)
        return min(1.0, overlap / len(query_tokens))

    def _recency_score(self, result: SearchResult) -> float:
        """Boost recently modified files."""
        commit_date = result.metadata.get("commit_date", "")
        if not commit_date:
            return 0.2

        try:
            from datetime import datetime, timezone
            dt = datetime.fromisoformat(commit_date.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            days_ago = (now - dt).days
            if days_ago <= 7:
                return 1.0
            if days_ago <= 30:
                return 0.8
            if days_ago <= 90:
                return 0.5
            return 0.2
        except (ValueError, TypeError):
            return 0.2

    # ── Facets ────────────────────────────────────────────────────────

    def _compute_facets(self, results: list[SearchResult]) -> dict:
        """Compute facet counts for languages, types, and sources."""
        lang_counts: dict[str, int] = defaultdict(int)
        type_counts: dict[str, int] = defaultdict(int)
        source_counts: dict[str, int] = defaultdict(int)

        for r in results:
            if r.language:
                lang_counts[r.language] += 1
            type_counts[r.type] += 1
            source_counts[r.retrieval_source] += 1

        return {
            "languages": dict(lang_counts),
            "result_types": dict(type_counts),
            "retrieval_sources": dict(source_counts),
        }

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _bm25_score(query: str, keywords: list[str], content: str) -> float:
        """Simplified BM25-inspired scoring."""
        if not content or not keywords:
            return 0.0

        content_lower = content.lower()
        content_tokens = content_lower.split()
        doc_len = len(content_tokens) if content_tokens else 1

        avg_dl = 50.0
        k1 = 1.5
        b = 0.75

        score = 0.0
        for kw in keywords:
            kw_lower = kw.lower()
            tf = content_lower.count(kw_lower)
            if tf == 0:
                continue

            term_freq = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc_len / avg_dl))
            idf = math.log(2.0)
            score += term_freq * idf

        return min(1.0, score / max(len(keywords), 1))

    @staticmethod
    def _symbol_name_score(query: str, name: str) -> float:
        """Score how well a symbol name matches the query."""
        if not name:
            return 0.0

        query_lower = query.lower()
        name_lower = name.lower()

        if query_lower == name_lower:
            return 1.0
        if query_lower in name_lower:
            return 0.8

        query_tokens = set(query_lower.split())
        name_tokens = set(re.split(r"[._\s]", name_lower))
        overlap = len(query_tokens & name_tokens)
        if overlap:
            return min(0.7, overlap / len(query_tokens) * 0.7)

        return 0.0

    @staticmethod
    def _extract_highlights(content: str, keywords: list[str]) -> list[str]:
        """Extract matching snippets as highlights."""
        highlights: list[str] = []
        if not content:
            return highlights

        lines = content.split("\n")
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue
            for kw in keywords:
                if kw.lower() in line_stripped.lower():
                    highlights.append(line_stripped[:200])
                    break
            if len(highlights) >= 5:
                break

        return highlights

    @staticmethod
    def _safe_regex(pattern: str) -> bool:
        """Check if a regex pattern is safe (no catastrophic backtracking risk)."""
        if not pattern or len(pattern) > 500:
            return False

        if pattern in _DANGEROUS_PATTERNS:
            return False

        nested_groups = len(re.findall(r"\((?:[^)]*\([^)]*\))*[^)]*\)\+", pattern))
        if nested_groups > 0:
            return False

        quantified_groups = re.findall(r"\([^)]*\)[*+?]{2,}", pattern)
        if quantified_groups:
            return False

        star_star = re.findall(r"\*{2,}|\+{2,}", pattern)
        if star_star:
            return False

        alternation_in_group = re.findall(r"\([^)]*\|[^)]*\)[*+]", pattern)
        if len(alternation_in_group) > 3:
            return False

        return True

    @staticmethod
    def _glob_to_regex(pattern: str) -> str:
        """Convert a glob pattern to a regex pattern."""
        regex = re.escape(pattern)
        regex = regex.replace(r"\*\*", ".*")
        regex = regex.replace(r"\*", "[^/]*")
        regex = regex.replace(r"\?", "[^/]")
        return f"^{regex}$"

    @staticmethod
    def _extract_keyword_from_regex(pattern: str) -> str:
        """Extract a likely keyword from a regex pattern for pre-filtering."""
        literal = re.sub(r"[\\()\[\]{}*+?.|^$]", " ", pattern)
        words = [w.strip() for w in literal.split() if len(w.strip()) > 2]
        return words[0] if words else ""

    async def _get_transitive_callees(
        self, symbol_db_id: UUID, depth: int, max_results: int
    ) -> list[tuple[UUID, int]]:
        """BFS to find transitive callees of a symbol."""
        results: list[tuple[UUID, int]] = []
        visited: set[str] = set()
        queue: list[tuple[UUID, int]] = [(symbol_db_id, 0)]

        while queue and len(results) < max_results:
            current_id, current_depth = queue.pop(0)
            if current_depth >= depth:
                continue
            key = str(current_id)
            if key in visited:
                continue
            visited.add(key)

            stmt = (
                select(CodeCall.callee_symbol_id)
                .where(CodeCall.caller_symbol_id == current_id)
                .limit(10)
            )
            result = await self._db.execute(stmt)
            for (callee_id,) in result.all():
                if callee_id and str(callee_id) not in visited:
                    results.append((callee_id, current_depth + 1))
                    queue.append((callee_id, current_depth + 1))

        return results

    async def _get_transitive_callers(
        self, symbol_db_id: UUID, depth: int, max_results: int
    ) -> list[tuple[UUID, int]]:
        """BFS to find transitive callers of a symbol."""
        results: list[tuple[UUID, int]] = []
        visited: set[str] = set()
        queue: list[tuple[UUID, int]] = [(symbol_db_id, 0)]

        while queue and len(results) < max_results:
            current_id, current_depth = queue.pop(0)
            if current_depth >= depth:
                continue
            key = str(current_id)
            if key in visited:
                continue
            visited.add(key)

            stmt = (
                select(CodeCall.caller_symbol_id)
                .where(CodeCall.callee_symbol_id == current_id)
                .limit(10)
            )
            result = await self._db.execute(stmt)
            for (caller_id,) in result.all():
                if caller_id and str(caller_id) not in visited:
                    results.append((caller_id, current_depth + 1))
                    queue.append((caller_id, current_depth + 1))

        return results

    async def _resolve_symbol(self, symbol_id: str) -> CodeSymbol | None:
        stmt = select(CodeSymbol).where(CodeSymbol.symbol_id == symbol_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def _resolve_symbol_by_db_id(self, db_id: UUID) -> CodeSymbol | None:
        stmt = select(CodeSymbol).where(CodeSymbol.id == db_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_file_path(self, file_id: UUID) -> str:
        stmt = select(CodeFile.file_path).where(CodeFile.id == file_id)
        result = await self._db.execute(stmt)
        row = result.scalar_one_or_none()
        return row or ""
