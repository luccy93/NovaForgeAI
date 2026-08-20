"""AI Software Quality Engine -- Code Smells Analyzer (Volume 48).

Detects large functions, god classes, high complexity, deep nesting,
excessive parameters, duplicate patterns.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from app.quality.analyzers.base import AnalyzerResult, BaseAnalyzer, ReviewContext


class CodeSmellAnalyzer(BaseAnalyzer):
    name = "code_smells"
    category = "maintainability"

    COMPLEXITY_KEYWORDS = {
        "if", "elif", "else", "for", "while", "except", "except",
        "and", "or", "in", "not", "is", "with", "assert",
        "raise", "yield", "await", "?:", "&&", "||",
    }

    async def analyze(self, context: ReviewContext) -> AnalyzerResult:
        findings = []
        for file_path, content in context.file_contents.items():
            if not self._is_changed_file(file_path, context):
                continue
            if not file_path.endswith(".py"):
                continue
            lines = content.split("\n")
            findings.extend(self._check_long_functions(file_path, lines))
            findings.extend(self._check_large_classes(file_path, lines))
            findings.extend(self._check_complexity(file_path, lines))
            findings.extend(self._check_deep_nesting(file_path, lines))
            findings.extend(self._check_duplicate_patterns(file_path, lines))
        return AnalyzerResult(analyzer_name=self.name, findings=findings)

    def _check_long_functions(self, file_path: str, lines: list[str]) -> list:
        findings = []
        func_start = -1
        func_name = ""
        func_indent = 0

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            current_indent = len(line) - len(line.lstrip())
            if re.match(r"(?:async\s+)?def\s+\w+", stripped):
                if func_start >= 0:
                    length = i - func_start
                    if length > 50:
                        findings.append(self._make_finding(
                            severity="medium" if length > 80 else "low",
                            confidence=0.8,
                            file_path=file_path, line_start=func_start + 1, line_end=i,
                            description=f"Function '{func_name}' is {length} lines long",
                            evidence={"function": func_name, "line_count": length},
                            recommendation="Extract sub-functions or use helper methods",
                            rule_id="code_smells.long_function",
                        ))
                func_start = i
                func_name = stripped.split("(")[0].replace("async def ", "").replace("def ", "")
                func_indent = current_indent
            elif func_start >= 0 and current_indent <= func_indent and stripped:
                length = i - func_start
                if length > 50:
                    findings.append(self._make_finding(
                        severity="medium" if length > 80 else "low",
                        confidence=0.8,
                        file_path=file_path, line_start=func_start + 1, line_end=i,
                        description=f"Function '{func_name}' is {length} lines long",
                        evidence={"function": func_name, "line_count": length},
                        recommendation="Extract sub-functions or use helper methods",
                        rule_id="code_smells.long_function",
                    ))
                func_start = -1

        if func_start >= 0:
            length = len(lines) - func_start
            if length > 50:
                findings.append(self._make_finding(
                    severity="medium" if length > 80 else "low",
                    confidence=0.8,
                    file_path=file_path, line_start=func_start + 1, line_end=len(lines),
                    description=f"Function '{func_name}' is {length} lines long",
                    evidence={"function": func_name, "line_count": length},
                    recommendation="Extract sub-functions or use helper methods",
                    rule_id="code_smells.long_function",
                ))
        return findings

    def _check_large_classes(self, file_path: str, lines: list[str]) -> list:
        findings = []
        class_start = -1
        class_name = ""
        method_count = 0
        line_count = 0

        for i, line in enumerate(lines):
            stripped = line.strip()
            if re.match(r"class\s+\w+", stripped):
                if class_start >= 0 and method_count > 10:
                    findings.append(self._make_finding(
                        severity="medium" if method_count > 20 else "low",
                        confidence=0.7,
                        file_path=file_path, line_start=class_start + 1, line_end=i,
                        description=f"Class '{class_name}' has {method_count} methods ({line_count} lines)",
                        evidence={"class": class_name, "methods": method_count, "lines": line_count},
                        recommendation="Split into smaller, focused classes (Single Responsibility)",
                        rule_id="code_smells.god_class",
                    ))
                class_start = i
                class_name = stripped.split("(")[0].split(":")[0].replace("class ", "")
                method_count = 0
                line_count = 0
            elif class_start >= 0:
                line_count += 1
                if re.match(r"(?:async\s+)?def\s+", stripped):
                    method_count += 1
        return findings

    def _check_complexity(self, file_path: str, lines: list[str]) -> list:
        findings = []
        func_start = -1
        func_name = ""
        func_indent = 0
        complexity = 1

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            current_indent = len(line) - len(line.lstrip())
            if re.match(r"(?:async\s+)?def\s+\w+", stripped):
                if func_start >= 0 and complexity > 10:
                    findings.append(self._make_finding(
                        severity="medium" if complexity > 15 else "low",
                        confidence=0.7,
                        file_path=file_path, line_start=func_start + 1, line_end=i,
                        description=f"Function '{func_name}' has cyclomatic complexity {complexity}",
                        evidence={"function": func_name, "complexity": complexity},
                        recommendation="Reduce complexity by extracting conditions into helper functions",
                        rule_id="code_smells.high_complexity",
                    ))
                func_start = i
                func_name = stripped.split("(")[0].replace("async def ", "").replace("def ", "")
                func_indent = current_indent
                complexity = 1
            elif func_start >= 0:
                if current_indent > func_indent:
                    words = set(re.findall(r"\b(\w+)\b", stripped))
                    complexity += len(words & self.COMPLEXITY_KEYWORDS)
                elif current_indent <= func_indent and stripped:
                    if complexity > 10:
                        findings.append(self._make_finding(
                            severity="medium" if complexity > 15 else "low",
                            confidence=0.7,
                            file_path=file_path, line_start=func_start + 1, line_end=i,
                            description=f"Function '{func_name}' has cyclomatic complexity {complexity}",
                            evidence={"function": func_name, "complexity": complexity},
                            recommendation="Reduce complexity by extracting conditions into helper functions",
                            rule_id="code_smells.high_complexity",
                        ))
                    func_start = -1
        return findings

    def _check_deep_nesting(self, file_path: str, lines: list[str]) -> list:
        findings = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue
            indent = len(line) - len(line.lstrip())
            depth = indent // 4
            if depth > 4:
                findings.append(self._make_finding(
                    severity="medium" if depth > 5 else "low",
                    confidence=0.7,
                    file_path=file_path, line_start=i, line_end=i,
                    description=f"Deep nesting (depth {depth}) — code is hard to follow",
                    evidence={"line": stripped[:80], "depth": depth},
                    recommendation="Extract nested logic into separate functions or use early returns",
                    rule_id="code_smells.deep_nesting",
                ))
        return findings

    def _check_duplicate_patterns(self, file_path: str, lines: list[str]) -> list:
        findings = []
        blocks: Counter[str] = Counter()
        block_lines: dict[str, list[int]] = {}
        window = 4
        for i in range(len(lines) - window):
            block = "\n".join(line.strip() for line in lines[i:i + window] if line.strip())
            if len(block) > 30:
                blocks[block] += 1
                if block not in block_lines:
                    block_lines[block] = []
                block_lines[block].append(i + 1)

        for block, count in blocks.items():
            if count >= 3:
                start_line = block_lines[block][0]
                findings.append(self._make_finding(
                    severity="low", confidence=0.5,
                    file_path=file_path, line_start=start_line, line_end=start_line + window,
                    description=f"Code pattern duplicated {count} times",
                    evidence={"duplicate_count": count, "sample": block[:120]},
                    recommendation="Extract duplicated logic into a shared function",
                    rule_id="code_smells.duplicate_pattern",
                ))
        return findings
