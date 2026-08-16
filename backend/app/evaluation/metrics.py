"""Evaluation metrics (Volume 34).

Pure numeric metric implementations used across the evaluation platform:

- Retrieval: Recall@K, Precision@K, MRR, NDCG, Hit Rate, Context Recall/Precision
- Generation: Faithfulness, Answer Relevance, Context Relevance, Groundedness,
  Citation Correctness/Completeness, Hallucination Rate
- Statistics: agreement, Cohen's Kappa, Fleiss' Kappa, Krippendorff's Alpha
  (reported only where the data type actually supports them)

All functions are deterministic and testable without any external services.
"""
import math
from typing import Iterable, Sequence


# ─────────────────────────────────────────────────────────── retrieval ──
def recall_at_k(relevant: Sequence[str], retrieved: Sequence[str], k: int | None = None) -> float:
    """Fraction of relevant items found in the top-k retrieved items."""
    if k is not None:
        retrieved = retrieved[:k]
    rel = set(relevant)
    if not rel:
        return 0.0
    return len(rel.intersection(retrieved)) / len(rel)


def precision_at_k(relevant: Sequence[str], retrieved: Sequence[str], k: int | None = None) -> float:
    """Fraction of retrieved top-k items that are relevant."""
    if k is not None:
        retrieved = retrieved[:k]
    if not retrieved:
        return 0.0
    return len(set(retrieved).intersection(relevant)) / len(retrieved)


def hit_rate(relevant: Sequence[str], retrieved: Sequence[str], k: int | None = None) -> float:
    """1.0 if any relevant item appears in top-k else 0.0."""
    if k is not None:
        retrieved = retrieved[:k]
    return 1.0 if set(relevant).intersection(retrieved) else 0.0


def mrr(relevant: Sequence[str], retrieved: Sequence[str]) -> float:
    """Mean reciprocal rank: 1/rank of first relevant hit (0 if none)."""
    rel = set(relevant)
    for rank, item in enumerate(retrieved, start=1):
        if item in rel:
            return 1.0 / rank
    return 0.0


def _dcg(scores: Sequence[float]) -> float:
    return sum(score / math.log2(i + 2) for i, score in enumerate(scores))


def ndcg(relevant: Sequence[str], retrieved: Sequence[str], k: int | None = None) -> float:
    """Normalized discounted cumulative gain at k."""
    if k is not None:
        retrieved = retrieved[:k]
    rel = set(relevant)
    gains = [1.0 if item in rel else 0.0 for item in retrieved]
    if not gains:
        return 0.0
    ideal = sorted(gains, reverse=True)
    ideal_gain = _dcg(ideal)
    if ideal_gain == 0:
        return 0.0
    return _dcg(gains) / ideal_gain


def context_recall(context: Sequence[str], relevant: Sequence[str]) -> float:
    """Fraction of gold evidence sentences found in the retrieved context."""
    return recall_at_k(relevant, context, k=None)


def context_precision(context: Sequence[str], relevant: Sequence[str]) -> float:
    """Precision of the retrieved context against gold evidence."""
    return precision_at_k(relevant, context, k=None)


def retrieval_report(relevant: Sequence[str], retrieved: Sequence[str],
                     k: int | None = None) -> dict:
    """Full retrieval metric bundle for one query."""
    return {
        "recall@k": round(recall_at_k(relevant, retrieved, k), 4),
        "precision@k": round(precision_at_k(relevant, retrieved, k), 4),
        "mrr": round(mrr(relevant, retrieved), 4),
        "ndcg@k": round(ndcg(relevant, retrieved, k), 4),
        "hit_rate": round(hit_rate(relevant, retrieved, k), 4),
    }


# ────────────────────────────────────────────────────────── generation ──
def faithfulness(claims_supported: int, claims_total: int) -> float:
    """Fraction of generated claims supported by the provided context."""
    if claims_total <= 0:
        return 0.0
    return claims_supported / claims_total


def answer_relevance(score_sum: float, criteria_count: int) -> float:
    """Normalized relevance (0..1) of an answer against query criteria."""
    if criteria_count <= 0:
        return 0.0
    return max(0.0, min(1.0, score_sum / criteria_count))


