"""AI Benchmarking & Evaluation volume tests (Volume 34).

Every test uses tmp_path JsonFileStorage so the suite stays hermetic
(mirrors the automation/multimodal test hygiene rule).
"""
import json
import math
from pathlib import Path

import pytest

from app.common.storage import JsonFileStorage
from app.evaluation.metrics import (
    recall_at_k, precision_at_k, mrr, ndcg, hit_rate,
    faithfulness, hallucination_rate, citation_correctness,
    citation_completeness, context_relevance, answer_relevance,
    agreement_rate, cohens_kappa, fleiss_kappa, krippendorffs_alpha,
    win_rate, aggregate, retrieval_report,
)
from app.evaluation.datasets import DatasetManager, DatasetExample
from app.evaluation.benchmark import BenchmarkRunner
from app.evaluation.judges import LLMJudge, JudgeCalibration
from app.evaluation.human import HumanReviewManager
from app.evaluation.pairwise import PairwiseEvaluator
from app.evaluation.code_eval import (
    code_generation_report, code_repair_report, code_review_report,
    security_eval_report, build_test_generation_report, documentation_report,
    architecture_report,
)
from app.evaluation.agents_eval import AgentEvaluator
from app.evaluation.providers import get_model, EvalModel
from app.evaluation.regression import RegressionEngine
from app.evaluation.prompts import PromptStore
from app.evaluation.gateway import EvaluationGateway
from app.evaluation.multimodal_eval import MultimodalEvaluator
from app.evaluation.automation_eval import AutomationEvaluator


def store(tmp_path: Path, name: str) -> JsonFileStorage:
    return JsonFileStorage(str(tmp_path / name))


def make_dataset(tmp_path: Path, n: int = 3, org: str = "acme") -> dict:
    manager = DatasetManager(store(tmp_path, "datasets.json"))
    dataset = manager.create("qa-bench", "qa", organization_id=org)
    examples = [
        {"input": f"q{i}", "expected_output": f"a{i}",
         "reference_answer": f"a{i}", "tags": ["math"]}
        for i in range(n)
    ]
    manager.add_version(dataset["id"], examples, notes="first")
    return dataset


# ────────────────────────────────────────────────────── metrics ──
class TestRetrievalMetrics:
    def test_recall_precision_hit(self):
        relevant = ["d1", "d2"]
        retrieved = ["d1", "d3", "d4"]
        assert recall_at_k(relevant, retrieved, 2) == 0.5
        assert precision_at_k(relevant, retrieved, 2) == 0.5
        assert hit_rate(relevant, retrieved, 2) == 1.0
        assert hit_rate(relevant, ["d9"], 2) == 0.0

    def test_mrr(self):
        assert mrr(["d3"], ["d1", "d2", "d3"]) == 1 / 3
        assert mrr(["d3"], ["d1", "d2"]) == 0.0

    def test_ndcg_perfect(self):
        assert ndcg(["d1", "d2"], ["d1", "d2"], 2) == 1.0
        assert ndcg(["d1"], ["d1", "d2"], 2) == 1.0
        assert ndcg(["d2"], ["d1", "d2"], 2) < 1.0

    def test_empty_relevant(self):
        assert recall_at_k([], ["d1"], 2) == 0.0
        assert precision_at_k([], ["d1"], 2) == 0.0
        assert mrr([], ["d1"]) == 0.0
        assert ndcg([], ["d1"], 2) == 0.0

    def test_report_shape(self):
        report = retrieval_report(["d1"], ["d1", "d2"], k=2)
        for key in ("recall@k", "precision@k", "mrr", "ndcg@k", "hit_rate"):
            assert key in report


