"""AI Software Quality Engine -- Correctness Analyzer (Volume 48).

Detects logic errors, null/empty handling, race conditions, resource leaks,
error handling issues, and edge cases.
"""

from __future__ import annotations

import re
from typing import Any

from app.quality.analyzers.base import AnalyzerResult, BaseAnalyzer, ReviewContext


class CorrectnessAnalyzer(BaseAnalyzer):
    name = "correctness"
    category = "correctness"

    ERROR_HANDLING_PATTERNS = [
        (r"except\s*:", "bare_except", "Bare except catches all exceptions including SystemExit and KeyboardInterrupt"),
        (r"except\s+Exception\s*:\s*pass", "swallowed_error", "Exception silently swallowed without logging or re-raising"),
        (r"except\s+\w+.*:\s*\.\.\.", "ellipsis_except", "Exception handler uses ellipsis (pass) instead of handling"),
    ]

    NULL_PATTERNS = [
        (r"\.get\(\w+\)\s*\.\w+", "chained_get", "Chaining method calls after .get() without default — may raise AttributeError"),
        (r"if\s+\w+\s*is\s+None\s*:\s*return\s+None", "null_return", "Returning None instead of raising or providing default"),
    ]

    RESOURCE_PATTERNS = [
        (r"open\([^)]+\)(?!\s*as\s+)", "unclosed_open", "File opened without context manager (with statement)"),
        (r"except.*:\s*\n\s*pass", "resource_leak", "Possible resource leak — exception swallowed after resource operation"),
    ]

    EDGE_CASE_PATTERNS = [
        (r"\/\s*0\b", "div_zero", "Potential division by zero"),
        (r"\[\s*-\s*1\s*\]", "negative_index", "Negative indexing may fail on empty sequences"),
        (r"while\s+True\s*:", "infinite_loop", "Infinite loop — verify exit condition"),
    ]

    RACE_CONDITION_PATTERNS = [
        (r"global\s+\w+", "global_state", "Global mutable state may cause race conditions in async code"),
        (r"self\.\w+\s*=\s*\w+", "shared_state", "Shared state mutation in potentially concurrent context"),
    ]

    async def analyze(self, context: ReviewContext) -> AnalyzerResult:
        findings = []
        for file_path, content in context.file_contents.items():
            if not self._is_changed_file(file_path, context):
                continue
            lines = content.split("\n")
            findings.extend(self._check_error_handling(file_path, lines))
            findings.extend(self._check_null_handling(file_path, lines))
            findings.extend(self._check_resource_management(file_path, lines))
            findings.extend(self._check_edge_cases(file_path, lines))
            findings.extend(self._check_state_consistency(file_path, lines))
        return AnalyzerResult(analyzer_name=self.name, findings=findings)

    def _check_error_handling(self, file_path: str, lines: list[str]) -> list:
        findings = []
        for i, line in enumerate(lines, 1):
            for pattern, rule_id, desc in self.ERROR_HANDLING_PATTERNS:
                if re.search(pattern, line):
                    findings.append(self._make_finding(
                        severity="medium", confidence=0.8,
                        file_path=file_path, line_start=i, line_end=i,
                        description=desc,
                        evidence={"line": line.strip(), "rule": rule_id},
                        recommendation="Use specific exception types and handle or log errors appropriately",
                        rule_id=f"correctness.{rule_id}",
                    ))
        return findings

    def _check_null_handling(self, file_path: str, lines: list[str]) -> list:
        findings = []
        for i, line in enumerate(lines, 1):
            for pattern, rule_id, desc in self.NULL_PATTERNS:
                if re.search(pattern, line):
                    findings.append(self._make_finding(
                        severity="medium", confidence=0.6,
                        file_path=file_path, line_start=i, line_end=i,
                        description=desc,
                        evidence={"line": line.strip()},
                        recommendation="Add null check or provide default value",
                        rule_id=f"correctness.{rule_id}",
                    ))
        return findings

    def _check_resource_management(self, file_path: str, lines: list[str]) -> list:
        findings = []
        in_except = False
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if "except" in stripped:
                in_except = True
            elif in_except and stripped and not stripped.startswith("#"):
                in_except = False
            for pattern, rule_id, desc in self.RESOURCE_PATTERNS:
                if re.search(pattern, line):
                    if rule_id == "unclosed_open" and "with open" in line:
                        continue
                    findings.append(self._make_finding(
                        severity="medium", confidence=0.7,
                        file_path=file_path, line_start=i, line_end=i,
                        description=desc,
                        evidence={"line": stripped},
                        recommendation="Use context managers (with statement) for resource management",
                        rule_id=f"correctness.{rule_id}",
                    ))
        return findings

    def _check_edge_cases(self, file_path: str, lines: list[str]) -> list:
        findings = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pattern, rule_id, desc in self.EDGE_CASE_PATTERNS:
                if re.search(pattern, line):
                    if rule_id == "negative_index":
                        context_start = max(0, i - 3)
                        context_lines = lines[context_start:i]
                        if any("if" in cl and "len" in cl for cl in context_lines):
                            continue
                    findings.append(self._make_finding(
                        severity="low" if rule_id == "infinite_loop" else "medium",
                        confidence=0.5,
                        file_path=file_path, line_start=i, line_end=i,
                        description=desc,
                        evidence={"line": stripped},
                        recommendation=f"Add boundary check for {rule_id} case",
                        rule_id=f"correctness.{rule_id}",
                    ))
        return findings

    def _check_state_consistency(self, file_path: str, lines: list[str]) -> list:
        findings = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pattern, rule_id, desc in self.RACE_CONDITION_PATTERNS:
                if re.search(pattern, line):
                    findings.append(self._make_finding(
                        severity="low", confidence=0.4,
                        file_path=file_path, line_start=i, line_end=i,
                        description=desc,
                        evidence={"line": stripped},
                        recommendation="Consider thread/async safety for shared state",
                        rule_id=f"correctness.{rule_id}",
                    ))
        return findings
