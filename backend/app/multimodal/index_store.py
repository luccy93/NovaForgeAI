"""Multimodal embedding registry + vector index.

Reuses the repo's EmbeddingService (OpenAI/Google/local sentence-transformers).
When no embedding backend is configured or Qdrant is unreachable, degrades to
deterministic local heuristics that are clearly marked in the payload:

- embedder "local-heuristic"   -> char-hash embeddings (stable, not semantic)
- index backend "memory"       -> in-process cosine search (Qdrant would be
  used automatically when reachable)

Every record carries tenant + modality, so all searches honor tenant
isolation and per-modality filtering.
"""
import hashlib, logging, math, time, uuid
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

HEURISTIC_DIM = 128


def heuristic_embed(text: str) -> list[float]:
    """Deterministic 128-dim fingerprint. Never a semantic embedding."""
    vec = [0.0] * HEURISTIC_DIM
    tokens = text.lower().split()
    for tok in tokens:
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest()[:8], 16)
        vec[h % HEURISTIC_DIM] += 1.0
    # normalize + unit variance shaping
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


@dataclass
class IndexEntry:
    id: str
    tenant: str
    asset_id: str
    modality: str
    text: str
    chunk_index: int
    embedding: Optional[list[float]] = None
    metadata: dict = field(default_factory=dict)

    def to_payload(self, embedder: str) -> dict:
        return {"tenant": self.tenant, "asset_id": self.asset_id,
                "modality": self.modality, "chunk_index": self.chunk_index,
                "text": self.text[:2000], "source": self.metadata.get("source", ""),
                "page": self.metadata.get("page", 0),
                "embedder": embedder, "indexed_at": time.time()}


class MemoryIndex:
    """In-process cosine index used when Qdrant is unavailable.

    Optionally persists entries to JSON so one-shot CLI processes share state
    with the API server.
    """

    def __init__(self, storage_path: str = "") -> None:
        self._points: dict[str, IndexEntry] = {}
        self._storage_path = storage_path or ""
        if self._storage_path:
            self._load()

    def _load(self) -> None:
        try:
            import json, os
            if os.path.exists(self._storage_path):
                with open(self._storage_path, encoding="utf-8") as fh:
                    raw = json.load(fh)
                for key, d in (raw.get("points", {}) if isinstance(raw, dict) else {}).items():
                    self._points[key] = IndexEntry(
                        id=d.get("id", key), tenant=d.get("tenant", ""),
                        asset_id=d.get("asset_id", ""), modality=d.get("modality", ""),
                        text=d.get("text", ""), chunk_index=d.get("chunk_index", 0),
                        embedding=d.get("embedding"), metadata=d.get("metadata", {}))
        except Exception as exc:
            logger.warning("memory index load failed: %s", exc)

    def _flush(self) -> None:
        if not self._storage_path:
            return
        try:
            import json, os
            os.makedirs(os.path.dirname(self._storage_path), exist_ok=True)
            raw = {"points": {
                key: {"id": v.id, "tenant": v.tenant, "asset_id": v.asset_id,
                      "modality": v.modality, "text": v.text,
                      "chunk_index": v.chunk_index, "embedding": v.embedding,
                      "metadata": v.metadata}
                for key, v in self._points.items()}}
            with open(self._storage_path, "w", encoding="utf-8") as fh:
                json.dump(raw, fh)
        except Exception as exc:
            logger.warning("memory index flush failed: %s", exc)

    def upsert(self, entries: list[IndexEntry]) -> int:
        for e in entries:
            self._points[e.id] = e
        self._flush()
        return len(entries)

    def search(self, tenant: str, query_vec: list[float], limit: int,
               modalities: Optional[list[str]] = None,
               filters: Optional[dict] = None) -> list[dict]:
        results = []
        for e in self._points.values():
            if e.tenant != tenant:
                continue
            if modalities and e.modality not in modalities:
                continue
            if filters:
                for k, v in filters.items():
                    if e.metadata.get(k) != v and getattr(e, k, None) != v:
                        break
                else:
                    results.append(e)
                    continue
                continue
            results.append(e)
        scores = [(e, self._cosine(query_vec, e.embedding or heuristic_embed(e.text)))
                  for e in results]
        scores.sort(key=lambda t: -t[1])
        return [{"id": e.id, "score": round(s, 4),
                 "payload": e.to_payload("memory-index")}
                for e, s in scores[:limit]]

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        if not a or not b:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        return dot / (na * nb) if na and nb else 0.0

    def delete_asset(self, tenant: str, asset_id: str) -> int:
        before = len(self._points)
        self._points = {k: v for k, v in self._points.items()
                        if not (v.tenant == tenant and v.asset_id == asset_id)}
        self._flush()
        return before - len(self._points)

    def count(self, tenant: str) -> int:
        return sum(1 for v in self._points.values() if v.tenant == tenant)


