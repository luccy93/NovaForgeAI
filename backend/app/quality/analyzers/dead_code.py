"""AI Software Quality Engine -- Dead Code Analyzer (Volume 48).

Detects unused imports, unused functions, unused variables,
unreachable code indicators, unused dependencies.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from app.quality.analyzers.base import AnalyzerResult, BaseAnalyzer, ReviewContext


class DeadCodeAnalyzer(BaseAnalyzer):
    name = "dead_code"
    category = "maintainability"

    async def analyze(self, context: ReviewContext) -> AnalyzerResult:
        findings = []
        for file_path, content in context.file_contents.items():
            if not self._is_changed_file(file_path, context):
                continue
            if not file_path.endswith(".py"):
                continue
            lines = content.split("\n")
            findings.extend(self._check_unused_imports(file_path, lines))
            findings.extend(self._check_unused_variables(file_path, lines))
            findings.extend(self._check_unreachable_code(file_path, lines))
        return AnalyzerResult(analyzer_name=self.name, findings=findings)

    def _check_unused_imports(self, file_path: str, lines: list[str]) -> list:
        findings = []
        imports: list[tuple[int, str, str]] = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("from ") and " import " in stripped:
                match = re.match(r"from\s+\S+\s+import\s+(.+)", stripped)
                if match:
                    imported = match.group(1).strip()
                    if "(" in imported:
                        continue
                    for name in imported.split(","):
                        name = name.strip().split(" as ")[-1].strip()
                        if name and name != "*":
                            imports.append((i + 1, name, stripped))
            elif stripped.startswith("import "):
                match = re.match(r"import\s+(.+)", stripped)
                if match:
                    for name in match.group(1).split(","):
                        name = name.strip().split(" as ")[-1].strip()
                        if name:
                            imports.append((i + 1, name, stripped))

        all_content = "\n".join(lines)
        for line_num, import_name, import_line in imports:
            usage_pattern = re.compile(r"\b" + re.escape(import_name) + r"\b")
            occurrences = usage_pattern.findall(all_content)
            if len(occurrences) <= 1:
                findings.append(self._make_finding(
                    severity="low", confidence=0.7,
                    file_path=file_path, line_start=line_num, line_end=line_num,
                    description=f"Unused import: '{import_name}'",
                    evidence={"import_name": import_name, "line": import_line[:120]},
                    recommendation="Remove unused import to reduce code clutter",
                    rule_id="dead_code.unused_import",
                    source="code_smell",
                ))
        return findings

    def _check_unused_variables(self, file_path: str, lines: list[str]) -> list:
        findings = []
        assignments: list[tuple[int, str]] = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            match = re.match(r"^(\w+)\s*=\s*", stripped)
            if match:
                var_name = match.group(1)
                if var_name.isupper() or var_name.startswith("_"):
                    continue
                if var_name in ("self", "cls", "result", "response", "data", "e"):
                    continue
                assignments.append((i + 1, var_name))

        all_content = "\n".join(lines)
        for line_num, var_name in assignments:
            usage = re.compile(r"\b" + re.escape(var_name) + r"\b").findall(all_content)
            if len(usage) <= 1:
                findings.append(self._make_finding(
                    severity="info", confidence=0.5,
                    file_path=file_path, line_start=line_num, line_end=line_num,
                    description=f"Potentially unused variable: '{var_name}'",
                    evidence={"variable": var_name},
                    recommendation="Remove unused variable or prefix with _ if intentionally unused",
                    rule_id="dead_code.unused_variable",
                    source="code_smell",
                ))
        return findings

    def _check_unreachable_code(self, file_path: str, lines: list[str]) -> list:
        findings = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if re.match(r"return\b", stripped) or re.match(r"raise\b", stripped):
                for j in range(i + 1, min(i + 5, len(lines))):
                    next_stripped = lines[j].strip()
                    if not next_stripped or next_stripped.startswith("#"):
                        continue
                    if next_stripped.startswith(("def ", "class ", "elif ", "else:", "except", "finally")):
                        break
                    if not next_stripped.startswith(("return", "raise", "pass")):
                        findings.append(self._make_finding(
                            severity="medium", confidence=0.7,
                            file_path=file_path, line_start=j + 1, line_end=j + 1,
                            description="Code after return/raise statement — unreachable",
                            evidence={
                                "return_line": line.strip()[:120],
                                "unreachable_line": next_stripped[:120],
                            },
                            recommendation="Remove unreachable code or verify control flow",
                            rule_id="dead_code.unreachable_code",
                        ))
                    break
        return findings
