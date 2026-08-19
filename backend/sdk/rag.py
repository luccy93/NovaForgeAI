"""NovaForge SDK — Knowledge & Retrieval (RAG) extensions.

Provides :class:`RagMixin` (sync) and :class:`AsyncRagMixin` (async) that add
methods for knowledge-source management, hybrid/graph retrieval, citation
validation, knowledge health and evaluation. They compose with
``NovaForgeClient`` / ``AsyncNovaForgeClient`` and return the parsed JSON
responses from the ``/api/v1/rag`` endpoints.

Usage:
    from backend.sdk import NovaForgeClient
    from backend.sdk.rag import RagMixin

    class MyClient(RagMixin, NovaForgeClient):
        pass
"""

from __future__ import annotations

from typing import Any, Optional


# ---------------------------------------------------------------------------
# Sync mixin
# ---------------------------------------------------------------------------


class RagMixin:
    """Mixin that adds Knowledge & RAG methods to ``NovaForgeClient``.

    Expects the host class to provide ``self.get()``, ``self.post()``,
    ``self.put()``, ``self.delete()`` and ``self._build_url()``.
    """

    # ─── Source management ──────────────────────────────────────────────

    def create_source(
        self,
        name: str,
        source_type: str,
        source_uri: Optional[str] = None,
        repository_id: Optional[str] = None,
        content: Optional[str] = None,
        permissions: Optional[dict] = None,
        classification: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        """Register a new knowledge source."""
        payload: dict[str, Any] = {"name": name, "source_type": source_type}
        if source_uri is not None:
            payload["source_uri"] = source_uri
        if repository_id is not None:
            payload["repository_id"] = repository_id
        if content is not None:
            payload["content"] = content
        if permissions is not None:
            payload["permissions"] = permissions
        if classification is not None:
            payload["classification"] = classification
        if metadata is not None:
            payload["metadata"] = metadata
        return self.post(self._build_url("/rag/sources"), data=payload)

    def list_sources(
        self,
        repository_id: Optional[str] = None,
        source_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[dict]:
        """List knowledge sources."""
        params: dict[str, Any] = {}
        if repository_id is not None:
            params["repository_id"] = repository_id
        if source_type is not None:
            params["source_type"] = source_type
        if status is not None:
            params["status"] = status
        return self.get(self._build_url("/rag/sources"), params=params)

    def get_source(self, source_id: str) -> dict:
        """Get a single knowledge source."""
        return self.get(self._build_url(f"/rag/sources/{source_id}"))

    def index_source(self, source_id: str, content: Optional[str] = None) -> dict:
        """Trigger indexing of a knowledge source."""
        payload: dict[str, Any] = {}
        if content is not None:
            payload["content"] = content
        return self.post(self._build_url(f"/rag/sources/{source_id}/index"), data=payload)

    def delete_source(self, source_id: str) -> dict:
        """Soft-delete a knowledge source and propagate deletion."""
        return self.delete(self._build_url(f"/rag/sources/{source_id}"))

    def source_status(self, source_id: str) -> dict:
        """Get the status / version / staleness of a source."""
        return self.get(self._build_url(f"/rag/sources/{source_id}/status"))

    def update_permissions(
        self,
        source_id: str,
        permissions: Optional[dict] = None,
        classification: Optional[str] = None,
    ) -> dict:
        """Update a source's permissions and/or classification."""
        payload: dict[str, Any] = {}
        if permissions is not None:
            payload["permissions"] = permissions
        if classification is not None:
            payload["classification"] = classification
        return self.put(self._build_url(f"/rag/sources/{source_id}/permissions"), data=payload)

    # ─── Retrieval ──────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        repository_id: Optional[str] = None,
        filters: Optional[dict] = None,
        limit: Optional[int] = None,
        rerank_strategy: Optional[str] = None,
    ) -> dict:
        """Hybrid retrieval returning assembled context and citations."""
        payload: dict[str, Any] = {"query": query}
        if repository_id is not None:
            payload["repository_id"] = repository_id
        if filters is not None:
            payload["filters"] = filters
        if limit is not None:
            payload["limit"] = limit
        if rerank_strategy is not None:
            payload["rerank_strategy"] = rerank_strategy
        return self.post(self._build_url("/rag/search"), data=payload)

    def hybrid_search(
        self,
        query: str,
        repository_id: Optional[str] = None,
        filters: Optional[dict] = None,
        limit: Optional[int] = None,
        rerank_strategy: Optional[str] = None,
    ) -> dict:
        """Hybrid retrieval returning the full ContextSet plus query intent."""
        payload: dict[str, Any] = {"query": query}
        if repository_id is not None:
            payload["repository_id"] = repository_id
        if filters is not None:
            payload["filters"] = filters
        if limit is not None:
            payload["limit"] = limit
        if rerank_strategy is not None:
            payload["rerank_strategy"] = rerank_strategy
        return self.post(self._build_url("/rag/hybrid"), data=payload)

    def context(
        self,
        query: str,
        repository_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> dict:
        """Return only the assembled context set for a query."""
        payload: dict[str, Any] = {"query": query}
        if repository_id is not None:
            payload["repository_id"] = repository_id
        if limit is not None:
            payload["limit"] = limit
        return self.post(self._build_url("/rag/context"), data=payload)

    def validate_citations(
        self,
        query: str,
        repository_id: Optional[str] = None,
    ) -> dict:
        """Run retrieval and split citations into valid / invalid."""
        payload: dict[str, Any] = {"query": query}
        if repository_id is not None:
            payload["repository_id"] = repository_id
        return self.post(self._build_url("/rag/citations/validate"), data=payload)

    def graph_retrieve(
        self,
        query: str,
        repository_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> dict:
        """Graph traversal retrieval over the code-intelligence graph."""
        payload: dict[str, Any] = {"query": query}
        if repository_id is not None:
            payload["repository_id"] = repository_id
        if limit is not None:
            payload["limit"] = limit
        return self.post(self._build_url("/rag/graph/retrieve"), data=payload)

    # ─── Index versions & health ────────────────────────────────────────

    def index_versions(
        self,
        source_id: Optional[str] = None,
        repository_id: Optional[str] = None,
    ) -> list[dict]:
        """List knowledge source versions."""
        params: dict[str, Any] = {}
        if source_id is not None:
            params["source_id"] = source_id
        if repository_id is not None:
            params["repository_id"] = repository_id
        return self.get(self._build_url("/rag/index/versions"), params=params)

    def knowledge_health(self) -> dict:
        """Return knowledge health metrics for the tenant."""
        return self.get(self._build_url("/rag/health"))

    # ─── Evaluation ─────────────────────────────────────────────────────

    def evaluate(
        self,
        dataset_name: str,
        queries: list[str],
        expected_chunk_ids: list[list[str]],
        query_type: Optional[str] = None,
        rerank_strategy: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> dict:
        """Compute IR metrics over the provided queries vs expected chunk ids."""
        payload: dict[str, Any] = {
            "dataset_name": dataset_name,
            "queries": queries,
            "expected_chunk_ids": expected_chunk_ids,
        }
        if query_type is not None:
            payload["query_type"] = query_type
        if rerank_strategy is not None:
            payload["rerank_strategy"] = rerank_strategy
        if limit is not None:
            payload["limit"] = limit
        return self.post(self._build_url("/rag/evaluate"), data=payload)

    def list_evaluation_runs(self, limit: int = 50) -> list[dict]:
        """List recent RAG evaluation runs."""
        return self.get(self._build_url("/rag/evaluation/runs"), params={"limit": limit})


# ---------------------------------------------------------------------------
# Async mixin
# ---------------------------------------------------------------------------


class AsyncRagMixin:
    """Mixin that adds Knowledge & RAG methods to ``AsyncNovaForgeClient``.

    Expects the host class to provide ``self.get()``, ``self.post()``,
    ``self.put()``, ``self.delete()`` and ``self._build_url()``.
    """

    # ─── Source management ──────────────────────────────────────────────

    async def create_source(
        self,
        name: str,
        source_type: str,
        source_uri: Optional[str] = None,
        repository_id: Optional[str] = None,
        content: Optional[str] = None,
        permissions: Optional[dict] = None,
        classification: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        """Register a new knowledge source."""
        payload: dict[str, Any] = {"name": name, "source_type": source_type}
        if source_uri is not None:
            payload["source_uri"] = source_uri
        if repository_id is not None:
            payload["repository_id"] = repository_id
        if content is not None:
            payload["content"] = content
        if permissions is not None:
            payload["permissions"] = permissions
        if classification is not None:
            payload["classification"] = classification
        if metadata is not None:
            payload["metadata"] = metadata
        return await self.post(self._build_url("/rag/sources"), data=payload)

    async def list_sources(
        self,
        repository_id: Optional[str] = None,
        source_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[dict]:
        """List knowledge sources."""
        params: dict[str, Any] = {}
        if repository_id is not None:
            params["repository_id"] = repository_id
        if source_type is not None:
            params["source_type"] = source_type
        if status is not None:
            params["status"] = status
        return await self.get(self._build_url("/rag/sources"), params=params)

    async def get_source(self, source_id: str) -> dict:
        """Get a single knowledge source."""
        return await self.get(self._build_url(f"/rag/sources/{source_id}"))

    async def index_source(self, source_id: str, content: Optional[str] = None) -> dict:
        """Trigger indexing of a knowledge source."""
        payload: dict[str, Any] = {}
        if content is not None:
            payload["content"] = content
        return await self.post(self._build_url(f"/rag/sources/{source_id}/index"), data=payload)

    async def delete_source(self, source_id: str) -> dict:
        """Soft-delete a knowledge source and propagate deletion."""
        return await self.delete(self._build_url(f"/rag/sources/{source_id}"))

    async def source_status(self, source_id: str) -> dict:
        """Get the status / version / staleness of a source."""
        return await self.get(self._build_url(f"/rag/sources/{source_id}/status"))

    async def update_permissions(
        self,
        source_id: str,
        permissions: Optional[dict] = None,
        classification: Optional[str] = None,
    ) -> dict:
        """Update a source's permissions and/or classification."""
        payload: dict[str, Any] = {}
        if permissions is not None:
            payload["permissions"] = permissions
        if classification is not None:
            payload["classification"] = classification
        return await self.put(self._build_url(f"/rag/sources/{source_id}/permissions"), data=payload)

    # ─── Retrieval ──────────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        repository_id: Optional[str] = None,
        filters: Optional[dict] = None,
        limit: Optional[int] = None,
        rerank_strategy: Optional[str] = None,
    ) -> dict:
        """Hybrid retrieval returning assembled context and citations."""
        payload: dict[str, Any] = {"query": query}
        if repository_id is not None:
            payload["repository_id"] = repository_id
        if filters is not None:
            payload["filters"] = filters
        if limit is not None:
            payload["limit"] = limit
        if rerank_strategy is not None:
            payload["rerank_strategy"] = rerank_strategy
        return await self.post(self._build_url("/rag/search"), data=payload)

    async def hybrid_search(
        self,
        query: str,
        repository_id: Optional[str] = None,
        filters: Optional[dict] = None,
        limit: Optional[int] = None,
        rerank_strategy: Optional[str] = None,
    ) -> dict:
        """Hybrid retrieval returning the full ContextSet plus query intent."""
        payload: dict[str, Any] = {"query": query}
        if repository_id is not None:
            payload["repository_id"] = repository_id
        if filters is not None:
            payload["filters"] = filters
        if limit is not None:
            payload["limit"] = limit
        if rerank_strategy is not None:
            payload["rerank_strategy"] = rerank_strategy
        return await self.post(self._build_url("/rag/hybrid"), data=payload)

    async def context(
        self,
        query: str,
        repository_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> dict:
        """Return only the assembled context set for a query."""
        payload: dict[str, Any] = {"query": query}
        if repository_id is not None:
            payload["repository_id"] = repository_id
        if limit is not None:
            payload["limit"] = limit
        return await self.post(self._build_url("/rag/context"), data=payload)

    async def validate_citations(
        self,
        query: str,
        repository_id: Optional[str] = None,
    ) -> dict:
        """Run retrieval and split citations into valid / invalid."""
        payload: dict[str, Any] = {"query": query}
        if repository_id is not None:
            payload["repository_id"] = repository_id
        return await self.post(self._build_url("/rag/citations/validate"), data=payload)

    async def graph_retrieve(
        self,
        query: str,
        repository_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> dict:
        """Graph traversal retrieval over the code-intelligence graph."""
        payload: dict[str, Any] = {"query": query}
        if repository_id is not None:
            payload["repository_id"] = repository_id
        if limit is not None:
            payload["limit"] = limit
        return await self.post(self._build_url("/rag/graph/retrieve"), data=payload)

    # ─── Index versions & health ────────────────────────────────────────

    async def index_versions(
        self,
        source_id: Optional[str] = None,
        repository_id: Optional[str] = None,
    ) -> list[dict]:
        """List knowledge source versions."""
        params: dict[str, Any] = {}
        if source_id is not None:
            params["source_id"] = source_id
        if repository_id is not None:
            params["repository_id"] = repository_id
        return await self.get(self._build_url("/rag/index/versions"), params=params)

    async def knowledge_health(self) -> dict:
        """Return knowledge health metrics for the tenant."""
        return await self.get(self._build_url("/rag/health"))

    # ─── Evaluation ─────────────────────────────────────────────────────

    async def evaluate(
        self,
        dataset_name: str,
        queries: list[str],
        expected_chunk_ids: list[list[str]],
        query_type: Optional[str] = None,
        rerank_strategy: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> dict:
        """Compute IR metrics over the provided queries vs expected chunk ids."""
        payload: dict[str, Any] = {
            "dataset_name": dataset_name,
            "queries": queries,
            "expected_chunk_ids": expected_chunk_ids,
        }
        if query_type is not None:
            payload["query_type"] = query_type
        if rerank_strategy is not None:
            payload["rerank_strategy"] = rerank_strategy
        if limit is not None:
            payload["limit"] = limit
        return await self.post(self._build_url("/rag/evaluate"), data=payload)

    async def list_evaluation_runs(self, limit: int = 50) -> list[dict]:
        """List recent RAG evaluation runs."""
        return await self.get(self._build_url("/rag/evaluation/runs"), params={"limit": limit})