class TestGenerationMetrics:
    def test_faithfulness(self):
        assert faithfulness(2, 4) == 0.5
        assert faithfulness(0, 0) == 0.0

    def test_hallucination(self):
        assert hallucination_rate(1, 4) == 0.25
        assert hallucination_rate(0, 0) == 0.0

    def test_citations(self):
        assert citation_correctness(3, 4) == 0.75
        assert citation_completeness(2, 4) == 0.5
        assert citation_completeness(2, 0) == 0.0

    def test_context_and_answer_relevance(self):
        assert context_relevance(2, 4) == 0.5
        assert answer_relevance(6.0, 3) == 1.0
        assert answer_relevance(1.5, 3) == 0.5


class TestReliabilityMetrics:
    def test_cohens_kappa_perfect(self):
        assert cohens_kappa(["a", "a", "b"], ["a", "a", "b"]) == 1.0

    def test_cohens_kappa_known_value(self):
        # classic example: ~0.41-0.45 region depending on distribution
        a = ["yes", "yes", "no", "no", "yes", "yes", "no", "yes"]
        b = ["yes", "no", "no", "no", "yes", "yes", "no", "yes"]
        kappa = cohens_kappa(a, b)
        assert 0.0 <= kappa <= 1.0
        assert kappa > 0.4

    def test_fleiss_kappa_many_raters(self):
        labels = [
            ["a", "a", "a"], ["a", "a", "a"], ["b", "b", "b"],
            ["b", "b", "b"], ["a", "a", "b"],
        ]
        kappa = fleiss_kappa(labels)
        assert -1.0 <= kappa <= 1.0
        assert kappa > 0.0

    def test_agreement_rate(self):
        assert agreement_rate([["a", "a"], ["b", "b"]]) == 1.0
        assert agreement_rate([["a", "b"], ["b", "a"]]) == 0.0

    def test_krippendorff_smoke(self):
        alpha = krippendorffs_alpha([[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]])
        assert alpha == pytest.approx(1.0, abs=1e-6)


class TestAggregateAndWinRate:
    def test_aggregate(self):
        stats = aggregate([{"score": 0.5}, {"score": 0.9}, {"score": 0.7}])
        assert stats["mean"] == pytest.approx(0.7)
        assert stats["median"] == pytest.approx(0.7)
        assert stats["count"] == 3

    def test_win_rate(self):
        stats = win_rate(8, 1, 1)
        assert stats["win_rate_a"] == pytest.approx(0.8)
        assert stats["win_rate_b"] == pytest.approx(0.1)
        assert stats["tie_rate"] == pytest.approx(0.1)
        assert stats["comparisons"] == 10


