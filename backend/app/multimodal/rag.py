"""Multimodal RAG: cross-modal retrieval, citation-grounded answers, KG interlink.

- Retrieval: VectorIndex with per-tenant isolation + modality filters.
- Answers: provider-neutral. When an OpenAI-compatible LLM key is configured a
  grounded summary is generated over retrieved evidence; otherwise an honest
  evidence-concatenation answer is returned (marked `synthesized: false`).
- Citations: every source carries asset_id, modality, chunk text, and score.
- KG: `interlink` writes asset/entity nodes and relationships to Neo4j through
  GraphStoreService when reachable; failures are reported, never blocking.
"""
import json, logging, os, time, uuid
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class RAGSource:
    asset_id: str
    modality: str
    text: str
    score: float
    chunk_index: int = 0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"asset_id": self.asset_id, "modality": self.modality,
                "text": self.text[:500], "score": round(self.score, 4),
                "chunk_index": self.chunk_index, "metadata": self.metadata}


@dataclass
class RAGResult:
    query: str
    tenant: str
    sources: list[RAGSource] = field(default_factory=list)
    answer: str = ""
    synthesized: bool = False
    model: str = ""
    latency_ms: float = 0.0
    error: str = ""

    def to_dict(self) -> dict:
        return {"query": self.query, "tenant": self.tenant,
                "sources": [s.to_dict() for s in self.sources],
                "answer": self.answer, "synthesized": self.synthesized,
                "model": self.model, "latency_ms": round(self.latency_ms, 2),
                "error": self.error}


class MultimodalRAG:
    """Cross-modal retrieval + citation-grounded answer synthesis."""

    def __init__(self, index: Optional["object"] = None,
                 max_context_chars: int = 6000):
        self.index = index
        self.max_context_chars = max_context_chars

    def search(self, tenant: str, query: str, limit: int = 8,
               modalities: Optional[list[str]] = None,
               filters: Optional[dict] = None) -> list[RAGSource]:
        if self.index is None:
            return []
        results = self.index.search(tenant, query, limit=limit,
                                    modalities=modalities, filters=filters)
        sources = []
        for r in results:
            p = r.get("payload", {})
            sources.append(RAGSource(
                asset_id=p.get("asset_id", ""), modality=p.get("modality", ""),
                text=p.get("text", ""), score=r.get("score", 0.0),
                chunk_index=p.get("chunk_index", 0),
                metadata={k: v for k, v in p.items()
                          if k not in ("text", "asset_id", "modality",
                                       "chunk_index", "embedder", "indexed_at")}))
        return sources

    def answer(self, tenant: str, query: str, limit: int = 8,
               modalities: Optional[list[str]] = None,
               generate: bool = True) -> RAGResult:
        start = time.time()
        sources = self.search(tenant, query, limit=limit, modalities=modalities)
        result = RAGResult(query=query, tenant=tenant, sources=sources)
        if not sources:
            result.answer = ("No relevant multimodal context found for this "
                             "tenant. Ingest documents/images/video/audio "
                             "first, then retry.")
            result.latency_ms = (time.time() - start) * 1000
            return result
        if generate:
            answer, model = self._synthesize(query, sources)
            result.answer = answer
            result.model = model
            result.synthesized = bool(model)
        else:
            result.answer = self._evidence_answer(sources)
        result.latency_ms = (time.time() - start) * 1000
        return result

    def _evidence_answer(self, sources: list[RAGSource]) -> str:
        lines = []
        for i, s in enumerate(sources, 1):
            lines.append(f"[{i}] ({s.modality}) {s.asset_id}: {s.text[:300]}")
        return ("Evidence-based answer (no generative model configured):\n"
                + "\n".join(lines))

    def _synthesize(self, query: str, sources: list[RAGSource]) -> tuple[str, str]:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return self._evidence_answer(sources), ""
        context = self._build_context(sources)
        prompt = (
            "Answer the question using ONLY the provided multimodal context.\n"
            f"QUESTION: {query}\n\nCONTEXT:\n{context}\n\n"
            "Rules: cite sources as [n] using their numbers; if the context "
            "lacks the answer, say so explicitly. Be concise.")
        try:
            import openai
            client = openai.OpenAI(api_key=api_key)
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800, temperature=0.0)
            return (resp.choices[0].message.content or ""), "openai/gpt-4o-mini"
        except Exception as e:
            logger.warning("LLM synthesis failed: %s", e)
            return self._evidence_answer(sources), ""

    def _build_context(self, sources: list[RAGSource]) -> str:
        parts, total = [], 0
        for i, s in enumerate(sources, 1):
            chunk = f"[{i}] ({s.modality} / {s.asset_id}): {s.text}"
            if total + len(chunk) > self.max_context_chars:
                break
            parts.append(chunk)
            total += len(chunk)
        return "\n".join(parts)