def context_relevance(useful_sentences: int, context_sentences: int) -> float:
    """Fraction of retrieved context sentences actually used by the answer."""
    if context_sentences <= 0:
        return 0.0
    return useful_sentences / context_sentences


def groundedness(supported_claims: int, total_claims: int) -> float:
    """Alias of faithfulness used for groundedness reporting."""
    return faithfulness(supported_claims, total_claims)


def hallucination_rate(unsupported_claims: int, total_claims: int) -> float:
    """Fraction of claims that contradict or are unsupported by context."""
    if total_claims <= 0:
        return 0.0
    return unsupported_claims / total_claims


def citation_correctness(correct_citations: int, total_citations: int) -> float:
    """Fraction of citations that actually support the claims they anchor."""
    if total_citations <= 0:
        return 0.0
    return correct_citations / total_citations


def citation_completeness(cited_claims: int, total_claims: int) -> float:
    """Fraction of claims anchored by a citation."""
    if total_claims <= 0:
        return 0.0
    return cited_claims / total_claims


def rag_generation_report(claims_supported: int, claims_total: int,
                          unsupported_claims: int, useful_sentences: int,
                          context_sentences: int, correct_citations: int,
                          total_citations: int, cited_claims: int) -> dict:
    """Full RAG generation metric bundle."""
    return {
        "faithfulness": round(faithfulness(claims_supported, claims_total), 4),
        "groundedness": round(groundedness(claims_supported, claims_total), 4),
        "hallucination_rate": round(hallucination_rate(unsupported_claims, claims_total), 4),
        "context_relevance": round(context_relevance(useful_sentences, context_sentences), 4),
        "citation_correctness": round(citation_correctness(correct_citations, total_citations), 4),
        "citation_completeness": round(citation_completeness(cited_claims, claims_total), 4),
    }


# ──────────────────────────────────────────────────────── statistics ──
def agreement_rate(labels: Sequence[Sequence[str]]) -> float:
    """Overall pairwise agreement across raters (0..1)."""
    if not labels:
        return 0.0
    total_pairs = 0
    agreements = 0
    for item_labels in labels:
        for i in range(len(item_labels)):
            for j in range(i + 1, len(item_labels)):
                total_pairs += 1
                if item_labels[i] == item_labels[j]:
                    agreements += 1
    if total_pairs == 0:
        return 0.0
    return agreements / total_pairs


def cohens_kappa(rater_a: Sequence[str], rater_b: Sequence[str]) -> float:
    """Cohen's Kappa for exactly two raters (categorical labels)."""
    if len(rater_a) != len(rater_b) or not rater_a:
        raise ValueError("raters must have equal, non-empty length")
    n = len(rater_a)
    observed = sum(1 for a, b in zip(rater_a, rater_b) if a == b) / n
    categories = set(rater_a) | set(rater_b)
    p_a = {}
    p_b = {}
    for cat in categories:
        p_a[cat] = rater_a.count(cat) / n
        p_b[cat] = rater_b.count(cat) / n
    expected = sum(p_a[cat] * p_b[cat] for cat in categories)
    if expected == 1.0:
        return 1.0
    return (observed - expected) / (1.0 - expected)


def fleiss_kappa(labels: Sequence[Sequence[str]]) -> float:
    """Fleiss' Kappa for multiple raters (n subjects x k raters)."""
    if not labels:
        return 0.0
    n_subjects = len(labels)
    n_raters = len(labels[0])
    if n_raters < 2:
        raise ValueError("at least two raters required")
    categories = sorted({cat for item in labels for cat in item})
    if not categories:
        return 0.0
    n_categories = len(categories)
    p_j = [0.0] * n_categories
    for item in labels:
        for cat_idx, cat in enumerate(categories):
            p_j[cat_idx] += item.count(cat)
    for idx in range(n_categories):
        p_j[idx] /= (n_subjects * n_raters)
    if sum(p_j) == 0:
        return 0.0
    p_e = sum(p * p for p in p_j)
    p_bar = 0.0
    for item in labels:
        counts = [item.count(cat) for cat in categories]
        agreement = sum(c * (c - 1) for c in counts) / (n_raters * (n_raters - 1))
        p_bar += agreement
    p_bar /= n_subjects
    if p_e == 1.0:
        return 1.0
    return (p_bar - p_e) / (1.0 - p_e)