# ─────────────────────────────────────────────────────── datasets ──
class TestDatasets:
    def test_create_and_version(self, tmp_path):
        manager = DatasetManager(store(tmp_path, "datasets.json"))
        dataset = manager.create("gen-bench", "code_generation",
                                 organization_id="acme")
        assert dataset["status"] == "active"
        version = manager.add_version(dataset["id"], [
            {"input": "fix bug", "expected_code": "return 1"},
        ])
        assert version["version"] == 1
        assert version["checksum"]
        assert manager.get_version(dataset["id"], 1)["examples"][0]["input"] == "fix bug"

    def test_invalid_task_type(self, tmp_path):
        manager = DatasetManager(store(tmp_path, "datasets.json"))
        with pytest.raises(ValueError):
            manager.create("x", "not_a_task")

    def test_version_immutability(self, tmp_path):
        manager = DatasetManager(store(tmp_path, "datasets.json"))
        dataset = manager.create("qa", "qa")
        manager.add_version(dataset["id"], [{"input": "q1", "expected_output": "a1"}])
        # later versions never mutate earlier snapshots
        version2 = manager.add_version(dataset["id"],
                                       [{"input": "q2", "expected_output": "a2"}])
        assert version2["version"] == 2
        assert version2["parent_version"] == 1
        assert manager.get_version(dataset["id"], 1)["examples"][0]["input"] == "q1"

    def test_clone_and_diff(self, tmp_path):
        dataset = make_dataset(tmp_path, n=2)
        manager = DatasetManager(store(tmp_path, "datasets.json"))
        clone = manager.clone(dataset["id"], "clone-name")
        assert clone["name"] == "clone-name"
        assert clone["metadata"]["cloned_from"] == dataset["id"]
        diff = manager.diff(dataset["id"], 1, 1)
        assert diff["unchanged"] and not diff["added"]

    def test_rollback_creates_version(self, tmp_path):
        dataset = make_dataset(tmp_path, n=1)
        manager = DatasetManager(store(tmp_path, "datasets.json"))
        manager.add_version(dataset["id"], [{"input": "changed", "expected_output": "z"}])
        rolled = manager.rollback(dataset["id"], 1)
        assert rolled["version"] == 3
        assert rolled["examples"][0]["input"] == "q0"

    def test_publish_archive_lineage(self, tmp_path):
        dataset = make_dataset(tmp_path, n=2)
        manager = DatasetManager(store(tmp_path, "datasets.json"))
        published = manager.publish(dataset["id"], 1)
        assert published["status"] == "published"
        lineage = manager.lineage(dataset["id"])
        assert lineage["lineage"][0]["version"] == 1
        archived = manager.archive(dataset["id"])
        assert archived["status"] == "archived"

    def test_compare_versions(self, tmp_path):
        dataset = make_dataset(tmp_path, n=2)
        manager = DatasetManager(store(tmp_path, "datasets.json"))
        manager.add_version(dataset["id"], [{"input": "x", "expected_output": "y"}])
        comparison = manager.compare(dataset["id"], 1, 2)
        assert comparison["identical"] is False


# ────────────────────────────────────────────────────── benchmark ──
class TestBenchmarkRunner:
    def test_reference_run(self, tmp_path):
        dataset = make_dataset(tmp_path, n=3)
        runner = BenchmarkRunner(store(tmp_path, "runs.json"),
                                 datasets=DatasetManager(store(tmp_path, "datasets.json")))
        run = runner.run(dataset["id"], model="")
        assert run["status"] == "completed"
        assert run["model"] == "reference"
        assert run["dataset_version"] == 1
        assert len(run["results"]) == 3
        assert "pass_rate" in run["metrics"]

    def test_custom_runner(self, tmp_path):
        dataset = make_dataset(tmp_path, n=2)
        runner = BenchmarkRunner(store(tmp_path, "runs.json"),
                                 datasets=DatasetManager(store(tmp_path, "datasets.json")))
        run = runner.run(dataset["id"], runner=lambda ex, meta: {
            "score": 0.9 if ex["input"] == "q0" else 0.2,
            "correct": ex["input"] == "q0",
            "passed": ex["input"] == "q0",
            "latency_ms": 10.0, "tokens": {"total": 5}, "cost": 0.001,
        })
        assert run["metrics"]["pass_rate"] == pytest.approx(0.5)
        assert run["cost"] == pytest.approx(0.002)
        assert run["metrics"]["mean_latency_ms"] == pytest.approx(10.0)

    def test_runner_errors_tracked(self, tmp_path):
        dataset = make_dataset(tmp_path, n=2)
        runner = BenchmarkRunner(store(tmp_path, "runs.json"),
                                 datasets=DatasetManager(store(tmp_path, "datasets.json")))

        def boom(ex, meta):
            if ex["input"] == "q1":
                raise RuntimeError("kaboom")
            return {"score": 1.0, "correct": True, "passed": True}

        run = runner.run(dataset["id"], runner=boom)
        assert len(run["errors"]) == 1
        assert run["errors"][0]["error"] == "kaboom"
        assert len(run["results"]) == 2

    def test_archived_version_rejected(self, tmp_path):
        dataset = make_dataset(tmp_path, n=1)
        manager = DatasetManager(store(tmp_path, "datasets.json"))
        manager.archive(dataset["id"])
        runner = BenchmarkRunner(store(tmp_path, "runs.json"), datasets=manager)
        with pytest.raises(ValueError):
            runner.run(dataset["id"])

    def test_get_missing_run(self, tmp_path):
        runner = BenchmarkRunner(store(tmp_path, "runs.json"),
                                 datasets=DatasetManager(store(tmp_path, "datasets.json")))
        with pytest.raises(KeyError):
            runner.get("nope")


