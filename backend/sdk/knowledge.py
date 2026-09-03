"""Knowledge SDK — Volume 68."""

from typing import Any, Dict, Optional


class KnowledgeMixin:
    """Synchronous Knowledge mixin (namespace /api/v1/knowledge)."""

    def search_knowledge(
        self, query: str, *, source_type: str | None = None,
        doc_type: str | None = None, classification: str | None = None,
        limit: int = 20, offset: int = 0,
    ) -> dict:
        params: Dict[str, Any] = {"query": query, "limit": limit, "offset": offset}
        if source_type:
            params["source_type"] = source_type
        if doc_type:
            params["doc_type"] = doc_type
        if classification:
            params["classification"] = classification
        return self.get(self._build_url("/knowledge/search"), params=params)

    def list_knowledge_sources(self, *, status: str | None = None, limit: int = 50) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        return self.get(self._build_url("/knowledge/sources"), params=params)

    def create_knowledge_source(
        self, name: str, source_type: str, *,
        connector_config: dict | None = None, classification: str = "INTERNAL",
        region: str | None = None,
    ) -> dict:
        payload: Dict[str, Any] = {
            "name": name, "source_type": source_type, "classification": classification,
        }
        if connector_config:
            payload["connector_config"] = connector_config
        if region:
            payload["region"] = region
        return self.post(self._build_url("/knowledge/sources"), data=payload)

    def get_knowledge_source(self, source_id: str) -> dict:
        return self.get(self._build_url(f"/knowledge/sources/{source_id}"))

    def update_knowledge_source(
        self, source_id: str, *, status: str | None = None,
        connector_config: dict | None = None, classification: str | None = None,
    ) -> dict:
        payload: Dict[str, Any] = {}
        if status:
            payload["status"] = status
        if connector_config:
            payload["connector_config"] = connector_config
        if classification:
            payload["classification"] = classification
        return self.patch(self._build_url(f"/knowledge/sources/{source_id}"), data=payload)

    def delete_knowledge_source(self, source_id: str) -> dict:
        return self.delete(self._build_url(f"/knowledge/sources/{source_id}"))

    def get_knowledge_document(self, document_id: str) -> dict:
        return self.get(self._build_url(f"/knowledge/documents/{document_id}"))

    def add_knowledge_document(
        self, source_id: str, external_id: str, title: str, content: str, *,
        doc_type: str = "document", classification: str = "INTERNAL",
        tags: list | None = None,
    ) -> dict:
        payload: Dict[str, Any] = {
            "source_id": source_id, "external_id": external_id,
            "title": title, "content": content,
            "doc_type": doc_type, "classification": classification,
        }
        if tags:
            payload["tags"] = tags
        return self.post(self._build_url("/knowledge/documents"), data=payload)

    def trigger_ingestion(self, source_id: str, job_type: str = "incremental") -> dict:
        return self.post(
            self._build_url("/knowledge/ingestion/jobs"),
            data={"source_id": source_id, "job_type": job_type},
        )

    def list_ingestion_jobs(self, *, source_id: str | None = None, limit: int = 50) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if source_id:
            params["source_id"] = source_id
        return self.get(self._build_url("/knowledge/ingestion/jobs"), params=params)

    def get_ingestion_job(self, job_id: str) -> dict:
        return self.get(self._build_url(f"/knowledge/ingestion/jobs/{job_id}"))

    def trigger_reindex(self, source_id: str) -> dict:
        return self.post(
            self._build_url("/knowledge/ingestion/reindex"),
            data={"source_id": source_id},
        )

    def list_knowledge_entities(self, *, entity_type: str | None = None, limit: int = 50) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if entity_type:
            params["entity_type"] = entity_type
        return self.get(self._build_url("/knowledge/entities"), params=params)

    def create_knowledge_entity(
        self, entity_type: str, name: str, *,
        canonical_id: str | None = None, description: str | None = None,
        properties: dict | None = None, classification: str = "INTERNAL",
    ) -> dict:
        payload: Dict[str, Any] = {
            "entity_type": entity_type, "name": name, "classification": classification,
        }
        if canonical_id:
            payload["canonical_id"] = canonical_id
        if description:
            payload["description"] = description
        if properties:
            payload["properties"] = properties
        return self.post(self._build_url("/knowledge/entities"), data=payload)

    def get_knowledge_entity(self, entity_id: str) -> dict:
        return self.get(self._build_url(f"/knowledge/entities/{entity_id}"))

    def create_knowledge_link(
        self, source_entity_id: str, target_entity_id: str, link_type: str, *,
        weight: float = 1.0, properties: dict | None = None,
    ) -> dict:
        payload: Dict[str, Any] = {
            "source_entity_id": source_entity_id,
            "target_entity_id": target_entity_id,
            "link_type": link_type,
            "weight": weight,
        }
        if properties:
            payload["properties"] = properties
        return self.post(self._build_url("/knowledge/links"), data=payload)

    def get_freshness_stats(self) -> dict:
        return self.get(self._build_url("/knowledge/freshness/stats"))

    def mark_stale_documents(self, older_than_hours: int = 168) -> dict:
        return self.post(
            self._build_url("/knowledge/freshness/mark-stale"),
            data={"older_than_hours": older_than_hours},
        )

    def get_knowledge_usage(self, *, since_hours: int = 24) -> dict:
        return self.get(
            self._build_url("/knowledge/audit/usage"),
            params={"since_hours": since_hours},
        )

    def get_query_history(self, *, limit: int = 50) -> dict:
        return self.get(
            self._build_url("/knowledge/audit/history"),
            params={"limit": limit},
        )


