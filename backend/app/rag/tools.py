"""Volume 43 — agent retrieval tools.

Specialized, authorization-aware retrieval tools exposed to agents. Every
tool returns structured results (not just text): each item carries ``source``,
``content``, ``metadata``, ``score``, ``citation`` and ``confidence`` so an
agent can reason over them and cite them. All tools go through the same
tenant/repository/permission enforcement as the public API.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.rag.config import RagConfig, DEFAULT_RAG_CONFIG
from app.rag.embeddings import EmbeddingClient
from app.rag.retrieval.retrievers import GraphRetriever
from app.rag.retrieval.service import RAGService
from app.rag.schemas import RetrievedChunk

logger = logging.getLogger(__name__)


def _to_tool_result(chunk: RetrievedChunk) -> dict:
    return {
        "source": chunk.source_id or chunk.chunk_id,
        "content": chunk.content,
        "metadata": chunk.metadata,
        "score": chunk.scores.get("rerank", chunk.scores.get("rrf", 0.0)),
        "citation": {
            "source_id": chunk.source_id,
            "chunk_id": chunk.chunk_id,
            "file_path": chunk.file_path,
            "start_line": chunk.start_line,
            "end_line": chunk.end_line,
            "symbol": chunk.symbol,
            "commit": chunk.commit,
        },
        "confidence": chunk.scores.get("rerank", 0.5),
    }


class RAGTools:
    def __init__(
        self,
        config: Optional[RagConfig] = None,
        embedding_client: Optional[EmbeddingClient] = None,
        vector_store=None,
    ) -> None:
        self.config = config or DEFAULT_RAG_CONFIG
        self.service = RAGService(self.config, embedding_client, vector_store)
        self.graph = GraphRetriever(self.config)

    async def _auth(self, db, *, tenant_id, organization_id, user, repository_id, filters):
        f = dict(filters or {})
        if repository_id is not None:
            f["repository_id"] = repository_id
        return f

    async def search_code(
        self, db, query, *, tenant_id, organization_id, user=None, repository_id=None,
        filters=None, limit=10,
    ) -> list[dict]:
        f = await self._auth(db, tenant_id=tenant_id, organization_id=organization_id, user=user,
                             repository_id=repository_id, filters=filters)
        ctx = await self.service.retrieve(
            query, db, tenant_id=tenant_id, organization_id=organization_id, user=user,
            repository_id=repository_id, filters={**f, "source_type": "repository"}, limit=limit,
        )
        return [_to_tool_result(c) for c in ctx.chunks]

    async def search_docs(
        self, db, query, *, tenant_id, organization_id, user=None, repository_id=None,
        filters=None, limit=10,
    ) -> list[dict]:
        f = await self._auth(db, tenant_id=tenant_id, organization_id=organization_id, user=user,
                             repository_id=repository_id, filters=filters)
        ctx = await self.service.retrieve(
            query, db, tenant_id=tenant_id, organization_id=organization_id, user=user,
            repository_id=repository_id, filters=f, limit=limit,
        )
        return [_to_tool_result(c) for c in ctx.chunks]

    async def find_symbol(
        self, db, symbol, *, tenant_id, organization_id, user=None, repository_id=None,
        filters=None, limit=10,
    ) -> list[dict]:
        return await self.search_code(
            db, f"symbol {symbol}", tenant_id=tenant_id, organization_id=organization_id,
            user=user, repository_id=repository_id, filters=filters, limit=limit,
        )

    async def find_references(
        self, db, symbol, *, tenant_id, organization_id, user=None, repository_id=None,
        filters=None, limit=10,
    ) -> list[dict]:
        f = await self._auth(db, tenant_id=tenant_id, organization_id=organization_id, user=user,
                             repository_id=repository_id, filters=filters)
        chunks = await self.graph.search(db, f"references to {symbol}", tenant_id=tenant_id,
                                         filters=f, limit=limit)
        return [_to_tool_result(c) for c in chunks]

    async def find_dependencies(
        self, db, target, *, tenant_id, organization_id, user=None, repository_id=None,
        filters=None, limit=10,
    ) -> list[dict]:
        return await self.find_references(
            db, target, tenant_id=tenant_id, organization_id=organization_id, user=user,
            repository_id=repository_id, filters=filters, limit=limit,
        )

    async def find_callers(
        self, db, symbol, *, tenant_id, organization_id, user=None, repository_id=None,
        filters=None, limit=10,
    ) -> list[dict]:
        chunks = await self.graph.search(db, f"callers of {symbol}", tenant_id=tenant_id,
                                         filters={"repository_id": repository_id} if repository_id else filters,
                                         limit=limit)
        # Keep only caller relationships.
        callers = [c for c in chunks if (c.metadata or {}).get("relationship") == "caller"]
        return [_to_tool_result(c) for c in (callers or chunks)]

    async def find_tests(
        self, db, symbol, *, tenant_id, organization_id, user=None, repository_id=None,
        filters=None, limit=10,
    ) -> list[dict]:
        chunks = await self.graph.search(db, f"tests for {symbol}", tenant_id=tenant_id,
                                         filters={"repository_id": repository_id} if repository_id else filters,
                                         limit=limit)
        tests = [c for c in chunks if (c.metadata or {}).get("relationship") == "test"]
        return [_to_tool_result(c) for c in (tests or chunks)]

    async def find_architecture(
        self, db, query, *, tenant_id, organization_id, user=None, repository_id=None,
        filters=None, limit=10,
    ) -> list[dict]:
        return await self.search_docs(
            db, f"architecture {query}", tenant_id=tenant_id, organization_id=organization_id,
            user=user, repository_id=repository_id, filters=filters, limit=limit,
        )

    async def find_history(
        self, db, query, *, tenant_id, organization_id, user=None, repository_id=None,
        filters=None, limit=10,
    ) -> list[dict]:
        # History is best answered from change intelligence; fall back to a
        # documentation/metadata retrieval scoped to the repository.
        return await self.search_docs(
            db, f"history {query}", tenant_id=tenant_id, organization_id=organization_id,
            user=user, repository_id=repository_id, filters=filters, limit=limit,
        )

    async def find_security_context(
        self, db, query, *, tenant_id, organization_id, user=None, repository_id=None,
        filters=None, limit=10,
    ) -> list[dict]:
        ctx = await self.service.retrieve(
            f"security {query}", db, tenant_id=tenant_id, organization_id=organization_id,
            user=user, repository_id=repository_id, filters=filters, limit=limit,
        )
        return [_to_tool_result(c) for c in ctx.chunks]
