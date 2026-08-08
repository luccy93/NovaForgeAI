"""Unified Search — full-text search, indexing, suggestions, analytics, and trending for the Data Platform & Knowledge Fabric."""

import json
import uuid
import os
import re
import logging
import math
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
from collections import defaultdict, Counter

logger = logging.getLogger(__name__)


class SearchDomain(Enum):
    REPOSITORIES = "repositories"
    DOCUMENTATION = "documentation"
    ARCHITECTURE = "architecture"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    CONVERSATIONS = "conversations"
    REPORTS = "reports"
    DEPLOYMENTS = "deployments"
    SECURITY_FINDINGS = "security_findings"
    TESTS = "tests"
    ANALYTICS = "analytics"
    METADATA = "metadata"
    CODE = "code"
    ALL = "all"


class SearchResultType(Enum):
    NODE = "node"
    DOCUMENT = "document"
    CODE_SNIPPET = "code_snippet"
    CONVERSATION = "conversation"
    REPORT = "report"
    METRIC = "metric"
    GRAPH = "graph"
    RELATIONSHIP = "relationship"


class SearchSortBy(Enum):
    RELEVANCE = "relevance"
    DATE = "date"
    NAME = "name"
    POPULARITY = "popularity"
    SIZE = "size"
    SCORE = "score"


class SearchFilterOperator(Enum):
    EQUALS = "equals"
    CONTAINS = "contains"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    IN_RANGE = "in_range"
    EXISTS = "exists"


@dataclass
class SearchIndex:
    id: str
    org_id: str
    domain: SearchDomain
    entity_id: str
    title: str
    content: str
    summary: str = ""
    result_type: SearchResultType = SearchResultType.DOCUMENT
    url: str = ""
    tags: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    score: float = 1.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["domain"] = self.domain.value
        d["result_type"] = self.result_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "SearchIndex":
        data = data.copy()
        data["domain"] = SearchDomain(data.get("domain", "all"))
        data["result_type"] = SearchResultType(data.get("result_type", "document"))
        return cls(**data)


@dataclass
class SearchQuery:
    id: str
    org_id: str
    user_id: str
    query_text: str
    domains: list[SearchDomain] = field(default_factory=lambda: [SearchDomain.ALL])
    filters: dict = field(default_factory=dict)
    sort_by: SearchSortBy = SearchSortBy.RELEVANCE
    limit: int = 10
    offset: int = 0
    executed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    execution_time_ms: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["domains"] = [dom.value for dom in self.domains]
        d["sort_by"] = self.sort_by.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "SearchQuery":
        data = data.copy()
        data["domains"] = [SearchDomain(d) for d in data.get("domains", ["all"])]
        data["sort_by"] = SearchSortBy(data.get("sort_by", "relevance"))
        return cls(**data)


@dataclass
class SearchResult:
    id: str
    query_id: str
    index_id: str
    domain: SearchDomain
    title: str
    summary: str = ""
    content_preview: str = ""
    result_type: SearchResultType = SearchResultType.DOCUMENT
    score: float = 0.0
    url: str = ""
    metadata: dict = field(default_factory=dict)
    rank: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["domain"] = self.domain.value
        d["result_type"] = self.result_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "SearchResult":
        data = data.copy()
        data["domain"] = SearchDomain(data.get("domain", "all"))
        data["result_type"] = SearchResultType(data.get("result_type", "document"))
        return cls(**data)


@dataclass
class SearchSuggestion:
    id: str
    org_id: str
    query_text: str
    suggestions: list = field(default_factory=list)
    frequency: int = 1
    last_used: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SearchSuggestion":
        return cls(**data)


@dataclass
class SearchAnalytics:
    id: str
    org_id: str
    period_start: str
    period_end: str
    total_searches: int = 0
    unique_users: int = 0
    top_queries: list = field(default_factory=list)
    top_domains: list = field(default_factory=list)
    avg_results: float = 0.0
    zero_result_queries: list = field(default_factory=list)
    trending: list = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SearchAnalytics":
        return cls(**data)


