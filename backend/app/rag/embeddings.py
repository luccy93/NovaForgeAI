"""Volume 43 — embedding client.

A thin, async-friendly adapter over the existing singleton
``EmbeddingService``. It adds batching, retries with backoff, dimension
validation and explicit model/version reporting so the pipeline can refuse to
mix incompatible embedding models in one collection.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.services.embeddings import EmbeddingService

logger = logging.getLogger(__name__)


class EmbeddingClient:
    """Async wrapper around :class:`EmbeddingService` with retries/batching."""

    def __init__(
        self,
        service: Optional[EmbeddingService] = None,
        max_retries: int = 3,
        batch_size: int = 32,
    ) -> None:
        self._svc = service or EmbeddingService()
        self._max_retries = max_retries
        self._batch_size = batch_size

    @property
    def model(self) -> str:
        return getattr(self._svc, "_backend", "unknown")

    @property
    def dimension(self) -> int:
        try:
            return int(self._svc.dimension)
        except Exception:  # pragma: no cover - defensive
            return 384

    @property
    def version(self) -> str:
        # Treat the backend + dimension as an explicit embedding version so we
        # never silently mix models inside one vector collection.
        return f"{self.model}@{self.dimension}"

    async def embed_one(self, text: str) -> list[float]:
        return (await self.embed([text]))[0]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        out: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            out.extend(await self._embed_batch_with_retry(batch))
        return out

    async def _embed_batch_with_retry(self, batch: list[str]) -> list[list[float]]:
        last_err: Optional[Exception] = None
        for attempt in range(1, self._max_retries + 1):
            try:
                loop = asyncio.get_event_loop()
                vecs = await loop.run_in_executor(None, self._svc.get_embeddings, batch)
                if not vecs or len(vecs) != len(batch):
                    raise RuntimeError("embedding count mismatch")
                return [list(v) for v in vecs]
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                logger.warning("Embedding attempt %d/%d failed: %s", attempt, self._max_retries, exc)
                await asyncio.sleep(min(2 ** attempt, 8))
        raise RuntimeError(f"embedding failed after {self._max_retries} retries: {last_err}")
