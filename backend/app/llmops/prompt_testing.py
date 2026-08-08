import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
import json, uuid, hashlib, time, math, re
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)


class TestMetric(Enum):
    ACCURACY = "accuracy"
    LATENCY = "latency"
    COST = "cost"
    CITATION_QUALITY = "citation_quality"
    HALLUCINATION = "hallucination"
    CONTEXT_USAGE = "context_usage"
    DETERMINISM = "determinism"
    TOOL_USAGE = "tool_usage"
    RELEVANCE = "relevance"
    COMPLETENESS = "completeness"
    CONSISTENCY = "consistency"


class TestStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class PromptTest:
    id: str = ""
    prompt_id: str = ""
    version: int = 1
    test_name: str = ""
    test_cases: list[dict] = field(default_factory=list)
    metrics: list[TestMetric] = field(default_factory=list)
    status: TestStatus = TestStatus.PENDING
    results: dict = field(default_factory=dict)
    score: float = 0.0
    created_at: str = ""
    completed_at: Optional[str] = None
    duration_ms: float = 0.0
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["metrics"] = [m.value for m in self.metrics]
        d["status"] = self.status.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "PromptTest":
        data = data.copy()
        data["metrics"] = [TestMetric(m) for m in data.get("metrics", [])]
        data["status"] = TestStatus(data.get("status", "pending"))
        return PromptTest(**data)


@dataclass
class TestCase:
    id: str = ""
    prompt_id: str = ""
    input: str = ""
    expected_output: str = ""
    actual_output: str = ""
    latency_ms: float = 0.0
    token_count: int = 0
    cost: float = 0.0
    score: float = 0.0
    passed: bool = False
    errors: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "TestCase":
        return TestCase(**data)


@dataclass
class TestSuite:
    id: str = ""
    name: str = ""
    tests: list[str] = field(default_factory=list)
    schedule: str = ""
    last_run: Optional[str] = None
    status: str = "idle"

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "TestSuite":
        return TestSuite(**data)


@dataclass
class HallucinationScore:
    test_id: str = ""
    factual_accuracy: float = 0.0
    source_alignment: float = 0.0
    invented_facts: int = 0
    hallucination_rate: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "HallucinationScore":
        return HallucinationScore(**data)


@dataclass
class DeterminismScore:
    test_id: str = ""
    runs: int = 0
    output_variance: float = 0.0
    consistent_ratio: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "DeterminismScore":
        return DeterminismScore(**data)