class UnifiedSearch:
    def __init__(self, storage_dir: str = "search_data"):
        self.storage_dir = storage_dir
        self._indices: dict[str, SearchIndex] = {}
        self._queries: dict[str, SearchQuery] = {}
        self._suggestions: dict[str, SearchSuggestion] = {}
        self._analytics: dict[str, SearchAnalytics] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        self._term_index: dict[str, dict[str, float]] = {}
        self._total_docs: int = 0
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _indices_path(self) -> str:
        return os.path.join(self.storage_dir, "indices.json")

    def _queries_path(self) -> str:
        return os.path.join(self.storage_dir, "queries.json")

    def _suggestions_path(self) -> str:
        return os.path.join(self.storage_dir, "suggestions.json")

    def _analytics_path(self) -> str:
        return os.path.join(self.storage_dir, "analytics.json")

    def _save(self) -> None:
        try:
            idx_data = {iid: idx.to_dict() for iid, idx in self._indices.items()}
            with open(self._indices_path(), "w", encoding="utf-8") as f:
                json.dump(idx_data, f, indent=2, default=str)

            q_data = {qid: q.to_dict() for qid, q in self._queries.items()}
            with open(self._queries_path(), "w", encoding="utf-8") as f:
                json.dump(q_data, f, indent=2, default=str)

            sug_data = {sid: s.to_dict() for sid, s in self._suggestions.items()}
            with open(self._suggestions_path(), "w", encoding="utf-8") as f:
                json.dump(sug_data, f, indent=2, default=str)

            an_data = {aid: a.to_dict() for aid, a in self._analytics.items()}
            with open(self._analytics_path(), "w", encoding="utf-8") as f:
                json.dump(an_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save search data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._indices_path()):
                with open(self._indices_path(), "r", encoding="utf-8") as f:
                    idx_data = json.load(f)
                for iid, data in idx_data.items():
                    try:
                        self._indices[iid] = SearchIndex.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed search index %s: %s", iid, e)

            if os.path.exists(self._queries_path()):
                with open(self._queries_path(), "r", encoding="utf-8") as f:
                    q_data = json.load(f)
                for qid, data in q_data.items():
                    try:
                        self._queries[qid] = SearchQuery.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed search query %s: %s", qid, e)

            if os.path.exists(self._suggestions_path()):
                with open(self._suggestions_path(), "r", encoding="utf-8") as f:
                    sug_data = json.load(f)
                for sid, data in sug_data.items():
                    try:
                        self._suggestions[sid] = SearchSuggestion.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed suggestion %s: %s", sid, e)

            if os.path.exists(self._analytics_path()):
                with open(self._analytics_path(), "r", encoding="utf-8") as f:
                    an_data = json.load(f)
                for aid, data in an_data.items():
                    try:
                        self._analytics[aid] = SearchAnalytics.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed analytics %s: %s", aid, e)

            self._rebuild_term_index()
        except Exception as e:
            logger.error("Failed to load search data: %s", e, exc_info=True)

    def _rebuild_term_index(self) -> None:
        self._term_index.clear()
        self._total_docs = len(self._indices)
        for idx_id, idx in self._indices.items():
            terms = self._tokenize(f"{idx.title} {idx.content} {idx.summary} {' '.join(idx.tags)}")
            term_freq = Counter(terms)
            for term, count in term_freq.items():
                if term not in self._term_index:
                    self._term_index[term] = {}
                self._term_index[term][idx_id] = count

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        tokens = re.findall(r"[a-zA-Z0-9_]+", text.lower())
        return [t for t in tokens if len(t) > 1]

    def _compute_tfidf(self, query_terms: list[str], idx_id: str, idx: SearchIndex) -> float:
        score = 0.0
        doc_len = len(self._tokenize(f"{idx.title} {idx.content} {idx.summary}"))
        if doc_len == 0:
            return 0.0
        for term in query_terms:
            if term in self._term_index and idx_id in self._term_index[term]:
                tf = self._term_index[term][idx_id] / doc_len
                df = len(self._term_index[term])
                idf = math.log((self._total_docs + 1) / (df + 1)) + 1
                score += tf * idf
        return score

    def index_document(self, index: SearchIndex) -> SearchIndex:
        self._telemetry["index_document_calls"] += 1
        if not index.id:
            index.id = str(uuid.uuid4())
        if not index.created_at:
            index.created_at = datetime.now(timezone.utc).isoformat()
        if not index.updated_at:
            index.updated_at = index.created_at
        self._indices[index.id] = index
        self._rebuild_term_index()
        self._save()
        logger.info("Indexed document %s: %s (%s)", index.id, index.title, index.domain.value)
        return index

    def bulk_index(self, documents: list[SearchIndex]) -> int:
        self._telemetry["bulk_index_calls"] += 1
        now = datetime.now(timezone.utc).isoformat()
        for idx in documents:
            if not idx.id:
                idx.id = str(uuid.uuid4())
            if not idx.created_at:
                idx.created_at = now
            if not idx.updated_at:
                idx.updated_at = now
            self._indices[idx.id] = idx
        self._rebuild_term_index()
        self._save()
        logger.info("Bulk indexed %d documents", len(documents))
        return len(documents)

    def remove_index(self, index_id: str) -> bool:
        self._telemetry["remove_index_calls"] += 1
        if index_id not in self._indices:
            logger.warning("Attempted to remove unknown index: %s", index_id)
            return False
        del self._indices[index_id]
        self._rebuild_term_index()
        self._save()
        logger.info("Removed index: %s", index_id)
        return True

    def search(self, query: SearchQuery) -> list[SearchResult]:
        self._telemetry["search_calls"] += 1
        start = datetime.now(timezone.utc)

        query_terms = self._tokenize(query.query_text)
        scored: list[tuple[float, SearchIndex]] = []

        for idx_id, idx in self._indices.items():
            if SearchDomain.ALL not in query.domains and idx.domain not in query.domains:
                continue

            filter_match = True
            for field, condition in query.filters.items():
                op = condition.get("operator", SearchFilterOperator.EQUALS)
                value = condition.get("value")
                field_value = getattr(idx, field, None)
                if field_value is None:
                    field_value = idx.metadata.get(field)
                if op == SearchFilterOperator.EQUALS:
                    if field_value != value:
                        filter_match = False
                elif op == SearchFilterOperator.CONTAINS:
                    if value and (not field_value or value.lower() not in str(field_value).lower()):
                        filter_match = False
                elif op == SearchFilterOperator.GREATER_THAN:
                    if field_value is None or not (float(field_value) > float(value)):
                        filter_match = False
                elif op == SearchFilterOperator.LESS_THAN:
                    if field_value is None or not (float(field_value) < float(value)):
                        filter_match = False
                elif op == SearchFilterOperator.IN_RANGE:
                    lo = condition.get("min")
                    hi = condition.get("max")
                    if field_value is None or not (float(lo) <= float(field_value) <= float(hi)):
                        filter_match = False
                elif op == SearchFilterOperator.EXISTS:
                    if field_value is None:
                        filter_match = False
                if not filter_match:
                    break

            if not filter_match:
                continue

            score = self._compute_tfidf(query_terms, idx_id, idx)
            if score > 0 or not query_terms:
                scored.append((score, idx))

        if query.sort_by == SearchSortBy.SCORE:
            scored.sort(key=lambda x: x[0], reverse=True)
        elif query.sort_by == SearchSortBy.DATE:
            scored.sort(key=lambda x: x[1].updated_at, reverse=True)
        elif query.sort_by == SearchSortBy.NAME:
            scored.sort(key=lambda x: x[1].title.lower())
        elif query.sort_by == SearchSortBy.POPULARITY:
            scored.sort(key=lambda x: x[1].score, reverse=True)
        elif query.sort_by == SearchSortBy.SIZE:
            scored.sort(key=lambda x: len(x[1].content), reverse=True)
        else:
            scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for rank, (score, idx) in enumerate(scored[query.offset:query.offset + query.limit]):
            preview = (idx.content[:300] + "...") if len(idx.content) > 300 else idx.content
            result = SearchResult(
                id=str(uuid.uuid4()),
                query_id=query.id,
                index_id=idx.id,
                domain=idx.domain,
                title=idx.title,
                summary=idx.summary,
                content_preview=preview,
                result_type=idx.result_type,
                score=round(score, 4),
                url=idx.url,
                metadata=idx.metadata,
                rank=rank + 1,
            )
            results.append(result)

        elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        query.execution_time_ms = round(elapsed, 2)
        self._queries[query.id] = query
        self._save()

        logger.info("Search '%s' returned %d results in %.0fms", query.query_text, len(results), elapsed)
        return results

    def search_domains(self, query_text: str, domains: list[SearchDomain], limit: int = 10) -> list[SearchResult]:
        self._telemetry["search_domains_calls"] += 1
        q = SearchQuery(
            id=str(uuid.uuid4()),
            org_id="",
            user_id="",
            query_text=query_text,
            domains=domains,
            limit=limit,
        )
        return self.search(q)

    def get_suggestions(self, partial_query: str, limit: int = 5) -> list[str]:
        self._telemetry["get_suggestions_calls"] += 1
        pq = partial_query.lower().strip()
        if not pq:
            return []

        candidates: list[tuple[str, int]] = []
        for sug in self._suggestions.values():
            if pq in sug.query_text.lower():
                candidates.append((sug.query_text, sug.frequency))

        seen = set()
        suggestions = []
        for text, freq in sorted(candidates, key=lambda x: x[1], reverse=True):
            if text not in seen:
                seen.add(text)
                suggestions.append(text)
            if len(suggestions) >= limit:
                break

        return suggestions

    def record_suggestion(self, suggestion: SearchSuggestion) -> SearchSuggestion:
        self._telemetry["record_suggestion_calls"] += 1
        if not suggestion.id:
            suggestion.id = str(uuid.uuid4())
        if not suggestion.created_at:
            suggestion.created_at = datetime.now(timezone.utc).isoformat()
        suggestion.last_used = datetime.now(timezone.utc).isoformat()

        existing = None
        for sid, s in self._suggestions.items():
            if s.query_text.lower() == suggestion.query_text.lower() and s.org_id == suggestion.org_id:
                existing = s
                break
        if existing:
            existing.frequency += 1
            existing.last_used = suggestion.last_used
            if suggestion.suggestions:
                existing.suggestions = list(set(existing.suggestions + suggestion.suggestions))
        else:
            self._suggestions[suggestion.id] = suggestion

        self._save()
        logger.info("Recorded suggestion: %s", suggestion.query_text)
        return existing or suggestion

    def get_search_analytics(self, org_id: str, days: int = 30) -> SearchAnalytics:
        self._telemetry["get_search_analytics_calls"] += 1
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        org_queries = [
            q for q in self._queries.values()
            if q.org_id == org_id
        ]
        recent_queries = []
        for q in org_queries:
            try:
                q_time = datetime.fromisoformat(q.executed_at)
                if q_time >= cutoff:
                    recent_queries.append(q)
            except (ValueError, TypeError):
                recent_queries.append(q)

        total_searches = len(recent_queries)
        unique_users = len(set(q.user_id for q in recent_queries if q.user_id))

        query_counter: Counter = Counter()
        domain_counter: Counter = Counter()
        zero_result_queries = []
        trending_counter: Counter = Counter()

        for q in recent_queries:
            query_counter[q.query_text] += 1
            for d in q.domains:
                domain_counter[d.value] += 1
            trending_counter[q.query_text] += 1

        top_queries = [{"query": text, "count": cnt} for text, cnt in query_counter.most_common(20)]
        top_domains = [{"domain": dom, "count": cnt} for dom, cnt in domain_counter.most_common(10)]

        recent_results_count = 0
        recent_results_total = 0
        for idx in self._indices.values():
            try:
                idx_time = datetime.fromisoformat(idx.updated_at)
                if idx_time >= cutoff:
                    recent_results_total += 1
            except (ValueError, TypeError):
                pass

        avg_results = round(recent_results_total / max(total_searches, 1), 2)

        trending = [{"query": text, "count": cnt} for text, cnt in trending_counter.most_common(20)]

        analytics = SearchAnalytics(
            id=str(uuid.uuid4()),
            org_id=org_id,
            period_start=cutoff.isoformat(),
            period_end=datetime.now(timezone.utc).isoformat(),
            total_searches=total_searches,
            unique_users=unique_users,
            top_queries=top_queries,
            top_domains=top_domains,
            avg_results=avg_results,
            zero_result_queries=zero_result_queries,
            trending=trending,
        )
        self._analytics[analytics.id] = analytics
        self._save()
        return analytics

    def get_trending_searches(self, org_id: str, days: int = 7, limit: int = 10) -> list[dict]:
        self._telemetry["get_trending_searches_calls"] += 1
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        counter: Counter = Counter()
        for q in self._queries.values():
            if q.org_id != org_id:
                continue
            try:
                q_time = datetime.fromisoformat(q.executed_at)
                if q_time >= cutoff:
                    counter[q.query_text] += 1
            except (ValueError, TypeError):
                counter[q.query_text] += 1
        return [{"query": text, "count": cnt} for text, cnt in counter.most_common(limit)]

    def reindex_entity(self, domain: SearchDomain, entity_id: str) -> bool:
        self._telemetry["reindex_entity_calls"] += 1
        found = False
        for idx_id, idx in list(self._indices.items()):
            if idx.domain == domain and idx.entity_id == entity_id:
                idx.updated_at = datetime.now(timezone.utc).isoformat()
                found = True
        if found:
            self._rebuild_term_index()
            self._save()
            logger.info("Reindexed entity %s in domain %s", entity_id, domain.value)
        else:
            logger.warning("No indices found for entity %s in domain %s", entity_id, domain.value)
        return found

    def get_telemetry(self) -> dict:
        self._telemetry["get_telemetry_calls"] += 1
        return dict(self._telemetry)
