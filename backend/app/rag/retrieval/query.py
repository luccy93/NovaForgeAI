"""Volume 43 — query understanding, routing and expansion.

Transforms a raw query into a :class:`RetrievalPlan` (intent + strategies +
weights + filters) and optionally expands it with controlled terms.
"""

from __future__ import annotations

import re
from typing import Optional

from app.rag.config import RagConfig, DEFAULT_RAG_CONFIG
from app.rag.schemas import QueryClassification, QueryIntent, RetrievalPlan

_SYMBOL_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b")
_IDENTIFIER_RE = re.compile(r"\b[a-z][a-z0-9_]*(?:[A-Z][a-z0-9_]*)*\b")


def classify_query(query: str) -> QueryClassification:
    q = (query or "").lower()
    tokens = set(re.findall(r"[a-z0-9_]+", q))

    # Symbol-like query: contains CamelCase, dotted paths, or "function X".
    has_symbol = bool(re.search(r"\b[a-z][a-zA-Z0-9_]+\.[a-z][a-zA-Z0-9_]+\b", query)) or bool(
        re.search(r"\b[A-Z][a-zA-Z0-9]{3,}\b", query)
    )
    has_func = bool(re.search(r"\b(def|function|func|method|class|interface|struct)\s+[A-Za-z_]", query, re.I))
    has_find = bool(re.search(r"\b(find|where is|locate|show me)\b", q))

    if has_symbol or has_func or has_find:
        intent = QueryIntent.SYMBOL_LOOKUP
        strategies = ["symbol", "lexical", "vector"]
        confidence = 0.85
    elif re.search(r"\b(how does|how do|architecture|design|overview|components?|services?)\b", q):
        intent = QueryIntent.ARCHITECTURE
        strategies = ["semantic", "graph", "lexical"]
        confidence = 0.7
    elif re.search(r"\b(bug|broken|failing|error|exception|crash|why is|why does)\b", q):
        intent = QueryIntent.BUG_INVESTIGATION
        strategies = ["semantic", "lexical", "graph", "vector"]
        confidence = 0.7
    elif re.search(r"\b(dependency|depends on|imports|packages?|libraries)\b", q):
        intent = QueryIntent.DEPENDENCY_ANALYSIS
        strategies = ["graph", "symbol", "lexical"]
        confidence = 0.75
    elif re.search(r"\b(security|vulnerab|secret|cve|injection|auth|permission|access control)\b", q):
        intent = QueryIntent.SECURITY
        strategies = ["semantic", "lexical", "graph"]
        confidence = 0.75
    elif re.search(r"\b(doc|documentation|readme|guide|tutorial|explain)\b", q):
        intent = QueryIntent.DOCUMENTATION
        strategies = ["semantic", "lexical", "metadata"]
        confidence = 0.7
    elif re.search(r"\b(code|implement|function|method|class|module|file)\b", q):
        intent = QueryIntent.CODE_SEARCH
        strategies = ["lexical", "vector", "symbol"]
        confidence = 0.7
    else:
        intent = QueryIntent.NL_KNOWLEDGE
        strategies = ["semantic", "lexical", "metadata"]
        confidence = 0.5

    expansion = _extract_terms(query)
    return QueryClassification(
        intent=intent.value,
        confidence=confidence,
        strategies=strategies,
        expansion_terms=expansion,
    )


def _extract_terms(query: str) -> list[str]:
    # Candidate symbols / identifiers used for controlled expansion.
    terms = set()
    for m in re.findall(r"[A-Za-z_][A-Za-z0-9_\.]{2,}", query):
        terms.add(m)
    return sorted(terms)[:20]


def route_query(
    query: str,
    config: Optional[RagConfig] = None,
    base_filters: Optional[dict] = None,
) -> RetrievalPlan:
    cfg = config or DEFAULT_RAG_CONFIG
    cls = classify_query(query)
    intent = cls.intent

    # Map each strategy to a fusion weight for this intent.
    weights = {
        "lexical": getattr(cfg.fusion, "lexical", 0.3),
        "semantic": getattr(cfg.fusion, "semantic", 0.35),
        "symbol": getattr(cfg.fusion, "symbol", 0.15),
        "graph": getattr(cfg.fusion, "graph", 0.1),
        "metadata": getattr(cfg.fusion, "metadata", 0.05),
        "recency": getattr(cfg.fusion, "recency", 0.05),
    }
    # Boost the strategies the classifier selected.
    plan_weights = {}
    for s in cls.strategies:
        plan_weights[s] = weights.get(s, 0.2) * 1.5
    # Always keep lexical + semantic as a baseline.
    plan_weights.setdefault("lexical", weights["lexical"])
    plan_weights.setdefault("semantic", weights["semantic"])

    filters = dict(base_filters or {})
    return RetrievalPlan(
        intent=intent,
        strategies=cls.strategies,
        weights=plan_weights,
        filters=filters,
        expansion_terms=cls.expansion_terms,
    )


def expand_query(query: str, plan: RetrievalPlan | None = None) -> list[str]:
    """Controlled query expansion (no unrelated terms)."""
    terms = _extract_terms(query)
    if plan is not None:
        terms = terms + [t for t in plan.expansion_terms if t not in terms]
    # Add likely framework/alias forms without exploding the result set.
    expanded = set(terms)
    for t in list(terms):
        if "." in t:
            expanded.add(t.split(".")[-1])
    return sorted(expanded)[:25]
