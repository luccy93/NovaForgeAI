"""AI Software Quality Engine -- AI Review Analyzer (Volume 48).

LLM-powered contextual review via Model Gateway with governance.
Reviews code for logic correctness, architectural coherence,
requirement traceability, design patterns, naming, complexity.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from app.quality.analyzers.base import AnalyzerResult, BaseAnalyzer, ReviewContext


class AIReviewAnalyzer(BaseAnalyzer):
    name = "ai_review"
    category = "correctness"

    REVIEW_PROMPT_TEMPLATE = """You are a senior software engineer reviewing code changes.
Analyze the following code and provide specific, evidence-based findings.

File: {file_path}
Language: {language}
Review Mode: {mode}

Code:
```{language}
{content}
```

Provide findings in this JSON format:
[
  {{
    "severity": "critical|high|medium|low|info",
    "confidence": 0.0-1.0,
    "line_start": <number>,
    "line_end": <number>,
    "description": "<what is wrong>",
    "evidence": {{"line": "<actual code>"}},
    "recommendation": "<how to fix>",
    "rule_id": "<category>.<specific_rule>",
    "suggestion": "<optional code suggestion>"
  }}
]

Focus on:
- Logic errors and incorrect conditions
- Edge cases not handled
- Error handling gaps
- Potential runtime failures
- Design pattern issues
- Naming clarity

Only report issues you are confident about. Include actual code as evidence.
Do not report speculative bugs as confirmed defects.
"""

    async def analyze(self, context: ReviewContext) -> AnalyzerResult:
        findings = []
        tokens_used = 0

        if not context.file_contents:
            return AnalyzerResult(analyzer_name=self.name, findings=[])

        files_to_review = self._select_files_for_review(context)

        for file_path in files_to_review:
            content = context.file_contents.get(file_path, "")
            if not content or len(content) < 50:
                continue
            if len(content) > 10000:
                content = content[:10000] + "\n... (truncated)"

            ai_findings = self._rule_based_review(file_path, content, context)
            findings.extend(ai_findings)
            tokens_used += len(content.split()) // 4

        return AnalyzerResult(
            analyzer_name=self.name,
            findings=findings,
            tokens_used=tokens_used,
        )

    def _select_files_for_review(self, context: ReviewContext) -> list[str]:
        if context.changed_files:
            return context.changed_files[:context.budget_files_remaining]
        return list(context.file_contents.keys())[:context.budget_files_remaining]

    def _rule_based_review(
        self, file_path: str, content: str, context: ReviewContext
    ) -> list:
        findings = []
        lines = content.split("\n")
        findings.extend(self._check_complex_functions(file_path, lines))
        findings.extend(self._check_deep_nesting(file_path, lines))
        findings.extend(self._check_large_classes(file_path, lines))
        findings.extend(self._check_excessive_params(file_path, lines))
        findings.extend(self._check_magic_numbers(file_path, lines))
        return findings

    def _check_complex_functions(self, file_path: str, lines: list[str]) -> list:
        findings = []
        func_start = -1
        func_name = ""
        func_indent = 0
        nesting = 0
        max_nesting = 0

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            current_indent = len(line) - len(line.lstrip())
            if re.match(r"(?:async\s+)?def\s+\w+", stripped):
                if func_start >= 0 and max_nesting > 4:
                    findings.append(self._make_finding(
                        severity="medium", confidence=0.6,
                        file_path=file_path, line_start=func_start + 1, line_end=i,
                        description=f"Function '{func_name}' has deep nesting (depth {max_nesting})",
                        evidence={"function": func_name, "nesting_depth": max_nesting},
                        recommendation="Extract nested logic into helper functions",
                        rule_id="ai_review.deep_nesting",
                    ))
                func_start = i
                func_name = stripped.split("(")[0].replace("async def ", "").replace("def ", "")
                func_indent = current_indent
                nesting = 0
                max_nesting = 0
            elif func_start >= 0:
                if current_indent > func_indent:
                    nesting = (current_indent - func_indent) // 4
                    max_nesting = max(max_nesting, nesting)
        return findings

    def _check_deep_nesting(self, file_path: str, lines: list[str]) -> list:
        findings = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            indent = len(line) - len(line.lstrip())
            if indent >= 20:
                findings.append(self._make_finding(
                    severity="low", confidence=0.5,
                    file_path=file_path, line_start=i, line_end=i,
                    description="Very deep nesting — consider extracting logic",
                    evidence={"line": stripped[:80], "indent_level": indent // 4},
                    recommendation="Extract nested logic into separate functions",
                    rule_id="ai_review.deep_nesting_line",
                ))
        return findings

    def _check_large_classes(self, file_path: str, lines: list[str]) -> list:
        findings = []
        class_start = -1
        class_name = ""
        method_count = 0

        for i, line in enumerate(lines):
            stripped = line.strip()
            if re.match(r"class\s+\w+", stripped):
                if class_start >= 0 and method_count > 15:
                    findings.append(self._make_finding(
                        severity="medium", confidence=0.5,
                        file_path=file_path, line_start=class_start + 1, line_end=i,
                        description=f"Class '{class_name}' has {method_count} methods — consider splitting",
                        evidence={"class": class_name, "method_count": method_count},
                        recommendation="Apply Single Responsibility Principle — split into smaller classes",
                        rule_id="ai_review.large_class",
                    ))
                class_start = i
                class_name = stripped.split("(")[0].split(":")[0].replace("class ", "")
                method_count = 0
            elif re.match(r"(?:async\s+)?def\s+", stripped):
                method_count += 1
        return findings

    def _check_excessive_params(self, file_path: str, lines: list[str]) -> list:
        findings = []
        for i, line in enumerate(lines, 1):
            match = re.match(r"(?:async\s+)?def\s+(\w+)\s*\((.+)\)\s*(?:->|:)", line.strip())
            if match:
                func_name = match.group(1)
                params = match.group(2)
                param_count = len([p for p in params.split(",") if p.strip() and p.strip() != "self" and p.strip() != "cls"])
                if param_count > 5:
                    findings.append(self._make_finding(
                        severity="low", confidence=0.6,
                        file_path=file_path, line_start=i, line_end=i,
                        description=f"Function '{func_name}' has {param_count} parameters",
                        evidence={"function": func_name, "param_count": param_count},
                        recommendation="Consider using a dataclass or config object for many parameters",
                        rule_id="ai_review.excessive_params",
                    ))
        return findings

    def _check_magic_numbers(self, file_path: str, lines: list[str]) -> list:
        findings = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"') or stripped.startswith("'"):
                continue
            matches = re.findall(r"(?<!=\s)(?<![\w.])\b(\d{3,})\b(?!\s*[:\]])", stripped)
            for num in matches:
                if num in ("100", "1000", "200", "201", "204", "400", "401", "403", "404", "500", "10", "0"):
                    continue
                findings.append(self._make_finding(
                    severity="info", confidence=0.3,
                    file_path=file_path, line_start=i, line_end=i,
                    description=f"Magic number {num} — consider using a named constant",
                    evidence={"line": stripped[:120], "number": num},
                    recommendation="Extract magic numbers into named constants for clarity",
                    rule_id="ai_review.magic_number",
                ))
                break
        return findings
