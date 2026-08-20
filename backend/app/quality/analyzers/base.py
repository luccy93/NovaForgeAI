"""AI Software Quality Engine -- Base Analyzer (Volume 48)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.quality.finding_model import FindingData


@dataclass
class ReviewContext:
    """Context passed to analyzers containing all review information."""

    tenant: str = "default"
    repo_id: str = ""
    file_contents: dict[str, str] = field(default_factory=dict)
    changed_files: list[str] = field(default_factory=list)
    diff_text: str = ""
    languages: dict[str, str] = field(default_factory=dict)
    architecture: dict[str, Any] = field(default_factory=dict)
    symbols: list[dict[str, Any]] = field(default_factory=list)
    dependencies: list[dict[str, Any]] = field(default_factory=list)
    tests: list[dict[str, Any]] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    review_mode: str = "standard"
    budget_tokens_remaining: int = 20000
    budget_files_remaining: int = 50


@dataclass
class AnalyzerResult:
    """Result from a single analyzer run."""

    analyzer_name: str
    findings: list[FindingData] = field(default_factory=list)
    tokens_used: int = 0
    cost_usd: float = 0.0
    duration_ms: int = 0
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseAnalyzer(ABC):
    """Base class for all quality analyzers."""

    name: str = "base"
    category: str = "maintainability"

    @abstractmethod
    async def analyze(self, context: ReviewContext) -> AnalyzerResult:
        """Run analysis and return findings."""
        ...

    def _make_finding(
        self,
        severity: str,
        confidence: float,
        file_path: str,
        line_start: int,
        line_end: int,
        description: str,
        evidence: dict[str, Any] | None = None,
        recommendation: str = "",
        rule_id: str = "",
        symbol: str = "",
        suggestion: str = "",
        source: str = "code_smell",
    ) -> FindingData:
        return FindingData(
            category=self.category,
            severity=severity,
            confidence=confidence,
            file_path=file_path,
            line_start=line_start,
            line_end=line_end,
            symbol=symbol,
            description=description,
            evidence=evidence or {},
            recommendation=recommendation,
            rule_id=rule_id or f"{self.name}.{severity}",
            source=source,
            suggestion=suggestion,
        )

    def _is_changed_file(self, file_path: str, context: ReviewContext) -> bool:
        if not context.changed_files:
            return True
        return file_path in context.changed_files

    def _get_lines(self, file_path: str, context: ReviewContext) -> list[str]:
        content = context.file_contents.get(file_path, "")
        return content.split("\n") if content else []
