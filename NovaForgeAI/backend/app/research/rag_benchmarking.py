"""RAG Benchmarking — evaluate chunking strategies, embedding models, hybrid search, BM25, dense/sparse retrieval, reranking, context builder, citation engine, memory retrieval on recall, precision, MRR, NDCG, latency, cost."""
import json, uuid, os, logging, math
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class ChunkingStrategy(Enum):
    FIXED_SIZE = "fixed_size"
    RECURSIVE = "recursive"
    SEMANTIC = "semantic"
    SENTENCE = "sentence"
    PARAGRAPH = "paragraph"
    TOKEN = "token"


class RetrievalMethod(Enum):
    DENSE = "dense"
    SPARSE = "sparse"
    HYBRID = "hybrid"
    BM25 = "bm25"


@dataclass
class RAGBenchmarkConfig:
    chunking_strategy: ChunkingStrategy = ChunkingStrategy.FIXED_SIZE
    embedding_model: str = ""
    retrieval_method: RetrievalMethod = RetrievalMethod.HYBRID
    top_k: int = 10
    reranker: str = ""
    chunk_size: int = 512
    chunk_overlap: int = 64

    def to_dict(self) -> dict:
        d = asdict(self)
        d["chunking_strategy"] = self.chunking_strategy.value
        d["retrieval_method"] = self.retrieval_method.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RAGBenchmarkConfig":
        data = data.copy()
        data["chunking_strategy"] = ChunkingStrategy(data.get("chunking_strategy", "fixed_size"))
        data["retrieval_method"] = RetrievalMethod(data.get("retrieval_method", "hybrid"))
        return cls(**data)


@dataclass
class RAGBenchmarkResult:
    id: str
    config: dict
    recall: float = 0.0
    precision: float = 0.0
    mrr: float = 0.0
    ndcg: float = 0.0
    latency_ms: float = 0.0
    cost: float = 0.0
    total_queries: int = 0
    passed: bool = False
    details: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RAGBenchmarkResult":
        return cls(**data)


@dataclass
class RAGQueryResult:
    query: str
    relevant_docs: list = field(default_factory=list)
    retrieved_docs: list = field(default_factory=list)
    relevance_scores: list = field(default_factory=list)

    def recall_at_k(self, k: int) -> float:
        if not self.relevant_docs: return 0.0
        retrieved = set(self.retrieved_docs[:k])
        relevant = set(self.relevant_docs)
        hits = len(retrieved & relevant)
        return hits / len(relevant)

    def precision_at_k(self, k: int) -> float:
        if not self.retrieved_docs[:k]: return 0.0
        retrieved = set(self.retrieved_docs[:k])
        relevant = set(self.relevant_docs)
        hits = len(retrieved & relevant)
        return hits / min(k, len(self.retrieved_docs))

    def reciprocal_rank(self) -> float:
        for i, doc in enumerate(self.retrieved_docs):
            if doc in self.relevant_docs:
                return 1.0 / (i + 1)
        return 0.0

    def ndcg_at_k(self, k: int) -> float:
        gains = []
        for doc in self.retrieved_docs[:k]:
            if doc in self.relevant_docs:
                idx = self.relevant_docs.index(doc)
                gains.append(1.0 / (idx + 1) if idx >= 0 else 0.0)
            else:
                gains.append(0.0)
        dcg = sum(g / math.log2(i + 2) for i, g in enumerate(gains))
        ideal = sorted(gains, reverse=True)
        idcg = sum(g / math.log2(i + 2) for i, g in enumerate(ideal))
        return dcg / idcg if idcg > 0 else 0.0


class RAGBenchmarking:
    def __init__(self, storage_dir: str = "research_data/rag_benchmarks"):
        self.storage_dir = storage_dir
        self._results: dict[str, RAGBenchmarkResult] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "results.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._results[k] = RAGBenchmarkResult.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Failed to load RAG benchmarks: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._results.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save RAG benchmarks: %s", e)

    def run_benchmark(self, config: RAGBenchmarkConfig, query_results: list[RAGQueryResult] = None) -> RAGBenchmarkResult:
        qr = query_results or []
        recall_vals = [q.recall_at_k(config.top_k) for q in qr]
        precision_vals = [q.precision_at_k(config.top_k) for q in qr]
        mrr_vals = [q.reciprocal_rank() for q in qr]
        ndcg_vals = [q.ndcg_at_k(config.top_k) for q in qr]
        n = len(qr) or 1
        result = RAGBenchmarkResult(
            id=str(uuid.uuid4()), config=config.to_dict(),
            recall=round(sum(recall_vals) / n, 4),
            precision=round(sum(precision_vals) / n, 4),
            mrr=round(sum(mrr_vals) / n, 4),
            ndcg=round(sum(ndcg_vals) / n, 4),
            latency_ms=0.0, total_queries=n,
            passed=(sum(recall_vals) / n) >= 0.5,
            details={"queries_evaluated": n},
        )
        self._results[result.id] = result
        self._save()
        return result

    def get_leaderboard(self, metric: str = "recall", top_n: int = 10) -> list[dict]:
        valid = [r for r in self._results.values() if r.total_queries > 0]
        sorted_results = sorted(valid, key=lambda r: getattr(r, metric, 0.0), reverse=True)
        return [{"rank": i+1, "id": r.id, "config": r.config, metric: getattr(r, metric, 0.0), "recall": r.recall, "precision": r.precision, "mrr": r.mrr, "ndcg": r.ndcg} for i, r in enumerate(sorted_results[:top_n])]

    def compare_strategies(self) -> dict:
        by_strategy = {}
        for r in self._results.values():
            strat = r.config.get("chunking_strategy", "unknown")
            if strat not in by_strategy: by_strategy[strat] = []
            by_strategy[strat].append(r)
        comparison = {}
        for strat, results in by_strategy.items():
            n = len(results)
            comparison[strat] = {
                "avg_recall": round(sum(r.recall for r in results) / n, 4),
                "avg_precision": round(sum(r.precision for r in results) / n, 4),
                "avg_mrr": round(sum(r.mrr for r in results) / n, 4),
                "avg_ndcg": round(sum(r.ndcg for r in results) / n, 4),
                "count": n,
            }
        return comparison

    def list_results(self, limit: int = 50) -> list[RAGBenchmarkResult]:
        results = sorted(self._results.values(), key=lambda r: r.created_at, reverse=True)
        return results[:limit]

    def get_telemetry(self) -> dict: return dict(self._telemetry)
