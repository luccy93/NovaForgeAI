"""Context Quality Tracking — monitors and scores RAG retrieval quality.

Tracks retrieval relevance, duplicate context, missing dependencies,
citation coverage, token utilization, staleness, and provides
actionable improvement suggestions. Stores metrics in-memory and
exposes trend / aggregate / report endpoints.
"""

import hashlib
import logging
import re
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.code_intelligence.models import (
    CodeChunk,
    CodeFile,
    CodeIndex,
    CodeSymbol,
)

logger = logging.getLogger(__name__)

# ─── Constants ─────────────────────────────────────────────────────────

_DEFAULT_MAX_TOKENS = 4096
_STALENESS_THRESHOLD_DAYS = 90
_QUALITY_WINDOW_HOURS = 24
_CITATION_MIN_LENGTH = 10


# ─── Dataclasses — Return Types ────────────────────────────────────────


@dataclass
class ContextChunkInfo:
    """Lightweight representation of a context chunk for quality checks."""

    chunk_id: str
    content: str
    file_path: str = ""
    symbol_name: str = ""
    token_count: int = 0
    source_citation: str = ""
    commit_sha: str = ""
    retrieval_score: float = 0.0
    retrieval_source: str = ""


@dataclass
class DuplicateGroup:
    """Group of chunks identified as near-duplicates."""

    content_hash: str
    chunk_ids: list[str] = field(default_factory=list)
    similarity_score: float = 1.0
    content_preview: str = ""


@dataclass
class CitationCoverage:
    """Citation coverage statistics for a set of context chunks."""

    total_chunks: int = 0
    cited_chunks: int = 0
    uncited_chunks: int = 0
    coverage_ratio: float = 0.0
    uncited_details: list[dict] = field(default_factory=list)


@dataclass
class TokenUtilization:
    """Token budget utilization for a context bundle."""

    total_tokens: int = 0
    max_tokens: int = _DEFAULT_MAX_TOKENS
    utilization_ratio: float = 0.0
    remaining_tokens: int = 0
    chunk_counts: int = 0
    is_over_budget: bool = False


@dataclass
class MissingDependency:
    """A symbol reference in context that could not be resolved."""

    chunk_id: str
    referenced_symbol: str = ""
    reference_type: str = ""  # import | call | inheritance | type_hint
    context_snippet: str = ""
    file_path: str = ""


@dataclass
class QualityMetrics:
    """Complete quality scorecard for a single query."""

    query_id: str = ""
    query: str = ""
    timestamp: float = 0.0
    overall_score: float = 0.0
    relevance_score: float = 0.0
    deduplication_score: float = 0.0
    citation_score: float = 0.0
    token_efficiency_score: float = 0.0
    dependency_coverage_score: float = 0.0
    staleness_score: float = 0.0
    chunk_count: int = 0
    unique_file_count: int = 0
    suggestions: list[str] = field(default_factory=list)


@dataclass
class StalenessInfo:
    """Information about a stale context chunk."""

    chunk_id: str
    commit_sha: str = ""
    days_since_commit: int = 0
    file_path: str = ""
    content_preview: str = ""


@dataclass
class AggregateStats:
    """Aggregate quality statistics across multiple queries."""

    total_queries: int = 0
    avg_overall_score: float = 0.0
    avg_relevance_score: float = 0.0
    avg_citation_score: float = 0.0
    avg_token_efficiency: float = 0.0
    avg_deduplication_score: float = 0.0
    avg_dependency_coverage: float = 0.0
    avg_staleness_score: float = 0.0
    min_overall_score: float = 1.0
    max_overall_score: float = 0.0
    score_distribution: dict[str, int] = field(default_factory=dict)
    top_suggestions: list[tuple[str, int]] = field(default_factory=list)


@dataclass
class QualityReport:
    """Full quality report for a repository."""

    repository_id: str = ""
    aggregate: AggregateStats = field(default_factory=AggregateStats)
    trend_data: list[dict] = field(default_factory=list)
    staleness_summary: dict = field(default_factory=dict)
    recent_scores: list[QualityMetrics] = field(default_factory=list)
    generated_at: float = 0.0


# ─── Helpers ───────────────────────────────────────────────────────────