class AsyncKnowledgeMixin:
    """Async Knowledge mixin — same interface, uses await + self.post/get."""

    async def search_knowledge(
        self, query: str, *, source_type: str | None = None,
        doc_type: str | None = None, classification: str | None = None,
        limit: int = 20, offset: int = 0,
    ) -> dict:
        params: Dict[str, Any] = {"query": query, "limit": limit, "offset": offset}
        if source_type:
            params["source_type"] = source_type
        if doc_type:
            params["doc_type"] = doc_type
        if classification:
            params["classification"] = classification
        return await self.get(self._build_url("/knowledge/search"), params=params)

    async def list_knowledge_sources(self, *, status: str | None = None, limit: int = 50) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        return await self.get(self._build_url("/knowledge/sources"), params=params)

    async def create_knowledge_source(
        self, name: str, source_type: str, *,
        connector_config: dict | None = None, classification: str = "INTERNAL",
        region: str | None = None,
    ) -> dict:
        payload: Dict[str, Any] = {
            "name": name, "source_type": source_type, "classification": classification,
        }
        if connector_config:
            payload["connector_config"] = connector_config
        if region:
            payload["region"] = region
        return await self.post(self._build_url("/knowledge/sources"), data=payload)

    async def get_knowledge_source(self, source_id: str) -> dict:
        return await self.get(self._build_url(f"/knowledge/sources/{source_id}"))

    async def update_knowledge_source(
        self, source_id: str, *, status: str | None = None,
        connector_config: dict | None = None, classification: str | None = None,
    ) -> dict:
        payload: Dict[str, Any] = {}
        if status:
            payload["status"] = status
        if connector_config:
            payload["connector_config"] = connector_config
        if classification:
            payload["classification"] = classification
        return await self.patch(self._build_url(f"/knowledge/sources/{source_id}"), data=payload)

    async def delete_knowledge_source(self, source_id: str) -> dict:
        return await self.delete(self._build_url(f"/knowledge/sources/{source_id}"))

    async def get_knowledge_document(self, document_id: str) -> dict:
        return await self.get(self._build_url(f"/knowledge/documents/{document_id}"))

    async def add_knowledge_document(
        self, source_id: str, external_id: str, title: str, content: str, *,
        doc_type: str = "document", classification: str = "INTERNAL",
        tags: list | None = None,
    ) -> dict:
        payload: Dict[str, Any] = {
            "source_id": source_id, "external_id": external_id,
            "title": title, "content": content,
            "doc_type": doc_type, "classification": classification,
        }
        if tags:
            payload["tags"] = tags
        return await self.post(self._build_url("/knowledge/documents"), data=payload)

    async def trigger_ingestion(self, source_id: str, job_type: str = "incremental") -> dict:
        return await self.post(
            self._build_url("/knowledge/ingestion/jobs"),
            data={"source_id": source_id, "job_type": job_type},
        )

    async def get_ingestion_job(self, job_id: str) -> dict:
        return await self.get(self._build_url(f"/knowledge/ingestion/jobs/{job_id}"))

    async def list_knowledge_entities(self, *, entity_type: str | None = None, limit: int = 50) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if entity_type:
            params["entity_type"] = entity_type
        return await self.get(self._build_url("/knowledge/entities"), params=params)

    async def create_knowledge_entity(
        self, entity_type: str, name: str, *,
        canonical_id: str | None = None, description: str | None = None,
        properties: dict | None = None, classification: str = "INTERNAL",
    ) -> dict:
        payload: Dict[str, Any] = {
            "entity_type": entity_type, "name": name, "classification": classification,
        }
        if canonical_id:
            payload["canonical_id"] = canonical_id
        if description:
            payload["description"] = description
        if properties:
            payload["properties"] = properties
        return await self.post(self._build_url("/knowledge/entities"), data=payload)

    async def create_knowledge_link(
        self, source_entity_id: str, target_entity_id: str, link_type: str, *,
        weight: float = 1.0, properties: dict | None = None,
    ) -> dict:
        payload: Dict[str, Any] = {
            "source_entity_id": source_entity_id,
            "target_entity_id": target_entity_id,
            "link_type": link_type,
            "weight": weight,
        }
        if properties:
            payload["properties"] = properties
        return await self.post(self._build_url("/knowledge/links"), data=payload)

    async def get_freshness_stats(self) -> dict:
        return await self.get(self._build_url("/knowledge/freshness/stats"))

    async def mark_stale_documents(self, older_than_hours: int = 168) -> dict:
        return await self.post(
            self._build_url("/knowledge/freshness/mark-stale"),
            data={"older_than_hours": older_than_hours},
        )

    async def get_knowledge_usage(self, *, since_hours: int = 24) -> dict:
        return await self.get(
            self._build_url("/knowledge/audit/usage"),
            params={"since_hours": since_hours},
        )
