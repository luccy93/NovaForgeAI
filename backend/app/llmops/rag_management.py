import json
import uuid
import hashlib
import time
import math
import re
import os
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class ChunkStrategy(Enum):
    FIXED_SIZE = "fixed_size"
    RECURSIVE_SPLIT = "recursive_split"
    SEMANTIC = "semantic"
    PARAGRAPH = "paragraph"
    SENTENCE = "sentence"
    TOKEN_BOUNDARY = "token_boundary"
    DOCUMENT_AWARE = "document_aware"


class RetrievalStrategy(Enum):
    SIMILARITY = "similarity"
    KEYWORD_HYBRID = "keyword_hybrid"
    RERANKED = "reranked"
    MULTI_QUERY = "multi_query"
    PARENT_DOCUMENT = "parent_document"
    CONTEXTUAL_COMPRESSION = "contextual_compression"


class RerankerType(Enum):
    CROSS_ENCODER = "cross_encoder"
    COHERE_RERANK = "cohere_rerank"
    BGE_RERANK = "bge_rerank"
    RECIPROCAL_RANK_FUSION = "reciprocal_rank_fusion"
    LLM_RERANK = "llm_rerank"


@dataclass
class ChunkConfig:
    id: str
    strategy: ChunkStrategy
    chunk_size: int = 512
    chunk_overlap: int = 64
    separators: list[str] = field(default_factory=lambda: ["\n\n", "\n", ".", " ", ""])
    max_chunks: int = 1000

    def to_dict(self) -> dict:
        d = asdict(self)
        d["strategy"] = self.strategy.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ChunkConfig":
        data["strategy"] = ChunkStrategy(data["strategy"])
        return cls(**data)


@dataclass
class DocumentChunk:
    id: str
    document_id: str
    content: str
    chunk_index: int = 0
    tokens: int = 0
    embedding_id: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DocumentChunk":
        return cls(**data)


@dataclass
class RAGPipeline:
    id: str
    name: str
    chunk_config: ChunkConfig
    embedding_model: str
    retrieval_strategy: RetrievalStrategy
    reranker_type: Optional[RerankerType] = None
    top_k: int = 10
    min_score: float = 0.0
    max_context_tokens: int = 4096
    org_id: str = "default"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["chunk_config"] = self.chunk_config.to_dict()
        d["retrieval_strategy"] = self.retrieval_strategy.value
        if self.reranker_type:
            d["reranker_type"] = self.reranker_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RAGPipeline":
        data["chunk_config"] = ChunkConfig.from_dict(data["chunk_config"])
        data["retrieval_strategy"] = RetrievalStrategy(data["retrieval_strategy"])
        if data.get("reranker_type"):
            data["reranker_type"] = RerankerType(data["reranker_type"])
        return cls(**data)


@dataclass
class RetrievalResult:
    id: str
    query: str
    chunks: list[dict] = field(default_factory=list)
    scores: list[float] = field(default_factory=list)
    context: str = ""
    total_tokens: int = 0
    latency_ms: float = 0.0
    reranked: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RetrievalResult":
        return cls(**data)


@dataclass
class Citation:
    id: str
    chunk_id: str
    document_id: str
    content: str
    relevance_score: float = 0.0
    citation_text: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Citation":
        return cls(**data)


