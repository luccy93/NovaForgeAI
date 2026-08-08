import json
import uuid
import hashlib
import time
import math
import os
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class EvalCategory(Enum):
    ACCURACY = "accuracy"
    LATENCY = "latency"
    REASONING = "reasoning"
    CODE_QUALITY = "code_quality"
    SECURITY = "security"
    DOCUMENTATION = "documentation"
    SEARCH = "search"
    TOOL_CALLING = "tool_calling"
    CITATION = "citation"
    COST = "cost"
    HALLUCINATION = "hallucination"
    INSTRUCTION_FOLLOWING = "instruction_following"
    SAFETY = "safety"


class BenchmarkType(Enum):
    HUMAN_EVAL = "human_eval"
    MMLU = "mmlu"
    GSM8K = "gsm8k"
    MATH = "math"
    TRUTHFULQA = "truthfulqa"
    BIG_BENCH_HELD = "big_bench_held"
    CUSTOM = "custom"


class EvalStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ModelEvaluation:
    id: str
    model_id: str
    provider: str
    category: EvalCategory
    benchmark: BenchmarkType
    score: float = 0.0
    metrics: dict = field(default_factory=dict)
    samples: int = 0
    status: EvalStatus = EvalStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    duration_hours: float = 0.0
    cost: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["category"] = self.category.value
        d["benchmark"] = self.benchmark.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ModelEvaluation":
        data["category"] = EvalCategory(data["category"])
        data["benchmark"] = BenchmarkType(data["benchmark"])
        data["status"] = EvalStatus(data["status"])
        return cls(**data)


@dataclass
class LeaderboardEntry:
    id: str
    model_id: str
    provider: str
    rank: int = 0
    overall_score: float = 0.0
    category_scores: dict = field(default_factory=dict)
    evaluations: int = 0
    last_evaluated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    version: str = "1.0"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "LeaderboardEntry":
        return cls(**data)


@dataclass
class BenchmarkResult:
    id: str
    evaluation_id: str
    test_name: str
    input: str = ""
    expected_output: str = ""
    actual_output: str = ""
    passed: bool = False
    score: float = 0.0
    latency_ms: float = 0.0
    tokens_used: int = 0
    cost: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "BenchmarkResult":
        return cls(**data)


@dataclass
class EvaluationReport:
    id: str
    model_id: str
    summary: dict = field(default_factory=dict)
    category_breakdown: dict = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    comparison: dict = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "EvaluationReport":
        return cls(**data)