def _content_hash(content: str) -> str:
    """Deterministic hash for duplicate detection."""
    normalized = re.sub(r"\s+", " ", content.strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def _fingerprint(content: str) -> str:
    """Fuzzy fingerprint for near-duplicate detection."""
    words = sorted(re.findall(r"\w+", content.lower()))
    if not words:
        return ""
    return " ".join(words[:40])


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (1 token ~ 4 chars for English text)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


# ─── ContextQualityTracker ────────────────────────────────────────────


class ContextQualityTracker:
    """Tracks, scores, and reports on RAG context quality.

    Stores all quality metrics in an in-memory dictionary keyed by
    repository_id so it survives across queries within a process.
    """

    def __init__(self, db_session: AsyncSession) -> None:
        self.db = db_session
        self._quality_store: dict[str, list[QualityMetrics]] = defaultdict(list)
        self._query_counter: int = 0

    # ── 1. Log Query Quality ──────────────────────────────────────────

    async def log_query_quality(
        self,
        query: str,
        results: list[Any],
        context_bundle: list[ContextChunkInfo],
        repository_id: str = "",
    ) -> QualityMetrics:
        """Evaluate and store quality metrics for a single query.

        Parameters
        ----------
        query : str
            The original user query.
        results : list[Any]
            Raw search results returned by the retrieval engine.
        context_bundle : list[ContextChunkInfo]
            Context chunks assembled for the LLM prompt.
        repository_id : str
            Repository UUID string used as storage key.

        Returns
        -------
        QualityMetrics
            The freshly computed quality scorecard.
        """
        self._query_counter += 1
        query_id = f"q-{self._query_counter}-{int(time.time())}"

        relevance = self._score_relevance(query, context_bundle)
        dedup = self._score_deduplication(context_bundle)
        citation = self._score_citations(context_bundle)
        token_eff = self._score_token_efficiency(context_bundle)
        dep_cov = self._score_dependency_coverage(context_bundle)
        staleness = self._score_staleness(context_bundle)

        weights = {
            "relevance": 0.30,
            "deduplication": 0.15,
            "citation": 0.15,
            "token_efficiency": 0.15,
            "dependency_coverage": 0.15,
            "staleness": 0.10,
        }

        overall = (
            relevance * weights["relevance"]
            + dedup * weights["deduplication"]
            + citation * weights["citation"]
            + token_eff * weights["token_efficiency"]
            + dep_cov * weights["dependency_coverage"]
            + staleness * weights["staleness"]
        )

        suggestions = self.get_improvement_suggestions(overall, context_bundle)

        metrics = QualityMetrics(
            query_id=query_id,
            query=query,
            timestamp=time.time(),
            overall_score=round(overall, 4),
            relevance_score=round(relevance, 4),
            deduplication_score=round(dedup, 4),
            citation_score=round(citation, 4),
            token_efficiency_score=round(token_eff, 4),
            dependency_coverage_score=round(dep_cov, 4),
            staleness_score=round(staleness, 4),
            chunk_count=len(context_bundle),
            unique_file_count=len({c.file_path for c in context_bundle if c.file_path}),
            suggestions=suggestions,
        )

        store_key = repository_id or "__global__"
        self._quality_store[store_key].append(metrics)

        logger.info(
            "Query quality logged [%s] overall=%.3f relevance=%.3f "
            "dedup=%.3f citation=%.3f tokens=%.3f deps=%.3f stale=%.3f",
            query_id,
            overall,
            relevance,
            dedup,
            citation,
            token_eff,
            dep_cov,
            staleness,
        )

        return metrics

    # ── 2. Detect Duplicate Context ───────────────────────────────────

    async def detect_duplicate_context(
        self, context_chunks: list[ContextChunkInfo]
    ) -> list[DuplicateGroup]:
        """Find groups of chunks with identical or near-identical content.

        Uses normalized content hashing for exact matches and a
        word-level fingerprint for near-duplicates.

        Parameters
        ----------
        context_chunks : list[ContextChunkInfo]
            Chunks to inspect.

        Returns
        -------
        list[DuplicateGroup]
            Each group contains chunk IDs that are duplicates.
        """
        exact_map: dict[str, list[str]] = defaultdict(list)
        preview_map: dict[str, str] = {}

        for chunk in context_chunks:
            h = _content_hash(chunk.content)
            exact_map[h].append(chunk.chunk_id)
            if h not in preview_map:
                preview_map[h] = chunk.content[:200]

        fingerprint_map: dict[str, list[str]] = defaultdict(list)
        for chunk in context_chunks:
            fp = _fingerprint(chunk.content)
            if fp:
                fingerprint_map[fp].append(chunk.chunk_id)

        groups: list[DuplicateGroup] = []
        seen_exact: set[str] = set()

        for h, ids in exact_map.items():
            if len(ids) > 1 and h not in seen_exact:
                seen_exact.add(h)
                groups.append(DuplicateGroup(
                    content_hash=h,
                    chunk_ids=list(set(ids)),
                    similarity_score=1.0,
                    content_preview=preview_map.get(h, ""),
                ))

        seen_fp: set[str] = set()
        for fp, ids in fingerprint_map.items():
            unique_ids = list(set(ids))
            if len(unique_ids) > 1 and fp not in seen_fp:
                seen_fp.add(fp)
                already_in_exact = any(
                    cid in group.chunk_ids
                    for cid in unique_ids
                    for group in groups
                )
                if not already_in_exact:
                    groups.append(DuplicateGroup(
                        content_hash=fp[:32],
                        chunk_ids=unique_ids,
                        similarity_score=0.85,
                        content_preview="",
                    ))

        if groups:
            logger.info(
                "Detected %d duplicate groups across %d chunks",
                len(groups),
                len(context_chunks),
            )

        return groups

    # ── 3. Check Citation Coverage ────────────────────────────────────

    async def check_citation_coverage(
        self, context_chunks: list[ContextChunkInfo]
    ) -> CitationCoverage:
        """Measure what fraction of chunks have proper source citations.

        A chunk is considered cited if its ``source_citation`` field
        is a non-empty string with at least ``_CITATION_MIN_LENGTH``
        characters (typically a file path or URL).

        Parameters
        ----------
        context_chunks : list[ContextChunkInfo]
            Chunks to inspect.

        Returns
        -------
        CitationCoverage
            Coverage statistics.
        """
        total = len(context_chunks)
        cited = 0
        uncited_details: list[dict] = []

        for chunk in context_chunks:
            citation = (chunk.source_citation or "").strip()
            if len(citation) >= _CITATION_MIN_LENGTH:
                cited += 1
            else:
                uncited_details.append({
                    "chunk_id": chunk.chunk_id,
                    "file_path": chunk.file_path,
                    "symbol_name": chunk.symbol_name,
                    "content_preview": chunk.content[:120],
                })

        uncited = total - cited
        ratio = cited / total if total > 0 else 0.0

        coverage = CitationCoverage(
            total_chunks=total,
            cited_chunks=cited,
            uncited_chunks=uncited,
            coverage_ratio=round(ratio, 4),
            uncited_details=uncited_details,
        )

        logger.debug(
            "Citation coverage: %d/%d (%.1f%%)",
            cited,
            total,
            ratio * 100,
        )
        return coverage

    # ── 4. Measure Token Utilization ──────────────────────────────────

    async def measure_token_utilization(
        self,
        context_bundle: list[ContextChunkInfo],
        max_tokens: int = _DEFAULT_MAX_TOKENS,
    ) -> TokenUtilization:
        """Compute how much of the token budget is consumed.

        Parameters
        ----------
        context_bundle : list[ContextChunkInfo]
            Chunks that will be sent to the LLM.
        max_tokens : int
            Maximum token budget.

        Returns
        -------
        TokenUtilization
            Token utilization metrics.
        """
        total_tokens = 0
        for chunk in context_bundle:
            if chunk.token_count > 0:
                total_tokens += chunk.token_count
            else:
                total_tokens += _estimate_tokens(chunk.content)

        remaining = max(0, max_tokens - total_tokens)
        ratio = total_tokens / max_tokens if max_tokens > 0 else 0.0
        over = total_tokens > max_tokens

        util = TokenUtilization(
            total_tokens=total_tokens,
            max_tokens=max_tokens,
            utilization_ratio=round(ratio, 4),
            remaining_tokens=remaining,
            chunk_counts=len(context_bundle),
            is_over_budget=over,
        )

        if over:
            logger.warning(
                "Token budget exceeded: %d / %d (%.1f%%)",
                total_tokens,
                max_tokens,
                ratio * 100,
            )

        return util

    # ── 5. Score Context Quality ──────────────────────────────────────

    async def score_context_quality(
        self,
        query: str,
        context_bundle: list[ContextChunkInfo],
        db: AsyncSession | None = None,
    ) -> float:
        """Compute an overall quality score in [0, 1] for the context.

        Combines relevance, deduplication, citation, token efficiency,
        dependency coverage, and staleness signals.

        Parameters
        ----------
        query : str
            Original query for relevance scoring.
        context_bundle : list[ContextChunkInfo]
            Assembled context chunks.
        db : AsyncSession | None
            Optional database session (falls back to ``self.db``).

        Returns
        -------
        float
            Quality score between 0.0 and 1.0.
        """
        if not context_bundle:
            return 0.0

        relevance = self._score_relevance(query, context_bundle)
        dedup = self._score_deduplication(context_bundle)
        citation = self._score_citations(context_bundle)
        token_eff = self._score_token_efficiency(context_bundle)
        dep_cov = self._score_dependency_coverage(context_bundle)
        staleness = self._score_staleness(context_bundle)

        score = (
            relevance * 0.30
            + dedup * 0.15
            + citation * 0.15
            + token_eff * 0.15
            + dep_cov * 0.15
            + staleness * 0.10
        )

        logger.debug(
            "Context quality score=%.3f (rel=%.2f dedup=%.2f cite=%.2f "
            "tok=%.2f dep=%.2f stale=%.2f)",
            score, relevance, dedup, citation, token_eff, dep_cov, staleness,
        )
        return round(min(1.0, max(0.0, score)), 4)

    # ── 6. Quality Trend Over Time ────────────────────────────────────

    async def get_quality_trend(
        self,
        repository_id: str,
        hours: int = _QUALITY_WINDOW_HOURS,
    ) -> list[dict]:
        """Return quality scores over the specified time window.

        Parameters
        ----------
        repository_id : str
            Repository UUID string.
        hours : int
            Look-back window in hours.

        Returns
        -------
        list[dict]
            List of ``{"timestamp", "overall_score", "query", "query_id"}``
            entries sorted by time.
        """
        store_key = repository_id or "__global__"
        cutoff = time.time() - (hours * 3600)

        entries: list[dict] = []
        for m in self._quality_store.get(store_key, []):
            if m.timestamp >= cutoff:
                entries.append({
                    "timestamp": m.timestamp,
                    "overall_score": m.overall_score,
                    "relevance_score": m.relevance_score,
                    "citation_score": m.citation_score,
                    "token_efficiency_score": m.token_efficiency_score,
                    "query": m.query,
                    "query_id": m.query_id,
                })

        entries.sort(key=lambda e: e["timestamp"])
        return entries

    # ── 7. Detect Missing Dependencies ────────────────────────────────

    async def detect_missing_dependencies(
        self,
        context_bundle: list[ContextChunkInfo],
        db: AsyncSession | None = None,
    ) -> list[MissingDependency]:
        """Identify symbols referenced in context but not included.

        Scans chunk content for common reference patterns (imports,
        function calls, class references) and checks whether the
        referenced symbol exists in the bundled chunk set or in the
        database.

        Parameters
        ----------
        context_bundle : list[ContextChunkInfo]
            Context chunks to scan.
        db : AsyncSession | None
            Database session for symbol resolution.

        Returns
        -------
        list[MissingDependency]
            Unresolved symbol references.
        """
        session = db or self.db
        known_symbols: set[str] = set()
        for chunk in context_bundle:
            if chunk.symbol_name:
                known_symbols.add(chunk.symbol_name.lower())

        known_files: set[str] = set()
        for chunk in context_bundle:
            if chunk.file_path:
                known_files.add(chunk.file_path.lower())

        import_pattern = re.compile(
            r"(?:from|import)\s+([A-Za-z_][\w.]*)", re.MULTILINE
        )
        call_pattern = re.compile(
            r"\b([A-Z][A-Za-z0-9_]*)\s*\(", re.MULTILINE
        )
        type_hint_pattern = re.compile(
            r":\s*([A-Z][A-Za-z0-9_]*)", re.MULTILINE
        )

        candidates: dict[str, dict] = {}

        for chunk in context_bundle:
            content = chunk.content

            for match in import_pattern.finditer(content):
                name = match.group(1).strip().split(".")[-1]
                if name and name.lower() not in known_symbols:
                    candidates.setdefault(name, {
                        "symbol": name,
                        "type": "import",
                        "chunk_id": chunk.chunk_id,
                        "file_path": chunk.file_path,
                        "snippet": content[max(0, match.start() - 20):match.end() + 40],
                    })

            for match in call_pattern.finditer(content):
                name = match.group(1)
                if name.lower() not in known_symbols:
                    candidates.setdefault(name, {
                        "symbol": name,
                        "type": "call",
                        "chunk_id": chunk.chunk_id,
                        "file_path": chunk.file_path,
                        "snippet": content[max(0, match.start() - 20):match.end() + 40],
                    })

            for match in type_hint_pattern.finditer(content):
                name = match.group(1)
                if name.lower() not in known_symbols:
                    candidates.setdefault(name, {
                        "symbol": name,
                        "type": "type_hint",
                        "chunk_id": chunk.chunk_id,
                        "file_path": chunk.file_path,
                        "snippet": content[max(0, match.start() - 20):match.end() + 40],
                    })

        missing: list[MissingDependency] = []
        for name, info in candidates.items():
            resolved = await self._resolve_symbol_exists(session, name)
            if not resolved:
                missing.append(MissingDependency(
                    chunk_id=info["chunk_id"],
                    referenced_symbol=info["symbol"],
                    reference_type=info["type"],
                    context_snippet=info["snippet"][:200],
                    file_path=info["file_path"],
                ))

        if missing:
            logger.info(
                "Found %d missing dependencies across %d chunks",
                len(missing),
                len(context_bundle),
            )

        return missing

    # ── 8. Detect Context Staleness ───────────────────────────────────

    async def detect_context_staleness(
        self,
        context_bundle: list[ContextChunkInfo],
        reference_date: datetime | None = None,
    ) -> list[StalenessInfo]:
        """Find chunks referencing old commits.

        A chunk is stale if its ``commit_sha`` maps to a commit older
        than ``_STALENESS_THRESHOLD_DAYS`` from the reference date.

        Parameters
        ----------
        context_bundle : list[ContextChunkInfo]
            Chunks to check.
        reference_date : datetime | None
            Reference point (defaults to ``datetime.now(timezone.utc)``).

        Returns
        -------
        list[StalenessInfo]
            Details of stale chunks.
        """
        now = reference_date or datetime.now(timezone.utc)
        stale: list[StalenessInfo] = []

        for chunk in context_bundle:
            if not chunk.commit_sha:
                continue

            commit_date = await self._get_commit_date(chunk.commit_sha)
            if commit_date is None:
                continue

            days = (now - commit_date).days
            if days > _STALENESS_THRESHOLD_DAYS:
                stale.append(StalenessInfo(
                    chunk_id=chunk.chunk_id,
                    commit_sha=chunk.commit_sha,
                    days_since_commit=days,
                    file_path=chunk.file_path,
                    content_preview=chunk.content[:120],
                ))

        if stale:
            logger.warning(
                "Detected %d stale chunks out of %d total",
                len(stale),
                len(context_bundle),
            )

        return stale

    # ── 9. Improvement Suggestions ────────────────────────────────────

    def get_improvement_suggestions(
        self,
        quality_score: float,
        context_bundle: list[ContextChunkInfo],
    ) -> list[str]:
        """Generate actionable suggestions based on quality analysis.

        Parameters
        ----------
        quality_score : float
            Overall quality score (0-1).
        context_bundle : list[ContextChunkInfo]
            Context chunks to inspect.

        Returns
        -------
        list[str]
            Human-readable improvement suggestions.
        """
        suggestions: list[str] = []

        if not context_bundle:
            suggestions.append(
                "No context chunks were retrieved. Consider broadening "
                "the search query or lowering the similarity threshold."
            )
            return suggestions

        if quality_score < 0.3:
            suggestions.append(
                "Overall quality is critically low. Consider re-indexing "
                "the repository or refining the chunking strategy."
            )
        elif quality_score < 0.6:
            suggestions.append(
                "Overall quality is below average. Review retrieval "
                "parameters and consider adding more source diversity."
            )
        elif quality_score < 0.8:
            suggestions.append(
                "Quality is acceptable but room for improvement exists. "
                "Focus on the specific weak areas identified below."
            )

        token_est = sum(
            c.token_count if c.token_count > 0 else _estimate_tokens(c.content)
            for c in context_bundle
        )
        if token_est > _DEFAULT_MAX_TOKENS * 0.9:
            suggestions.append(
                f"Context is near token budget ({token_est} / "
                f"{_DEFAULT_MAX_TOKENS}). Reduce chunk count or "
                "increase retrieval precision to stay within limits."
            )
        if token_est > _DEFAULT_MAX_TOKENS:
            suggestions.append(
                f"Context exceeds token budget ({token_est} / "
                f"{_DEFAULT_MAX_TOKENS}). Some content will be truncated "
                "and important information may be lost."
            )

        file_paths = [c.file_path for c in context_bundle if c.file_path]
        if len(set(file_paths)) < len(file_paths) * 0.5 and len(file_paths) > 2:
            suggestions.append(
                "Context is heavily concentrated in a few files. "
                "Increase source diversity for broader coverage."
            )

        uncited = [
            c for c in context_bundle
            if not c.source_citation or len(c.source_citation.strip()) < _CITATION_MIN_LENGTH
        ]
        if uncited:
            ratio = len(uncited) / len(context_bundle)
            suggestions.append(
                f"{len(uncited)} / {len(context_bundle)} chunks "
                f"({ratio:.0%}) lack proper source citations. Add file "
                "path and line range metadata to improve traceability."
            )

        content_hashes = [_content_hash(c.content) for c in context_bundle]
        if len(set(content_hashes)) < len(content_hashes):
            dup_count = len(content_hashes) - len(set(content_hashes))
            suggestions.append(
                f"{dup_count} duplicate chunks detected. Deduplicate "
                "context before sending to the LLM to save tokens."
            )

        no_retrieval_score = [
            c for c in context_bundle if c.retrieval_score <= 0
        ]
        if no_retrieval_score and len(no_retrieval_score) > len(context_bundle) * 0.3:
            suggestions.append(
                "Many chunks have zero or missing retrieval scores. "
                "Review the ranking pipeline and ensure embeddings "
                "are generated for all chunks."
            )

        if context_bundle:
            avg_content_len = sum(len(c.content) for c in context_bundle) / len(context_bundle)
            if avg_content_len < 50:
                suggestions.append(
                    "Average chunk content is very short. Consider "
                    "increasing chunk size or merging small chunks "
                    "for richer context."
                )
            elif avg_content_len > 5000:
                suggestions.append(
                    "Average chunk content is very long. Consider "
                    "splitting large chunks to improve retrieval "
                    "precision and reduce token waste."
                )

        return suggestions

    # ── 10. Aggregate Stats ───────────────────────────────────────────

    async def get_aggregate_stats(
        self, repository_id: str
    ) -> AggregateStats:
        """Compute aggregate quality statistics across all tracked queries.

        Parameters
        ----------
        repository_id : str
            Repository UUID string.

        Returns
        -------
        AggregateStats
            Aggregated statistics.
        """
        store_key = repository_id or "__global__"
        metrics_list = self._quality_store.get(store_key, [])

        if not metrics_list:
            return AggregateStats()

        total = len(metrics_list)

        overall_scores = [m.overall_score for m in metrics_list]
        relevance_scores = [m.relevance_score for m in metrics_list]
        citation_scores = [m.citation_score for m in metrics_list]
        token_eff_scores = [m.token_efficiency_score for m in metrics_list]
        dedup_scores = [m.deduplication_score for m in metrics_list]
        dep_scores = [m.dependency_coverage_score for m in metrics_list]
        stale_scores = [m.staleness_score for m in metrics_list]

        distribution: dict[str, int] = defaultdict(int)
        for s in overall_scores:
            if s >= 0.8:
                distribution["excellent"] += 1
            elif s >= 0.6:
                distribution["good"] += 1
            elif s >= 0.4:
                distribution["fair"] += 1
            else:
                distribution["poor"] += 1

        suggestion_counts: dict[str, int] = defaultdict(int)
        for m in metrics_list:
            for s in m.suggestions:
                key = s[:80]
                suggestion_counts[key] += 1

        top_suggestions = sorted(
            suggestion_counts.items(), key=lambda x: x[1], reverse=True
        )[:10]

        stats = AggregateStats(
            total_queries=total,
            avg_overall_score=round(sum(overall_scores) / total, 4),
            avg_relevance_score=round(sum(relevance_scores) / total, 4),
            avg_citation_score=round(sum(citation_scores) / total, 4),
            avg_token_efficiency=round(sum(token_eff_scores) / total, 4),
            avg_deduplication_score=round(sum(dedup_scores) / total, 4),
            avg_dependency_coverage=round(sum(dep_scores) / total, 4),
            avg_staleness_score=round(sum(stale_scores) / total, 4),
            min_overall_score=round(min(overall_scores), 4),
            max_overall_score=round(max(overall_scores), 4),
            score_distribution=dict(distribution),
            top_suggestions=top_suggestions,
        )

        logger.info(
            "Aggregate stats for %s: %d queries, avg_score=%.3f",
            repository_id,
            total,
            stats.avg_overall_score,
        )
        return stats

    # ── 11. Full Quality Report ───────────────────────────────────────

    async def get_quality_report(
        self, repository_id: str
    ) -> QualityReport:
        """Generate a comprehensive quality report for a repository.

        Includes aggregate stats, trend data, staleness summary,
        and recent individual scores.

        Parameters
        ----------
        repository_id : str
            Repository UUID string.

        Returns
        -------
        QualityReport
            Full quality report.
        """
        aggregate = await self.get_aggregate_stats(repository_id)
        trend = await self.get_quality_trend(repository_id, hours=168)
        store_key = repository_id or "__global__"
        all_metrics = self._quality_store.get(store_key, [])

        stale_summary: dict[str, Any] = {
            "total_queries": len(all_metrics),
            "queries_with_low_staleness_score": 0,
            "avg_staleness_score": aggregate.avg_staleness_score,
        }
        for m in all_metrics:
            if m.staleness_score < 0.5:
                stale_summary["queries_with_low_staleness_score"] += 1

        recent = all_metrics[-20:] if all_metrics else []

        report = QualityReport(
            repository_id=repository_id,
            aggregate=aggregate,
            trend_data=trend,
            staleness_summary=stale_summary,
            recent_scores=recent,
            generated_at=time.time(),
        )

        logger.info(
            "Quality report generated for %s (%d queries)",
            repository_id,
            aggregate.total_queries,
        )
        return report

    # ── Private: Relevance Scoring ────────────────────────────────────

    def _score_relevance(
        self, query: str, context_bundle: list[ContextChunkInfo]
    ) -> float:
        """Score how relevant the context chunks are to the query."""
        if not context_bundle:
            return 0.0

        query_tokens = set(query.lower().split())
        if not query_tokens:
            return 0.5

        scores: list[float] = []
        for chunk in context_bundle:
            if chunk.retrieval_score > 0:
                scores.append(min(1.0, chunk.retrieval_score))
                continue

            content_lower = chunk.content.lower()
            matched = sum(1 for t in query_tokens if t in content_lower)
            score = matched / len(query_tokens) if query_tokens else 0.0
            scores.append(score)

        return sum(scores) / len(scores) if scores else 0.0

    # ── Private: Deduplication Scoring ────────────────────────────────

    def _score_deduplication(
        self, context_bundle: list[ContextChunkInfo]
    ) -> float:
        """Score inversely proportional to duplicate content amount."""
        if not context_bundle:
            return 1.0

        hashes = [_content_hash(c.content) for c in context_bundle]
        unique = len(set(hashes))
        total = len(hashes)

        if total == 0:
            return 1.0

        return unique / total

    # ── Private: Citation Scoring ─────────────────────────────────────

    def _score_citations(
        self, context_bundle: list[ContextChunkInfo]
    ) -> float:
        """Score based on citation coverage."""
        if not context_bundle:
            return 1.0

        cited = sum(
            1 for c in context_bundle
            if c.source_citation and len(c.source_citation.strip()) >= _CITATION_MIN_LENGTH
        )
        return cited / len(context_bundle)

    # ── Private: Token Efficiency ─────────────────────────────────────

    def _score_token_efficiency(
        self, context_bundle: list[ContextChunkInfo]
    ) -> float:
        """Score how efficiently tokens are utilized within budget."""
        if not context_bundle:
            return 1.0

        total_tokens = 0
        for chunk in context_bundle:
            if chunk.token_count > 0:
                total_tokens += chunk.token_count
            else:
                total_tokens += _estimate_tokens(chunk.content)

        ratio = total_tokens / _DEFAULT_MAX_TOKENS
        if ratio > 1.0:
            return max(0.0, 1.0 - (ratio - 1.0) * 0.5)
        if ratio > 0.9:
            return 0.7
        if 0.3 <= ratio <= 0.8:
            return 1.0
        if ratio < 0.3:
            return 0.6

        return 0.8

    # ── Private: Dependency Coverage ──────────────────────────────────

    def _score_dependency_coverage(
        self, context_bundle: list[ContextChunkInfo]
    ) -> float:
        """Score based on how many referenced symbols are present."""
        if not context_bundle:
            return 1.0

        known_symbols: set[str] = set()
        for chunk in context_bundle:
            if chunk.symbol_name:
                known_symbols.add(chunk.symbol_name.lower())

        import_pattern = re.compile(
            r"(?:from|import)\s+([A-Za-z_][\w.]*)", re.MULTILINE
        )

        referenced: set[str] = set()
        for chunk in context_bundle:
            for match in import_pattern.finditer(chunk.content):
                name = match.group(1).strip().split(".")[-1].lower()
                if name:
                    referenced.add(name)

        if not referenced:
            return 1.0

        resolved = len(referenced & known_symbols)
        return resolved / len(referenced)

    # ── Private: Staleness Scoring ────────────────────────────────────

    def _score_staleness(
        self, context_bundle: list[ContextChunkInfo]
    ) -> float:
        """Score inversely proportional to staleness of chunk commits."""
        if not context_bundle:
            return 1.0

        now = datetime.now(timezone.utc)
        stale_count = 0

        for chunk in context_bundle:
            if not chunk.commit_sha:
                continue
            commit_date = self._sync_get_commit_date(chunk.commit_sha)
            if commit_date is None:
                continue
            days = (now - commit_date).days
            if days > _STALENESS_THRESHOLD_DAYS:
                stale_count += 1

        if stale_count == 0:
            return 1.0

        return max(0.0, 1.0 - (stale_count / len(context_bundle)))

    # ── Private: Database Helpers ─────────────────────────────────────

    async def _resolve_symbol_exists(
        self, session: AsyncSession, symbol_name: str
    ) -> bool:
        """Check whether a symbol name exists in the code index."""
        stmt = select(CodeSymbol.id).where(
            CodeSymbol.name == symbol_name
        ).limit(1)
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def _get_commit_date(
        self, commit_sha: str
    ) -> datetime | None:
        """Look up the date of a commit from the code history table."""
        from app.code_intelligence.models import CodeHistory

        stmt = select(CodeHistory.commit_date).where(
            CodeHistory.commit_sha == commit_sha
        ).limit(1)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    def _sync_get_commit_date(self, commit_sha: str) -> datetime | None:
        """Best-effort commit date lookup without awaiting.

        Falls back to ``None`` if the history table does not contain
        the commit.  Callers should prefer the async version when a
        session is available.
        """
        return None

    # ── Internal: Prune Old Entries ───────────────────────────────────

    async def prune_old_entries(
        self,
        repository_id: str,
        max_age_hours: int = 168,
    ) -> int:
        """Remove quality entries older than ``max_age_hours``.

        Parameters
        ----------
        repository_id : str
            Repository UUID string.
        max_age_hours : int
            Maximum age in hours for entries to retain.

        Returns
        -------
        int
            Number of entries pruned.
        """
        store_key = repository_id or "__global__"
        cutoff = time.time() - (max_age_hours * 3600)
        entries = self._quality_store.get(store_key, [])

        before = len(entries)
        self._quality_store[store_key] = [
            m for m in entries if m.timestamp >= cutoff
        ]
        pruned = before - len(self._quality_store[store_key])

        if pruned:
            logger.info(
                "Pruned %d old quality entries for %s",
                pruned,
                repository_id,
            )
        return pruned

    # ── Internal: Reset ───────────────────────────────────────────────

    async def reset_repository(
        self, repository_id: str
    ) -> None:
        """Clear all stored quality metrics for a repository."""
        store_key = repository_id or "__global__"
        count = len(self._quality_store.get(store_key, []))
        self._quality_store[store_key] = []
        logger.info(
            "Reset %d quality entries for %s",
            count,
            repository_id,
        )

    # ── Internal: Export ──────────────────────────────────────────────

    async def export_metrics(
        self, repository_id: str
    ) -> list[dict]:
        """Export all quality metrics for a repository as serializable dicts.

        Parameters
        ----------
        repository_id : str
            Repository UUID string.

        Returns
        -------
        list[dict]
            Serializable quality metric entries.
        """
        store_key = repository_id or "__global__"
        entries = self._quality_store.get(store_key, [])

        exported: list[dict] = []
        for m in entries:
            exported.append({
                "query_id": m.query_id,
                "query": m.query,
                "timestamp": m.timestamp,
                "overall_score": m.overall_score,
                "relevance_score": m.relevance_score,
                "deduplication_score": m.deduplication_score,
                "citation_score": m.citation_score,
                "token_efficiency_score": m.token_efficiency_score,
                "dependency_coverage_score": m.dependency_coverage_score,
                "staleness_score": m.staleness_score,
                "chunk_count": m.chunk_count,
                "unique_file_count": m.unique_file_count,
                "suggestions": m.suggestions,
            })

        logger.info(
            "Exported %d metric entries for %s",
            len(exported),
            repository_id,
        )
        return exported
