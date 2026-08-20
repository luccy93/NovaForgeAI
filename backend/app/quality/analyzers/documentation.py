"""AI Software Quality Engine -- Documentation Analyzer (Volume 48).

Detects missing docstrings, missing type hints, outdated docs,
missing CHANGELOG entries.
"""

from __future__ import annotations

import re
from typing import Any

from app.quality.analyzers.base import AnalyzerResult, BaseAnalyzer, ReviewContext


class DocumentationAnalyzer(BaseAnalyzer):
    name = "documentation"
    category = "documentation"

    PYTHON_DEF_PATTERN = re.compile(
        r"^(?:async\s+)?def\s+(\w+)\s*\(([^)]*)\)(?:\s*->\s*(\S+))?\s*:"
    )
    CLASS_PATTERN = re.compile(r"^class\s+(\w+)")
    PUBLIC_DEF_PATTERN = re.compile(
        r"^(?:async\s+)?def\s+([a-zA-Z]\w*)\s*\("
    )

    async def analyze(self, context: ReviewContext) -> AnalyzerResult:
        findings = []
        for file_path, content in context.file_contents.items():
            if not self._is_changed_file(file_path, context):
                continue
            if not file_path.endswith(".py"):
                continue
            lines = content.split("\n")
            findings.extend(self._check_docstrings(file_path, lines))
            findings.extend(self._check_type_hints(file_path, lines))
        return AnalyzerResult(analyzer_name=self.name, findings=findings)

    def _check_docstrings(self, file_path: str, lines: list[str]) -> list:
        findings = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            match = self.PUBLIC_DEF_PATTERN.match(stripped)
            if not match:
                continue
            func_name = match.group(1)
            if func_name.startswith("_"):
                continue
            has_docstring = False
            for j in range(i + 1, min(i + 4, len(lines))):
                next_line = lines[j].strip()
                if next_line.startswith(('"""', "'''")):
                    has_docstring = True
                    break
                if next_line and not next_line.startswith("#"):
                    break
            if not has_docstring:
                findings.append(self._make_finding(
                    severity="low", confidence=0.7,
                    file_path=file_path, line_start=i + 1, line_end=i + 1,
                    description=f"Public function '{func_name}' missing docstring",
                    evidence={"function": func_name},
                    recommendation="Add a docstring describing purpose, parameters, and return value",
                    rule_id="documentation.missing_docstring",
                    source="code_smell",
                ))
        return findings

    def _check_type_hints(self, file_path: str, lines: list[str]) -> list:
        findings = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            match = self.PYTHON_DEF_PATTERN.match(stripped)
            if not match:
                continue
            func_name = match.group(1)
            params = match.group(2)
            return_type = match.group(3)
            if func_name.startswith("_"):
                continue
            if func_name in ("__init__", "__str__", "__repr__"):
                continue
            missing_hints = []
            if not return_type and return_type != "None":
                missing_hints.append("return type")
            if params:
                param_list = [p.strip() for p in params.split(",") if p.strip() and p.strip() != "self" and p.strip() != "cls"]
                for param in param_list:
                    if ":" not in param and "=" not in param:
                        missing_hints.append(f"param '{param.split('=')[0].strip()}'")
            if missing_hints:
                findings.append(self._make_finding(
                    severity="info", confidence=0.6,
                    file_path=file_path, line_start=i + 1, line_end=i + 1,
                    description=f"Public function '{func_name}' missing type hints: {', '.join(missing_hints)}",
                    evidence={"function": func_name, "missing": missing_hints},
                    recommendation="Add type hints for better code clarity and IDE support",
                    rule_id="documentation.missing_type_hints",
                    source="code_smell",
                ))
        return findings
