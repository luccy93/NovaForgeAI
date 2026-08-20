"""AI Software Quality Engine -- Test Quality Analyzer (Volume 48).

Analyzes test changes, assertion quality, edge case coverage,
flaky test patterns, and weakened checks.
"""

from __future__ import annotations

import re
from typing import Any

from app.quality.analyzers.base import AnalyzerResult, BaseAnalyzer, ReviewContext


class TestQualityAnalyzer(BaseAnalyzer):
    name = "test_quality"
    category = "testing"

    WEAKENED_PATTERNS = [
        (r"@pytest\.mark\.skip", "skipped_test", "Skipped test — verify skip is justified"),
        (r"@pytest\.mark\.skipif", "conditional_skip", "Conditional skip — verify condition is valid"),
        (r"@unittest\.skip", "unittest_skip", "Skipped unittest"),
        (r"pass\s*$", "empty_test", "Test function body is just 'pass' — no assertions"),
        (r"assert\s+True\s*$", "trivial_assert", "Trivial assertion 'assert True' — no actual check"),
        (r"assert\s+1\s*==\s*1", "trivial_eq", "Trivial equality assertion"),
    ]

    FLAKY_PATTERNS = [
        (r"time\.sleep\(", "time_dependent", "Test uses time.sleep — may be flaky"),
        (r"datetime\.now\(\)", "time_dependent", "Test uses current time — may be non-deterministic"),
        (r"random\.(?:randint|random|choice|sample)", "random_values", "Test uses random values — may be non-deterministic"),
        (r"uuid\.uuid4\(\)", "random_uuid", "Test uses random UUID — may be non-deterministic"),
        (r"mock\.patch.*\n.*mock\.patch", "nested_mock", "Multiple nested mocks — complex mock setup"),
    ]

    TEST_FRAMEWORKS = {"pytest", "unittest", "jest", "mocha", "vitest", "junit", "rspec", "go test"}

    async def analyze(self, context: ReviewContext) -> AnalyzerResult:
        findings = []
        for file_path, content in context.file_contents.items():
            if not self._is_changed_file(file_path, context):
                continue
            if not self._is_test_file(file_path):
                continue
            lines = content.split("\n")
            findings.extend(self._check_test_quality(file_path, lines))
            findings.extend(self._check_flaky_patterns(file_path, lines))
            findings.extend(self._check_assertion_quality(file_path, lines))
        return AnalyzerResult(analyzer_name=self.name, findings=findings)

    def _is_test_file(self, file_path: str) -> bool:
        lower = file_path.lower()
        return (
            "test" in lower
            or lower.endswith("_test.py")
            or lower.endswith("_test.js")
            or lower.endswith("_test.ts")
            or lower.endswith(".test.js")
            or lower.endswith(".test.ts")
            or lower.endswith("_spec.js")
            or lower.endswith("_spec.ts")
            or "/tests/" in lower
            or "/test/" in lower
            or "/__tests__/" in lower
        )

    def _check_test_quality(self, file_path: str, lines: list[str]) -> list:
        findings = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pattern, rule_id, desc in self.WEAKENED_PATTERNS:
                if re.search(pattern, stripped):
                    findings.append(self._make_finding(
                        severity="medium" if "skip" in rule_id else "low",
                        confidence=0.7,
                        file_path=file_path, line_start=i, line_end=i,
                        description=desc,
                        evidence={"line": stripped[:120]},
                        recommendation="Ensure test skip/weakening is justified and documented",
                        rule_id=f"testing.{rule_id}",
                    ))
        return findings

    def _check_flaky_patterns(self, file_path: str, lines: list[str]) -> list:
        findings = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pattern, rule_id, desc in self.FLAKY_PATTERNS:
                if re.search(pattern, stripped):
                    findings.append(self._make_finding(
                        severity="low", confidence=0.5,
                        file_path=file_path, line_start=i, line_end=i,
                        description=desc,
                        evidence={"line": stripped[:120], "rule": rule_id},
                        recommendation="Use deterministic values or mock time/random for reliable tests",
                        rule_id=f"testing.{rule_id}",
                    ))
        return findings

    def _check_assertion_quality(self, file_path: str, lines: list[str]) -> list:
        findings = []
        test_funcs = []
        current_func = None
        func_start = 0
        assert_count = 0

        for i, line in enumerate(lines):
            stripped = line.strip()
            if re.match(r"(?:def|it|test)\s+\w+", stripped):
                if current_func and assert_count == 0:
                    findings.append(self._make_finding(
                        severity="medium", confidence=0.6,
                        file_path=file_path, line_start=func_start + 1, line_end=i,
                        description=f"Test function '{current_func}' has no assertions",
                        evidence={"function": current_func},
                        recommendation="Add meaningful assertions to verify expected behavior",
                        rule_id="testing.no_assertions",
                    ))
                current_func = stripped.split("(")[0].replace("def ", "").replace("it ", "").replace("test ", "")
                func_start = i
                assert_count = 0
            if re.search(r"assert\s+", stripped) or re.search(r"expect\(", stripped):
                assert_count += 1

        if current_func and assert_count == 0:
            findings.append(self._make_finding(
                severity="medium", confidence=0.6,
                file_path=file_path, line_start=func_start + 1, line_end=len(lines),
                description=f"Test function '{current_func}' has no assertions",
                evidence={"function": current_func},
                recommendation="Add meaningful assertions",
                rule_id="testing.no_assertions",
            ))
        return findings
