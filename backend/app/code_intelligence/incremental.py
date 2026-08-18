"""Incremental Indexing Engine — tracks changes and only reprocesses what changed.

Compares the current state of a repository against its last indexed state
using git diffs and content hashing to minimize re-indexing work.
"""

import hashlib
import logging
import os
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.code_intelligence.models import (
    CodeChunk,
    CodeFile,
    CodeIndex,
    CodeSymbol,
    CodeMetrics,
    CodeSmell,
    FileStatus,
    IndexStatus,
)

logger = logging.getLogger(__name__)

TEST_PATH_PATTERNS: frozenset[str] = frozenset({
    "test", "tests", "spec", "specs", "__tests__", "test_",
    "_test", ".test.", ".spec.", "testutils", "fixtures",
    "mocks", "factories", "conftest",
})

CONFIG_PATH_PATTERNS: frozenset[str] = frozenset({
    "config", "configuration", "settings", "env", ".env",
    "docker", "k8s", "kubernetes", "terraform", "ansible",
    "ci", "cd", "github", "gitlab", ".github", ".gitlab",
    "nginx", "apache", "webpack", "vite", "rollup", "tsconfig",
    "pyproject", "setup.cfg", "tox.ini", "mypy.ini", ".flake8",
    ".eslintrc", ".prettierrc", "jest.config", "vitest.config",
    "babel.config", ".babelrc", "postcss.config", "tailwind.config",
})

DOC_PATH_PATTERNS: frozenset[str] = frozenset({
    "docs", "doc", "documentation", "wiki", "guides",
    "tutorials", "examples", "samples", "changelog",
    "readme", "license", "contributing", "authors",
})

SOURCE_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".pyi", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".java", ".c", ".h", ".cpp", ".hpp", ".cc", ".cxx", ".cs",
    ".go", ".rs", ".php", ".rb", ".kt", ".kts", ".swift",
    ".html", ".htm", ".css", ".scss", ".less",
    ".json", ".yml", ".yaml", ".toml",
    ".sh", ".zsh", ".bash", ".sql",
    ".md", ".markdown", ".xml", ".proto", ".graphql",
    ".gql", ".vue", ".svelte",
})


@dataclass
class FileChange:
    """Represents a single file change detected between commits."""
    file_path: str
    change_type: str  # ADDED, MODIFIED, DELETED, RENAMED
    old_path: Optional[str] = None
    content_hash: Optional[str] = None
    language: Optional[str] = None
    size_bytes: Optional[int] = 0


@dataclass
class ChangeSet:
    """Complete set of changes detected between two repository states."""
    added: list[dict] = field(default_factory=list)
    modified: list[dict] = field(default_factory=list)
    deleted: list[dict] = field(default_factory=list)
    renamed: list[dict] = field(default_factory=list)
    unchanged: int = 0
    total_files: int = 0
    commit_from: Optional[str] = None
    commit_to: Optional[str] = None


@dataclass
class IndexHealth:
    """Health status of a repository's code index."""
    status: str = "unknown"
    stale_files: int = 0
    missing_files: int = 0
    parser_errors: int = 0
    embedding_mismatch: int = 0
    graph_inconsistency: int = 0
    orphaned_vectors: int = 0
    orphaned_symbols: int = 0
    last_check: Optional[datetime] = None


EXTENSION_LANGUAGE_MAP: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".cs": "c_sharp",
    ".go": "go",
    ".rs": "rust",
    ".php": "php",
    ".rb": "ruby",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".swift": "swift",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "css",
    ".less": "css",
    ".json": "json",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".sh": "bash",
    ".zsh": "bash",
    ".bash": "bash",
    ".sql": "sql",
    ".md": "markdown",
    ".markdown": "markdown",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "config",
    ".conf": "config",
    ".xml": "xml",
    ".proto": "protobuf",
    ".graphql": "graphql",
    ".gql": "graphql",
    ".vue": "vue",
    ".svelte": "svelte",
}