class ModelEvaluator:
    def __init__(self, storage_dir: str = "evaluation_data"):
        self.storage_dir = storage_dir
        self._evaluations: dict[str, ModelEvaluation] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _evaluations_path(self) -> str:
        return os.path.join(self.storage_dir, "evaluations.json")

    def _save(self) -> None:
        try:
            data = {eid: e.to_dict() for eid, e in self._evaluations.items()}
            with open(self._evaluations_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save evaluations: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._evaluations_path()):
                with open(self._evaluations_path(), "r", encoding="utf-8") as f:
                    data = json.load(f)
                for eid, edata in data.items():
                    try:
                        self._evaluations[eid] = ModelEvaluation.from_dict(edata)
                    except Exception as e:
                        logger.warning("Skipping malformed evaluation %s: %s", eid, e)
        except Exception as e:
            logger.error("Failed to load evaluations: %s", e, exc_info=True)

    def evaluate_model(self, model_id: str, provider: str, category: EvalCategory, benchmark: BenchmarkType) -> ModelEvaluation:
        self._telemetry["evaluate_model_calls"] += 1
        evaluation = ModelEvaluation(
            id=str(uuid.uuid4()),
            model_id=model_id,
            provider=provider,
            category=category,
            benchmark=benchmark,
        )
        self._evaluations[evaluation.id] = evaluation
        self._save()
        logger.info("Created evaluation %s for model %s (%s/%s)", evaluation.id, model_id, category.value, benchmark.value)
        return evaluation

    def get_evaluation(self, evaluation_id: str) -> Optional[ModelEvaluation]:
        self._telemetry["get_evaluation_calls"] += 1
        return self._evaluations.get(evaluation_id)

    def list_evaluations(self, model_id: Optional[str] = None, category: Optional[EvalCategory] = None) -> list[ModelEvaluation]:
        self._telemetry["list_evaluations_calls"] += 1
        results = list(self._evaluations.values())
        if model_id:
            results = [e for e in results if e.model_id == model_id]
        if category:
            results = [e for e in results if e.category == category]
        return results

    def compare_models(self, model_ids: list[str], category: Optional[EvalCategory] = None) -> dict:
        self._telemetry["compare_models_calls"] += 1
        comparison = {}
        for mid in model_ids:
            evals = [e for e in self._evaluations.values() if e.model_id == mid]
            if category:
                evals = [e for e in evals if e.category == category]
            if not evals:
                comparison[mid] = {"error": "No evaluations found"}
                continue
            avg_score = sum(e.score for e in evals) / len(evals)
            comparison[mid] = {
                "avg_score": round(avg_score, 4),
                "evaluations": len(evals),
                "categories": list(set(e.category.value for e in evals)),
                "total_cost": round(sum(e.cost for e in evals), 6),
            }
        ranked = sorted(comparison.items(), key=lambda x: x[1].get("avg_score", 0), reverse=True)
        return {
            "comparison": comparison,
            "ranking": [{"model_id": m, "rank": i + 1, **s} for i, (m, s) in enumerate(ranked)],
            "category": category.value if category else "all",
        }

    def run_benchmark(self, evaluation_id: str, results: list[BenchmarkResult]) -> Optional[ModelEvaluation]:
        self._telemetry["run_benchmark_calls"] += 1
        evaluation = self._evaluations.get(evaluation_id)
        if not evaluation:
            return None
        start = time.time()
        evaluation.status = EvalStatus.RUNNING

        passed = sum(1 for r in results if r.passed)
        total = len(results)
        avg_score = sum(r.score for r in results) / max(total, 1)
        avg_latency = sum(r.latency_ms for r in results) / max(total, 1)
        total_tokens = sum(r.tokens_used for r in results)
        total_cost = sum(r.cost for r in results)

        evaluation.score = round(avg_score, 4)
        evaluation.samples = total
        evaluation.metrics = {
            "passed": passed,
            "failed": total - passed,
            "pass_rate": round(passed / max(total, 1), 4),
            "avg_latency_ms": round(avg_latency, 2),
            "total_tokens": total_tokens,
            "total_cost": round(total_cost, 6),
        }
        evaluation.cost = total_cost
        evaluation.status = EvalStatus.COMPLETED
        evaluation.completed_at = datetime.now(timezone.utc).isoformat()
        evaluation.duration_hours = round((time.time() - start) / 3600, 6)
        self._save()
        logger.info("Completed evaluation %s with score %.4f", evaluation_id, evaluation.score)
        return evaluation

    def run_all_benchmarks(self, model_id: str, provider: str) -> list[ModelEvaluation]:
        self._telemetry["run_all_benchmarks_calls"] += 1
        evaluations = []
        for category in EvalCategory:
            for benchmark in BenchmarkType:
                if benchmark == BenchmarkType.CUSTOM:
                    continue
                eval_obj = self.evaluate_model(model_id, provider, category, benchmark)
                evaluations.append(eval_obj)
        logger.info("Created %d evaluations for model %s", len(evaluations), model_id)
        return evaluations

    def get_evaluation_progress(self, evaluation_id: str) -> Optional[dict]:
        self._telemetry["get_evaluation_progress_calls"] += 1
        evaluation = self._evaluations.get(evaluation_id)
        if not evaluation:
            return None
        return {
            "id": evaluation.id,
            "model_id": evaluation.model_id,
            "status": evaluation.status.value,
            "category": evaluation.category.value,
            "benchmark": evaluation.benchmark.value,
            "score": evaluation.score,
            "samples": evaluation.samples,
            "progress": f"{evaluation.samples} samples" if evaluation.samples > 0 else "pending",
            "duration_hours": evaluation.duration_hours,
        }


