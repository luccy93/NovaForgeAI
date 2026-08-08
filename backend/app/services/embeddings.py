import logging
from typing import Optional
from functools import wraps

import numpy as np
from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    _instance: Optional["EmbeddingService"] = None
    _openai_client: Optional[object] = None
    _google_client: Optional[object] = None
    _local_model: Optional[object] = None
    _backend: str = "openai"

    def __new__(cls) -> "EmbeddingService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._init_clients()

    def _init_clients(self) -> None:
        try:
            if settings.openai_api_key:
                import openai
                self._openai_client = openai.OpenAI(api_key=settings.openai_api_key)
                self._backend = "openai"
                logger.info("EmbeddingService using OpenAI backend")
                return
        except Exception as e:
            logger.warning("OpenAI init failed: %s", e)

        try:
            if settings.google_api_key:
                import google.generativeai as genai
                genai.configure(api_key=settings.google_api_key)
                self._google_client = genai
                self._backend = "google"
                logger.info("EmbeddingService using Google backend")
                return
        except Exception as e:
            logger.warning("Google init failed: %s", e)

        try:
            from sentence_transformers import SentenceTransformer
            self._local_model = SentenceTransformer("all-MiniLM-L6-v2")
            self._backend = "local"
            logger.info("EmbeddingService using local sentence-transformers backend")
        except Exception as e:
            logger.warning("sentence-transformers init failed: %s", e)
            self._backend = "none"

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        if self._backend == "openai" and self._openai_client is not None:
            return self._get_openai_embeddings(texts)
        if self._backend == "google" and self._google_client is not None:
            return self._get_google_embeddings(texts)
        if self._backend == "local" and self._local_model is not None:
            return self._get_local_embeddings(texts)

        raise RuntimeError("No embedding backend available")

    def _get_openai_embeddings(self, texts: list[str]) -> list[list[float]]:
        resp = self._openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=texts,
        )
        return [item.embedding for item in resp.data]

    def _get_google_embeddings(self, texts: list[str]) -> list[list[float]]:
        result = self._google_client.embed_content(
            model="models/embedding-001",
            content=texts,
            task_type="retrieval_document",
        )
        return result["embedding"]

    def _get_local_embeddings(self, texts: list[str]) -> list[list[float]]:
        embeddings = self._local_model.encode(texts, show_progress_bar=False)
        if isinstance(embeddings, np.ndarray):
            return embeddings.tolist()
        return [e.tolist() if isinstance(e, np.ndarray) else e for e in embeddings]

    @property
    def dimension(self) -> int:
        sample = self.get_embeddings(["test"])
        return len(sample[0])
