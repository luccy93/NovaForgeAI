"""Volume 43 — fusion (Reciprocal Rank Fusion) and configurable reranking."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from app.rag.config import RagConfig, DEFAULT_RAG_CONFIG
from app.rag.schemas import RetrievedChunk

logger = logging.getLogger(__name__)


def reciprocal_rank_fusion(
    results_by_method: dict[str, list[RetrievedChunk]],
    weights: Optional[dict[str, float]] = None,
    k: int = 60,
) -> list[RetrievedChunk]:
    """Fuse multiple ranked result lists via Reciprocal Rank Fusion.

    Each method contributes ``weight / (k + rank)`` to a chunk's combined
    score. Chunks appearing in multiple methods are merged (scores kept).
    """
    weights = weights or {}
    fused: dict[str, RetrievedChunk] = {}
    for method, results in results_by_method.items():
        w = weights.get(method, 1.0)
        for rank, chunk in enumerate(results, start=1):
            contrib = w / (k + rank)
            existing = fused.get(chunk.chunk_id)
            if existing is None:
                new = RetrievedChunk(**chunk.to_dict())
                new.scores = dict(chunk.scores)
                new.scores["rrf"] = contrib
                new.retrieval_method = "hybrid"
                fused[chunk.chunk_id] = new
            else:
                for kk, vv in chunk.scores.items():
                    existing.scores[kk] = existing.scores.get(kk, 0.0) + vv
                existing.scores["rrf"] = existing.scores.get("rrf", 0.0) + contrib
    out = list(fused.values())
    out.sort(key=lambda c: c.scores.get("rrf", 0.0), reverse=True)
    return out


class Reranker:
    """Configurable reranker.

    Strategies:
      * ``rrf``      — sort by RRF score already computed during fusion.
      * ``weighted`` — multi-factor weighted score (default, always available).
      * ``cross_encoder`` — uses sentence-transformers CrossEncoder when
        installed; raises ``RuntimeError`` if unavailable so the caller can
        fall back (never silently returns unranked results).
    """

    def __init__(self, config: Optional[RagConfig] = None) -> None:
        self.config = config or DEFAULT_RAG_CONFIG

    def rerank(
        self,
        chunks: list[RetrievedChunk],
        query: str,
        strategy: Optional[str] = None,
        query_classification=None,
    ) -> list[RetrievedChunk]:
        strategy = strategy or self.config.rerank_strategy
        if strategy == "rrf":
            return sorted(chunks, key=lambda c: c.scores.get("rrf", 0.0), reverse=True)
        if strategy == "cross_encoder":
            return self._cross_encoder(chunks, query)
        return self._weighted(chunks, query)

    def _weighted(self, chunks: list[RetrievedChunk], query: str) -> list[RetrievedChunk]:
        w = self.config.rerank
        for c in chunks:
            s = c.scores
            score = (
                w.query_relevance * s.get("rrf", s.get("lexical", 0.0))
                + w.semantic_similarity * s.get("semantic", 0.0)
                + w.symbol_relevance * s.get("symbol", s.get("graph", 0.0))
                + w.graph_relevance * s.get("graph", 0.0)
                + w.source_quality * self._source_quality(c)
                + w.freshness * self._freshness(c)
                + w.permission_validity * 1.0
            )
            c.scores["rerank"] = score
        return sorted(chunks, key=lambda c: c.scores.get("rerank", 0.0), reverse=True)

    def _cross_encoder(self, chunks: list[RetrievedChunk], query: str) -> list[RetrievedChunk]:
        try:  # pragma: no cover - optional dependency
            from sentence_transformers import CrossEncoder  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "cross_encoder reranker requires sentence-transformers; "
                "configure rerank_strategy='weighted' or install the dependency"
            ) from exc
        model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        pairs = [(query, c.content) for c in chunks]
        scores = model.predict(pairs)
        for c, sc in zip(chunks, scores):
            c.scores["rerank"] = float(sc)
        return sorted(chunks, key=lambda c: c.scores.get("rerank", 0.0), reverse=True)

    @staticmethod
    def _source_quality(c: RetrievedChunk) -> float:
        q = (c.metadata or {}).get("quality") or c.metadata.get("source_quality") or "maintained"
        return {"official": 1.0, "maintained": 0.8, "generated": 0.5, "user-uploaded": 0.4,
                "external": 0.3, "stale": 0.1}.get(str(q).lower(), 0.6)

    @staticmethod
    def _freshness(c: RetrievedChunk) -> float:
        ts = c.created_at or (c.metadata or {}).get("created_at")
        if ts is None:
            return 0.6
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts)
            except Exception:
                return 0.6
        age_days = (datetime.now(timezone.utc) - ts).days
        half = max(1, 90)
        return float(0.5 ** (age_days / half))