# ─────────────────────────────────────────────────────── judges ──
class TestJudges:
    def test_judge_scores(self):
        judge = LLMJudge()
        result = judge.judge("explain X", "X is a component that does Y")
        assert result["overall"] > 0
        assert "correctness" in result["criterion_scores"]
        assert result["judge_model"]

    def test_judge_with_reference(self):
        judge = LLMJudge()
        good = judge.judge("sum 2+2", "4", reference="4")
        bad = judge.judge("sum 2+2", "banana", reference="4")
        assert good["overall"] > bad["overall"]

    def test_calibration_position_bias(self):
        calibration = JudgeCalibration()
        report = calibration.calibrate(
            judge_scores=[0.9, 0.8, 0.7],
            human_scores=[0.9, 0.8, 0.7],
            swapped_scores=[0.8, 0.75, 0.65],
            short_scores=[0.6, 0.6], long_scores=[0.7, 0.7],
        )
        assert "human_agreement" in report
        assert "cohens_kappa_judge_human" in report
        assert report["position_bias"] == pytest.approx(0.0667, abs=1e-4)
        assert report["length_bias"] == pytest.approx(0.1)


class TestHumanReview:
    def test_reviews_and_aggregate(self, tmp_path):
        manager = HumanReviewManager(store(tmp_path, "reviews.json"))
        manager.add("run-1", "ex-1", reviewer="alice",
                    scores={"correctness": 0.9, "quality": 0.8})
        manager.add("run-1", "ex-1", reviewer="bob",
                    scores={"correctness": 0.7, "quality": 0.6})
        report = manager.aggregate("run-1")
        assert report["reviews"] == 2
        assert report["criteria"]["correctness"]["mean"] == pytest.approx(0.8)
        assert report["overall"] == pytest.approx(0.75)

    def test_pairwise_verdict(self, tmp_path):
        manager = HumanReviewManager(store(tmp_path, "reviews.json"))
        manager.add("run-1", "ex-1", reviewer="a", preference="a")
        manager.add("run-1", "ex-1", reviewer="b", preference="b")
        manager.add("run-1", "ex-1", reviewer="c", preference="a")
        verdict = manager.pairwise_verdict("run-1")
        assert verdict["prefer_a"] == pytest.approx(2 / 3, abs=1e-4)

    def test_reliability_needs_two_raters(self, tmp_path):
        manager = HumanReviewManager(store(tmp_path, "reviews.json"))
        manager.add("run-1", "ex-1", reviewer="alice",
                    scores={"overall": 0.9})
        manager.add("run-1", "ex-2", reviewer="alice",
                    scores={"overall": 0.8})
        report = manager.reliability("run-1")
        assert report["reviews"] == 2
        assert "agreement_rate" in report


# ───────────────────────────────────────────────────── pairwise ──
class TestPairwise:
    def test_compare_winners(self, tmp_path):
        evaluator = PairwiseEvaluator(store(tmp_path, "pairwise.json"))
        examples = [{"input": f"q{i}", "expected_output": f"a{i}"} for i in range(4)]
        result = evaluator.compare("A", "B", examples,
                                   lambda label, ex: 0.9 if label == "A" else 0.5)
        assert result["a_win"] == 4
        assert result["b_win"] == 0
        assert result["win_rate_a"] == 1.0

    def test_empty_examples_rejected(self, tmp_path):
        evaluator = PairwiseEvaluator(store(tmp_path, "pairwise.json"))
        with pytest.raises(ValueError):
            evaluator.compare("A", "B", [])


