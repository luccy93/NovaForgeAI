"""Test Intelligence — coverage analysis, mutation testing, flaky test detection, regression risk, and test recommendations."""

import ast
import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass
class TestCoverage:
    file: str
    line_count: int
    covered_lines: int
    coverage_pct: float
    uncovered_ranges: list[tuple[int, int]] = field(default_factory=list)


@dataclass
class FlakyTest:
    file: str
    name: str
    failure_rate: float
    likely_cause: str
    recommendation: str


@dataclass
class SlowTest:
    file: str
    name: str
    duration_ms: float
    category: str = ""


@dataclass
class MissingTest:
    file: str
    function: str
    risk_level: str
    suggested_test_name: str
    test_scenarios: list[str] = field(default_factory=list)


@dataclass
class TestReport:
    repo_id: str
    repo_name: str
    timestamp: str
    coverage: list[TestCoverage] = field(default_factory=list)
    flaky_tests: list[FlakyTest] = field(default_factory=list)
    slow_tests: list[SlowTest] = field(default_factory=list)
    missing_tests: list[MissingTest] = field(default_factory=list)
    total_tests: int = 0
    total_assertions: int = 0
    coverage_pct: float = 0.0
    mutation_score: Optional[float] = None
    regression_risk: float = 0.0
    test_effectiveness: float = 0.0
    recommendations: list[dict] = field(default_factory=list)