class LeaderboardManager:
    def __init__(self, storage_dir: str = "leaderboard_data"):
        self.storage_dir = storage_dir
        self._leaderboards: dict[str, list[LeaderboardEntry]] = defaultdict(list)
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _leaderboards_path(self) -> str:
        return os.path.join(self.storage_dir, "leaderboards.json")

    def _save(self) -> None:
        try:
            data = {}
            for lb_id, entries in self._leaderboards.items():
                data[lb_id] = [e.to_dict() for e in entries]
            with open(self._leaderboards_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save leaderboards: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._leaderboards_path()):
                with open(self._leaderboards_path(), "r", encoding="utf-8") as f:
                    data = json.load(f)
                for lb_id, entries in data.items():
                    self._leaderboards[lb_id] = []
                    for edata in entries:
                        try:
                            self._leaderboards[lb_id].append(LeaderboardEntry.from_dict(edata))
                        except Exception as e:
                            logger.warning("Skipping malformed leaderboard entry: %s", e)
        except Exception as e:
            logger.error("Failed to load leaderboards: %s", e, exc_info=True)

    def create_leaderboard(self, leaderboard_id: str) -> list[LeaderboardEntry]:
        self._telemetry["create_leaderboard_calls"] += 1
        if leaderboard_id not in self._leaderboards:
            self._leaderboards[leaderboard_id] = []
            self._save()
        return self._leaderboards[leaderboard_id]

    def update_entry(self, leaderboard_id: str, model_id: str, provider: str, overall_score: float, category_scores: Optional[dict] = None, version: str = "1.0") -> Optional[LeaderboardEntry]:
        self._telemetry["update_entry_calls"] += 1
        if leaderboard_id not in self._leaderboards:
            self.create_leaderboard(leaderboard_id)

        entry = None
        for e in self._leaderboards[leaderboard_id]:
            if e.model_id == model_id:
                entry = e
                break

        if not entry:
            entry = LeaderboardEntry(
                id=str(uuid.uuid4()),
                model_id=model_id,
                provider=provider,
                version=version,
            )
            self._leaderboards[leaderboard_id].append(entry)

        entry.overall_score = overall_score
        entry.category_scores = category_scores or {}
        entry.evaluations += 1
        entry.last_evaluated = datetime.now(timezone.utc).isoformat()
        entry.version = version

        self._recalculate_ranks(leaderboard_id)
        self._save()
        logger.info("Updated leaderboard %s entry for model %s (score=%.4f)", leaderboard_id, model_id, overall_score)
        return entry

    def _recalculate_ranks(self, leaderboard_id: str) -> None:
        entries = self._leaderboards.get(leaderboard_id, [])
        entries.sort(key=lambda e: e.overall_score, reverse=True)
        for i, entry in enumerate(entries):
            entry.rank = i + 1

    def get_leaderboard(self, leaderboard_id: str) -> list[LeaderboardEntry]:
        self._telemetry["get_leaderboard_calls"] += 1
        return list(self._leaderboards.get(leaderboard_id, []))

    def get_top_models(self, leaderboard_id: str, top_n: int = 10) -> list[LeaderboardEntry]:
        self._telemetry["get_top_models_calls"] += 1
        entries = self._leaderboards.get(leaderboard_id, [])
        entries.sort(key=lambda e: e.overall_score, reverse=True)
        return entries[:top_n]

    def get_model_rank(self, leaderboard_id: str, model_id: str) -> Optional[dict]:
        self._telemetry["get_model_rank_calls"] += 1
        for entry in self._leaderboards.get(leaderboard_id, []):
            if entry.model_id == model_id:
                return {
                    "model_id": model_id,
                    "provider": entry.provider,
                    "rank": entry.rank,
                    "overall_score": entry.overall_score,
                    "evaluations": entry.evaluations,
                    "version": entry.version,
                }
        return None

    def list_leaderboards(self) -> list[str]:
        self._telemetry["list_leaderboards_calls"] += 1
        return list(self._leaderboards.keys())

    def compare_leaderboards(self, leaderboard_ids: list[str]) -> dict:
        self._telemetry["compare_leaderboards_calls"] += 1
        comparison = {}
        for lb_id in leaderboard_ids:
            entries = self._leaderboards.get(lb_id, [])
            comparison[lb_id] = {
                "total_entries": len(entries),
                "top_model": entries[0].model_id if entries else None,
                "top_score": entries[0].overall_score if entries else 0,
                "avg_score": round(sum(e.overall_score for e in entries) / max(len(entries), 1), 4) if entries else 0,
            }
        return comparison