class ChunkManager:
    def __init__(self, storage_dir: str = "chunk_data"):
        self.storage_dir = storage_dir
        self._chunks: dict[str, DocumentChunk] = {}
        self._configs: dict[str, ChunkConfig] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _chunks_path(self) -> str:
        return os.path.join(self.storage_dir, "chunks.json")

    def _configs_path(self) -> str:
        return os.path.join(self.storage_dir, "chunk_configs.json")

    def _save(self) -> None:
        try:
            chunks_data = {cid: c.to_dict() for cid, c in self._chunks.items()}
            with open(self._chunks_path(), "w", encoding="utf-8") as f:
                json.dump(chunks_data, f, indent=2, default=str)

            configs_data = {cid: c.to_dict() for cid, c in self._configs.items()}
            with open(self._configs_path(), "w", encoding="utf-8") as f:
                json.dump(configs_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save chunk data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._chunks_path()):
                with open(self._chunks_path(), "r", encoding="utf-8") as f:
                    chunks_data = json.load(f)
                for cid, data in chunks_data.items():
                    try:
                        self._chunks[cid] = DocumentChunk.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed chunk %s: %s", cid, e)

            if os.path.exists(self._configs_path()):
                with open(self._configs_path(), "r", encoding="utf-8") as f:
                    configs_data = json.load(f)
                for cid, data in configs_data.items():
                    try:
                        self._configs[cid] = ChunkConfig.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed chunk config %s: %s", cid, e)
        except Exception as e:
            logger.error("Failed to load chunk data: %s", e, exc_info=True)

    def _estimate_tokens(self, text: str) -> int:
        return len(text.split())

    def _split_fixed_size(self, content: str, config: ChunkConfig) -> list[str]:
        words = content.split()
        chunks = []
        for i in range(0, len(words), config.chunk_size - config.chunk_overlap):
            chunk_words = words[i:i + config.chunk_size]
            if chunk_words:
                chunks.append(" ".join(chunk_words))
            if len(chunks) >= config.max_chunks:
                break
        return chunks

    def _split_recursive(self, content: str, config: ChunkConfig) -> list[str]:
        chunks = []
        remaining = content
        for separator in config.separators:
            if len(remaining) <= config.chunk_size or not separator:
                break
            segments = remaining.split(separator)
            current = ""
            for segment in segments:
                candidate = current + (separator if current else "") + segment
                if len(candidate) <= config.chunk_size:
                    current = candidate
                else:
                    if current:
                        chunks.append(current)
                    current = segment
                    if len(chunks) >= config.max_chunks:
                        return chunks
            remaining = current
        if remaining:
            chunks.append(remaining)
        return chunks[:config.max_chunks]

    def _split_paragraph(self, content: str, config: ChunkConfig) -> list[str]:
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        chunks = []
        current = ""
        for para in paragraphs:
            if len(current) + len(para) <= config.chunk_size * 4:
                current = (current + "\n\n" + para).strip() if current else para
            else:
                if current:
                    chunks.append(current)
                current = para
                if len(chunks) >= config.max_chunks:
                    return chunks
        if current:
            chunks.append(current)
        return chunks

    def _split_sentence(self, content: str, config: ChunkConfig) -> list[str]:
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', content) if s.strip()]
        chunks = []
        current = ""
        for sentence in sentences:
            if len(current) + len(sentence) <= config.chunk_size:
                current = (current + " " + sentence).strip() if current else sentence
            else:
                if current:
                    chunks.append(current)
                current = sentence
                if len(chunks) >= config.max_chunks:
                    return chunks
        if current:
            chunks.append(current)
        return chunks

    def _split_by_strategy(self, content: str, config: ChunkConfig) -> list[str]:
        strategies = {
            ChunkStrategy.FIXED_SIZE: self._split_fixed_size,
            ChunkStrategy.RECURSIVE_SPLIT: self._split_recursive,
            ChunkStrategy.PARAGRAPH: self._split_paragraph,
            ChunkStrategy.SENTENCE: self._split_sentence,
        }
        fn = strategies.get(config.strategy, self._split_fixed_size)
        return fn(content, config)

    def chunk_document(self, document_id: str, content: str, config: Optional[ChunkConfig] = None) -> list[DocumentChunk]:
        self._telemetry["chunk_document_calls"] += 1
        if not config:
            config_id = f"config_{uuid.uuid4().hex[:12]}"
            config = ChunkConfig(id=config_id, strategy=ChunkStrategy.FIXED_SIZE)
            self._configs[config.id] = config

        split_chunks = self._split_by_strategy(content, config)
        doc_chunks = []
        for idx, chunk_text in enumerate(split_chunks):
            chunk = DocumentChunk(
                id=str(uuid.uuid4()),
                document_id=document_id,
                content=chunk_text,
                chunk_index=idx,
                tokens=self._estimate_tokens(chunk_text),
                metadata={"strategy": config.strategy.value, "chunk_size": config.chunk_size},
            )
            self._chunks[chunk.id] = chunk
            doc_chunks.append(chunk)

        self._save()
        logger.info("Chunked document %s into %d chunks (strategy=%s)", document_id, len(doc_chunks), config.strategy.value)
        return doc_chunks

    def get_chunk(self, chunk_id: str) -> Optional[DocumentChunk]:
        self._telemetry["get_chunk_calls"] += 1
        return self._chunks.get(chunk_id)

    def list_chunks(self, document_id: Optional[str] = None) -> list[DocumentChunk]:
        self._telemetry["list_chunks_calls"] += 1
        if document_id:
            return [c for c in self._chunks.values() if c.document_id == document_id]
        return list(self._chunks.values())

    def delete_chunks(self, document_id: Optional[str] = None) -> int:
        self._telemetry["delete_chunks_calls"] += 1
        if document_id:
            to_delete = [cid for cid, c in self._chunks.items() if c.document_id == document_id]
        else:
            to_delete = list(self._chunks.keys())
        for cid in to_delete:
            del self._chunks[cid]
        self._save()
        logger.info("Deleted %d chunks for document %s", len(to_delete), document_id or "all")
        return len(to_delete)

    def re_chunk(self, document_id: str, content: str, config: ChunkConfig) -> list[DocumentChunk]:
        self._telemetry["re_chunk_calls"] += 1
        self.delete_chunks(document_id)
        return self.chunk_document(document_id, content, config)

    def get_chunk_stats(self) -> dict:
        self._telemetry["get_chunk_stats_calls"] += 1
        doc_counts = defaultdict(int)
        total_tokens = 0
        strategy_counts = defaultdict(int)
        for chunk in self._chunks.values():
            doc_counts[chunk.document_id] += 1
            total_tokens += chunk.tokens
            strategy = chunk.metadata.get("strategy", "unknown")
            strategy_counts[strategy] += 1
        return {
            "total_chunks": len(self._chunks),
            "total_documents": len(doc_counts),
            "avg_chunks_per_doc": round(len(self._chunks) / max(len(doc_counts), 1), 2),
            "total_tokens": total_tokens,
            "avg_tokens_per_chunk": round(total_tokens / max(len(self._chunks), 1), 1),
            "strategy_distribution": dict(strategy_counts),
            "telemetry": dict(self._telemetry),
        }

    def suggest_chunk_config(self, content: str) -> dict:
        self._telemetry["suggest_chunk_config_calls"] += 1
        total_chars = len(content)
        total_words = len(content.split())
        total_sentences = len([s for s in content.split(".") if s.strip()])
        total_paragraphs = len([p for p in content.split("\n\n") if p.strip()])
        avg_sentence_words = total_words / max(total_sentences, 1)
        avg_para_chars = total_chars / max(total_paragraphs, 1)

        if avg_sentence_words < 15:
            suggested_strategy = ChunkStrategy.SENTENCE
            chunk_size = max(64, int(avg_sentence_words * 20))
        elif avg_para_chars < 500:
            suggested_strategy = ChunkStrategy.PARAGRAPH
            chunk_size = int(avg_para_chars * 2)
        else:
            suggested_strategy = ChunkStrategy.RECURSIVE_SPLIT
            chunk_size = 512

        return {
            "suggested_strategy": suggested_strategy.value,
            "suggested_chunk_size": min(chunk_size, 2048),
            "suggested_overlap": max(32, chunk_size // 8),
            "document_stats": {
                "characters": total_chars,
                "words": total_words,
                "sentences": total_sentences,
                "paragraphs": total_paragraphs,
                "avg_sentence_words": round(avg_sentence_words, 1),
                "avg_paragraph_chars": round(avg_para_chars, 1),
            },
        }


class RetrievalEngine:
    def __init__(self, storage_dir: str = "retrieval_data"):
        self.storage_dir = storage_dir
        self._results: list[RetrievalResult] = []
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _results_path(self) -> str:
        return os.path.join(self.storage_dir, "retrieval_results.json")

    def _save(self) -> None:
        try:
            data = [r.to_dict() for r in self._results[-1000:]]
            with open(self._results_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save retrieval results: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._results_path()):
                with open(self._results_path(), "r", encoding="utf-8") as f:
                    data = json.load(f)
                for rdata in data:
                    try:
                        self._results.append(RetrievalResult.from_dict(rdata))
                    except Exception as e:
                        logger.warning("Skipping malformed retrieval result: %s", e)
        except Exception as e:
            logger.error("Failed to load retrieval results: %s", e, exc_info=True)

    def retrieve(self, query: str, chunks: list[dict], top_k: int = 10, strategy: RetrievalStrategy = RetrievalStrategy.SIMILARITY) -> RetrievalResult:
        self._telemetry["retrieve_calls"] += 1
        start = time.time()

        if strategy == RetrievalStrategy.KEYWORD_HYBRID:
            result = self.hybrid_search(query, chunks, top_k)
        elif strategy == RetrievalStrategy.RERANKED:
            result = self.retrieve(query, chunks, top_k, RetrievalStrategy.SIMILARITY)
            result = self.rerank_results(result, chunks)
        else:
            result = self._similarity_retrieve(query, chunks, top_k)

        result.query = query
        result.latency_ms = (time.time() - start) * 1000
        result.reranked = strategy == RetrievalStrategy.RERANKED
        self._results.append(result)
        self._save()
        return result

    def _similarity_retrieve(self, query: str, chunks: list[dict], top_k: int) -> RetrievalResult:
        query_terms = set(query.lower().split())
        scored = []
        for chunk in chunks:
            chunk_content = chunk.get("content", chunk.get("text", ""))
            chunk_terms = set(chunk_content.lower().split())
            if not chunk_terms:
                continue
            overlap = len(query_terms & chunk_terms)
            score = overlap / max(len(query_terms | chunk_terms), 1)
            scored.append({
                "chunk": chunk,
                "score": score,
            })
        scored.sort(key=lambda x: x["score"], reverse=True)
        top = scored[:top_k]
        context = "\n\n".join(s["chunk"].get("content", s["chunk"].get("text", "")) for s in top)
        return RetrievalResult(
            id=str(uuid.uuid4()),
            query=query,
            chunks=[s["chunk"] for s in top],
            scores=[s["score"] for s in top],
            context=context,
            total_tokens=len(context.split()),
        )

    def hybrid_search(self, query: str, chunks: list[dict], top_k: int = 10, keyword_weight: float = 0.3, semantic_weight: float = 0.7) -> RetrievalResult:
        self._telemetry["hybrid_search_calls"] += 1
        similarity_result = self._similarity_retrieve(query, chunks, top_k * 2)
        scored = []
        query_terms = set(query.lower().split())
        for item in similarity_result.chunks:
            chunk_content = item.get("content", item.get("text", ""))
            keyword_score = self._keyword_score(query_terms, chunk_content)
            semantic_score = item.get("score", 0.0)
            combined = keyword_weight * keyword_score + semantic_weight * semantic_score
            scored.append({
                "chunk": item,
                "score": combined,
            })
        scored.sort(key=lambda x: x["score"], reverse=True)
        top = scored[:top_k]
        context = "\n\n".join(s["chunk"].get("content", s["chunk"].get("text", "")) for s in top)
        return RetrievalResult(
            id=str(uuid.uuid4()),
            query=query,
            chunks=[s["chunk"] for s in top],
            scores=[s["score"] for s in top],
            context=context,
            total_tokens=len(context.split()),
            reranked=True,
        )

    def _keyword_score(self, query_terms: set, content: str) -> float:
        content_lower = content.lower()
        matches = sum(1 for term in query_terms if term in content_lower)
        return matches / max(len(query_terms), 1)

    def rerank_results(self, result: RetrievalResult, chunks: list[dict], reranker: RerankerType = RerankerType.RECIPROCAL_RANK_FUSION) -> RetrievalResult:
        self._telemetry["rerank_results_calls"] += 1
        if not result.chunks:
            return result

        if reranker == RerankerType.RECIPROCAL_RANK_FUSION:
            reranked = self._rrf_rerank(result.chunks, result.scores)
        else:
            reranked = list(zip(result.chunks, result.scores))
            reranked.sort(key=lambda x: x[1], reverse=True)

        result.chunks = [r[0] for r in reranked]
        result.scores = [r[1] for r in reranked]
        result.reranked = True
        context = "\n\n".join(c.get("content", c.get("text", "")) for c in result.chunks)
        result.context = context
        return result

    def _rrf_rerank(self, chunks: list[dict], scores: list[float], k: int = 60) -> list[tuple]:
        scored = []
        for i, (chunk, score) in enumerate(zip(chunks, scores)):
            rank = i + 1
            rrf_score = 1.0 / (k + rank)
            rrf_score += score * 0.5
            scored.append((chunk, rrf_score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def build_context(self, result: RetrievalResult, max_tokens: int = 4096) -> str:
        self._telemetry["build_context_calls"] += 1
        context_parts = []
        token_count = 0
        for chunk, score in zip(result.chunks, result.scores):
            content = chunk.get("content", chunk.get("text", ""))
            chunk_tokens = len(content.split())
            if token_count + chunk_tokens > max_tokens:
                remaining = max_tokens - token_count
                if remaining > 0:
                    words = content.split()[:remaining]
                    context_parts.append(" ".join(words))
                break
            context_parts.append(content)
            token_count += chunk_tokens
        return "\n\n".join(context_parts)

    def calculate_relevance(self, query: str, chunk_content: str) -> float:
        self._telemetry["calculate_relevance_calls"] += 1
        query_terms = set(query.lower().split())
        chunk_terms = set(chunk_content.lower().split())
        if not query_terms or not chunk_terms:
            return 0.0
        overlap = len(query_terms & chunk_terms)
        jaccard = overlap / len(query_terms | chunk_terms)
        query_coverage = overlap / len(query_terms)
        return 0.6 * jaccard + 0.4 * query_coverage

    def get_retrieval_quality(self, relevant_queries: list[dict]) -> dict:
        self._telemetry["get_retrieval_quality_calls"] += 1
        if not relevant_queries:
            return {"error": "No queries provided"}
        total_precision = 0.0
        total_recall = 0.0
        for item in relevant_queries:
            total_precision += item.get("precision", 0.0)
            total_recall += item.get("recall", 0.0)
        n = len(relevant_queries)
        return {
            "avg_precision": round(total_precision / n, 4),
            "avg_recall": round(total_recall / n, 4),
            "f1_score": round(2 * (total_precision / n) * (total_recall / n) / max((total_precision / n) + (total_recall / n), 0.001), 4),
            "queries_analyzed": n,
        }


class CitationEngine:
    def __init__(self, storage_dir: str = "citation_data"):
        self.storage_dir = storage_dir
        self._citations: dict[str, Citation] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _citations_path(self) -> str:
        return os.path.join(self.storage_dir, "citations.json")

    def _save(self) -> None:
        try:
            data = {cid: c.to_dict() for cid, c in self._citations.items()}
            with open(self._citations_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save citations: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._citations_path()):
                with open(self._citations_path(), "r", encoding="utf-8") as f:
                    data = json.load(f)
                for cid, cdata in data.items():
                    try:
                        self._citations[cid] = Citation.from_dict(cdata)
                    except Exception as e:
                        logger.warning("Skipping malformed citation %s: %s", cid, e)
        except Exception as e:
            logger.error("Failed to load citations: %s", e, exc_info=True)

    def generate_citations(self, retrieval_result: RetrievalResult, documents: dict[str, str]) -> list[Citation]:
        self._telemetry["generate_citations_calls"] += 1
        citations = []
        for i, (chunk, score) in enumerate(zip(retrieval_result.chunks, retrieval_result.scores)):
            chunk_id = chunk.get("id", str(uuid.uuid4()))
            doc_id = chunk.get("document_id", chunk.get("doc_id", "unknown"))
            content = chunk.get("content", chunk.get("text", ""))
            citation = Citation(
                id=str(uuid.uuid4()),
                chunk_id=chunk_id,
                document_id=doc_id,
                content=content[:500],
                relevance_score=score,
                citation_text=f"[{i + 1}] {doc_id} (relevance: {score:.2f})",
            )
            self._citations[citation.id] = citation
            citations.append(citation)
        self._save()
        return citations

    def format_citations(self, citations: list[Citation], format: str = "inline") -> str:
        self._telemetry["format_citations_calls"] += 1
        if not citations:
            return ""
        if format == "inline":
            parts = []
            for i, c in enumerate(citations):
                parts.append(f"[{i + 1}] {c.citation_text}")
            return " | ".join(parts)
        elif format == "numbered":
            lines = []
            for i, c in enumerate(citations):
                lines.append(f"{i + 1}. {c.document_id} - {c.content[:150]}...")
            return "\n".join(lines)
        elif format == "bibtex":
            entries = []
            for i, c in enumerate(citations):
                title = c.content[:100].replace('}', '').replace('{', '')
                entries.append(f"@misc{{citation{i + 1},\n  author = {{{c.document_id}}},\n  title = {{{title}...}},\n  year = {{{datetime.now(timezone.utc).year}}},\n}}")
            return "\n\n".join(entries)
        return json.dumps([c.to_dict() for c in citations], indent=2)

    def verify_citations(self, citations: list[Citation], documents: dict[str, str]) -> dict:
        self._telemetry["verify_citations_calls"] += 1
        verified = 0
        failed = 0
        for c in citations:
            if c.document_id in documents:
                doc_content = documents[c.document_id]
                if c.content[:100] in doc_content:
                    verified += 1
                    continue
            failed += 1
        return {
            "total": len(citations),
            "verified": verified,
            "failed": failed,
            "verification_rate": round(verified / max(len(citations), 1), 4),
        }

    def get_citation_stats(self) -> dict:
        self._telemetry["get_citation_stats_calls"] += 1
        doc_counts = defaultdict(int)
        for c in self._citations.values():
            doc_counts[c.document_id] += 1
        return {
            "total_citations": len(self._citations),
            "unique_documents": len(doc_counts),
            "avg_citations_per_doc": round(len(self._citations) / max(len(doc_counts), 1), 2),
            "avg_relevance_score": round(sum(c.relevance_score for c in self._citations.values()) / max(len(self._citations), 1), 4),
            "telemetry": dict(self._telemetry),
        }


class RAGPipelineManager(ChunkManager, RetrievalEngine, CitationEngine):
    def __init__(self, storage_dir: str = "rag_pipeline_data"):
        ChunkManager.__init__(self, storage_dir=os.path.join(storage_dir, "chunks"))
        RetrievalEngine.__init__(self, storage_dir=os.path.join(storage_dir, "retrieval"))
        CitationEngine.__init__(self, storage_dir=os.path.join(storage_dir, "citations"))
        self.storage_dir = storage_dir
        self._pipelines: dict[str, RAGPipeline] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _pipelines_path(self) -> str:
        return os.path.join(self.storage_dir, "pipelines.json")

    def _save(self) -> None:
        try:
            ChunkManager._save(self)
            RetrievalEngine._save(self)
            CitationEngine._save(self)

            pipelines_data = {pid: p.to_dict() for pid, p in self._pipelines.items()}
            with open(self._pipelines_path(), "w", encoding="utf-8") as f:
                json.dump(pipelines_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save pipeline data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._pipelines_path()):
                with open(self._pipelines_path(), "r", encoding="utf-8") as f:
                    pipelines_data = json.load(f)
                for pid, data in pipelines_data.items():
                    try:
                        self._pipelines[pid] = RAGPipeline.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed pipeline %s: %s", pid, e)
        except Exception as e:
            logger.error("Failed to load pipeline data: %s", e, exc_info=True)

    def create_pipeline(self, name: str, chunk_config: ChunkConfig, embedding_model: str, retrieval_strategy: RetrievalStrategy, reranker_type: Optional[RerankerType] = None, top_k: int = 10, min_score: float = 0.0, max_context_tokens: int = 4096, org_id: str = "default") -> RAGPipeline:
        self._telemetry["create_pipeline_calls"] += 1
        pipeline = RAGPipeline(
            id=str(uuid.uuid4()),
            name=name,
            chunk_config=chunk_config,
            embedding_model=embedding_model,
            retrieval_strategy=retrieval_strategy,
            reranker_type=reranker_type,
            top_k=top_k,
            min_score=min_score,
            max_context_tokens=max_context_tokens,
            org_id=org_id,
        )
        self._pipelines[pipeline.id] = pipeline
        if chunk_config.id not in self._configs:
            self._configs[chunk_config.id] = chunk_config
        self._save()
        logger.info("Created RAG pipeline: %s (id=%s)", name, pipeline.id)
        return pipeline

    def get_pipeline(self, pipeline_id: str) -> Optional[RAGPipeline]:
        self._telemetry["get_pipeline_calls"] += 1
        return self._pipelines.get(pipeline_id)

    def update_pipeline(self, pipeline_id: str, updates: dict) -> Optional[RAGPipeline]:
        self._telemetry["update_pipeline_calls"] += 1
        pipeline = self._pipelines.get(pipeline_id)
        if not pipeline:
            return None
        for key, value in updates.items():
            if hasattr(pipeline, key) and key not in ("id", "created_at"):
                if key == "chunk_config" and isinstance(value, dict):
                    value = ChunkConfig.from_dict(value)
                elif key == "retrieval_strategy":
                    value = RetrievalStrategy(value) if isinstance(value, str) else value
                elif key == "reranker_type":
                    value = RerankerType(value) if isinstance(value, str) else value
                setattr(pipeline, key, value)
        pipeline.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Updated pipeline %s", pipeline_id)
        return pipeline

    def run_pipeline(self, pipeline_id: str, query: str, documents: dict[str, str]) -> dict:
        self._telemetry["run_pipeline_calls"] += 1
        start = time.time()
        pipeline = self._pipelines.get(pipeline_id)
        if not pipeline:
            return {"error": f"Pipeline {pipeline_id} not found"}

        all_chunks = []
        for doc_id, content in documents.items():
            chunks = self.chunk_document(doc_id, content, pipeline.chunk_config)
            for c in chunks:
                all_chunks.append(c.to_dict())

        result = self.retrieve(query, all_chunks, pipeline.top_k, pipeline.retrieval_strategy)

        if pipeline.reranker_type:
            result = self.rerank_results(result, all_chunks, pipeline.reranker_type)

        citations = self.generate_citations(result, documents)
        context = self.build_context(result, pipeline.max_context_tokens)
        elapsed = (time.time() - start) * 1000

        pipeline_metrics = pipeline.metrics
        pipeline_metrics["last_run_ms"] = round(elapsed, 2)
        pipeline_metrics["total_runs"] = pipeline_metrics.get("total_runs", 0) + 1
        pipeline.metrics = pipeline_metrics
        self._save()

        return {
            "pipeline_id": pipeline_id,
            "pipeline_name": pipeline.name,
            "query": query,
            "retrieval_result": result.to_dict(),
            "context": context,
            "citations": [c.to_dict() for c in citations],
            "total_chunks_processed": len(all_chunks),
            "latency_ms": round(elapsed, 2),
        }

    def test_pipeline(self, pipeline_id: str, test_queries: list[str], test_documents: dict[str, str]) -> dict:
        self._telemetry["test_pipeline_calls"] += 1
        results = []
        for query in test_queries:
            result = self.run_pipeline(pipeline_id, query, test_documents)
            results.append({
                "query": query,
                "result_count": len(result.get("retrieval_result", {}).get("chunks", [])),
                "latency_ms": result.get("latency_ms", 0),
            })
        return {
            "pipeline_id": pipeline_id,
            "tests_run": len(test_queries),
            "results": results,
            "avg_latency_ms": round(sum(r["latency_ms"] for r in results) / max(len(results), 1), 2),
        }

    def get_pipeline_metrics(self, pipeline_id: str) -> Optional[dict]:
        self._telemetry["get_pipeline_metrics_calls"] += 1
        pipeline = self._pipelines.get(pipeline_id)
        if not pipeline:
            return None
        return {
            "pipeline_id": pipeline.id,
            "pipeline_name": pipeline.name,
            "metrics": pipeline.metrics,
            "chunk_stats": self.get_chunk_stats(),
            "citation_stats": self.get_citation_stats(),
        }

    def list_pipelines(self, org_id: Optional[str] = None) -> list[RAGPipeline]:
        self._telemetry["list_pipelines_calls"] += 1
        if org_id:
            return [p for p in self._pipelines.values() if p.org_id == org_id]
        return list(self._pipelines.values())

    def optimize_pipeline(self, pipeline_id: str, optimization_target: str = "relevance") -> dict:
        self._telemetry["optimize_pipeline_calls"] += 1
        pipeline = self._pipelines.get(pipeline_id)
        if not pipeline:
            return {"error": f"Pipeline {pipeline_id} not found"}

        suggestions = {}
        if optimization_target == "relevance":
            suggestions["top_k"] = min(pipeline.top_k + 5, 50)
            suggestions["min_score"] = max(pipeline.min_score - 0.05, 0.0)
            if pipeline.retrieval_strategy != RetrievalStrategy.KEYWORD_HYBRID:
                suggestions["retrieval_strategy"] = RetrievalStrategy.KEYWORD_HYBRID.value
        elif optimization_target == "latency":
            suggestions["top_k"] = max(pipeline.top_k - 3, 3)
            suggestions["max_context_tokens"] = min(pipeline.max_context_tokens, 2048)
            suggestions["reranker_type"] = None
        elif optimization_target == "cost":
            suggestions["max_context_tokens"] = min(pipeline.max_context_tokens, 2048)
            suggestions["reranker_type"] = None

        pipeline.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return {
            "pipeline_id": pipeline_id,
            "optimization_target": optimization_target,
            "current_config": {
                "top_k": pipeline.top_k,
                "min_score": pipeline.min_score,
                "max_context_tokens": pipeline.max_context_tokens,
                "retrieval_strategy": pipeline.retrieval_strategy.value,
                "reranker_type": pipeline.reranker_type.value if pipeline.reranker_type else None,
            },
            "suggestions": suggestions,
        }