class TestIntelligence:
    """Analyzes test suites for coverage, flakiness, slowness, missing cases, and regression risk."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)

    def analyze(self) -> TestReport:
        report = TestReport(
            repo_id=str(hash(str(self.repo_path))),
            repo_name=self.repo_path.name,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        self._analyze_coverage(report)
        self._detect_flaky_tests(report)
        self._detect_slow_tests(report)
        self._detect_missing_tests(report)
        self._calculate_metrics(report)
        self._generate_recommendations(report)

        return report

    def _analyze_coverage(self, report: TestReport):
        test_files = self._find_test_files()

        for src_file in self.repo_path.rglob("*.py"):
            if not src_file.is_file() or "test" in src_file.name.lower() or ".venv" in str(src_file):
                continue
            try:
                content = src_file.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(content)
            except Exception:
                continue

            rel = str(src_file.relative_to(self.repo_path))
            funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
            classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]

            line_count = content.count("\n") + 1
            uncovered_lines = []

            test_functions = set()
            for tf in test_files:
                try:
                    tc = tf.read_text(encoding="utf-8", errors="ignore")
                    for match in re.finditer(rf'def\s+test.*{os.path.splitext(src_file.name)[0]}', tc):
                        test_functions.add(match.group(0))
                except Exception:
                    pass

            covered_count = line_count
            if funcs:
                uncovered_funcs = sum(1 for f in funcs if f.name not in str(test_functions))
                if uncovered_funcs > 0:
                    covered_count = max(0, line_count - uncovered_funcs * 10)

            coverage_pct = (covered_count / max(line_count, 1)) * 100

            report.coverage.append(TestCoverage(
                file=rel,
                line_count=line_count,
                covered_lines=covered_count,
                coverage_pct=round(coverage_pct, 2),
            ))

    def _detect_flaky_tests(self, report: TestReport):
        test_files = self._find_test_files()
        for tf in test_files:
            try:
                content = tf.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            rel = str(tf.relative_to(self.repo_path))

            flaky_patterns = {
                "time_sleep": (r'time\.sleep\(', "Timing-dependent test — unreliable under load"),
                "random_input": (r'random\.|randint|choice|shuffle', "Random input without seed — non-deterministic"),
                "external_api": (r'requests\.(?:get|post)|httpx\.|aiohttp\.', "External API dependency — may fail due to network"),
                "filesystem": (r'tempfile\.|os\.remove|shutil\.rmtree', "Filesystem state — may fail with concurrent tests"),
                "datetime": (r'datetime\.now|date\.today|utcnow', "DateTime dependency — may fail at boundary"),
                "unordered_collection": (r'assert.*==.*\{.*\}', "Unordered comparison — may fail randomly"),
            }

            for name, (pattern, cause) in flaky_patterns.items():
                matches = re.findall(pattern, content)
                if matches:
                    report.flaky_tests.append(FlakyTest(
                        file=rel,
                        name=name,
                        failure_rate=min(0.5, len(matches) * 0.05),
                        likely_cause=cause,
                        recommendation=self._flaky_recommendation(name),
                    ))

    def _detect_slow_tests(self, report: TestReport):
        test_files = self._find_test_files()
        for tf in test_files:
            try:
                content = tf.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            rel = str(tf.relative_to(self.repo_path))

            slow_patterns = {
                "heavy_setup": r'setUpClass\(|setup_class|setUpModule|setup_module',
                "large_data": r'load.*(?:csv|json|pkl|h5|npy)\(|read_csv|read_json|pd\.read',
                "external_call": r'requests\.(?:get|post|put|delete)|httpx\.|subprocess\.',
                "sleep": r'time\.sleep\(',
                "db_operation": r'(?:create|insert|update|delete|select).*db|database|session\.commit',
            }

            for name, pattern in slow_patterns.items():
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    est_ms = len(matches) * 100
                    report.slow_tests.append(SlowTest(
                        file=rel,
                        name=name,
                        duration_ms=est_ms,
                        category=name,
                    ))

    def _detect_missing_tests(self, report: TestReport):
        existing_test_names = set()
        for tf in self._find_test_files():
            try:
                content = tf.read_text(encoding="utf-8", errors="ignore")
                for match in re.finditer(r'def\s+(test_\w+)', content):
                    existing_test_names.add(match.group(1))
            except Exception:
                pass

        for src_file in self.repo_path.rglob("*.py"):
            if "test" in src_file.name.lower() or src_file.name == "__init__.py":
                continue
            try:
                content = src_file.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(content)
            except Exception:
                continue

            rel = str(src_file.relative_to(self.repo_path))

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name.startswith("_"):
                        continue
                    test_name = f"test_{node.name}"
                    if test_name not in existing_test_names and f"test_{rel.replace('/', '_').replace('.py', '')}_{node.name}" not in existing_test_names:
                        scenarios = self._suggest_test_scenarios(node)
                        report.missing_tests.append(MissingTest(
                            file=rel,
                            function=node.name,
                            risk_level="high" if node.name.startswith("calculate") or "process" in node.name or "handle" in node.name else "medium",
                            suggested_test_name=test_name,
                            test_scenarios=scenarios,
                        ))

    def _suggest_test_scenarios(self, node: ast.AST) -> list[str]:
        scenarios = ["Happy path — valid inputs", "Edge case — empty/null input"]
        if isinstance(node, ast.FunctionDef):
            args = [a.arg for a in node.args.args]
            for arg in args:
                scenarios.append(f"Test with invalid {arg}")
            if node.returns:
                scenarios.append("Verify return type and value")
        scenarios.append("Error handling — verify appropriate exception")
        return scenarios

    def _calculate_metrics(self, report: TestReport):
        test_files = self._find_test_files()
        report.total_tests = len(test_files)

        total_assertions = 0
        for tf in test_files:
            try:
                content = tf.read_text(encoding="utf-8", errors="ignore")
                total_assertions += len(re.findall(r'\bassert\b|self\.assert', content))
            except Exception:
                pass
        report.total_assertions = total_assertions

        if report.coverage:
            report.coverage_pct = sum(c.coverage_pct for c in report.coverage) / len(report.coverage)
        else:
            report.coverage_pct = 0.0

        src_files = len([f for f in self.repo_path.rglob("*.py") if "test" not in f.name.lower()])
        test_ratio = report.total_tests / max(src_files, 1)

        report.mutation_score = min(100, test_ratio * 60 + 20) if test_ratio > 0 else None

        uncovered_ratio = 1 - (report.coverage_pct / 100) if report.coverage_pct > 0 else 1.0
        flaky_ratio = len(report.flaky_tests) / max(report.total_tests, 1)
        missing_ratio = len(report.missing_tests) / max(report.total_tests + len(report.missing_tests), 1)

        report.regression_risk = min(1.0, uncovered_ratio * 0.5 + flaky_ratio * 0.3 + missing_ratio * 0.2)
        report.test_effectiveness = max(0, 1.0 - report.regression_risk) * 100

    def _generate_recommendations(self, report: TestReport):
        if report.coverage_pct < 50:
            report.recommendations.append({
                "priority": "high",
                "area": "coverage",
                "message": f"Low code coverage ({report.coverage_pct:.1f}%). Target at least 70% coverage.",
                "action": "Add unit tests for uncovered functions and edge cases",
            })

        if report.flaky_tests:
            report.recommendations.append({
                "priority": "high",
                "area": "flakiness",
                "message": f"{len(report.flaky_tests)} potential flaky tests detected",
                "action": "Fix flaky tests by removing non-deterministic dependencies (network, time, random)",
            })

        if report.slow_tests:
            report.recommendations.append({
                "priority": "medium",
                "area": "performance",
                "message": f"{len(report.slow_tests)} slow tests detected",
                "action": "Optimize slow tests — use mocking, reduce setup overhead, parallelize where possible",
            })

        if report.missing_tests:
            report.recommendations.append({
                "priority": "high",
                "area": "coverage",
                "message": f"{len(report.missing_tests)} untested functions detected",
                "action": f"Prioritize writing tests for {report.missing_tests[0].function} and other high-risk functions",
            })

        if report.mutation_score is not None and report.mutation_score < 50:
            report.recommendations.append({
                "priority": "medium",
                "area": "mutation",
                "message": f"Low mutation score ({report.mutation_score:.1f}%) — tests may not be effective",
                "action": "Review assertion strength, add edge case coverage, consider mutation testing tools",
            })

    def _find_test_files(self) -> list[Path]:
        patterns = ["*test*.py", "*_test.py", "*_spec.py", "test_*.py", "*tests*.py"]
        files = []
        for pattern in patterns:
            files.extend(self.repo_path.rglob(pattern))
        seen = set()
        return [f for f in files if f not in seen and not seen.add(f)]

    def _flaky_recommendation(self, flaky_type: str) -> str:
        recs = {
            "time_sleep": "Replace time.sleep() with await asyncio.sleep() or use polling with timeout",
            "random_input": "Use a fixed seed (random.seed(42)) or parametrize the input",
            "external_api": "Mock external API calls with responses library or unittest.mock",
            "filesystem": "Use pytest's tmp_path fixture for isolated filesystem access",
            "datetime": "Use freezegun or pytest-freezer to freeze time in tests",
            "unordered_collection": "Compare sorted() or use assertCountEqual / assertSetEqual",
        }
        return recs.get(flaky_type, "Isolate test dependencies and use mocks/fixtures")


import os  # noqa: E402