class BenchmarkRunner:
    def __init__(self, storage_dir: str = "benchmark_data"):
        self.storage_dir = storage_dir
        self._results: dict[str, list[BenchmarkResult]] = defaultdict(list)
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _results_path(self) -> str:
        return os.path.join(self.storage_dir, "benchmark_results.json")

    def _save(self) -> None:
        try:
            data = {}
            for eid, results in self._results.items():
                data[eid] = [r.to_dict() for r in results]
            with open(self._results_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save benchmark results: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._results_path()):
                with open(self._results_path(), "r", encoding="utf-8") as f:
                    data = json.load(f)
                for eid, results in data.items():
                    self._results[eid] = []
                    for rdata in results:
                        try:
                            self._results[eid].append(BenchmarkResult.from_dict(rdata))
                        except Exception as e:
                            logger.warning("Skipping malformed benchmark result: %s", e)
        except Exception as e:
            logger.error("Failed to load benchmark results: %s", e, exc_info=True)

    def run_benchmark(self, evaluation_id: str, tests: list[dict]) -> list[BenchmarkResult]:
        self._telemetry["run_benchmark_calls"] += 1
        results = []
        for i, test in enumerate(tests):
            result = BenchmarkResult(
                id=str(uuid.uuid4()),
                evaluation_id=evaluation_id,
                test_name=test.get("name", f"test_{i}"),
                input=test.get("input", ""),
                expected_output=test.get("expected", ""),
                actual_output=test.get("actual", ""),
                passed=test.get("passed", False),
                score=test.get("score", 0.0),
                latency_ms=test.get("latency_ms", 0.0),
                tokens_used=test.get("tokens_used", 0),
                cost=test.get("cost", 0.0),
                error=test.get("error"),
            )
            self._results[evaluation_id].append(result)
            results.append(result)
        self._save()
        logger.info("Recorded %d benchmark results for evaluation %s", len(results), evaluation_id)
        return results

    def get_benchmark_results(self, evaluation_id: str) -> list[BenchmarkResult]:
        self._telemetry["get_benchmark_results_calls"] += 1
        return list(self._results.get(evaluation_id, []))

    def list_benchmarks(self) -> list[str]:
        self._telemetry["list_benchmarks_calls"] += 1
        return list(self._results.keys())

    def run_custom_benchmark(self, test_cases: list[dict], model_fn) -> list[BenchmarkResult]:
        self._telemetry["run_custom_benchmark_calls"] += 1
        eval_id = str(uuid.uuid4())
        results = []
        for i, case in enumerate(test_cases):
            start = time.time()
            error = None
            passed = False
            actual = ""
            try:
                actual = model_fn(case.get("input", ""))
                passed = actual == case.get("expected", "")
            except Exception as e:
                error = str(e)
            elapsed = (time.time() - start) * 1000
            result = BenchmarkResult(
                id=str(uuid.uuid4()),
                evaluation_id=eval_id,
                test_name=case.get("name", f"custom_test_{i}"),
                input=case.get("input", ""),
                expected_output=case.get("expected", ""),
                actual_output=actual,
                passed=passed,
                score=1.0 if passed else 0.0,
                latency_ms=round(elapsed, 2),
                tokens_used=case.get("tokens_used", 0),
                cost=case.get("cost", 0.0),
                error=error,
            )
            self._results[eval_id].append(result)
            results.append(result)
        self._save()
        logger.info("Completed custom benchmark %s with %d tests", eval_id, len(results))
        return results


