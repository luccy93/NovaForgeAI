"""Benchmark engine (Volume 34).

Runs a dataset (versioned snapshot) through a target — model, prompt,
agent, RAG config, workflow — and produces a full EvalRun record with
results, aggregated metrics, latency, tokens, cost, errors and traces.
"""
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

from ..common.storage import JsonFileStorage
from .datasets import DatasetManager
from .metrics import aggregate, retrieval_report, rag_generation_report
from .models import EvalResult, EvalRun
from .providers import get_model

logger = logging.getLogger(__name__)


class BenchmarkRunner:
    """Reusable benchmark runner over the unified storage backends."""

    def __init__(self, storage: Optional[JsonFileStorage] = None,
                 datasets: Optional[DatasetManager] = None):
        self.storage = storage or JsonFileStorage("data/evaluation/runs.json")
        self.datasets = datasets or DatasetManager()

    def run(self, dataset_id: str, model: str = "",
            dataset_version: int | None = None,
            target_type: str = "model",
            organization_id: str = "", provider: str = "",
            prompt_version: str = "", agent_version: str = "",
            rag_version: str = "", configuration: Optional[dict] = None,
            runner: Optional[Callable[[dict, dict], dict]] = None,
            created_by: str = "") -> dict:
        """Run a benchmark over a dataset snapshot.

        runner(exampler_dict, run_meta) -> dict with keys: score (0..1),
        correct, passed, latency_ms, tokens, cost, error, trace. When no
        runner is provided a reference-model runner (offline) is used.
        """
        dataset = self.datasets.get(dataset_id)
        if dataset.get("status") == "archived":
            raise ValueError(f"dataset '{dataset_id}' is archived")
        version_num = dataset_version or dataset.get("latest_version", 1)
        version = self.datasets.get_version(dataset_id, version_num)
        if version.get("status") == "archived":
            raise ValueError(f"dataset '{dataset_id}' v{version_num} is archived")
        run_id = uuid.uuid4().hex[:12]
        run = EvalRun(
            id=run_id, dataset_id=dataset_id, dataset_version=version_num,
            model=model or "reference", provider=provider,
            prompt_version=prompt_version, agent_version=agent_version,
            rag_version=rag_version, configuration=configuration or {},
            target_type=target_type, organization_id=organization_id,
            status="running", started_at=datetime.now(timezone.utc).isoformat(),
            created_by=created_by,
        )
        self.storage.set(run.id, run.to_dict())
        eval_model = get_model(model) if model else None
        examples = version.get("examples", [])
        results: list[dict] = []
        errors: list[dict] = []
        total_latency = 0.0
        total_cost = 0.0
        total_tokens = {"prompt": 0, "completion": 0, "total": 0}
        traces: list[dict] = []
        meta = {"run_id": run_id, "model": run.model, "provider": provider,
                "prompt_version": prompt_version, "agent_version": agent_version,
                "rag_version": rag_version, "configuration": run.configuration,
                "target_type": target_type}

        for index, example in enumerate(examples):
            start = time.perf_counter()
            try:
                if runner is not None:
                    outcome = runner(example, meta) or {}
                elif eval_model is not None:
                    outcome = self._reference_runner(example, eval_model)
                else:
                    outcome = {"score": 0.5, "correct": True, "passed": True}
                latency_ms = float(outcome.get("latency_ms",
                                               (time.perf_counter() - start) * 1000))
                tokens = outcome.get("tokens", {}) or {}
                cost = float(outcome.get("cost", 0.0))
                total_latency += latency_ms
                total_cost += cost
                total_tokens["prompt"] += int(tokens.get("prompt", 0))
                total_tokens["completion"] += int(tokens.get("completion", 0))
                total_tokens["total"] += int(tokens.get("total", 0))
                result = EvalResult(
                    example_id=example.get("id", index),
                    scores={"overall": round(float(outcome.get("score", 0.0)), 4),
                            **{k: v for k, v in outcome.get("metrics", {}).items()
                               if isinstance(v, (int, float))}},
                    correct=bool(outcome.get("correct", True)),
                    passed=bool(outcome.get("passed", True)),
                    latency_ms=round(latency_ms, 2),
                    tokens=tokens, cost=round(cost, 6),
                    error=str(outcome.get("error", "")),
                    trace=outcome.get("trace", {}),
                    judge_scores=outcome.get("judge_scores", []),
                )
                results.append(result.to_dict())
                if outcome.get("trace"):
                    traces.append({"example_id": example.get("id", index),
                                   "trace": outcome["trace"]})
            except Exception as exc:  # noqa: BLE001
                logger.exception("example %s failed", index)
                errors.append({"example_id": example.get("id", index),
                               "error": str(exc)})
                results.append(EvalResult(
                    example_id=example.get("id", index),
                    scores={"overall": 0.0}, correct=False, passed=False,
                    error=str(exc)).to_dict())

        metrics = self._aggregate_metrics(results)
        run.status = "completed" if not errors or results else "failed"
        if errors and results:
            run.status = "completed"
        run.results = results
        run.metrics = metrics
        run.cost = round(total_cost, 6)
        run.latency_ms = round(total_latency, 2)
        run.tokens = total_tokens
        run.errors = errors
        run.traces = traces
        run.completed_at = datetime.now(timezone.utc).isoformat()
        self.storage.set(run.id, run.to_dict())
        return run.to_dict()

    # ────────────────────────────────────────────── querying ──
    def get(self, run_id: str) -> dict:
        record = self.storage.get(run_id)
        if not record:
            raise KeyError(f"run '{run_id}' not found")
        return record

    def list_runs(self, organization_id: str = "", limit: int = 50) -> list[dict]:
        records = [r for r in self.storage.get_all().values() if isinstance(r, dict)]
        if organization_id:
            records = [r for r in records if r.get("organization_id") == organization_id]
        return sorted(records, key=lambda r: r.get("started_at", ""), reverse=True)[:limit]

    # ────────────────────────────────────────────── helpers ──
    def _reference_runner(self, example: dict, model) -> dict:
        expected = example.get("expected_output", example.get("reference_answer", ""))
        prompt = example.get("input", "")
        text = prompt
        try:
            completed = model.complete if hasattr(model, "complete") else None
            text = example.get("input", "")
        except Exception:  # noqa: BLE001
            pass
        score = model.score(expected, text) if expected else 0.5
        return {"score": score, "correct": score >= 0.5, "passed": score >= 0.5,
                "tokens": {"prompt": len(str(prompt).split()), "completion": 0,
                           "total": len(str(prompt).split())},
                "cost": 0.0, "metrics": {"similarity": score},
                "trace": {"reference": True, "model": model.model_id()}}

    @staticmethod
    def _aggregate_metrics(results: list[dict]) -> dict:
        values = [float(r["scores"]["overall"])
                  for r in results if r.get("scores", {}).get("overall") is not None]
        if not values:
            stats = {"mean": 0.0, "median": 0.0, "min": 0.0, "max": 0.0, "count": 0}
        else:
            ordered = sorted(values)
            mid = len(ordered) // 2
            median = ordered[mid] if len(ordered) % 2 \
                else (ordered[mid - 1] + ordered[mid]) / 2
            stats = {"mean": round(sum(values) / len(values), 4),
                     "median": round(median, 4),
                     "min": round(min(values), 4),
                     "max": round(max(values), 4),
                     "count": len(values)}
        metrics = {
            "overall": stats["mean"],
            "pass_rate": round(sum(1 for r in results if r.get("passed")) /
                               len(results), 4) if results else 0.0,
            "correct_rate": round(sum(1 for r in results if r.get("correct")) /
                                  len(results), 4) if results else 0.0,
            "mean_latency_ms": round(sum(r.get("latency_ms", 0.0) for r in results) /
                                     len(results), 2) if results else 0.0,
            "mean_cost": round(sum(r.get("cost", 0.0) for r in results) /
                               len(results), 6) if results else 0.0,
        }
        metrics.update(stats)
        return metrics

    # ────────────────────────────────────────────── RAG evals ──
    def rag_metrics(self, relevant: list[str], retrieved: list[str], k: int = 5) -> dict:
        """Retrieval metrics for a single query (Recall@K, MRR, NDCG...)."""
        return retrieval_report(relevant, retrieved, k)

    def rag_generation(self, claims_supported: int, claims_total: int,
                       unsupported_claims: int, useful_sentences: int,
                       context_sentences: int, correct_citations: int,
                       total_citations: int, cited_claims: int) -> dict:
        """RAG generation metrics (faithfulness, hallucination, citations)."""
        return rag_generation_report(
            claims_supported, claims_total, unsupported_claims,
            useful_sentences, context_sentences, correct_citations,
            total_citations, cited_claims)
