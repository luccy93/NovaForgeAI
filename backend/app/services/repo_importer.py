"""Repository import service — clones, analyzes, and indexes repos."""

import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.repository import Repository
from app.services.code_analysis import CodeAnalysisService

logger = logging.getLogger(__name__)


class GitImportError(Exception):
    """Raised when git import fails."""


class RepoImporter:
    """Clones a git repository and indexes its code into Neo4j + Qdrant."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._analysis = CodeAnalysisService()

    async def import_from_url(self, repo_id: uuid.UUID, git_url: str, branch: str = "main") -> dict:
        """Clone a git repo and index all files."""
        tmp_dir = None
        try:
            tmp_dir = tempfile.mkdtemp(prefix="novaforge_import_")
            repo_path = await self._clone(git_url, tmp_dir, branch)
            stats = await self._index_repo(repo_id, repo_path)
            return stats
        finally:
            if tmp_dir:
                import shutil
                shutil.rmtree(tmp_dir, ignore_errors=True)

    async def import_from_path(self, repo_id: uuid.UUID, local_path: str) -> dict:
        """Index a repo already on disk."""
        path = Path(local_path)
        if not path.is_dir():
            raise GitImportError(f"Not a directory: {local_path}")
        return await self._index_repo(repo_id, path)

    async def _clone(self, git_url: str, dest: str, branch: str) -> Path:
        """Shell out to git clone."""
        import asyncio
        from urllib.parse import urlparse

        scheme = urlparse(git_url).scheme.lower()
        if scheme not in ("https", "http", "ssh", "git"):
            raise GitImportError(f"Unsupported git URL scheme: {scheme or '(none)'}")
        # Strip leading dashes: branch names must not smuggle git flags.
        safe_branch = branch.lstrip("-") or "main"
        proc = await asyncio.create_subprocess_exec(
            "git", "clone", "--depth", "1", "--branch", safe_branch, git_url, dest,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise GitImportError(f"git clone failed: {stderr.decode()}")
        return Path(dest)

    async def _index_repo(self, repo_id: uuid.UUID, repo_path: Path) -> dict:
        """Walk the repo and analyze all supported files."""
        supported_extensions = {
            ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java",
        }
        language_map = {
            ".py": "python", ".ts": "typescript", ".tsx": "typescript",
            ".js": "javascript", ".jsx": "javascript",
            ".go": "go", ".rs": "rust", ".java": "java",
        }

        files_indexed = 0
        functions_found = 0
        classes_found = 0
        errors = 0

        for file_path in repo_path.rglob("*"):
            if file_path.suffix not in supported_extensions:
                continue
            if any(part.startswith(".") for part in file_path.parts):
                continue
            if "node_modules" in file_path.parts or "__pycache__" in file_path.parts:
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                language = language_map.get(file_path.suffix, "python")
                result = self._analysis.analyze_file(content, language)
                files_indexed += 1
                functions_found += len(result.get("functions", []))
                classes_found += len(result.get("classes", []))
            except Exception as e:
                logger.warning("Failed to index %s: %s", file_path, e)
                errors += 1

        logger.info(
            "Indexed repo %s: %d files, %d functions, %d classes, %d errors",
            repo_id, files_indexed, functions_found, classes_found, errors,
        )

        return {
            "repository_id": str(repo_id),
            "files_indexed": files_indexed,
            "functions_found": functions_found,
            "classes_found": classes_found,
            "errors": errors,
        }