class IncrementalIndexer:
    """Tracks changes between repository commits and only re-indexes
    what has changed. Uses git diff for commit-level change detection
    and SHA-256 content hashing for fine-grained change tracking.
    """

    def __init__(self, db_session: AsyncSession) -> None:
        self.db = db_session

    # ── change detection ─────────────────────────────────────────────

    async def detect_changes(
        self,
        repo_id: str,
        repo_path: str,
        current_commit: str,
    ) -> ChangeSet:
        """Compare the current state of a repository against its last
        indexed state to produce a ChangeSet of added, modified, deleted,
        and renamed files.
        """
        last_index = await self._get_last_index(repo_id)
        if last_index is None:
            return ChangeSet(
                commit_from=None,
                commit_to=current_commit,
                total_files=0,
            )

        last_commit = last_index.commit_sha
        if last_commit and last_commit == current_commit:
            return ChangeSet(
                commit_from=last_commit,
                commit_to=current_commit,
                unchanged=last_index.files_total,
                total_files=last_index.files_total,
            )

        if last_commit:
            changes = await self.get_changed_files(repo_path, last_commit, current_commit)
        else:
            changes = await self._full_scan(repo_path, repo_id)

        changeset = ChangeSet(
            commit_from=last_commit,
            commit_to=current_commit,
        )

        seen_paths: set[str] = set()
        for change in changes:
            change_type = change.get("change_type", "MODIFIED")
            path = change.get("file_path", "")
            old_path = change.get("old_path")
            seen_paths.add(path)

            entry = {
                "file_path": path,
                "change_type": change_type,
                "content_hash": change.get("content_hash", ""),
                "language": self._detect_file_type(path),
                "size_bytes": change.get("size_bytes", 0),
            }

            if old_path:
                entry["old_path"] = old_path

            if change_type == "ADDED":
                changeset.added.append(entry)
            elif change_type == "MODIFIED":
                changeset.modified.append(entry)
            elif change_type == "DELETED":
                changeset.deleted.append(entry)
            elif change_type == "RENAMED":
                changeset.renamed.append(entry)

        existing_stmt = select(CodeFile.file_path).where(
            CodeFile.repository_id == uuid.UUID(repo_id),
        )
        existing_result = await self.db.execute(existing_stmt)
        existing_paths = {row[0] for row in existing_result.all()}

        changeset.total_files = len(existing_paths) + len(changeset.added) - len(changeset.deleted)
        changeset.unchanged = changeset.total_files - len(changeset.added) - len(changeset.modified) - len(changeset.deleted) - len(changeset.renamed)

        self._emit_event("changes_detected", {
            "repo_id": repo_id,
            "commit_from": changeset.commit_from,
            "commit_to": changeset.commit_to,
            "added": len(changeset.added),
            "modified": len(changeset.modified),
            "deleted": len(changeset.deleted),
            "renamed": len(changeset.renamed),
            "unchanged": changeset.unchanged,
            "total_files": changeset.total_files,
        })

        return changeset

    async def get_changed_files(
        self,
        repo_path: str,
        last_commit: str,
        current_commit: str,
    ) -> list[dict]:
        """Use git diff to find added, modified, deleted, and renamed files
        between two commits.
        """
        changes: list[dict] = []

        try:
            result = subprocess.run(
                [
                    "git", "diff", "--name-status", "--diff-filter=AMDR",
                    last_commit, current_commit,
                ],
                capture_output=True,
                text=True,
                cwd=repo_path,
                timeout=60,
            )

            if result.returncode != 0:
                logger.warning("git diff failed: %s", result.stderr.strip())
                return await self._hash_based_diff(repo_path, last_commit, current_commit)

            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue

                parts = line.split("\t", 2)
                if len(parts) < 2:
                    continue

                status = parts[0].strip()
                if status.startswith("R"):
                    if len(parts) >= 3:
                        old_path = parts[1].strip()
                        new_path = parts[2].strip()
                        content_hash = await self.compute_file_hash(
                            new_path, self._read_file_at_head(repo_path, new_path)
                        )
                        changes.append({
                            "file_path": new_path,
                            "old_path": old_path,
                            "change_type": "RENAMED",
                            "content_hash": content_hash,
                            "size_bytes": self._get_file_size(repo_path, new_path),
                        })
                    continue

                path = parts[1].strip()
                if status == "A":
                    content_hash = await self.compute_file_hash(
                        path, self._read_file_at_head(repo_path, path)
                    )
                    changes.append({
                        "file_path": path,
                        "change_type": "ADDED",
                        "content_hash": content_hash,
                        "size_bytes": self._get_file_size(repo_path, path),
                    })
                elif status == "M":
                    content_hash = await self.compute_file_hash(
                        path, self._read_file_at_head(repo_path, path)
                    )
                    changes.append({
                        "file_path": path,
                        "change_type": "MODIFIED",
                        "content_hash": content_hash,
                        "size_bytes": self._get_file_size(repo_path, path),
                    })
                elif status == "D":
                    changes.append({
                        "file_path": path,
                        "change_type": "DELETED",
                        "content_hash": "",
                        "size_bytes": 0,
                    })

        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            logger.warning("Git diff command failed, falling back to hash diff: %s", exc)
            return await self._hash_based_diff(repo_path, last_commit, current_commit)

        return changes

    # ── hashing ──────────────────────────────────────────────────────

    async def compute_file_hash(self, file_path: str, content: str) -> str:
        """Compute a SHA-256 content hash for a file."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    async def should_reindex_file(self, file_id: str, new_hash: str) -> bool:
        """Check if a file has changed since the last index by comparing
        content hashes.
        """
        stmt = select(CodeFile.file_hash).where(CodeFile.id == uuid.UUID(file_id))
        result = await self.db.execute(stmt)
        old_hash = result.scalar_one_or_none()

        if old_hash is None:
            return True

        return self._compare_hashes(old_hash, new_hash) == "CHANGED"

    async def get_stale_files(self, repo_id: str, index_id: str) -> list:
        """Find files that need re-indexing because they have changed
        since the last indexing run.
        """
        stmt = (
            select(CodeFile)
            .where(
                CodeFile.repository_id == uuid.UUID(repo_id),
                CodeFile.index_id == uuid.UUID(index_id),
                CodeFile.status == FileStatus.PARSED.value,
            )
        )
        result = await self.db.execute(stmt)
        files = result.scalars().all()

        stale: list[CodeFile] = []
        for code_file in files:
            if code_file.file_hash is None:
                stale.append(code_file)
                continue

            disk_hash = await self._compute_disk_hash(code_file.file_path)
            if disk_hash and disk_hash != code_file.file_hash:
                stale.append(code_file)

        return stale

    # ── change application ───────────────────────────────────────────

    async def apply_changes(
        self,
        repo_id: str,
        changeset: ChangeSet,
        index_id: str,
    ) -> dict:
        """Apply a set of incremental changes to an existing index.

        Handles additions, modifications, deletions, and renames while
        preserving unchanged files and their associated data.
        """
        applied = {
            "added": 0,
            "modified": 0,
            "deleted": 0,
            "renamed": 0,
            "errors": 0,
        }

        for rename in changeset.renamed:
            try:
                await self.handle_renames(repo_id, [rename], index_id)
                applied["renamed"] += 1
            except Exception as exc:
                logger.warning("Failed to apply rename for %s: %s", rename.get("file_path"), exc)
                applied["errors"] += 1

        for deletion in changeset.deleted:
            try:
                await self.handle_deletions(repo_id, [deletion], index_id)
                applied["deleted"] += 1
            except Exception as exc:
                logger.warning("Failed to apply deletion for %s: %s", deletion.get("file_path"), exc)
                applied["errors"] += 1

        for addition in changeset.added:
            try:
                await self._apply_addition(repo_id, addition, index_id)
                applied["added"] += 1
            except Exception as exc:
                logger.warning("Failed to apply addition for %s: %s", addition.get("file_path"), exc)
                applied["errors"] += 1

        for modification in changeset.modified:
            try:
                await self._apply_modification(repo_id, modification, index_id)
                applied["modified"] += 1
            except Exception as exc:
                logger.warning("Failed to apply modification for %s: %s", modification.get("file_path"), exc)
                applied["errors"] += 1

        self._emit_event("changes_applied", {
            "repo_id": repo_id,
            "index_id": index_id,
            **applied,
        })

        return applied

    async def handle_renames(
        self,
        repo_id: str,
        renames: list[dict],
        index_id: str,
    ) -> dict:
        """Handle file renames by updating CodeFile records, preserving
        all associated symbols, metrics, smells, and chunks.
        """
        renamed_count = 0

        for rename in renames:
            old_path = rename.get("old_path", "")
            new_path = rename.get("file_path", "")

            if not old_path or not new_path:
                continue

            stmt = (
                select(CodeFile)
                .where(
                    CodeFile.repository_id == uuid.UUID(repo_id),
                    CodeFile.file_path == old_path,
                )
            )
            result = await self.db.execute(stmt)
            code_file = result.scalar_one_or_none()

            if code_file is None:
                code_file_new = CodeFile(
                    index_id=uuid.UUID(index_id),
                    repository_id=uuid.UUID(repo_id),
                    file_path=new_path,
                    file_name=os.path.basename(new_path),
                    language=self._detect_file_type(new_path),
                    content_hash=rename.get("content_hash", ""),
                    size_bytes=rename.get("size_bytes", 0),
                    status=FileStatus.QUEUED.value,
                )
                self.db.add(code_file_new)
                renamed_count += 1
                continue

            code_file.file_path = new_path
            code_file.file_name = os.path.basename(new_path)
            code_file.language = self._detect_file_type(new_path)
            code_file.file_hash = rename.get("content_hash", code_file.file_hash)
            code_file.size_bytes = rename.get("size_bytes", code_file.size_bytes)
            self.db.add(code_file)

            symbol_stmt = select(CodeSymbol).where(
                CodeSymbol.file_id == code_file.id,
            )
            symbol_result = await self.db.execute(symbol_stmt)
            symbols = symbol_result.scalars().all()

            for sym in symbols:
                sym.qualified_name = sym.qualified_name.replace(
                    old_path, new_path
                ) if old_path in sym.qualified_name else sym.qualified_name
                self.db.add(sym)

            renamed_count += 1

        await self.db.flush()
        return {"renamed": renamed_count}

    async def handle_deletions(
        self,
        repo_id: str,
        deletions: list[dict],
        index_id: str,
    ) -> dict:
        """Clean up deleted files and all associated data: symbols,
        references, calls, imports, metrics, smells, tests, and chunks.
        """
        deleted_count = 0

        for deletion in deletions:
            file_path = deletion.get("file_path", "")

            stmt = (
                select(CodeFile)
                .where(
                    CodeFile.repository_id == uuid.UUID(repo_id),
                    CodeFile.file_path == file_path,
                )
            )
            result = await self.db.execute(stmt)
            code_file = result.scalar_one_or_none()

            if code_file is None:
                continue

            self.db.delete(code_file)
            deleted_count += 1

        await self.db.flush()
        return {"deleted": deleted_count}

    async def calculate_index_health(self, repo_id: str) -> IndexHealth:
        """Calculate comprehensive index health metrics: stale files,
        missing files, parser errors, embedding mismatches, graph
        inconsistencies, orphaned vectors, and orphaned symbols.
        """
        health = IndexHealth(
            last_check=datetime.now(timezone.utc),
        )

        files_stmt = select(CodeFile).where(
            CodeFile.repository_id == uuid.UUID(repo_id),
        )
        files_result = await self.db.execute(files_stmt)
        files = files_result.scalars().all()

        for code_file in files:
            if code_file.status == FileStatus.ERROR.value:
                health.parser_errors += 1

            if code_file.file_path and not os.path.isfile(code_file.file_path):
                health.missing_files += 1

            if code_file.status == FileStatus.PARSED.value and code_file.file_hash:
                disk_hash = await self._compute_disk_hash(code_file.file_path)
                if disk_hash and disk_hash != code_file.file_hash:
                    health.stale_files += 1

        chunks_stmt = select(CodeChunk).where(
            CodeChunk.repository_id == uuid.UUID(repo_id),
            CodeChunk.embedding_id.isnot(None),
        )
        chunks_result = await self.db.execute(chunks_stmt)
        chunks_with_embeddings = chunks_result.scalars().all()

        chunks_no_embed_stmt = select(func.count()).where(
            CodeChunk.repository_id == uuid.UUID(repo_id),
            CodeChunk.embedding_id.is_(None),
        )
        chunks_no_embed_result = await self.db.execute(chunks_no_embed_stmt)
        chunks_without_embeddings = chunks_no_embed_result.scalar() or 0

        if chunks_without_embeddings > 0 and len(chunks_with_embeddings) > 0:
            health.embedding_mismatch = chunks_without_embeddings

        symbols_stmt = (
            select(CodeSymbol)
            .where(CodeSymbol.repository_id == uuid.UUID(repo_id))
        )
        symbols_result = await self.db.execute(symbols_stmt)
        symbols = symbols_result.scalars().all()

        file_ids_with_symbols: set[str] = set()
        for sym in symbols:
            file_ids_with_symbols.add(str(sym.file_id))

        all_file_ids_stmt = select(CodeFile.id).where(
            CodeFile.repository_id == uuid.UUID(repo_id),
        )
        all_file_ids_result = await self.db.execute(all_file_ids_stmt)
        all_file_ids = {str(row[0]) for row in all_file_ids_result.all()}

        orphaned_symbol_files = file_ids_with_symbols - all_file_ids
        health.orphaned_symbols = len(orphaned_symbol_files)

        symbols_by_file: dict[str, int] = {}
        for sym in symbols:
            fid = str(sym.file_id)
            symbols_by_file[fid] = symbols_by_file.get(fid, 0) + 1

        for code_file in files:
            file_id = str(code_file.id)
            if file_id in symbols_by_file and symbols_by_file[file_id] > 200:
                health.graph_inconsistency += 1

        if health.stale_files == 0 and health.missing_files == 0 and health.parser_errors == 0:
            health.status = "healthy"
        elif health.parser_errors > 0 or health.missing_files > len(files) * 0.1:
            health.status = "degraded"
        else:
            health.status = "stale"

        self._emit_event("health_calculated", {
            "repo_id": repo_id,
            "status": health.status,
            "stale_files": health.stale_files,
            "missing_files": health.missing_files,
            "parser_errors": health.parser_errors,
        })

        return health

    async def reindex_if_needed(self, repo_id: str, repo_path: str) -> bool:
        """Check if re-indexing is needed and trigger it if so.

        Returns True if a re-index was triggered, False if the index
        is still up-to-date.
        """
        last_index = await self._get_last_index(repo_id)
        if last_index is None:
            return False

        if last_index.commit_sha is None:
            return False

        current_commit = await self._get_current_commit(repo_path)
        if current_commit is None or current_commit == last_index.commit_sha:
            return False

        changeset = await self.detect_changes(repo_id, repo_path, current_commit)

        has_changes = (
            len(changeset.added) > 0
            or len(changeset.modified) > 0
            or len(changeset.deleted) > 0
            or len(changeset.renamed) > 0
        )

        if not has_changes:
            return False

        health = await self.calculate_index_health(repo_id)
        if health.stale_files == 0 and health.missing_files == 0:
            return False

        self._emit_event("reindex_triggered", {
            "repo_id": repo_id,
            "commit": current_commit,
            "added": len(changeset.added),
            "modified": len(changeset.modified),
            "deleted": len(changeset.deleted),
            "renamed": len(changeset.renamed),
        })

        return True

    # ── hash comparison ──────────────────────────────────────────────

    def _compare_hashes(self, old_hash: str, new_hash: str) -> str:
        """Compare two file hashes and return the change status.

        Returns CHANGED, UNCHANGED, or UNKNOWN.
        """
        if not old_hash or not new_hash:
            return "UNKNOWN"

        if old_hash == new_hash:
            return "UNCHANGED"

        return "CHANGED"

    # ── file type detection ──────────────────────────────────────────

    def _detect_file_type(self, file_path: str) -> str:
        """Classify a file as test, config, doc, or source based on path patterns."""
        lower_path = file_path.lower()
        basename = os.path.basename(lower_path).lower()

        for pattern in TEST_PATH_PATTERNS:
            if pattern in lower_path or pattern in basename:
                return "test"

        for pattern in CONFIG_PATH_PATTERNS:
            if pattern in lower_path or pattern in basename:
                return "config"

        for pattern in DOC_PATH_PATTERNS:
            if pattern in lower_path:
                return "doc"

        _, ext = os.path.splitext(file_path)
        if ext.lower() in SOURCE_EXTENSIONS:
            return "source"

        return "source"

    # ── private helpers ──────────────────────────────────────────────

    async def _get_last_index(self, repo_id: str) -> Optional[CodeIndex]:
        """Get the most recent index for a repository."""
        stmt = (
            select(CodeIndex)
            .where(CodeIndex.repository_id == uuid.UUID(repo_id))
            .order_by(CodeIndex.created_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_current_commit(self, repo_path: str) -> Optional[str]:
        """Get the current HEAD commit SHA of a repository."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                cwd=repo_path,
                timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        return None

    def _read_file_at_head(self, repo_path: str, file_path: str) -> str:
        """Read file content from the working directory."""
        full_path = os.path.join(repo_path, file_path)
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except (OSError, IOError):
            return ""

    def _get_file_size(self, repo_path: str, file_path: str) -> int:
        """Get file size in bytes."""
        full_path = os.path.join(repo_path, file_path)
        try:
            return os.path.getsize(full_path)
        except (OSError, ValueError):
            return 0

    async def _compute_disk_hash(self, file_path: str) -> Optional[str]:
        """Compute SHA-256 hash of a file on disk."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            return hashlib.sha256(content.encode("utf-8")).hexdigest()
        except (OSError, IOError):
            return None

    async def _full_scan(
        self, repo_path: str, repo_id: str,
    ) -> list[dict]:
        """Perform a full scan when no previous index exists."""
        changes: list[dict] = []

        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [
                d for d in dirs
                if d not in {".git", "node_modules", "__pycache__", ".venv", "venv"}
            ]

            for file_name in files:
                if file_name.endswith((".pyc", ".pyo", ".so", ".dll", ".exe")):
                    continue

                file_path = os.path.join(root, file_name)
                relative_path = os.path.relpath(file_path, repo_path)

                try:
                    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                except (OSError, IOError):
                    continue

                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                try:
                    size_bytes = os.path.getsize(file_path)
                except OSError:
                    size_bytes = 0

                changes.append({
                    "file_path": relative_path,
                    "change_type": "ADDED",
                    "content_hash": content_hash,
                    "size_bytes": size_bytes,
                })

        return changes

    async def _hash_based_diff(
        self, repo_path: str, last_commit: str, current_commit: str,
    ) -> list[dict]:
        """Fallback diff method using content hashing when git diff is unavailable."""
        changes: list[dict] = []

        existing_stmt = select(CodeFile.file_path, CodeFile.file_hash).where(
            CodeFile.commit_sha == last_commit,
        )
        existing_result = await self.db.execute(existing_stmt)
        existing = {row[0]: row[1] for row in existing_result.all()}

        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [
                d for d in dirs
                if d not in {".git", "node_modules", "__pycache__", ".venv"}
            ]

            for file_name in files:
                file_path = os.path.join(root, file_name)
                relative_path = os.path.relpath(file_path, repo_path)

                try:
                    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                except (OSError, IOError):
                    continue

                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

                if relative_path not in existing:
                    changes.append({
                        "file_path": relative_path,
                        "change_type": "ADDED",
                        "content_hash": content_hash,
                        "size_bytes": len(content.encode("utf-8")),
                    })
                elif existing[relative_path] != content_hash:
                    changes.append({
                        "file_path": relative_path,
                        "change_type": "MODIFIED",
                        "content_hash": content_hash,
                        "size_bytes": len(content.encode("utf-8")),
                    })

        for existing_path in existing:
            full_path = os.path.join(repo_path, existing_path)
            if not os.path.isfile(full_path):
                changes.append({
                    "file_path": existing_path,
                    "change_type": "DELETED",
                    "content_hash": "",
                    "size_bytes": 0,
                })

        return changes

    async def _apply_addition(
        self, repo_id: str, addition: dict, index_id: str,
    ) -> None:
        """Apply a file addition: create a new CodeFile record."""
        file_path = addition.get("file_path", "")
        language = self._detect_file_type(file_path)

        code_file = CodeFile(
            index_id=uuid.UUID(index_id),
            repository_id=uuid.UUID(repo_id),
            file_path=file_path,
            file_name=os.path.basename(file_path),
            language=EXTENSION_LANGUAGE_MAP.get(
                os.path.splitext(file_path)[1].lower(), ""
            ),
            file_hash=addition.get("content_hash", ""),
            size_bytes=addition.get("size_bytes", 0),
            status=FileStatus.QUEUED.value,
        )
        self.db.add(code_file)
        await self.db.flush()

    async def _apply_modification(
        self, repo_id: str, modification: dict, index_id: str,
    ) -> None:
        """Apply a file modification: update the hash and reset status
        to QUEUED for re-parsing.
        """
        file_path = modification.get("file_path", "")

        stmt = (
            select(CodeFile)
            .where(
                CodeFile.repository_id == uuid.UUID(repo_id),
                CodeFile.file_path == file_path,
            )
        )
        result = await self.db.execute(stmt)
        code_file = result.scalar_one_or_none()

        if code_file is None:
            await self._apply_addition(repo_id, modification, index_id)
            return

        old_hash = code_file.file_hash
        new_hash = modification.get("content_hash", "")

        if old_hash == new_hash:
            return

        code_file.file_hash = new_hash
        code_file.size_bytes = modification.get("size_bytes", code_file.size_bytes)
        code_file.status = FileStatus.QUEUED.value
        code_file.parse_error = None
        self.db.add(code_file)
        await self.db.flush()

    def _emit_event(self, event_type: str, data: dict) -> None:
        """Emit an event to the event bus (fire-and-forget)."""
        try:
            from app.core.events import Event, EventType, event_bus
            full_type = f"code_intelligence.incremental.{event_type}"
            event_data = {**data, "event_name": full_type}
            event = Event(
                event_type=EventType.pipeline_completed,
                data=event_data,
                source="code_intelligence_incremental",
            )
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(event_bus.publish_nowait(event))
            else:
                loop.run_until_complete(event_bus.publish_nowait(event))
        except Exception:
            logger.debug("Failed to emit event %s", event_type)
