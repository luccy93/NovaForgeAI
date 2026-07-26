"""AI Evaluation benchmarks — measures accuracy, latency, and quality.

Run with: python -m pytest tests/backend/benchmarks/ --run-slow -v
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any

import pytest

from app.services.code_analysis import CodeAnalysisService


# ─── Test Data ─────────────────────────────────────────────────────

BENCHMARK_QUERIES = [
    {"question": "What is a Python decorator?", "expected_topics": ["decorator", "function", "syntax"]},
    {"question": "How does async/await work in TypeScript?", "expected_topics": ["async", "await", "promise"]},
    {"question": "Explain dependency injection", "expected_topics": ["dependency", "injection", "pattern"]},
    {"question": "What is the difference between a class and an interface?", "expected_topics": ["class", "interface", "type"]},
]


@dataclass
class BenchmarkResult:
    name: str
    success: bool
    duration_ms: float
    accuracy: float = 0.0
    error: str = ""
    details: dict = field(default_factory=dict)


class BenchmarkSuite:
    """Collects and reports benchmark results."""

    def __init__(self):
        self.results: list[BenchmarkResult] = []

    def record(self, result: BenchmarkResult) -> None:
        self.results.append(result)

    def report(self) -> dict:
        total = len(self.results)
        passed = sum(1 for r in self.results if r.success)
        avg_duration = sum(r.duration_ms for r in self.results) / total if total else 0
        return {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": round(passed / total * 100, 2) if total else 0,
            "avg_duration_ms": round(avg_duration, 2),
            "results": [
                {
                    "name": r.name,
                    "success": r.success,
                    "duration_ms": r.duration_ms,
                    "accuracy": r.accuracy,
                }
                for r in self.results
            ],
        }


suite = BenchmarkSuite()


# ─── Code Analysis Benchmarks ──────────────────────────────────────

class TestCodeAnalysisBenchmarks:
    """Benchmark code analysis on various languages."""

    LARGE_PYTHON_FILE = "\n".join([f"def func_{i}():\n    pass\n" for i in range(100)])
    LARGE_TS_FILE = "\n".join([f"function func{i}(): void {{\n}}\n" for i in range(100)])

    def test_python_analysis_speed(self):
        svc = CodeAnalysisService()
        start = time.monotonic()
        result = svc.analyze_file(self.LARGE_PYTHON_FILE, "python")
        elapsed = (time.monotonic() - start) * 1000
        suite.record(BenchmarkResult(
            name="python_large_file_analysis",
            success=len(result["functions"]) > 0,
            duration_ms=elapsed,
            accuracy=len(result["functions"]) / 100,
        ))

    def test_typescript_analysis_speed(self):
        svc = CodeAnalysisService()
        start = time.monotonic()
        result = svc.analyze_file(self.LARGE_TS_FILE, "typescript")
        elapsed = (time.monotonic() - start) * 1000
        suite.record(BenchmarkResult(
            name="typescript_large_file_analysis",
            success=len(result["functions"]) > 0,
            duration_ms=elapsed,
            accuracy=len(result["functions"]) / 100,
        ))

    def test_complexity_benchmark(self):
        svc = CodeAnalysisService()
        content = """def a(): pass
def b():
    if True:
        for x in range(10):
            if x > 5:
                return x
    return 0
"""
        start = time.monotonic()
        result = svc.analyze_file(content, "python")
        elapsed = (time.monotonic() - start) * 1000
        suite.record(BenchmarkResult(
            name="complexity_calculation",
            success=result["complexity"] > 1,
            duration_ms=elapsed,
            accuracy=result["complexity"],
        ))

    def test_dependency_detection_speed(self):
        svc = CodeAnalysisService()
        content = "\n".join([f"import module_{i}" for i in range(50)])
        start = time.monotonic()
        result = svc.analyze_file(content, "python")
        elapsed = (time.monotonic() - start) * 1000
        suite.record(BenchmarkResult(
            name="dependency_detection",
            success=len(result["dependencies"]) == 50,
            duration_ms=elapsed,
            accuracy=len(result["dependencies"]) / 50,
        ))

    def test_empty_file_overhead(self):
        svc = CodeAnalysisService()
        start = time.monotonic()
        svc.analyze_file("", "python")
        elapsed = (time.monotonic() - start) * 1000
        suite.record(BenchmarkResult(
            name="empty_file_overhead",
            success=elapsed < 100,
            duration_ms=elapsed,
        ))

    def test_multiple_languages(self):
        svc = CodeAnalysisService()
        languages = ["python", "typescript", "go", "rust", "java"]
        for lang in languages:
            content = {"python": "def f(): pass",
                       "typescript": "function f(): void {}",
                       "go": "func f() {}",
                       "rust": "fn f() {}",
                       "java": "public void f() {}"}[lang]
            start = time.monotonic()
            result = svc.analyze_file(content, lang)
            elapsed = (time.monotonic() - start) * 1000
            suite.record(BenchmarkResult(
                name=f"{lang}_analysis",
                success=len(result["functions"]) > 0,
                duration_ms=elapsed,
            ))


# ─── Report ────────────────────────────────────────────────────────

def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Print benchmark report at end of test session."""
    report = suite.report()
    output = json.dumps(report, indent=2)
    print(f"\n{'='*60}")
    print("AI EVALUATION BENCHMARK REPORT")
    print(f"{'='*60}")
    print(f"Total: {report['total']} | Passed: {report['passed']} | Failed: {report['failed']}")
    print(f"Pass Rate: {report['pass_rate']}% | Avg Duration: {report['avg_duration_ms']}ms")
    print(f"\nDetailed Results:\n{output}")
    print(f"{'='*60}\n")
