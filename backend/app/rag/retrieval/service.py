"""Volume 43 — RAG service (orchestrator).

Ties together query understanding, the retrievers, fusion, reranking,
context assembly and citation validation. Authorization is applied *before*
any chunk reaches the model: tenant/repository filtering happens inside every
retriever, and denied/permission-invalid citations are dropped during
validation. Results are cached only when permission-safe.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import cache_get, cache_set
from app.rag.config import RagConfig, DEFAULT_RAG_CONFIG
from app.rag.embeddings import EmbeddingClient
from app.rag.exceptions import InsufficientEvidenceError, PermissionDeniedError
from app.rag.models import RagRetrievalLog
from app.rag.retrieval.assembly import CitationEngine, ContextAssembler
from app.rag.retrieval.fusion import Reranker, reciprocal_rank_fusion
from app.rag.retrieval.query import expand_query, route_query
from app.rag.retrieval.retrievers import GraphRetriever, LexicalRetriever, VectorRetriever
from app.rag.schemas import Answerability, ContextSet, QueryIntent, RetrievalMethod

logger = logging.getLogger(__name__)


class RAGService:
    def __init__(
        self,
        config: Optional[RagConfig] = None,
        embedding_client: Optional[EmbeddingClient] = None,
        vector_store=None,
    ) -> None:
        self.config = config or DEFAULT_RAG_CONFIG
        self.embeddings = embedding_client or EmbeddingClient()
        self.lexical = LexicalRetriever(self.config)
        self.vector = VectorRetriever(self.config, self.embeddings, vector_store)
        self.graph = GraphRetriever(self.config)
        self.reranker = Reranker(self.config)
        self.assembler = ContextAssembler(self.config)
        self.citations = CitationEngine()

    async def retrieve(
        self,
        query: str,
        db: AsyncSession,
        *,
        tenant_id: Any,
        organization_id: Any,
        user: Optional[Any] = None,
        repository_id: Optional[Any] = None,
        filters: Optional[dict] = None,
        limit: Optional[int] = None,
        rerank_strategy: Optional[str] = None,
        use_cache: bool = True,
    ) -> ContextSet:
        t0 = time.perf_counter()
        filters = dict(filters or {})
        if repository_id is not None:
            filters["repository_id"] = repository_id
        limit = limit or self.config.default_limit
        plan = route_query(query, self.config, filters)

        cache_key = self._cache_key(query, tenant_id, user, filters, rerank_strategy)
        if use_cache:
            cached = await cache_get(cache_key, namespace=self.config.cache_namespace)
            if cached:
                ctx = ContextSet(**json.loads(cached))
                await self._log(
                    db, query, tenant_id, organization_id, user, repository_id, plan,
                    ctx, cache_hit=True, total_ms=(time.perf_counter() - t0) * 1000,
                )
                return ctx

        # Run selected strategies.
        results_by_method: dict[str, list] = {}
        counts: dict[str, int] = {}
        lat: dict[str, float] = {}
        intent = plan.intent

        # Always run lexical + vector baseline; add graph when useful.
        strategies = set(plan.strategies) | {"lexical", "vector"}
        if intent in (QueryIntent.SYMBOL_LOOKUP.value, QueryIntent.DEPENDENCY_ANALYSIS.value,
                      QueryIntent.BUG_INVESTIGATION.value, QueryIntent.ARCHITECTURE.value):
            strategies.add("graph")

        if "lexical" in strategies:
            ta = time.perf_counter()
            results_by_method["lexical"] = await self.lexical.search(
                db, query, tenant_id=tenant_id, filters=filters, limit=limit
            )
            lat["lexical"] = (time.perf_counter() - ta) * 1000
        if "vector" in strategies:
            tv = time.perf_counter()
            results_by_method["vector"] = await self.vector.search(
                db, query, tenant_id=tenant_id, filters=filters, limit=limit
            )
            lat["vector"] = (time.perf_counter() - tv) * 1000
        if "graph" in strategies:
            tg = time.perf_counter()
            results_by_method["graph"] = await self.graph.search(
                db, query, tenant_id=tenant_id, filters=filters, limit=limit
            )
            lat["graph"] = (time.perf_counter() - tg) * 1000

        for m, res in results_by_method.items():
            counts[m] = len(res)

        fused = reciprocal_rank_fusion(results_by_method, plan.weights, k=self.config.rrf_k)
        tr = time.perf_counter()
        reranked = self.reranker.rerank(fused, query, rerank_strategy or self.config.rerank_strategy)
        lat["rerank"] = (time.perf_counter() - tr) * 1000

        # Validate citations (drop invalid) BEFORE assembly.
        valid_chunks: list = []
        invalid = 0
        for chunk in reranked:
            ok, detail, _ = await self.citations.validate(chunk, db, user=user, config=self.config)
            if ok:
                valid_chunks.append(chunk)
            else:
                invalid += 1
                logger.info("dropping invalid citation: %s", detail)

        context = self.assembler.assemble(valid_chunks, query=query)

        # Persist citation records for audit.
        for chunk in context.chunks:
            cit = self.citations.build(chunk)
            await self.citations.record(
                db, cit, tenant_id=tenant_id, organization_id=organization_id,
                user=user, repository_id=repository_id, valid=True,
            )
        for chunk in reranked:
            if chunk not in context.chunks:
                cit = self.citations.build(chunk)
                await self.citations.record(
                    db, cit, tenant_id=tenant_id, organization_id=organization_id,
                    user=user, repository_id=repository_id, valid=False, detail="dropped",
                )

        total_ms = (time.perf_counter() - t0) * 1000
        if use_cache and context.chunks:
            await cache_set(
                cache_key, json.dumps(context.to_dict()),
                ttl=self.config.cache_ttl_seconds, namespace=self.config.cache_namespace,
            )

        await self._log(
            db, query, tenant_id, organization_id, user, repository_id, plan, context,
            counts=counts, lat=lat, invalid=invalid, total_ms=total_ms,
        )

        if not context.chunks:
            # No evidence at all -> explicit failure, never hallucination.
            raise InsufficientEvidenceError(
                "No authorized, version-valid evidence was retrieved for the query.",
                answerability=Answerability.INSUFFICIENT.value,
            )
        return context

    def _cache_key(self, query, tenant_id, user, filters, rerank_strategy) -> str:
        payload = {
            "q": query,
            "t": str(tenant_id),
            "u": str(getattr(user, "id", "anon")),
            "f": filters,
            "r": rerank_strategy or self.config.rerank_strategy,
        }
        h = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:24]
        return f"retrieve:{h}"

    async def _log(
        self, db, query, tenant_id, organization_id, user, repository_id, plan, context,
        counts: Optional[dict] = None, lat: Optional[dict] = None, invalid: int = 0,
        cache_hit: bool = False, total_ms: float = 0.0,
    ) -> None:
        counts = counts or {}
        lat = lat or {}
        log = RagRetrievalLog(
            tenant_id=tenant_id,
            organization_id=organization_id,
            user_id=getattr(user, "id", None) if user else None,
            repository_id=repository_id,
            query=query,
            intent=plan.intent,
            strategies=plan.strategies,
            filters=plan.filters,
            rerank_strategy=self.config.rerank_strategy,
            lexical_count=counts.get("lexical", 0),
            vector_count=counts.get("vector", 0),
            graph_count=counts.get("graph", 0),
            fused_count=sum(counts.values()),
            context_chunks=len(context.chunks),
            citations=len(context.citations),
            invalid_citations=invalid,
            answerability=context.answerability,
            cache_hit=cache_hit,
            lexical_latency_ms=lat.get("lexical", 0.0),
            vector_latency_ms=lat.get("vector", 0.0),
            graph_latency_ms=lat.get("graph", 0.0),
            rerank_latency_ms=lat.get("rerank", 0.0),
            total_latency_ms=total_ms,
            empty_retrieval=len(context.chunks) == 0,
        )
        db.add(log)
        try:
            await db.flush()
        except Exception:  # pragma: no cover - logging must never break retrieval
            pass
