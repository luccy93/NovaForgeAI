import logging
from typing import Any, Optional
from dataclasses import dataclass

from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from qdrant_client.http.exceptions import UnexpectedResponse

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class PointStruct:
    id: int | str
    vector: list[float]
    payload: dict[str, Any] | None = None


class VectorStoreService:
    """Qdrant-backed vector store.

    All public operations fail soft: when Qdrant is unreachable they log a
    warning and return empty results instead of raising, so retrieval
    degrades gracefully (e.g. RAG answers with "no context").
    """

    def __init__(self) -> None:
        try:
            self._client = QdrantClient(
                url=settings.qdrant_url,
                prefer_grpc=True,
            )
        except Exception as e:
            logger.warning("Qdrant client init failed (%s); vector search disabled", e)
            self._client = None

    def create_collection(self, name: str, size: int = 1536) -> bool:
        if self._client is None:
            return False
        try:
            self._client.create_collection(
                collection_name=name,
                vectors_config=qdrant_models.VectorParams(
                    size=size,
                    distance=qdrant_models.Distance.COSINE,
                ),
            )
            logger.info("Created collection '%s' (size=%d)", name, size)
            return True
        except UnexpectedResponse as e:
            if "already exists" in str(e):
                return False
            logger.warning("Failed to create collection '%s': %s", name, e)
            return False
        except Exception as e:
            logger.warning("Failed to create collection '%s': %s", name, e)
            return False

    def _ensure_collection(self, name: str, size: int = 1536) -> None:
        if self._client is None:
            return
        try:
            self._client.get_collection(collection_name=name)
        except Exception:
            self.create_collection(name=name, size=size)

    def upsert_points(self, collection: str, points: list[PointStruct], size: int = 1536) -> int:
        if self._client is None:
            return 0
        try:
            self._ensure_collection(collection, size=size)
            qdrant_points = [
                qdrant_models.PointStruct(
                    id=p.id,
                    vector=p.vector,
                    payload=p.payload or {},
                )
                for p in points
            ]
            result = self._client.upsert(
                collection_name=collection,
                points=qdrant_points,
                wait=True,
            )
            logger.info("Upserted %d points into '%s'", len(points), collection)
            return result.status.value if hasattr(result, "status") else len(points)
        except Exception as e:
            logger.warning("Qdrant upsert failed for '%s': %s", collection, e)
            return 0

    def search(
        self,
        collection: str,
        query_vector: list[float],
        limit: int = 10,
        filter_: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        if self._client is None:
            return []
        try:
            self._ensure_collection(collection)
            qdrant_filter = None
            if filter_:
                qdrant_filter = qdrant_models.Filter(**filter_)

            results = self._client.search(
                collection_name=collection,
                query_vector=query_vector,
                limit=limit,
                query_filter=qdrant_filter,
            )
            return [
                {
                    "id": r.id,
                    "score": r.score,
                    "payload": r.payload,
                    "vector": r.vector,
                }
                for r in results
            ]
        except Exception as e:
            logger.warning("Qdrant search failed on '%s': %s", collection, e)
            return []

    def delete_collection(self, name: str) -> bool:
        if self._client is None:
            return False
        try:
            self._client.delete_collection(collection_name=name)
            logger.info("Deleted collection '%s'", name)
            return True
        except Exception as e:
            logger.warning("Failed to delete collection '%s': %s", name, e)
            return False

    def collection_exists(self, name: str) -> bool:
        if self._client is None:
            return False
        try:
            self._client.get_collection(collection_name=name)
            return True
        except Exception:
            return False
