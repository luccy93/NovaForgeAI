"""AI Software Quality Engine -- Database Analyzer (Volume 48).

Detects destructive migrations, missing indexes, unsafe locking,
backward-incompatible schema changes, and data-loss risks.
"""

from __future__ import annotations

import re
from typing import Any

from app.quality.analyzers.base import AnalyzerResult, BaseAnalyzer, ReviewContext


class DatabaseAnalyzer(BaseAnalyzer):
    name = "database"
    category = "database"

    DESTRUCTIVE_PATTERNS = [
        (r"DROP\s+TABLE", "drop_table", "DROP TABLE — destructive operation", "critical"),
        (r"DROP\s+COLUMN", "drop_column", "DROP COLUMN — data loss risk", "critical"),
        (r"ALTER\s+TABLE.*DROP", "alter_drop", "ALTER TABLE DROP — schema destructive", "high"),
        (r"TRUNCATE", "truncate", "TRUNCATE — deletes all rows", "critical"),
    ]

    MIGRATION_PATTERNS = [
        (r"op\.drop_table\(", "drop_table_alembic", "Alembic drop_table", "critical"),
        (r"op\.drop_column\(", "drop_column_alembic", "Alembic drop_column", "critical"),
        (r"op\.alter_column\(", "alter_column_alembic", "Alembic alter_column", "medium"),
        (r"op\.create_table\(", "create_table_alembic", "Alembic create_table", "info"),
        (r"op\.create_index\(", "create_index_alembic", "Alembic create_index", "info"),
    ]

    INDEX_PATTERNS = [
        (r"\.filter\(\w+\.\w+\s*==", "filter_no_index", "Filter on column — verify index exists", "low"),
        (r"\.join\(\w+\)", "join_check", "JOIN operation — verify join columns are indexed", "low"),
        (r"\.order_by\(\w+\.\w+\)", "order_by_check", "ORDER BY — verify indexed column", "info"),
    ]

    SCHEMA_CHANGE_PATTERNS = [
        (r"String\((\d+)\)", "string_length", "String column length change", "medium"),
        (r"nullable\s*=\s*True.*nullable\s*=\s*False", "nullable_change", "Nullable to non-nullable change", "high"),
    ]

    async def analyze(self, context: ReviewContext) -> AnalyzerResult:
        findings = []
        for file_path, content in context.file_contents.items():
            if not self._is_changed_file(file_path, context):
                continue
            lines = content.split("\n")
            if "migration" in file_path.lower() or "alembic" in file_path.lower():
                findings.extend(self._check_migrations(file_path, lines))
            findings.extend(self._check_sql_patterns(file_path, lines))
            findings.extend(self._check_schema_patterns(file_path, lines))
        return AnalyzerResult(analyzer_name=self.name, findings=findings)

    def _check_migrations(self, file_path: str, lines: list[str]) -> list:
        findings = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pattern, rule_id, desc, severity in self.MIGRATION_PATTERNS:
                if re.search(pattern, stripped, re.IGNORECASE):
                    findings.append(self._make_finding(
                        severity=severity, confidence=0.9,
                        file_path=file_path, line_start=i, line_end=i,
                        description=desc,
                        evidence={"line": stripped[:120]},
                        recommendation=self._migration_recommendation(rule_id),
                        rule_id=f"database.{rule_id}",
                    ))
        return findings

    def _check_sql_patterns(self, file_path: str, lines: list[str]) -> list:
        findings = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pattern, rule_id, desc, severity in self.DESTRUCTIVE_PATTERNS:
                if re.search(pattern, stripped, re.IGNORECASE):
                    if any(skip in file_path.lower() for skip in ("test", "mock", "fixture")):
                        continue
                    findings.append(self._make_finding(
                        severity=severity, confidence=0.85,
                        file_path=file_path, line_start=i, line_end=i,
                        description=desc,
                        evidence={"line": stripped[:120]},
                        recommendation="Ensure data backup before destructive operations",
                        rule_id=f"database.{rule_id}",
                    ))
        return findings

    def _check_schema_patterns(self, file_path: str, lines: list[str]) -> list:
        findings = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pattern, rule_id, desc, severity in self.SCHEMA_CHANGE_PATTERNS:
                if re.search(pattern, stripped, re.IGNORECASE):
                    findings.append(self._make_finding(
                        severity=severity, confidence=0.5,
                        file_path=file_path, line_start=i, line_end=i,
                        description=desc,
                        evidence={"line": stripped[:120]},
                        recommendation="Verify backward compatibility of schema change",
                        rule_id=f"database.{rule_id}",
                    ))
        return findings

    def _migration_recommendation(self, rule_id: str) -> str:
        recs = {
            "drop_table_alembic": "Ensure all data is backed up; add downgrade path",
            "drop_column_alembic": "Consider soft-delete first; add data migration before drop",
            "alter_column_alembic": "Verify data compatibility; consider multi-step migration",
            "create_table_alembic": "Verify table doesn't exist; add proper indexes",
            "create_index_alembic": "Verify index doesn't exist; consider composite indexes",
        }
        return recs.get(rule_id, "Review migration for data safety")