def krippendorffs_alpha(ratings: Sequence[Sequence[float]]) -> float:
    """Krippendorff's Alpha (ordinal/interval ratings) — nominal used here.

    ratings: n units, each a list of ratings (missing values must be NaN).
    Computes the standard alpha = 1 - D_o / D_e with nominal distance.
    """
    n_units = len(ratings)
    if n_units == 0:
        return 0.0
    values: list[tuple[int, float]] = []
    for unit_idx, unit in enumerate(ratings):
        for r in unit:
            if r is not None and not (isinstance(r, float) and math.isnan(r)):
                values.append((unit_idx, float(r)))
    n = len(values)
    if n < 2:
        return 0.0
    by_value: dict[float, list[int]] = {}
    for unit_idx, val in values:
        by_value.setdefault(val, []).append(unit_idx)
    # observed disagreement (nominal distance)
    d_o = 0.0
    for unit_idx in range(n_units):
        idxs = [i for i, (u, _) in enumerate(values) if u == unit_idx]
        for i in range(len(idxs)):
            for j in range(i + 1, len(idxs)):
                d_o += 1.0 if values[idxs[i]][1] != values[idxs[j]][1] else 0.0
    # expected disagreement
    d_e = 0.0
    for val, unit_idxs in by_value.items():
        for i in range(len(unit_idxs)):
            for j in range(i + 1, len(unit_idxs)):
                # expected co-occurrence of the same value across units
                d_e += 1.0
    # total pair count for expectation is based on all pairs
    total_pairs = n * (n - 1) / 2.0
    if total_pairs == 0 or d_e == 0:
        return 1.0 if d_o == 0 else 0.0
    d_e = d_e / (n_units * (n_units - 1) / 2.0) * (n * (n - 1) / 2.0) if n_units > 1 else 0.0
    if d_e == 0:
        return 1.0 if d_o == 0 else 0.0
    return 1.0 - d_o / d_e


def inter_rater_report(labels: Sequence[Sequence[str]]) -> dict:
    """Aggregate reliability bundle with metric suitability notes."""
    n_raters = len(labels[0]) if labels else 0
    report = {"agreement_rate": round(agreement_rate(labels), 4), "raters": n_raters}
    if n_raters == 2:
        rater_a = [item[0] for item in labels]
        rater_b = [item[1] for item in labels]
        report["cohens_kappa"] = round(cohens_kappa(rater_a, rater_b), 4)
        report["notes"] = ["cohens_kappa: two raters, categorical labels"]
    elif n_raters > 2:
        report["fleiss_kappa"] = round(fleiss_kappa(labels), 4)
        report["notes"] = ["fleiss_kappa: multi-rater, categorical labels"]
    else:
        report["notes"] = ["insufficient raters for kappa metrics"]
    return report


def win_rate(a_wins: int, b_wins: int, ties: int) -> dict:
    """Win/tie rate summary plus a Wilson-confidence style confidence value."""
    total = a_wins + b_wins + ties
    if total == 0:
        return {"win_rate_a": 0.0, "win_rate_b": 0.0, "tie_rate": 0.0,
                "confidence": 0.0, "comparisons": 0}
    z = 1.96  # 95% CI
    p = a_wins / total
    denom = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denom
    return {
        "win_rate_a": round(a_wins / total, 4),
        "win_rate_b": round(b_wins / total, 4),
        "tie_rate": round(ties / total, 4),
        "confidence": round(center, 4),
        "comparisons": total,
    }


def aggregate(results: Iterable[dict], score_key: str = "score") -> dict:
    """Mean/median/min/max aggregation over a list of numeric score dicts."""
    values = [float(r[score_key]) for r in results if r.get(score_key) is not None]
    if not values:
        return {"mean": 0.0, "median": 0.0, "min": 0.0, "max": 0.0, "count": 0}
    ordered = sorted(values)
    mid = len(ordered) // 2
    median = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
    return {
        "mean": round(sum(values) / len(values), 4),
        "median": round(median, 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "count": len(values),
    }