class PromptTester:
    def __init__(self, storage_dir: str):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._tests_file = self.storage_dir / "prompt_tests.json"
        self._test_cases_file = self.storage_dir / "test_cases.json"
        self._suites_file = self.storage_dir / "test_suites.json"
        self._tests: dict[str, PromptTest] = {}
        self._test_cases: dict[str, TestCase] = {}
        self._suites: dict[str, TestSuite] = {}
        self._load()
        self._telemetry = defaultdict(int)
        logger.info("PromptTester initialized at %s", storage_dir)

    def _save(self):
        try:
            self._tests_file.write_text(json.dumps({k: v.to_dict() for k, v in self._tests.items()}, indent=2))
            self._test_cases_file.write_text(json.dumps({k: v.to_dict() for k, v in self._test_cases.items()}, indent=2))
            self._suites_file.write_text(json.dumps({k: v.to_dict() for k, v in self._suites.items()}, indent=2))
        except Exception as e:
            logger.error("Failed to save test data: %s", e)
            raise

    def _load(self):
        try:
            if self._tests_file.exists():
                data = json.loads(self._tests_file.read_text())
                self._tests = {k: PromptTest.from_dict(v) for k, v in data.items()}
            if self._test_cases_file.exists():
                data = json.loads(self._test_cases_file.read_text())
                self._test_cases = {k: TestCase.from_dict(v) for k, v in data.items()}
            if self._suites_file.exists():
                data = json.loads(self._suites_file.read_text())
                self._suites = {k: TestSuite.from_dict(v) for k, v in data.items()}
        except Exception as e:
            logger.error("Failed to load test data: %s", e)

    def create_test(self, prompt_id: str, test_name: str, test_cases: list[dict],
                    metrics: list[TestMetric], version: int = 1) -> PromptTest:
        test = PromptTest(
            prompt_id=prompt_id,
            version=version,
            test_name=test_name,
            test_cases=test_cases,
            metrics=metrics,
        )
        self._tests[test.id] = test
        for tc_data in test_cases:
            tc = TestCase(
                prompt_id=prompt_id,
                input=tc_data.get("input", ""),
                expected_output=tc_data.get("expected_output", ""),
            )
            self._test_cases[tc.id] = tc
        self._save()
        self._telemetry["tests_created"] += 1
        return test

    def run_test(self, test_id: str, evaluator: Optional["TestEvaluator"] = None) -> Optional[PromptTest]:
        test = self._tests.get(test_id)
        if not test:
            return None
        test.status = TestStatus.RUNNING
        start = time.time()
        try:
            if evaluator is None:
                evaluator = TestEvaluator()
            results = {}
            for metric in test.metrics:
                val = evaluator.evaluate(test, metric)
                results[metric.value] = val
            test.results = results
            test.score = evaluator.compute_overall_score(results)
            test.status = TestStatus.COMPLETED
            test.duration_ms = (time.time() - start) * 1000
            test.completed_at = datetime.now(timezone.utc).isoformat()
            self._save()
            self._telemetry["tests_completed"] += 1
        except Exception as e:
            test.status = TestStatus.FAILED
            test.duration_ms = (time.time() - start) * 1000
            logger.error("Test %s failed: %s", test_id, e)
            self._save()
        return test

    def get_test(self, test_id: str) -> Optional[PromptTest]:
        return self._tests.get(test_id)

    def list_tests(self, prompt_id: Optional[str] = None) -> list[PromptTest]:
        if prompt_id:
            return [t for t in self._tests.values() if t.prompt_id == prompt_id]
        return list(self._tests.values())

    def compare_tests(self, test_ids: list[str]) -> list[dict]:
        results = []
        for tid in test_ids:
            test = self._tests.get(tid)
            if test:
                results.append({"id": tid, "name": test.test_name, "score": test.score, "results": test.results})
        return results

    def calculate_hallucination_score(self, test_id: str) -> Optional[HallucinationScore]:
        test = self._tests.get(test_id)
        if not test:
            return None
        total = len(test.test_cases)
        if total == 0:
            return HallucinationScore(test_id=test_id)
        invented = sum(1 for tc in test.test_cases if tc.get("invented", False))
        factual = sum(tc.get("factual_score", 1.0) for tc in test.test_cases) / total
        alignment = sum(tc.get("alignment_score", 1.0) for tc in test.test_cases) / total
        return HallucinationScore(
            test_id=test_id,
            factual_accuracy=round(factual, 4),
            source_alignment=round(alignment, 4),
            invented_facts=invented,
            hallucination_rate=round(invented / total, 4),
        )

    def calculate_determinism(self, test_id: str, runs: int = 5) -> Optional[DeterminismScore]:
        test = self._tests.get(test_id)
        if not test:
            return None
        outputs = []
        for tc in test.test_cases:
            for _ in range(runs):
                outputs.append(tc.get("actual_output", ""))
        if not outputs:
            return DeterminismScore(test_id=test_id)
        unique = len(set(outputs))
        total = len(outputs)
        variance = 1.0 - (unique / total) if total > 0 else 0.0
        return DeterminismScore(
            test_id=test_id,
            runs=runs * len(test.test_cases),
            output_variance=round(variance, 4),
            consistent_ratio=round(1.0 - variance, 4),
        )

    def run_suite(self, suite_id: str, evaluator: Optional["TestEvaluator"] = None) -> Optional[TestSuite]:
        suite = self._suites.get(suite_id)
        if not suite:
            return None
        suite.status = "running"
        for test_id in suite.tests:
            self.run_test(test_id, evaluator)
        suite.last_run = datetime.now(timezone.utc).isoformat()
        suite.status = "completed"
        self._save()
        self._telemetry["suites_run"] += 1
        return suite

    def schedule_suite(self, suite_id: str, cron_expression: str) -> bool:
        suite = self._suites.get(suite_id)
        if not suite:
            return False
        suite.schedule = cron_expression
        self._save()
        return True

    def get_telemetry(self) -> dict:
        return dict(self._telemetry)


