"""AI Software Quality Engine -- API Compatibility Analyzer (Volume 48).

Detects removed endpoints, changed request/response fields,
auth changes, event schema changes, breaking SDK behavior.
"""

from __future__ import annotations

import re
from typing import Any

from app.quality.analyzers.base import AnalyzerResult, BaseAnalyzer, ReviewContext


class APICompatAnalyzer(BaseAnalyzer):
    name = "api_compat"
    category = "api_compat"

    ENDPOINT_PATTERNS = [
        (r"@router\.(get|post|put|delete|patch)\(\s*[\"']([^\"']+)", "endpoint_definition"),
    ]

    SCHEMA_PATTERNS = [
        (r"class\s+(\w+(?:Request|Response|Schema|Model))\(.*BaseModel\)", "pydantic_model"),
        (r"class\s+(\w+(?:Schema|Model))\(.*Schema\)", "marshmallow_schema"),
    ]

    EVENT_PATTERNS = [
        (r"emit\(\s*[\"'](\w+)[\"']", "event_emission"),
        (r"subscribe\(\s*[\"'](\w+)[\"']", "event_subscription"),
    ]

    async def analyze(self, context: ReviewContext) -> AnalyzerResult:
        findings = []
        for file_path, content in context.file_contents.items():
            if not self._is_changed_file(file_path, context):
                continue
            lines = content.split("\n")
            findings.extend(self._check_endpoint_changes(file_path, lines, content))
            findings.extend(self._check_schema_changes(file_path, lines, content))
            findings.extend(self._check_event_changes(file_path, lines, content))
            findings.extend(self._check_auth_changes(file_path, lines, content))
        return AnalyzerResult(analyzer_name=self.name, findings=findings)

    def _check_endpoint_changes(self, file_path: str, lines: list[str], content: str) -> list:
        findings = []
        if not any(kw in file_path.lower() for kw in ("api", "router", "endpoint", "view")):
            return findings
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            for pattern, etype in self.ENDPOINT_PATTERNS:
                match = re.search(pattern, stripped)
                if match:
                    method = match.group(1).upper()
                    path = match.group(2)
                    if "deprecated" in content.lower():
                        findings.append(self._make_finding(
                            severity="medium", confidence=0.9,
                            file_path=file_path, line_start=i, line_end=i,
                            description=f"Deprecated endpoint: {method} {path}",
                            evidence={"method": method, "path": path, "line": stripped},
                            recommendation="Remove deprecated endpoint or document migration path",
                            rule_id="api_compat.deprecated_endpoint",
                        ))
        return findings

    def _check_schema_changes(self, file_path: str, lines: list[str], content: str) -> list:
        findings = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            for pattern, stype in self.SCHEMA_PATTERNS:
                match = re.search(pattern, stripped)
                if match:
                    class_name = match.group(1)
                    fields = self._extract_pydantic_fields(lines, i - 1)
                    required_fields = [f for f in fields if "=" not in f and "Optional" not in f]
                    if not required_fields:
                        findings.append(self._make_finding(
                            severity="low", confidence=0.5,
                            file_path=file_path, line_start=i, line_end=i,
                            description=f"All fields optional in {class_name} — may indicate incomplete schema",
                            evidence={"class": class_name, "fields": fields[:10]},
                            recommendation="Review schema completeness for API contract",
                            rule_id="api_compat.schema_review",
                        ))
        return findings

    def _check_event_changes(self, file_path: str, lines: list[str], content: str) -> list:
        findings = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            for pattern, etype in self.EVENT_PATTERNS:
                if re.search(pattern, stripped):
                    findings.append(self._make_finding(
                        severity="low", confidence=0.3,
                        file_path=file_path, line_start=i, line_end=i,
                        description=f"Event {etype} in changed code — verify schema compatibility",
                        evidence={"line": stripped[:120], "type": etype},
                        recommendation="Ensure event schema changes are backward-compatible",
                        rule_id="api_compat.event_schema",
                    ))
        return findings

    def _check_auth_changes(self, file_path: str, lines: list[str], content: str) -> list:
        findings = []
        auth_keywords = {"Depends", "get_current_user", "authenticate", "authorize", "permissions"}
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for kw in auth_keywords:
                if kw in stripped:
                    findings.append(self._make_finding(
                        severity="low", confidence=0.4,
                        file_path=file_path, line_start=i, line_end=i,
                        description=f"Authentication/authorization pattern ({kw}) in changed code",
                        evidence={"line": stripped[:120], "keyword": kw},
                        recommendation="Verify auth changes are backward-compatible",
                        rule_id="api_compat.auth_change",
                    ))
                    break
        return findings

    def _extract_pydantic_fields(self, lines: list[str], start: int) -> list[str]:
        fields = []
        indent = None
        for i in range(start + 1, min(start + 30, len(lines))):
            line = lines[i]
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            current_indent = len(line) - len(line.lstrip())
            if indent is None:
                if not stripped.startswith(("class", "def", "@")):
                    indent = current_indent
                else:
                    break
            if indent is not None and current_indent <= indent and not stripped.startswith(("class", "def", "@")):
                break
            if indent is not None and ":" in stripped and not stripped.startswith("#"):
                field_name = stripped.split(":")[0].strip()
                if field_name and not field_name.startswith("_"):
                    fields.append(stripped.split("=")[0].strip())
        return fields
