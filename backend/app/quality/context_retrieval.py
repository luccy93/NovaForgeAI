"""AI Software Quality Engine -- Context Retrieval (Volume 48).

Assembles ReviewContext from V42 code index, V43 RAG, V47 security,
and git diff.
"""

from __future__ import annotations

from typing import Any

from app.quality.analyzers.base import ReviewContext
from app.quality.diff_parser import DiffParser


class ContextBuilder:
    """Build ReviewContext from available codebase data."""

    def __init__(self):
        self.diff_parser = DiffParser()

    def build_from_files(
        self,
        tenant: str,
        repo_id: str,
        file_contents: dict[str, str],
        changed_files: list[str] | None = None,
        diff_text: str = "",
        mode: str = "standard",
    ) -> ReviewContext:
        languages: dict[str, str] = {}
        for fp in file_contents:
            languages[fp] = self.diff_parser._detect_language(fp)

        changeset = self.diff_parser.parse_diff_text(diff_text) if diff_text else None
        if changeset and not changed_files:
            changed_files = changeset.changed_files

        return ReviewContext(
            tenant=tenant,
            repo_id=repo_id,
            file_contents=file_contents,
            changed_files=changed_files or list(file_contents.keys()),
            diff_text=diff_text,
            languages=languages,
            review_mode=mode,
        )

    def build_from_code_intelligence(
        self,
        tenant: str,
        repo_id: str,
        code_index: dict[str, Any],
        architecture: dict[str, Any] | None = None,
        symbols: list[dict[str, Any]] | None = None,
        dependencies: list[dict[str, Any]] | None = None,
        tests: list[dict[str, Any]] | None = None,
        changed_files: list[str] | None = None,
        file_contents: dict[str, str] | None = None,
        mode: str = "standard",
    ) -> ReviewContext:
        return ReviewContext(
            tenant=tenant,
            repo_id=repo_id,
            file_contents=file_contents or {},
            changed_files=changed_files or [],
            architecture=architecture or code_index.get("architecture", {}),
            symbols=symbols or code_index.get("symbols", []),
            dependencies=dependencies or code_index.get("dependencies", []),
            tests=tests or code_index.get("tests", []),
            config=code_index.get("config", {}),
            review_mode=mode,
        )

    def enrich_with_rag(
        self, context: ReviewContext, rag_results: list[dict[str, Any]]
    ) -> ReviewContext:
        context.metadata_extra = getattr(context, "metadata_extra", {})
        if not hasattr(context, "metadata_extra"):
            context.metadata_extra = {}
        context.metadata_extra["rag_context"] = rag_results
        return context

    def enrich_with_security(
        self, context: ReviewContext, security_findings: list[dict[str, Any]]
    ) -> ReviewContext:
        if not hasattr(context, "metadata_extra"):
            context.metadata_extra = {}
        context.metadata_extra["security_findings"] = security_findings
        return context

    def limit_by_budget(self, context: ReviewContext, max_files: int, max_tokens: int) -> ReviewContext:
        if len(context.changed_files) > max_files:
            context.changed_files = context.changed_files[:max_files]
        if len(context.file_contents) > max_files:
            limited: dict[str, str] = {}
            for fp in context.changed_files[:max_files]:
                if fp in context.file_contents:
                    limited[fp] = context.file_contents[fp]
            context.file_contents = limited
        context.budget_files_remaining = max_files
        context.budget_tokens_remaining = max_tokens
        return context