class TestEvaluator:
    def __init__(self):
        self._telemetry = defaultdict(int)

    def evaluate(self, test: PromptTest, metric: TestMetric) -> float:
        method_map = {
            TestMetric.ACCURACY: self.evaluate_accuracy,
            TestMetric.LATENCY: self.evaluate_latency,
            TestMetric.COST: self.evaluate_cost,
            TestMetric.CITATION_QUALITY: self.evaluate_citation,
            TestMetric.CONTEXT_USAGE: self.evaluate_context_usage,
            TestMetric.TOOL_USAGE: self.evaluate_tool_usage,
            TestMetric.HALLUCINATION: lambda t: 1.0 - (sum(tc.get("hallucination_score", 0) for tc in t.test_cases) / max(len(t.test_cases), 1)),
            TestMetric.DETERMINISM: lambda t: sum(1 for tc in t.test_cases if tc.get("deterministic", True)) / max(len(t.test_cases), 1),
            TestMetric.RELEVANCE: lambda t: sum(tc.get("relevance_score", 1.0) for tc in t.test_cases) / max(len(t.test_cases), 1),
            TestMetric.COMPLETENESS: lambda t: sum(tc.get("completeness_score", 1.0) for tc in t.test_cases) / max(len(t.test_cases), 1),
            TestMetric.CONSISTENCY: lambda t: sum(tc.get("consistency_score", 1.0) for tc in t.test_cases) / max(len(t.test_cases), 1),
        }
        fn = method_map.get(metric)
        if not fn:
            logger.warning("No evaluator for metric %s", metric.value)
            return 0.0
        self._telemetry["evaluations"] += 1
        return round(fn(test), 4)

    def evaluate_accuracy(self, test: PromptTest) -> float:
        total = len(test.test_cases)
        if total == 0:
            return 0.0
        passed = sum(1 for tc in test.test_cases if tc.get("expected_output", "") == tc.get("actual_output", ""))
        return passed / total

    def evaluate_latency(self, test: PromptTest) -> float:
        latencies = [tc.get("latency_ms", 0) for tc in test.test_cases]
        if not latencies:
            return 0.0
        avg = sum(latencies) / len(latencies)
        return max(0.0, 1.0 - (avg / 1000.0))

    def evaluate_cost(self, test: PromptTest) -> float:
        costs = [tc.get("cost", 0) for tc in test.test_cases]
        if not costs:
            return 0.0
        avg = sum(costs) / len(costs)
        return max(0.0, 1.0 - (avg / 0.1))

    def evaluate_citation(self, test: PromptTest) -> float:
        scores = []
        for tc in test.test_cases:
            output = tc.get("actual_output", "")
            citations = re.findall(r"\[.*?\]|\(.*?\)", output)
            score = min(1.0, len(citations) / 3.0) if citations else 0.0
            scores.append(score)
        return sum(scores) / max(len(scores), 1)

    def evaluate_context_usage(self, test: PromptTest) -> float:
        scores = []
        for tc in test.test_cases:
            inp = tc.get("input", "")
            out = tc.get("actual_output", "")
            if not inp:
                scores.append(0.0)
                continue
            overlap = len(set(inp.lower().split()) & set(out.lower().split()))
            total = len(set(inp.lower().split()))
            scores.append(overlap / max(total, 1))
        return sum(scores) / max(len(scores), 1)

    def evaluate_tool_usage(self, test: PromptTest) -> float:
        scores = []
        for tc in test.test_cases:
            output = tc.get("actual_output", "")
            tool_pattern = r"tool|function|api|call|query"
            matches = len(re.findall(tool_pattern, output.lower()))
            scores.append(min(1.0, matches / 5.0))
        return sum(scores) / max(len(scores), 1)

    def compute_overall_score(self, results: dict[str, float]) -> float:
        if not results:
            return 0.0
        return round(sum(results.values()) / len(results), 4)

    def get_telemetry(self) -> dict:
        return dict(self._telemetry)
