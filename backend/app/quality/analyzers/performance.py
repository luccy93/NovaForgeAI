"""AI Software Quality Engine -- Performance Analyzer (Volume 48).

Detects N+1 queries, unbounded loops, large allocations, inefficient algorithms,
blocking operations, cache misuse, and database bottlenecks.
"""

from __future__ import annotations

import re
from typing import Any

from app.quality.analyzers.base import AnalyzerResult, BaseAnalyzer, ReviewContext


class PerformanceAnalyzer(BaseAnalyzer):
    name = "performance"
    category = "performance"

    N_PLUS_ONE_PATTERNS = [
        (r"for\s+\w+\s+in\s+.*:\s*\n(?:\s+.*\n)*?\s+.*(?:\.query|\.filter|\.get|session\.|db\.)",
         "n_plus_one_query", "Query inside loop — potential N+1 query problem", "high"),
    ]

    UNBOUNDED_PATTERNS = [
        (r"while\s+True\s*:", "unbounded_loop", "Unbounded loop — ensure termination condition", "medium"),
        (r"for\s+\w+\s+in\s+\w+\.items\(\)\s*:\s*\n(?:\s+.*\n)*?\s+.*append",
         "loop_append", "Appending to list in loop — consider list comprehension or generator", "low"),
    ]

    ALLOCATION_PATTERNS = [
        (r"\[\s*\w+\s+for\s+.*\s+in\s+.*\s+for\s+.*\s+in\s+", "nested_comprehension",
         "Deeply nested list comprehension — high memory allocation", "medium"),
    ]

    BLOCKING_PATTERNS = [
        (r"(?:^|\s)(?:requests\.|urllib\.|http\.client\.)", "sync_http",
         "Synchronous HTTP call in potentially async context", "medium"),
        (r"time\.sleep\(", "blocking_sleep", "time.sleep() blocks the event loop in async code", "medium"),
        (r"(?:\.write|\.read|\.flush|\.close)\(", "sync_io",
         "Synchronous I/O operation — consider async alternatives", "low"),
    ]

    DB_PATTERNS = [
        (r"SELECT\s+\*\s+FROM", "select_star", "SELECT * retrieves all columns — specify needed columns", "medium"),
        (r"\.all\(\)", "fetch_all", "Fetching all results — consider pagination or .limit()", "low"),
        (r"(?:\.query|\.filter)\(.*\)(?:(?!\.limit|\.first|\.one|\.count).)*$",
         "no_limit", "Query without LIMIT — may return unbounded results", "medium"),
    ]

    CACHE_PATTERNS = [
        (r"(?:def\s+\w+.*(?:get|fetch|load|read).*(?:cache|cached).*)"
         r"|(?:\w+\s*=\s*(?:redis|memcache|cache)\.)",
         "cache_usage", "Cache usage pattern detected — verify TTL and invalidation", "info"),
    ]

    async def analyze(self, context: ReviewContext) -> AnalyzerResult:
        findings = []
        for file_path, content in context.file_contents.items():
            if not self._is_changed_file(file_path, context):
                continue
            lines = content.split("\n")
            findings.extend(self._check_n_plus_one(file_path, lines))
            findings.extend(self._check_unbounded(file_path, lines))
            findings.extend(self._check_allocations(file_path, lines))
            findings.extend(self._check_blocking(file_path, lines))
            findings.extend(self._check_db_patterns(file_path, lines))
        return AnalyzerResult(analyzer_name=self.name, findings=findings)

    def _check_n_plus_one(self, file_path: str, lines: list[str]) -> list:
        findings = []
        for i, line in enumerate(lines):
            if re.search(r"for\s+\w+\s+in\s+", line):
                indent = len(line) - len(line.lstrip())
                for j in range(i + 1, min(i + 10, len(lines))):
                    inner = lines[j]
                    inner_indent = len(inner) - len(inner.lstrip())
                    if inner_indent <= indent and inner.strip():
                        break
                    if re.search(r"\.(?:query|filter|get|find|select|count|session|db)\.", inner):
                        findings.append(self._make_finding(
                            severity="high", confidence=0.75,
                            file_path=file_path, line_start=i + 1, line_end=j + 1,
                            description="Query inside loop — potential N+1 query problem",
                            evidence={"loop_line": line.strip(), "query_line": inner.strip()},
                            recommendation="Batch queries outside the loop or use eager loading",
                            rule_id="performance.n_plus_one_query",
                        ))
                        break
        return findings

    def _check_unbounded(self, file_path: str, lines: list[str]) -> list:
        findings = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if re.search(r"while\s+True\s*:", stripped):
                has_break = False
                for j in range(i, min(i + 20, len(lines))):
                    if "break" in lines[j] or "return" in lines[j]:
                        has_break = True
                        break
                if not has_break:
                    findings.append(self._make_finding(
                        severity="high", confidence=0.7,
                        file_path=file_path, line_start=i, line_end=i,
                        description="Infinite loop without break or return",
                        evidence={"line": stripped},
                        recommendation="Add termination condition, break, or return statement",
                        rule_id="performance.unbounded_loop",
                    ))
        return findings

    def _check_allocations(self, file_path: str, lines: list[str]) -> list:
        findings = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            depth = stripped.count(" for ") + stripped.count(" in ")
            if depth >= 3 and "[" in stripped:
                findings.append(self._make_finding(
                    severity="medium", confidence=0.6,
                    file_path=file_path, line_start=i, line_end=i,
                    description="Deeply nested comprehension — high memory allocation",
                    evidence={"line": stripped[:120]},
                    recommendation="Consider breaking into smaller operations or using generators",
                    rule_id="performance.nested_comprehension",
                ))
        return findings

    def _check_blocking(self, file_path: str, lines: list[str]) -> list:
        findings = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if re.search(r"time\.sleep\(", stripped):
                findings.append(self._make_finding(
                    severity="medium", confidence=0.8,
                    file_path=file_path, line_start=i, line_end=i,
                    description="time.sleep() blocks the event loop in async code",
                    evidence={"line": stripped},
                    recommendation="Use asyncio.sleep() in async contexts",
                    rule_id="performance.blocking_sleep",
                ))
            if re.search(r"requests\.(?:get|post|put|delete|patch)\(", stripped):
                findings.append(self._make_finding(
                    severity="medium", confidence=0.7,
                    file_path=file_path, line_start=i, line_end=i,
                    description="Synchronous HTTP call — may block event loop",
                    evidence={"line": stripped[:120]},
                    recommendation="Use httpx async client or aiohttp in async contexts",
                    rule_id="performance.sync_http",
                ))
        return findings

    def _check_db_patterns(self, file_path: str, lines: list[str]) -> list:
        findings = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if re.search(r"SELECT\s+\*\s+FROM", stripped, re.IGNORECASE):
                findings.append(self._make_finding(
                    severity="medium", confidence=0.8,
                    file_path=file_path, line_start=i, line_end=i,
                    description="SELECT * retrieves all columns",
                    evidence={"line": stripped[:120]},
                    recommendation="Specify only needed columns to reduce data transfer",
                    rule_id="performance.select_star",
                ))
            if re.search(r"\.all\(\)", stripped):
                findings.append(self._make_finding(
                    severity="low", confidence=0.5,
                    file_path=file_path, line_start=i, line_end=i,
                    description="Fetching all results without limit",
                    evidence={"line": stripped},
                    recommendation="Consider adding .limit() or using pagination",
                    rule_id="performance.fetch_all",
                ))
        return findings