# ─────────────────────────────────────────────────── code eval ──
class TestCodeEval:
    def test_generation_perfect(self):
        code = "def add(a, b):\n    return a + b"
        report = code_generation_report(code, code, tests_pass=True)
        assert report["correctness"] == pytest.approx(1.0)
        assert report["tests_pass"] == 1.0

    def test_repair(self):
        report = code_repair_report(bug_fixed=True, tests_passing=True,
                                    regression=False, security_ok=True)
        assert report["bug_fix_rate"] == 1.0
        assert report["regression_rate"] == 0.0

    def test_review_precision_recall(self):
        findings = [{"id": "f1", "issue": "sql injection"},
                    {"id": "f2", "issue": "XSS"}]
        report = code_review_report(findings, ["sql injection", "XSS"])
        assert report["finding_precision"] == 1.0
        assert report["finding_recall"] == 1.0

    def test_security_eval(self):
        report = security_eval_report(["sql injection"], ["sql injection"],
                                      remediations=[{"correct": True}])
        assert report["detection_precision"] == 1.0
        assert report["remediation_quality"] == 1.0

    def test_test_and_docs_and_arch(self):
        assert build_test_generation_report(0.3, 0.5, bug_detected=True)["mutation_score"] == 0.5
        assert documentation_report(0.9, 0.8, 0.9, 0.7, 0.8)["overall"] > 0.7
        assert architecture_report(0.9, 0.8, 0.8, 0.7)["overall"] > 0.7


# ──────────────────────────────────────────────────── agent eval ──
class TestAgentEval:
    def test_success_criteria(self):
        evaluator = AgentEvaluator()
        result = evaluator.evaluate_success(
            {"tests_pass": True, "no_unrelated_changes": True},
            {"tests_pass": True, "no_unrelated_changes": True})
        assert result["task_completed"] is True

    def test_tool_use(self):
        evaluator = AgentEvaluator()
        result = evaluator.evaluate_tool_use(["git", "test"], ["git", "test", "deploy"])
        assert result["wrong_tools"] == 1
        assert result["tool_precision"] == pytest.approx(2 / 3, abs=1e-4)

    def test_efficiency_cost_per_success(self):
        evaluator = AgentEvaluator()
        result = evaluator.evaluate_efficiency(successful=4, total=5, cost=8.0)
        assert result["cost_per_successful_task"] == pytest.approx(2.0)
        assert result["success_rate"] == pytest.approx(0.8)


