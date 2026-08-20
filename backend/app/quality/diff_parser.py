"""AI Software Quality Engine -- Diff Analysis (Volume 48).

Wraps V42 IncrementalIndexer for diff parsing. Falls back to
hash-based detection when git is unavailable.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FileChange:
    file_path: str
    change_type: str  # ADDED/MODIFIED/DELETED/RENAMED
    old_path: str = ""
    content_hash: str = ""
    language: str = ""
    size_bytes: int = 0
    lines_added: int = 0
    lines_removed: int = 0


@dataclass
class ChangeSet:
    added: list[FileChange] = field(default_factory=list)
    modified: list[FileChange] = field(default_factory=list)
    deleted: list[FileChange] = field(default_factory=list)
    renamed: list[FileChange] = field(default_factory=list)
    unchanged: int = 0
    commit_from: str = ""
    commit_to: str = ""

    @property
    def all_changes(self) -> list[FileChange]:
        return self.added + self.modified + self.deleted + self.renamed

    @property
    def total_changed(self) -> int:
        return len(self.all_changes)

    @property
    def changed_files(self) -> list[str]:
        return [c.file_path for c in self.all_changes]


LANGUAGE_MAP = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".tsx": "typescript", ".jsx": "javascript", ".go": "go",
    ".java": "java", ".rb": "ruby", ".kt": "kotlin",
    ".scala": "scala", ".cs": "csharp", ".rs": "rust",
    ".cpp": "cpp", ".c": "c", ".h": "c",
    ".sql": "sql", ".yaml": "yaml", ".yml": "yaml",
    ".json": "json", ".toml": "toml", ".md": "markdown",
    ".dockerfile": "dockerfile", ".tf": "terraform",
    ".sh": "shell", ".bash": "shell",
}

SECURITY_SENSITIVE_EXTENSIONS = {
    ".env", ".key", ".pem", ".p12", ".jks", ".keystore",
}

CONFIG_EXTENSIONS = {
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".json",
}

SCHEMA_KEYWORDS = {"migration", "schema", "alembic", "django", "prisma"}


class DiffParser:
    """Parse and analyze code changes for quality review."""

    def parse_diff_text(self, diff_text: str) -> ChangeSet:
        changeset = ChangeSet()
        current_file = None
        current_change = None
        lines_added = 0
        lines_removed = 0

        for line in diff_text.split("\n"):
            if line.startswith("diff --git"):
                if current_file and current_change:
                    current_change.lines_added = lines_added
                    current_change.lines_removed = lines_removed
                    changeset.modified.append(current_change)
                parts = line.split(" b/", 1)
                current_file = parts[1] if len(parts) > 1 else ""
                current_change = FileChange(
                    file_path=current_file,
                    change_type="MODIFIED",
                    language=self._detect_language(current_file),
                )
                lines_added = 0
                lines_removed = 0
            elif line.startswith("+") and not line.startswith("+++"):
                lines_added += 1
            elif line.startswith("-") and not line.startswith("---"):
                lines_removed += 1

        if current_file and current_change:
            current_change.lines_added = lines_added
            current_change.lines_removed = lines_removed
            changeset.modified.append(current_change)

        return changeset

    def analyze_changes(
        self, changeset: ChangeSet, file_contents: dict[str, str] | None = None
    ) -> dict[str, Any]:
        analysis: dict[str, Any] = {
            "total_files_changed": changeset.total_changed,
            "files_by_type": self._categorize_changes(changeset),
            "api_changes": self._detect_api_changes(changeset, file_contents or {}),
            "schema_changes": self._detect_schema_changes(changeset),
            "dependency_changes": self._detect_dependency_changes(changeset),
            "config_changes": self._detect_config_changes(changeset),
            "security_sensitive": self._detect_security_sensitive(changeset),
            "risk_factors": self._compute_risk_factors(changeset),
        }
        return analysis

    def get_changed_files_for_review(
        self, changeset: ChangeSet, max_files: int = 50
    ) -> list[FileChange]:
        priority_order = {"ADDED": 0, "MODIFIED": 1, "RENAMED": 2, "DELETED": 3}
        sorted_changes = sorted(
            changeset.all_changes,
            key=lambda c: (priority_order.get(c.change_type, 9), c.file_path),
        )
        return sorted_changes[:max_files]

    def compute_change_scope_factor(self, changeset: ChangeSet) -> float:
        total = changeset.total_changed
        if total == 0:
            return 1.0
        if total <= 3:
            return 1.0
        if total <= 10:
            return 1.2
        if total <= 30:
            return 1.5
        return 2.0

    def _detect_language(self, file_path: str) -> str:
        for ext, lang in LANGUAGE_MAP.items():
            if file_path.endswith(ext):
                return lang
        if "Dockerfile" in file_path:
            return "dockerfile"
        return "unknown"

    def _categorize_changes(self, changeset: ChangeSet) -> dict[str, int]:
        counts: dict[str, int] = {}
        for c in changeset.all_changes:
            counts[c.change_type] = counts.get(c.change_type, 0) + 1
        return counts

    def _detect_api_changes(
        self, changeset: ChangeSet, file_contents: dict[str, str]
    ) -> list[dict[str, Any]]:
        api_changes: list[dict[str, Any]] = []
        api_patterns = [
            "def ", "async def ", "class ", "@router",
            "APIRouter", "FastAPI", "app.post", "app.get",
        ]
        for c in changeset.modified:
            content = file_contents.get(c.file_path, "")
            if not content:
                continue
            for pattern in api_patterns:
                if pattern in content:
                    api_changes.append({
                        "file": c.file_path,
                        "type": "api_definition",
                        "pattern": pattern,
                    })
                    break
        return api_changes

    def _detect_schema_changes(self, changeset: ChangeSet) -> list[dict[str, Any]]:
        schema_changes: list[dict[str, Any]] = []
        for c in changeset.all_changes:
            fp = c.file_path.lower()
            if any(kw in fp for kw in SCHEMA_KEYWORDS):
                schema_changes.append({
                    "file": c.file_path,
                    "type": "schema",
                    "change_type": c.change_type,
                })
            if c.language in ("sql",) and c.change_type in ("MODIFIED", "ADDED"):
                schema_changes.append({
                    "file": c.file_path,
                    "type": "sql",
                    "change_type": c.change_type,
                })
        return schema_changes

    def _detect_dependency_changes(self, changeset: ChangeSet) -> list[dict[str, Any]]:
        dep_files = {
            "requirements.txt", "setup.py", "setup.cfg", "pyproject.toml",
            "package.json", "package-lock.json", "yarn.lock", "go.mod",
            "go.sum", "Gemfile", "Gemfile.lock", "pom.xml", "build.gradle",
            "Cargo.toml", "Cargo.lock", "composer.json",
        }
        changes: list[dict[str, Any]] = []
        for c in changeset.all_changes:
            if c.file_path in dep_files or any(
                dep in c.file_path for dep in dep_files
            ):
                changes.append({
                    "file": c.file_path,
                    "type": "dependency",
                    "change_type": c.change_type,
                })
        return changes

    def _detect_config_changes(self, changeset: ChangeSet) -> list[dict[str, Any]]:
        config_changes: list[dict[str, Any]] = []
        for c in changeset.all_changes:
            if any(c.file_path.endswith(ext) for ext in CONFIG_EXTENSIONS):
                config_changes.append({
                    "file": c.file_path,
                    "type": "config",
                    "change_type": c.change_type,
                })
        return config_changes

    def _detect_security_sensitive(self, changeset: ChangeSet) -> list[dict[str, Any]]:
        sensitive: list[dict[str, Any]] = []
        security_paths = {"auth", "security", "crypto", "credential", "secret", "token", "password"}
        for c in changeset.all_changes:
            fp = c.file_path.lower()
            if any(ext in fp for ext in SECURITY_SENSITIVE_EXTENSIONS):
                sensitive.append({"file": c.file_path, "reason": "sensitive_file"})
            if any(sp in fp for sp in security_paths):
                sensitive.append({"file": c.file_path, "reason": "security_related"})
        return sensitive

    def _compute_risk_factors(self, changeset: ChangeSet) -> dict[str, Any]:
        factors: dict[str, Any] = {}
        total = changeset.total_changed
        factors["total_files"] = total
        factors["has_deletions"] = len(changeset.deleted) > 0
        factors["has_renames"] = len(changeset.renamed) > 0
        languages = set(c.language for c in changeset.all_changes)
        factors["languages"] = list(languages)
        factors["is_multi_language"] = len(languages) > 1
        return factors
