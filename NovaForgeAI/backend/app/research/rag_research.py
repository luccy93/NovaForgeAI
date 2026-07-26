"""RAG Research — evaluate chunking strategies, embedding models, hybrid search, BM25, dense/sparse retrieval, reranking, context builder, citation engine, memory retrieval on recall, precision, MRR, NDCG, latency, cost."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


@dataclass
class RAGStrategyEval:
    id: str
    strategy_name: str
    chunking: str = ""
    embedding: str = ""
    retrieval: str = ""
    reranker: str = ""
    recall: float = 0.0
    precision: float = 0.0
    mrr: float = 0.0
    ndcg: float = 0.0
    latency_ms: float = 0.0
    cost: float = 0.0
    queries: int = 0
    passed: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "RAGStrategyEval": return cls(**data)


@dataclass
class RAGComponentEval:
    component_type: str
    component_name: str
    metric: str
    score: float
    runs: int
    last_evaluated: str

    def to_dict(self) -> dict: return asdict(self)


class RAGResearch:
    def __init__(self, storage_dir: str = "research_data/rag_research"):
        self.storage_dir = storage_dir
        self._evals: dict[str, RAGStrategyEval] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "evals.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._evals[k] = RAGStrategyEval.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Failed to load RAG research: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._evals.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save RAG research: %s", e)

    def record_evaluation(self, strategy_name: str, chunking: str, embedding: str, retrieval: str, reranker: str, recall: float, precision: float, mrr: float, ndcg: float, latency_ms: float = 0.0, cost: float = 0.0, queries: int = 0) -> RAGStrategyEval:
        eval = RAGStrategyEval(
            id=str(uuid.uuid4()), strategy_name=strategy_name, chunking=chunking,
            embedding=embedding, retrieval=retrieval, reranker=reranker,
            recall=recall, precision=precision, mrr=mrr, ndcg=ndcg,
            latency_ms=latency_ms, cost=cost, queries=queries, passed=recall >= 0.5,
        )
        self._evals[eval.id] = eval
        self._save()
        return eval

    def compare_chunking_strategies(self) -> dict:
        by_chunk = {}
        for e in self._evals.values():
            if e.chunking not in by_chunk: by_chunk[e.chunking] = []
            by_chunk[e.chunking].append(e)
        return {k: {
            "avg_recall": round(sum(e.recall for e in v) / len(v), 4),
            "avg_precision": round(sum(e.precision for e in v) / len(v), 4),
            "avg_mrr": round(sum(e.mrr for e in v) / len(v), 4),
            "avg_ndcg": round(sum(e.ndcg for e in v) / len(v), 4),
            "count": len(v),
        } for k, v in by_chunk.items()}

    def compare_embedding_models(self) -> dict:
        by_emb = {}
        for e in self._evals.values():
            if e.embedding not in by_emb: by_emb[e.embedding] = []
            by_emb[e.embedding].append(e)
        return {k: {
            "avg_recall": round(sum(e.recall for e in v) / len(v), 4),
            "avg_mrr": round(sum(e.mrr for e in v) / len(v), 4),
            "count": len(v),
        } for k, v in by_emb.items()}

    def get_leaderboard(self, metric: str = "recall", top_n: int = 10) -> list[dict]:
        sorted_evals = sorted(self._evals.values(), key=lambda e: getattr(e, metric, 0.0), reverse=True)
        return [{"rank": i+1, "strategy": e.strategy_name, metric: getattr(e, metric, 0.0), "chunking": e.chunking, "embedding": e.embedding, "retrieval": e.retrieval, "recall": e.recall, "mrr": e.mrr, "ndcg": e.ndcg} for i, e in enumerate(sorted_evals[:top_n])]

    def get_telemetry(self) -> dict: return dict(self._telemetry)