# ──────────────────────────────────────────────────── regression ──
class TestRegressionGate:
    def _make_runs(self, tmp_path) -> tuple[dict, dict]:
        dataset = make_dataset(tmp_path, n=3)
        manager = DatasetManager(store(tmp_path, "datasets.json"))
        runner = BenchmarkRunner(store(tmp_path, "runs.json"), datasets=manager)
        baseline = runner.run(dataset["id"], runner=lambda ex, meta: {
            "score": 0.9, "correct": True, "passed": True, "latency_ms": 100})
        candidate = runner.run(dataset["id"], runner=lambda ex, meta: {
            "score": 0.9, "correct": True, "passed": True, "latency_ms": 100})
        return baseline, candidate

    def test_gate_pass(self, tmp_path):
        baseline, candidate = self._make_runs(tmp_path)
        engine = RegressionEngine(store(tmp_path, "gates.json"))
        decision = engine.gate(baseline, candidate)
        assert decision["verdict"] == "pass"
        assert decision["failures"] == []

    def test_gate_fails_on_quality_regression(self, tmp_path):
        baseline, _ = self._make_runs(tmp_path)
        dataset = make_dataset(tmp_path, n=3)
        manager = DatasetManager(store(tmp_path, "datasets.json"))
        runner = BenchmarkRunner(store(tmp_path, "runs.json"), datasets=manager)
        candidate = runner.run(dataset["id"], runner=lambda ex, meta: {
            "score": 0.1, "correct": False, "passed": False, "latency_ms": 100})
        engine = RegressionEngine(store(tmp_path, "gates.json"))
        decision = engine.gate(baseline, candidate)
        assert decision["verdict"] == "fail"
        assert any("quality" in f for f in decision["failures"])

    def test_gate_fails_on_latency_blowup(self, tmp_path):
        dataset = make_dataset(tmp_path, n=3)
        manager = DatasetManager(store(tmp_path, "datasets.json"))
        runner = BenchmarkRunner(store(tmp_path, "runs.json"), datasets=manager)
        baseline = runner.run(dataset["id"], runner=lambda ex, meta: {
            "score": 0.9, "correct": True, "passed": True, "latency_ms": 100})
        candidate = runner.run(dataset["id"], runner=lambda ex, meta: {
            "score": 0.9, "correct": True, "passed": True, "latency_ms": 500})
        engine = RegressionEngine(store(tmp_path, "gates.json"))
        decision = engine.gate(baseline, candidate)
        assert decision["verdict"] == "fail"
        assert any("latency" in f for f in decision["failures"])

    def test_gate_threshold_override(self, tmp_path):
        dataset = make_dataset(tmp_path, n=3)
        manager = DatasetManager(store(tmp_path, "datasets.json"))
        runner = BenchmarkRunner(store(tmp_path, "runs.json"), datasets=manager)
        baseline = runner.run(dataset["id"], runner=lambda ex, meta: {
            "score": 0.9, "correct": True, "passed": True, "latency_ms": 100})
        candidate = runner.run(dataset["id"], runner=lambda ex, meta: {
            "score": 0.9, "correct": True, "passed": True, "latency_ms": 500})
        engine = RegressionEngine(store(tmp_path, "gates.json"))
        decision = engine.gate(baseline, candidate, thresholds={"latency_delta": 10.0})
        assert decision["verdict"] == "pass"


# ──────────────────────────────────────────────── gateway facade ──
class TestGateway:
    def test_full_workflow(self, tmp_path):
        gw = EvaluationGateway(storage_dir=str(tmp_path / "data"))
        dataset = gw.create_dataset("full", "qa", organization_id="acme")
        gw.add_version(dataset["id"], [
            {"input": "what is 2+2", "expected_output": "4"},
            {"input": "what is 1+1", "expected_output": "2"},
        ])
        gw.publish_version(dataset["id"], 1)
        run = gw.run_benchmark(dataset["id"], model="")
        assert run["status"] == "completed"
        report = gw.report(run["id"])
        assert report["overall"] is not None
        decision = gw.gate(run["id"], run["id"])
        assert decision["verdict"] == "pass"
        md = gw.markdown_report(gw.comparison_report(run["id"], run["id"]))
        assert md.startswith("#")
        health = gw.health()
        assert health["status"] == "healthy"
        assert health["runs"] >= 1

    def test_prompt_register_and_compare(self, tmp_path):
        gw = EvaluationGateway(storage_dir=str(tmp_path / "data"))
        a = gw.register_prompt("p1", "Do {task} carefully")
        b = gw.register_prompt("p2", "Do {task} quickly and {style}")
        comparison = gw.compare_prompts(a["id"], b["id"])
        assert comparison["only_in_b"] == ["style"]

    def test_model_provider_reference_fallback(self):
        model = get_model("")
        assert model.offline is True
        assert model.model_id() == "reference"
        score = model.score("expected answer", "expected answer")
        assert score == pytest.approx(1.0)

    def test_multimodal_and_automation_health(self, tmp_path):
        gw = EvaluationGateway(storage_dir=str(tmp_path / "data"))
        assert gw.multimodal_health()["integrated"] is True
        assert gw.automation_health()["integrated"] is True
        assert len(gw.multimodal_targets()) >= 8

    def test_unsupported_multimodal_target(self, tmp_path):
        gw = EvaluationGateway(storage_dir=str(tmp_path / "data"))
        assert "image_understanding" in gw.multimodal_targets()
