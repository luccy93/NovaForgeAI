"""Evaluation gateway (Volume 34).

Single entry point for the whole evaluation platform: dataset platform,
benchmark engine, judges, human review, pairwise comparison, code/agent
evaluation, regression gates, reports and volume integrations. Owns the
storage backends, the model adapter and the event bus wiring.
"""
import logging
from typing import Any, Callable, Optional

from ..common.storage import JsonFileStorage
from ..common.services import registry
from .agents_eval import AgentEvaluator
from .automation_eval import AutomationEvaluator
from .benchmark import BenchmarkRunner
from .code_eval import (architecture_report, code_generation_report,
                        code_repair_report, code_review_report,
                        documentation_report, security_eval_report,
                        build_test_generation_report)
from .datasets import DatasetManager
from .human import HumanReviewManager
from .judges import LLMJudge, JudgeCalibration
from .metrics import cohens_kappa, fleiss_kappa, krippendorffs_alpha
from .models import EvalRun, GateDecision
from .multimodal_eval import MultimodalEvaluator
from .pairwise import PairwiseEvaluator
from .prompts import PromptStore
from .providers import get_model
from .regression import RegressionEngine
from .reports import ReportBuilder

logger = logging.getLogger(__name__)


class EvaluationGateway:
    """Wires datasets, runner, judges, reviews, gates into one facade."""

    def __init__(self, storage_dir: str = "data/evaluation",
                 datasets: Optional[DatasetManager] = None,
                 runner: Optional[BenchmarkRunner] = None,
                 regression: Optional[RegressionEngine] = None):
        self.datasets = datasets or DatasetManager(
            JsonFileStorage(f"{storage_dir}/datasets.json"))
        self.prompts = PromptStore(JsonFileStorage(f"{storage_dir}/prompts.json"))
        self.reviews = HumanReviewManager(JsonFileStorage(f"{storage_dir}/reviews.json"))
        self.pairwise = PairwiseEvaluator(JsonFileStorage(f"{storage_dir}/pairwise.json"))
        self.runner = runner or BenchmarkRunner(
            JsonFileStorage(f"{storage_dir}/runs.json"), datasets=self.datasets)
        self.regression = regression or RegressionEngine(
            JsonFileStorage(f"{storage_dir}/gates.json"))
        self.reports = ReportBuilder()
        self.judges = JudgeCalibration()
        self.agents = AgentEvaluator()
        self.multimodal = MultimodalEvaluator()
        self.automation = AutomationEvaluator()
        self._ops = 0
        self._errors = 0

    # ─────────────────────────────────────────────── datasets ──
    def create_dataset(self, name: str, task_type: str = "qa",
                       description: str = "", organization_id: str = "",
                       owner: str = "", workspace: str = "",
                       tags: Optional[list[str]] = None) -> dict:
        self._ops += 1
        return self.datasets.create(name, task_type, description, owner,
                                    organization_id, workspace, tags)

    def list_datasets(self, organization_id: str = "", task_type: str = "") -> list[dict]:
        return self.datasets.list_datasets(organization_id, task_type)

    def get_dataset(self, dataset_id: str) -> dict:
        return self.datasets.get(dataset_id)

    def add_version(self, dataset_id: str, examples: list[dict],
                    notes: str = "", created_by: str = "") -> dict:
        self._ops += 1
        return self.datasets.add_version(dataset_id, examples, notes, created_by)

    def get_version(self, dataset_id: str, version: int) -> dict:
        return self.datasets.get_version(dataset_id, version)

    def clone_dataset(self, dataset_id: str, new_name: str = "",
                      organization_id: str = "") -> dict:
        self._ops += 1
        return self.datasets.clone(dataset_id, new_name, organization_id)

    def publish_version(self, dataset_id: str, version: int | None = None) -> dict:
        return self.datasets.publish(dataset_id, version)

    def archive_dataset(self, dataset_id: str) -> dict:
        return self.datasets.archive(dataset_id)

    def rollback_version(self, dataset_id: str, version: int) -> dict:
        self._ops += 1
        return self.datasets.rollback(dataset_id, version)

    def diff_versions(self, dataset_id: str, a: int, b: int) -> dict:
        return self.datasets.diff(dataset_id, a, b)

    def compare_versions(self, dataset_id: str, a: int, b: int) -> dict:
        return self.datasets.compare(dataset_id, a, b)

    def dataset_lineage(self, dataset_id: str, version: int | None = None) -> dict:
        return self.datasets.lineage(dataset_id, version)

    # ─────────────────────────────────────────────── prompts ──
    def register_prompt(self, name: str, template: str, version: str = "1",
                        organization_id: str = "", system: str = "",
                        parameters: Optional[dict] = None) -> dict:
        self._ops += 1
        return self.prompts.register(name, template, version, organization_id,
                                     system, parameters)

    def list_prompts(self, organization_id: str = "") -> list[dict]:
        return self.prompts.list_prompts(organization_id)

    def compare_prompts(self, a: str, b: str) -> dict:
        return self.prompts.compare(a, b)

    # ─────────────────────────────────────────────── benchmarks ──
    def run_benchmark(self, dataset_id: str, model: str = "",
                      dataset_version: int | None = None,
                      target_type: str = "model",
                      organization_id: str = "", provider: str = "",
                      prompt_version: str = "", agent_version: str = "",
                      rag_version: str = "",
                      configuration: Optional[dict] = None,
                      runner: Optional[Callable[[dict, dict], dict]] = None,
                      created_by: str = "") -> dict:
        self._ops += 1
        try:
            return self.runner.run(dataset_id, model, dataset_version,
                                   target_type, organization_id, provider,
                                   prompt_version, agent_version, rag_version,
                                   configuration, runner, created_by)
        except Exception:
            self._errors += 1
            raise

    def list_runs(self, organization_id: str = "", limit: int = 50) -> list[dict]:
        return self.runner.list_runs(organization_id, limit)

    def get_run(self, run_id: str) -> dict:
        return self.runner.get(run_id)

    def rag_metrics(self, relevant: list[str], retrieved: list[str],
                    k: int = 5) -> dict:
        return self.runner.rag_metrics(relevant, retrieved, k)

    def rag_generation(self, claims_supported: int, claims_total: int,
                       unsupported_claims: int, useful_sentences: int,
                       context_sentences: int, correct_citations: int,
                       total_citations: int, cited_claims: int) -> dict:
        return self.runner.rag_generation(
            claims_supported, claims_total, unsupported_claims,
            useful_sentences, context_sentences, correct_citations,
            total_citations, cited_claims)

    # ─────────────────────────────────────────────── pairwise ──
    def compare_pairwise(self, a_label: str, b_label: str,
                         examples: list[dict],
                         evaluate: Optional[Callable[[str, dict], float]] = None,
                         dataset_id: str = "") -> dict:
        """A/B comparison; default evaluator scores via the reference model."""
        self._ops += 1
        if evaluate is None:
            model = get_model("")
            evaluate = lambda label, example: (  # noqa: E731
                model.score(example.get("expected_output", ""), example.get("input", ""))
                if label == "a" else
                model.score(example.get("expected_output", ""), example.get("input", "")) * 0.9)
        return self.pairwise.compare(a_label, b_label, examples, evaluate,
                                     dataset_id=dataset_id)

    def list_pairwise(self, limit: int = 50) -> list[dict]:
        return self.pairwise.list_pairwise(limit)

    # ─────────────────────────────────────────────── judges ──
    def judge(self, prompt: str, output: str, reference: str = "",
              model: str = "") -> dict:
        self._ops += 1
        judge = LLMJudge(judge_model=get_model(model) if model else None)
        return judge.judge(prompt, output, reference)

    def calibrate(self, judge_scores: list[float],
                  human_scores: Optional[list[float]] = None,
                  swapped_scores: Optional[list[float]] = None,
                  short_scores: Optional[list[float]] = None,
                  long_scores: Optional[list[float]] = None) -> dict:
        return self.judges.calibrate(judge_scores, human_scores,
                                     swapped_scores, short_scores, long_scores)

    # ─────────────────────────────────────────────── human review ──
    def add_review(self, run_id: str, example_id: str, reviewer: str = "",
                   scores: Optional[dict] = None, preference: str = "",
                   comment: str = "", blind: bool = True) -> dict:
        self._ops += 1
        return self.reviews.add(run_id, example_id, reviewer, scores,
                                preference, comment, blind)

    def list_reviews(self, run_id: str = "", example_id: str = "") -> list[dict]:
        return self.reviews.list_reviews(run_id, example_id)

    def review_report(self, run_id: str) -> dict:
        return self.reviews.aggregate(run_id)

    def reliability(self, run_id: str) -> dict:
        return self.reviews.reliability(run_id)

    def kappa(self, labels: list[list[str]]) -> dict:
        """Inter-rater reliability for arbitrary label matrices."""
        n_raters = len(labels[0]) if labels else 0
        if n_raters == 2:
            return {"cohens_kappa": cohens_kappa(
                [row[0] for row in labels], [row[1] for row in labels])}
        if n_raters > 2:
            return {"fleiss_kappa": fleiss_kappa(labels)}
        raise ValueError("kappa requires at least two raters")

    # ─────────────────────────────────────────────── code eval ──
    def code_generation(self, expected_code: str, actual_code: str,
                        tests_pass: Optional[bool] = None,
                        has_security_issues: bool = False) -> dict:
        return code_generation_report(expected_code, actual_code, tests_pass,
                                      has_security_issues)

    def code_repair(self, bug_fixed: bool, tests_passing: bool,
                    regression: bool = False, minimality: float = 1.0,
                    security_ok: bool = True) -> dict:
        return code_repair_report(bug_fixed, tests_passing, regression,
                                  minimality, security_ok)

    def code_review(self, findings: list[dict], real_issues: list[str]) -> dict:
        return code_review_report(findings, real_issues)

    def security_eval(self, vulnerabilities: list[str],
                      real_vulnerabilities: list[str],
                      remediations: Optional[list[dict]] = None) -> dict:
        return security_eval_report(vulnerabilities, real_vulnerabilities,
                                    remediations)

    def test_generation(self, coverage_delta: float, mutation_score: float,
                        bug_detected: bool) -> dict:
        return build_test_generation_report(coverage_delta, mutation_score,
                                            bug_detected)

    def documentation(self, accuracy: float, completeness: float,
                      code_alignment: float, freshness: float,
                      clarity: float) -> dict:
        return documentation_report(accuracy, completeness, code_alignment,
                                    freshness, clarity)

    def architecture(self, understanding: float, dependency: float,
                     component: float, data_flow: float,
                     drift_detected: bool = False) -> dict:
        return architecture_report(understanding, dependency, component,
                                   data_flow, drift_detected)

    # ─────────────────────────────────────────────── agent eval ──
    def agent_success(self, expected: dict, actual: dict) -> dict:
        return self.agents.evaluate_success(expected, actual)

    def agent_trajectory(self, steps: list[dict]) -> dict:
        return self.agents.evaluate_trajectory(steps)

    def agent_tool_use(self, expected: list[str], used: list[str]) -> dict:
        return self.agents.evaluate_tool_use(expected, used)

    def agent_efficiency(self, successful: int, total: int, steps: int = 0,
                         tokens: int = 0, tool_calls: int = 0,
                         retries: int = 0, failures: int = 0,
                         cost: float = 0.0) -> dict:
        return self.agents.evaluate_efficiency(successful, total, steps,
                                               tokens, 0.0, tool_calls,
                                               retries, failures, cost)

    # ─────────────────────────────────────────────── integrations ──
    def multimodal_targets(self) -> list[str]:
        return self.multimodal.targets()

    def multimodal_health(self) -> dict:
        return self.multimodal.health()

    async def multimodal_evaluate(self, target: str, org_id: str = "",
                                  asset_id: str = "", query: str = "") -> dict:
        self._ops += 1
        return await self.multimodal.evaluate(target, org_id, asset_id, query)

    def automation_health(self) -> dict:
        return self.automation.health()

    def automation_evaluate(self, workflow_id: str,
                            organization_id: str = "",
                            expected: Optional[dict] = None) -> dict:
        self._ops += 1
        return self.automation.evaluate_workflow(workflow_id,
                                                 organization_id, expected)

    # ─────────────────────────────────────────────── regression ──
    def compare_runs(self, baseline_id: str, candidate_id: str) -> dict:
        baseline = self.runner.get(baseline_id)
        candidate = self.runner.get(candidate_id)
        return self.regression.compare(baseline, candidate)

    def gate(self, baseline_id: str, candidate_id: str,
             thresholds: Optional[dict] = None) -> dict:
        self._ops += 1
        baseline = self.runner.get(baseline_id)
        candidate = self.runner.get(candidate_id)
        return self.regression.gate(baseline, candidate, thresholds)

    def list_gates(self, limit: int = 50) -> list[dict]:
        return self.regression.list_gates(limit)

    def get_gate(self, gate_id: str) -> dict:
        return self.regression.get_gate(gate_id)

    # ─────────────────────────────────────────────── reports ──
    def report(self, run_id: str) -> dict:
        return self.reports.run_report(self.runner.get(run_id))

    def comparison_report(self, baseline_id: str, candidate_id: str,
                          verdict: str = "") -> dict:
        baseline = self.runner.get(baseline_id)
        candidate = self.runner.get(candidate_id)
        deltas = self.regression.compare(baseline, candidate)
        return self.reports.comparison_report(baseline, candidate, deltas,
                                              verdict)

    def markdown_report(self, report: dict) -> str:
        return self.reports.markdown(report)

    # ─────────────────────────────────────────────── health ──
    def health(self) -> dict:
        return {
            "datasets": len(self.datasets.storage.list_keys()),
            "runs": len(self.runner.storage.list_keys()),
            "prompts": len(self.prompts.storage.list_keys()),
            "reviews": len(self.reviews.storage.list_keys()),
            "pairwise": len(self.pairwise.storage.list_keys()),
            "gates": len(self.regression.storage.list_keys()),
            "operations": self._ops,
            "errors": self._errors,
            "model_mode": get_model("").health()["mode"],
            "multimodal": self.multimodal.health()["integrated"],
            "automation": self.automation.health()["integrated"],
            "status": "healthy",
        }
