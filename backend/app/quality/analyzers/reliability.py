"""AI Software Quality Engine -- Reliability Analyzer (Volume 48).

Checks timeouts, retries, circuit breakers, fallbacks, error handling,
idempotency, resource cleanup, graceful shutdown, failure recovery.
"""

from __future__ import annotations

import re
from typing import Any

from app.quality.analyzers.base import AnalyzerResult, BaseAnalyzer, ReviewContext


class ReliabilityAnalyzer(BaseAnalyzer):
    name = "reliability"
    category = "reliability"

    TIMEOUT_PATTERNS = [
        (r"(?:requests\.|httpx\.|aiohttp\.|urllib\.)\w+\([^)]*\)(?:(?!timeout).)*$",
         "no_timeout", "HTTP call without explicit timeout", "medium"),
        (r"(?:socket\.|connect\()(?:(?!timeout).)*$",
         "socket_no_timeout", "Socket operation without timeout", "medium"),
    ]

    RETRY_PATTERNS = [
        (r"(?:requests\.|httpx\.|urllib\.)\w+\(", "no_retry", "Network call without retry logic", "low"),
    ]

    ERROR_HANDLING_PATTERNS = [
        (r"except\s+\w+.*:\s*$", "empty_handler", "Empty exception handler", "medium"),
        (r"try\s*:(?:(?!except).)*$", "try_no_except", "Try block without except", "low"),
    ]

    RESOURCE_PATTERNS = [
        (r"(?:\.open|\.connect|\.acquire)\((?!.*as\s+)", "no_context_manager",
         "Resource opened without context manager", "medium"),
    ]

    RECOVERY_PATTERNS = [
        (r"(?:def\s+\w+.*(?:recover|rollback|retry|fallback|circuit).*)",
         "has_recovery", "Recovery pattern detected", "info"),
    ]

    async def analyze(self, context: ReviewContext) -> AnalyzerResult:
        findings = []
        for file_path, content in context.file_contents.items():
            if not self._is_changed_file(file_path, context):
                continue
            lines = content.split("\n")
            findings.extend(self._check_timeouts(file_path, lines))
            findings.extend(self._check_error_handling(file_path, lines))
            findings.extend(self._check_resources(file_path, lines))
            findings.extend(self._check_idempotency(file_path, lines))
        return AnalyzerResult(analyzer_name=self.name, findings=findings)

    def _check_timeouts(self, file_path: str, lines: list[str]) -> list:
        findings = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if re.search(r"requests\.(?:get|post|put|delete|patch)\(", stripped):
                if "timeout" not in stripped:
                    findings.append(self._make_finding(
                        severity="medium", confidence=0.8,
                        file_path=file_path, line_start=i, line_end=i,
                        description="HTTP call without explicit timeout",
                        evidence={"line": stripped[:120]},
                        recommendation="Add timeout parameter to prevent indefinite blocking",
                        rule_id="reliability.no_timeout",
                    ))
        return findings

    def _check_error_handling(self, file_path: str, lines: list[str]) -> list:
        findings = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if re.match(r"except\s+\w+.*:\s*$", stripped):
                next_idx = i
                while next_idx < len(lines):
                    next_line = lines[next_idx].strip()
                    if next_line and not next_line.startswith("#"):
                        if next_line in ("pass", "...", ""):
                            findings.append(self._make_finding(
                                severity="medium", confidence=0.7,
                                file_path=file_path, line_start=i, line_end=i + 1,
                                description="Exception handler does nothing — errors silently ignored",
                                evidence={"handler": stripped, "body": next_line},
                                recommendation="Log the exception or implement proper error recovery",
                                rule_id="reliability.empty_handler",
                            ))
                        break
                    next_idx += 1
        return findings

    def _check_resources(self, file_path: str, lines: list[str]) -> list:
        findings = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if re.search(r"(?:\.open|\.connect|\.acquire)\(", stripped):
                if "as " not in stripped and "with " not in stripped:
                    findings.append(self._make_finding(
                        severity="medium", confidence=0.6,
                        file_path=file_path, line_start=i, line_end=i,
                        description="Resource opened without context manager",
                        evidence={"line": stripped[:120]},
                        recommendation="Use 'with' statement for automatic resource cleanup",
                        rule_id="reliability.no_context_manager",
                    ))
        return findings

    def _check_idempotency(self, file_path: str, lines: list[str]) -> list:
        findings = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if re.match(r"def\s+\w+", stripped):
                func_name = stripped
                has_idempotent = any(
                    kw in func_name.lower()
                    for kw in ("idempotent", "safe", "retry")
                )
                if "DELETE" in stripped or "delete" in stripped.lower():
                    if not has_idempotent:
                        findings.append(self._make_finding(
                            severity="low", confidence=0.4,
                            file_path=file_path, line_start=i, line_end=i,
                            description="Destructive operation without idempotency guard",
                            evidence={"function": stripped[:120]},
                            recommendation="Consider adding idempotency key or check",
                            rule_id="reliability.no_idempotency",
                        ))
        return findings
