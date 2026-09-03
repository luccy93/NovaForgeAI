"""Result ranking and fusion — Volume 68.

Provides reciprocal rank fusion, weighted fusion, score normalization,
freshness boosting, and keyword-overlap reranking.
"""

import math
import re
from typing import Optional


def normalize_scores(results: list[dict]) -> list[dict]:
    """Min-max normalize the ``score`` field to 0-1."""
    if not results:
        return results

    scores = [r.get("score", 0.0) for r in results]
    min_s = min(scores)
    max_s = max(scores)
    span = max_s - min_s

    for r in results:
        if span > 0:
            r["score"] = (r.get("score", 0.0) - min_s) / span
        else:
            r["score"] = 1.0
    return results


def reciprocal_rank_fusion(
    result_lists: list[list[dict]],
    k: int = 60,
) -> list[dict]:
    """Standard RRF: score = sum(1 / (k + rank)) across lists.

    Deduplicates by document_id (falls back to chunk_id).  Returns sorted
    merged list descending by fused score.
    """
    doc_scores: dict[str, dict] = {}

    for results in result_lists:
        for rank, item in enumerate(results):
            key = _dedup_key(item)
            if key not in doc_scores:
                doc_scores[key] = {**item}
            doc_scores[key]["score"] = doc_scores[key].get("score", 0.0) + 1.0 / (k + rank + 1)

    merged = list(doc_scores.values())
    merged.sort(key=lambda r: r["score"], reverse=True)
    return merged


def weighted_fusion(
    result_lists: list[list[dict]],
    weights: list[float],
) -> list[dict]:
    """Weighted sum of normalized scores.  Deduplicates by document_id."""
    if len(result_lists) != len(weights):
        raise ValueError("result_lists and weights must have the same length")

    doc_scores: dict[str, dict] = {}

    for results, weight in zip(result_lists, weights):
        normalized = normalize_scores(list(results))
        for item in normalized:
            key = _dedup_key(item)
            if key not in doc_scores:
                doc_scores[key] = {**item}
                doc_scores[key]["score"] = 0.0
            doc_scores[key]["score"] += weight * item.get("score", 0.0)

    merged = list(doc_scores.values())
    merged.sort(key=lambda r: r["score"], reverse=True)
    return merged


def apply_freshness_boost(
    results: list[dict],
    freshness_map: dict,
) -> list[dict]:
    """Multiply each result's score by its freshness_score (0-1).

    ``freshness_map`` = ``{doc_id: freshness_score}``
    """
    for r in results:
        doc_id = r.get("document_id")
        if doc_id is not None:
            fs = freshness_map.get(str(doc_id), 1.0)
            r["score"] = r.get("score", 0.0) * fs
            r["freshness_score"] = fs
    results.sort(key=lambda r: r["score"], reverse=True)
    return results


def rerank_by_relevance(results: list[dict], query: str) -> list[dict]:
    """Simple keyword-overlap reranking.

    Counts query term occurrences in snippet / title and adds a bonus.
    """
    terms = [t.lower() for t in re.split(r"\W+", query) if t.strip()]
    if not terms:
        return results

    for r in results:
        text = " ".join(
            filter(None, [r.get("title", ""), r.get("snippet", "")])
        ).lower()
        hits = sum(text.count(t) for t in terms)
        bonus = min(hits * 0.05, 0.5)
        r["score"] = r.get("score", 0.0) + bonus

    results.sort(key=lambda r: r["score"], reverse=True)
    return results


# ─── Internal helpers ────────────────────────────────────────────────────────


def _dedup_key(item: dict) -> str:
    doc_id = item.get("document_id")
    if doc_id is not None:
        return f"doc:{doc_id}"
    chunk_id = item.get("chunk_id")
    if chunk_id is not None:
        return f"chunk:{chunk_id}"
    return f"obj:{id(item)}"