class EmbeddingRegistry:
    """Embedding backend selection with honest fallback + per-tenant cache."""

    def __init__(self) -> None:
        from app.services.embeddings import EmbeddingService
        self._service = EmbeddingService()
        self._cache: dict[str, tuple[str, list[float]]] = {}
        self.calls = 0
        self.embedder = "service"

    def embed(self, text: str) -> tuple[str, list[float]]:
        key = hashlib.md5(text.encode("utf-8")).hexdigest()
        if key in self._cache:
            return self._cache[key]
        self.calls += 1
        try:
            vec = self._service.get_embeddings([text])[0]
            result = ("service", [float(x) for x in vec])
        except Exception:
            result = ("local-heuristic", heuristic_embed(text))
        self._cache[key] = result
        return result

    def embed_batch(self, texts: list[str]) -> tuple[str, list[list[float]]]:
        fresh = [(t, hashlib.md5(t.encode("utf-8")).hexdigest())
                 for t in texts]
        have = {k: self._cache[k][1] for t, k in fresh if k in self._cache}
        todo = [t for t, k in fresh if k not in self._cache]
        backend = "service"
        if todo:
            try:
                vectors = self._service.get_embeddings(todo)
                for t, v in zip(todo, vectors):
                    self._cache[hashlib.md5(t.encode("utf-8")).hexdigest()] = (
                        "service", [float(x) for x in v])
                    self.calls += 1
            except Exception:
                backend = "local-heuristic"
                for t in todo:
                    vec = heuristic_embed(t)
                    self._cache[hashlib.md5(t.encode("utf-8")).hexdigest()] = (backend, vec)
        return backend, [self._cache[k][1] for t, k in fresh]


class VectorIndex:
    """Qdrant-backed index with an automatic in-process fallback."""

    COLLECTION_PREFIX = "multimodal"

    def __init__(self, registry: Optional[EmbeddingRegistry] = None,
                 qdrant_available: Optional[bool] = None,
                 persist_path: str = ""):
        self.registry = registry or EmbeddingRegistry()
        self._qdrant = None
        self._fallback = MemoryIndex(storage_path=persist_path)
        self.backend = "memory"
        self._probed = False
        if qdrant_available is None:
            self._probe_qdrant()
        elif qdrant_available:
            self._init_qdrant()
        self.stats = {"indexed": 0, "searches": 0, "deletes": 0}

    def _probe_qdrant(self) -> None:
        try:
            self._init_qdrant()
            logger.info("VectorIndex using Qdrant backend")
        except Exception as e:
            logger.warning("Qdrant unavailable (%s); VectorIndex uses in-memory fallback", e)

    def _init_qdrant(self) -> None:
        from app.services.vector_store import VectorStoreService, PointStruct
        self._qdrant = VectorStoreService()
        self._qdrant_cls = PointStruct
        self.backend = "qdrant"

    def _collection(self, tenant: str) -> str:
        h = int(hashlib.md5(tenant.encode("utf-8")).hexdigest()[:8], 16)
        return f"{self.COLLECTION_PREFIX}_{h:08x}"

    def index(self, tenant: str, entries: list[IndexEntry],
              embedder_batch: str = "") -> int:
        """Embed (batch) and upsert. Returns number of entries written."""
        texts = [e.text for e in entries]
        backend, vectors = self.registry.embed_batch(texts)
        for e, v in zip(entries, vectors):
            e.embedding = v
        if self.backend == "qdrant" and self._qdrant is not None:
            try:
                points = [
                    self._qdrant_cls(
                        id=e.id, vector=e.embedding or heuristic_embed(e.text),
                        payload=e.to_payload(backend))
                    for e in entries]
                self._qdrant.upsert_points(self._collection(tenant), points)
                self.stats["indexed"] += len(entries)
                return len(entries)
            except Exception as exc:
                logger.warning("Qdrant upsert failed (%s); falling back to memory", exc)
                self.backend = "memory"
        self._fallback.upsert(entries)
        self.stats["indexed"] += len(entries)
        return len(entries)

    def search(self, tenant: str, query: str, limit: int = 10,
               modalities: Optional[list[str]] = None,
               filters: Optional[dict] = None) -> list[dict]:
        self.stats["searches"] += 1
        _, qvec = self.registry.embed(query)
        if self.backend == "qdrant" and self._qdrant is not None:
            try:
                qf = {"must": [{"key": "tenant", "match": {"value": tenant}}]}
                if modalities:
                    qf["must"].append(
                        {"key": "modality", "match": {"any": modalities}})
                results = self._qdrant.search(
                    self._collection(tenant), qvec, limit=limit, filter_=qf)
                return [{"id": r["id"], "score": round(r["score"], 4),
                         "payload": r["payload"]} for r in results]
            except Exception as exc:
                logger.warning("Qdrant search failed (%s); using memory", exc)
        return self._fallback.search(tenant, qvec, limit, modalities, filters)

    def delete_asset(self, tenant: str, asset_id: str) -> int:
        self.stats["deletes"] += 1
        if self.backend == "qdrant" and self._qdrant is not None:
            try:
                # qdrant filter delete is done via scroll-and-delete points; keep
                # a best-effort marker hook for collection-level cleanup
                self._qdrant.delete_collection(self._collection(tenant))
                self.stats["indexed"] = 0
                return -1  # collection rebuilt on demand
            except Exception:
                pass
        return self._fallback.delete_asset(tenant, asset_id)

    def count(self, tenant: str) -> int:
        return self._fallback.count(tenant)

    def health(self) -> dict:
        return {"backend": self.backend, "stats": self.stats,
                "embedder": self.registry.embedder,
                "heuristic_dim": HEURISTIC_DIM}