class SynthGraph:
    """Knowledge-graph interlink for multimodal assets (Neo4j, best-effort).

    Nodes: MultimodalAsset (asset_id, tenant, modality) plus diagram
    components/relationships derived from parsed diagrams. All writes are
    guarded - a down Neo4j never breaks ingestion.
    """

    def __init__(self, driver_factory: Optional[Any] = None):
        self._driver_factory = driver_factory  # callable -> GraphStoreService

    def _service(self):
        if self._driver_factory is not None:
            return self._driver_factory()
        try:
            from app.services.graph_store import GraphStoreService
            return GraphStoreService()
        except Exception:
            return None

    async def upsert_asset(self, tenant: str, asset_id: str, modality: str,
                           title: str, tags: Optional[list[str]] = None) -> dict:
        svc = self._service()
        if svc is None:
            return {"written": False, "reason": "graph store unavailable"}
        query = (
            "MERGE (a:MultimodalAsset {asset_id: $asset_id}) "
            "SET a.tenant = $tenant, a.modality = $modality, a.title = $title, "
            "a.tags = $tags, a.updated_at = datetime() "
            "RETURN a.asset_id AS asset_id")
        try:
            records = await svc.execute_query(query, {
                "asset_id": asset_id, "tenant": tenant,
                "modality": modality, "title": title, "tags": tags or []})
            return {"written": True, "node": str(records[0]["asset_id"])
                    if records else asset_id}
        except Exception as e:
            logger.warning("KG upsert failed: %s", e)
            return {"written": False, "reason": str(e)[:200]}

    async def upsert_diagram(self, tenant: str, asset_id: str,
                             diagram: dict) -> dict:
        nodes = diagram.get("nodes", [])
        edges = diagram.get("edges", [])
        if not nodes:
            return {"written": False, "reason": "no diagram nodes"}
        svc = self._service()
        if svc is None:
            return {"written": False, "reason": "graph store unavailable"}
        try:
            node_query = (
                "MERGE (n:DiagramComponent {asset_id: $asset_id, node_id: $node_id}) "
                "SET n.label = $label, n.kind = $kind, n.tenant = $tenant "
                "RETURN n.node_id AS node_id")
            for node in nodes[:64]:
                await svc.execute_query(node_query, {
                    "asset_id": asset_id, "node_id": node.get("id", ""),
                    "label": node.get("label", ""), "kind": node.get("kind", ""),
                    "tenant": tenant})
            edge_query = (
                "MATCH (a:DiagramComponent {asset_id: $asset_id, node_id: $src}), "
                "(b:DiagramComponent {asset_id: $asset_id, node_id: $tgt}) "
                "MERGE (a)-[r:CONNECTS {kind: $kind}]->(b) RETURN count(r) AS n")
            written = 0
            for edge in edges[:128]:
                records = await svc.execute_query(edge_query, {
                    "asset_id": asset_id, "src": edge.get("source", ""),
                    "tgt": edge.get("target", ""), "kind": edge.get("kind", "")})
                written += int(records[0]["n"]) if records else 0
            return {"written": True, "nodes": len(nodes), "edges": len(edges)}
        except Exception as e:
            logger.warning("diagram KG upsert failed: %s", e)
            return {"written": False, "reason": str(e)[:200]}