class EvaluationManager(ModelEvaluator, LeaderboardManager, BenchmarkRunner):
    def __init__(self, storage_dir: str = "eval_manager_data"):
        ModelEvaluator.__init__(self, storage_dir=os.path.join(storage_dir, "evaluations"))
        LeaderboardManager.__init__(self, storage_dir=os.path.join(storage_dir, "leaderboards"))
        BenchmarkRunner.__init__(self, storage_dir=os.path.join(storage_dir, "benchmarks"))
        self.storage_dir = storage_dir
        self._reports: dict[str, EvaluationReport] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _reports_path(self) -> str:
        return os.path.join(self.storage_dir, "reports.json")

    def _save(self) -> None:
        try:
            ModelEvaluator._save(self)
            LeaderboardManager._save(self)
            BenchmarkRunner._save(self)

            reports_data = {rid: r.to_dict() for rid, r in self._reports.items()}
            with open(self._reports_path(), "w", encoding="utf-8") as f:
                json.dump(reports_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save eval manager data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._reports_path()):
                with open(self._reports_path(), "r", encoding="utf-8") as f:
                    reports_data = json.load(f)
                for rid, rdata in reports_data.items():
                    try:
                        self._reports[rid] = EvaluationReport.from_dict(rdata)
                    except Exception as e:
                        logger.warning("Skipping malformed report %s: %s", rid, e)
        except Exception as e:
            logger.error("Failed to load eval manager data: %s", e, exc_info=True)

    def get_ranking(self, leaderboard_id: str = "default", top_n: int = 10) -> list[dict]:
        self._telemetry["get_ranking_calls"] += 1
        entries = self.get_top_models(leaderboard_id, top_n)
        return [
            {
                "rank": e.rank,
                "model_id": e.model_id,
                "provider": e.provider,
                "overall_score": e.overall_score,
                "evaluations": e.evaluations,
                "version": e.version,
            }
            for e in entries
        ]

    def get_recommendation(self, model_id: str, leaderboard_id: str = "default") -> dict:
        self._telemetry["get_recommendation_calls"] += 1
        evals = self.list_evaluations(model_id)
        if not evals:
            return {"model_id": model_id, "recommendation": "No evaluation data available"}

        avg_score = sum(e.score for e in evals) / len(evals)
        best_category = max(set(e.category for e in evals), key=lambda c: sum(e.score for e in evals if e.category == c) / max(sum(1 for e in evals if e.category == c), 1))
        worst_category = min(set(e.category for e in evals), key=lambda c: sum(e.score for e in evals if e.category == c) / max(sum(1 for e in evals if e.category == c), 1))

        rank_info = self.get_model_rank(leaderboard_id, model_id)
        recommendations = []
        if rank_info and rank_info.get("rank", 999) > 3:
            recommendations.append(f"Consider improving performance in {worst_category.value}")
        if avg_score < 0.7:
            recommendations.append("Overall score is below 0.7 - further evaluation recommended")
        recommendations.append(f"Model performs best in {best_category.value}")

        return {
            "model_id": model_id,
            "overall_avg_score": round(avg_score, 4),
            "best_category": best_category.value,
            "worst_category": worst_category.value,
            "evaluations_count": len(evals),
            "rank": rank_info.get("rank") if rank_info else None,
            "recommendations": recommendations,
        }

    def generate_report(self, model_id: str, leaderboard_id: str = "default") -> EvaluationReport:
        self._telemetry["generate_report_calls"] += 1
        evals = self.list_evaluations(model_id)
        if not evals:
            report = EvaluationReport(
                id=str(uuid.uuid4()),
                model_id=model_id,
                summary={"error": "No evaluations available"},
            )
            self._reports[report.id] = report
            self._save()
            return report

        category_breakdown = {}
        for cat in EvalCategory:
            cat_evals = [e for e in evals if e.category == cat]
            if cat_evals:
                category_breakdown[cat.value] = {
                    "avg_score": round(sum(e.score for e in cat_evals) / len(cat_evals), 4),
                    "evaluations": len(cat_evals),
                    "total_cost": round(sum(e.cost for e in cat_evals), 6),
                }

        all_scores = [e.score for e in evals if e.status == EvalStatus.COMPLETED]
        summary = {
            "model_id": model_id,
            "total_evaluations": len(evals),
            "completed_evaluations": sum(1 for e in evals if e.status == EvalStatus.COMPLETED),
            "overall_avg_score": round(sum(all_scores) / max(len(all_scores), 1), 4),
            "total_cost": round(sum(e.cost for e in evals), 6),
            "benchmarks_covered": list(set(e.benchmark.value for e in evals)),
        }

        rank_info = self.get_model_rank(leaderboard_id, model_id)
        comparison_data = {"leaderboard_rank": rank_info} if rank_info else {}
        if len(all_scores) > 1:
            comparison_data["score_std_dev"] = round(math.sqrt(sum((s - (sum(all_scores) / len(all_scores))) ** 2 for s in all_scores) / len(all_scores)), 4)

        best_cat = max(category_breakdown.keys(), key=lambda c: category_breakdown[c]["avg_score"]) if category_breakdown else None
        worst_cat = min(category_breakdown.keys(), key=lambda c: category_breakdown[c]["avg_score"]) if category_breakdown else None
        recommendations = []
        if worst_cat:
            recommendations.append(f"Focus on improving {worst_cat} performance")
        if best_cat:
            recommendations.append(f"Leverage strength in {best_cat} for production use")
        if summary.get("overall_avg_score", 0) < 0.6:
            recommendations.append("Overall score is low - consider model fine-tuning or alternative model")

        report = EvaluationReport(
            id=str(uuid.uuid4()),
            model_id=model_id,
            summary=summary,
            category_breakdown=category_breakdown,
            recommendations=recommendations,
            comparison=comparison_data,
        )
        self._reports[report.id] = report
        self._save()
        logger.info("Generated evaluation report %s for model %s", report.id, model_id)
        return report
