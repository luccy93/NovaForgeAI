"""Semantic Chunking Engine — structural-boundary-aware code chunking.

Chunks code by functions, classes, modules, documentation, and config files.
Pairs with vector embeddings (Qdrant) and a RAG context builder for retrieval.
"""

import logging
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.code_intelligence.models import (
    CodeChunk,
    CodeFile,
    CodeHistory,
    CodeSymbol,
    CodeTest,
    IndexStatus,
    SymbolType,
)

logger = logging.getLogger(__name__)

# ─── Configuration Constants ───────────────────────────────────────────

DEFAULT_MAX_CHUNK_TOKENS = 2048
DEFAULT_OVERLAP_LINES = 3
EMBEDDING_COLLECTION = "repository_chunks"
DOC_EMBEDDING_COLLECTION = "documentation_chunks"
LANGUAGES_TO_CHUNK = frozenset({
    "python", "typescript", "javascript", "java", "go", "rust",
    "c", "cpp", "c_sharp", "kotlin", "swift", "php", "ruby",
    "scala", "sql", "html", "css", "bash", "yaml", "json", "markdown",
})
DOC_EXTENSIONS = frozenset({".md", ".rst", ".txt", ".adoc", ".wiki"})
CONFIG_EXTENSIONS = frozenset({
    ".toml", ".ini", ".cfg", ".conf", ".yaml", ".yml", ".json",
    ".env", ".editorconfig", ".gitignore", ".dockerignore",
    "Dockerfile", "Makefile", "Justfile",
})
CONFIG_FILENAMES = frozenset({
    "Makefile", "Dockerfile", "Justfile", ".gitignore", ".dockerignore",
    ".editorconfig", "tox.ini", "setup.cfg", "pyproject.toml",
    "package.json", "tsconfig.json", "tsconfig.build.json",
    "Cargo.toml", "go.mod", "go.sum", "pom.xml", "build.gradle",
    "Gemfile", "composer.json", ".eslintrc", ".prettierrc",
    "jest.config.js", "jest.config.ts", "vitest.config.ts",
    "webpack.config.js", "vite.config.ts", "vite.config.js",
    "next.config.js", "next.config.mjs", "nuxt.config.ts",
})
TEST_FILENAMES = frozenset({
    "test_", "_test.go", "Test", "spec_", "_spec.",
    ".test.", ".spec.", "conftest.py",
})
SOURCE_CHUNK_COLLECTION = "repository_chunks"


# ─── Dataclasses ───────────────────────────────────────────────────────


@dataclass
class RAGContextBundle:
    """Complete RAG context for a query."""

    query: str = ""
    symbols: list[dict] = field(default_factory=list)
    files: list[dict] = field(default_factory=list)
    dependencies: dict = field(default_factory=dict)
    graph_relationships: list[dict] = field(default_factory=list)
    tests: list[dict] = field(default_factory=list)
    documentation: list[dict] = field(default_factory=list)
    recent_changes: list[dict] = field(default_factory=list)
    snippets: list[dict] = field(default_factory=list)
    total_tokens: int = 0
    citations: list[dict] = field(default_factory=list)


# ─── SemanticChunker ──────────────────────────────────────────────────


class SemanticChunker:
    """Chunk source files based on structural boundaries.

    Produces ``CodeChunk`` rows keyed to symbols, files, and modules.
    Supports embedding generation and hybrid search over chunks.
    """

    def __init__(
        self,
        db_session: AsyncSession,
        embedding_service: Any | None = None,
        vector_store: Any | None = None,
    ) -> None:
        self._db = db_session
        self._embedding = embedding_service
        self._vector_store = vector_store

    # ── Public API ────────────────────────────────────────────────────

    async def chunk_repository(self, index_id: str, repo_id: str) -> dict:
        """Chunk every parsed file in an index.

        Returns summary counts ``{"chunks_created": …, "files_skipped": …, "errors": […]}``.
        """
        stmt = (
            select(CodeFile)
            .where(
                CodeFile.index_id == index_id,
                CodeFile.repository_id == repo_id,
                CodeFile.status.in_([IndexStatus.PARSING.value, IndexStatus.ANALYZING.value, IndexStatus.READY.value]),
            )
            .order_by(CodeFile.file_path)
        )
        result = await self._db.execute(stmt)
        files = result.scalars().all()

        total_chunks = 0
        files_skipped = 0
        errors: list[dict] = []

        for code_file in files:
            if not self._should_chunk_file(code_file.file_path, code_file.language or ""):
                files_skipped += 1
                continue

            try:
                content = await self._load_file_content(code_file)
                if not content:
                    files_skipped += 1
                    continue

                symbols = await self._load_file_symbols(code_file.id)
                symbol_dicts = [
                    {
                        "symbol_id": s.symbol_id,
                        "name": s.name,
                        "qualified_name": s.qualified_name,
                        "symbol_type": s.symbol_type,
                        "start_line": s.start_line or 1,
                        "end_line": s.end_line or content.count("\n") + 1,
                        "docstring": s.docstring or "",
                        "signature": s.signature or "",
                        "parent_symbol_id": s.parent_symbol_id,
                    }
                    for s in symbols
                ]

                chunks = await self.chunk_file(
                    file_id=str(code_file.id),
                    content=content,
                    language=code_file.language or "",
                    symbols=symbol_dicts,
                    repo_id=repo_id,
                    index_id=index_id,
                )

                code_file.chunk_count = len(chunks)
                total_chunks += len(chunks)
            except Exception as exc:
                logger.error("Chunking failed for file %s: %s", code_file.file_path, exc)
                errors.append({"file_id": str(code_file.id), "error": str(exc)})

        await self._db.flush()

        return {
            "chunks_created": total_chunks,
            "files_skipped": files_skipped,
            "errors": errors,
        }

    async def chunk_file(
        self,
        file_id: str,
        content: str,
        language: str,
        symbols: list[dict],
        repo_id: str,
        index_id: str,
    ) -> list[CodeChunk]:
        """Chunk a single file using the best strategy for its type."""
        lang = (language or "").lower()

        if self._is_documentation_file(file_id, content, lang):
            return await self.chunk_documentation(file_id, content, lang, repo_id, index_id)

        if self._is_config_file(file_id, content, lang):
            return await self.chunk_config(file_id, content, lang, repo_id, index_id)

        if symbols:
            return await self.chunk_by_symbol(file_id, symbols, content, repo_id, index_id)

        return await self.chunk_by_module(file_id, content, lang, repo_id, index_id)

    async def chunk_by_symbol(
        self,
        file_id: str,
        symbols: list[dict],
        content: str,
        repo_id: str,
        index_id: str,
    ) -> list[CodeChunk]:
        """One chunk per function / class / method with surrounding context."""
        lines = content.split("\n")
        chunks: list[CodeChunk] = []
        symbol_ids_added: set[str] = set()

        sorted_symbols = sorted(
            [s for s in symbols if s.get("symbol_type") != SymbolType.FILE.value],
            key=lambda s: s.get("start_line", 0),
        )

        for sym in sorted_symbols:
            start = max(0, (sym.get("start_line") or 1) - 1)
            end = min(len(lines), sym.get("end_line") or len(lines))

            context_before = max(0, start - DEFAULT_OVERLAP_LINES)
            context_after = min(len(lines), end + DEFAULT_OVERLAP_LINES)
            segment_lines = lines[context_before:context_after]
            segment = "\n".join(segment_lines)

            token_count = self._count_tokens(segment)

            if token_count > DEFAULT_MAX_CHUNK_TOKENS and (end - start) > 1:
                mid = start + (end - start) // 2
                first_half = "\n".join(lines[start:mid])
                second_half = "\n".join(lines[mid:end])

                for idx, half in enumerate([first_half, second_half]):
                    if not half.strip():
                        continue
                    chunk_type = self._chunk_type_from_symbol(sym.get("symbol_type", ""))
                    chunk = await self._create_chunk(
                        file_id=file_id,
                        repo_id=repo_id,
                        index_id=index_id,
                        symbol_id=sym.get("symbol_id"),
                        chunk_type=chunk_type,
                        content=half,
                        start_line=start + 1 if idx == 0 else mid + 1,
                        end_line=mid if idx == 0 else end,
                        language="",
                        metadata={"part": idx + 1, "name": sym.get("name", "")},
                    )
                    chunks.append(chunk)
                    symbol_ids_added.add(sym.get("symbol_id", ""))
            else:
                if not segment.strip():
                    continue
                chunk_type = self._chunk_type_from_symbol(sym.get("symbol_type", ""))
                chunk = await self._create_chunk(
                    file_id=file_id,
                    repo_id=repo_id,
                    index_id=index_id,
                    symbol_id=sym.get("symbol_id"),
                    chunk_type=chunk_type,
                    content=segment,
                    start_line=start + 1,
                    end_line=end,
                    language="",
                    metadata={"name": sym.get("name", ""), "qualified_name": sym.get("qualified_name", "")},
                )
                chunks.append(chunk)
                symbol_ids_added.add(sym.get("symbol_id", ""))

        added_ranges = set()
        for sym in sorted_symbols:
            s = sym.get("start_line", 1)
            e = sym.get("end_line", len(lines))
            for ln in range(s, e + 1):
                added_ranges.add(ln)

        uncovered_start: int | None = None
        for i in range(1, len(lines) + 1):
            if i not in added_ranges:
                if uncovered_start is None:
                    uncovered_start = i
            else:
                if uncovered_start is not None:
                    segment = "\n".join(lines[uncovered_start - 1:i - 1])
                    if segment.strip() and self._count_tokens(segment) > 20:
                        chunk = await self._create_chunk(
                            file_id=file_id,
                            repo_id=repo_id,
                            index_id=index_id,
                            symbol_id=None,
                            chunk_type="module",
                            content=segment,
                            start_line=uncovered_start,
                            end_line=i - 1,
                            language="",
                            metadata={"region": "interstitial"},
                        )
                        chunks.append(chunk)
                    uncovered_start = None

        if uncovered_start is not None:
            segment = "\n".join(lines[uncovered_start - 1:])
            if segment.strip() and self._count_tokens(segment) > 20:
                chunk = await self._create_chunk(
                    file_id=file_id,
                    repo_id=repo_id,
                    index_id=index_id,
                    symbol_id=None,
                    chunk_type="module",
                    content=segment,
                    start_line=uncovered_start,
                    end_line=len(lines),
                    language="",
                    metadata={"region": "trailing"},
                )
                chunks.append(chunk)

        await self._db.flush()
        return chunks

    async def chunk_by_module(
        self,
        file_id: str,
        content: str,
        language: str,
        repo_id: str,
        index_id: str,
    ) -> list[CodeChunk]:
        """Module-level chunking: split by blank-line-separated blocks."""
        lines = content.split("\n")
        chunks: list[CodeChunk] = []
        current_block: list[str] = []
        current_start = 1

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped == "" and current_block:
                block_text = "\n".join(current_block)
                if self._count_tokens(block_text) > 20:
                    chunk = await self._create_chunk(
                        file_id=file_id,
                        repo_id=repo_id,
                        index_id=index_id,
                        symbol_id=None,
                        chunk_type="module",
                        content=block_text,
                        start_line=current_start,
                        end_line=current_start + len(current_block) - 1,
                        language=language,
                        metadata={"chunk_strategy": "module"},
                    )
                    chunks.append(chunk)
                current_block = []
                current_start = i + 1
            else:
                if not current_block:
                    current_start = i
                current_block.append(line)

        if current_block:
            block_text = "\n".join(current_block)
            if self._count_tokens(block_text) > 20:
                chunk = await self._create_chunk(
                    file_id=file_id,
                    repo_id=repo_id,
                    index_id=index_id,
                    symbol_id=None,
                    chunk_type="module",
                    content=block_text,
                    start_line=current_start,
                    end_line=current_start + len(current_block) - 1,
                    language=language,
                    metadata={"chunk_strategy": "module"},
                )
                chunks.append(chunk)

        await self._db.flush()
        return chunks

    async def chunk_documentation(
        self,
        file_id: str,
        content: str,
        language: str,
        repo_id: str,
        index_id: str,
    ) -> list[CodeChunk]:
        """Chunk documentation files by headings and paragraph blocks."""
        lines = content.split("\n")
        chunks: list[CodeChunk] = []
        current_block: list[str] = []
        current_start = 1

        heading_re = re.compile(r"^(#{1,6})\s+.+")

        for i, line in enumerate(lines, 1):
            is_heading = bool(heading_re.match(line))
            is_blank = line.strip() == ""

            if (is_heading or is_blank) and current_block:
                block_text = "\n".join(current_block)
                if self._count_tokens(block_text) > 10:
                    chunk = await self._create_chunk(
                        file_id=file_id,
                        repo_id=repo_id,
                        index_id=index_id,
                        symbol_id=None,
                        chunk_type="documentation",
                        content=block_text,
                        start_line=current_start,
                        end_line=current_start + len(current_block) - 1,
                        language=language,
                        metadata={"chunk_strategy": "documentation"},
                    )
                    chunks.append(chunk)
                current_block = []

            if is_blank:
                current_start = i + 1
            else:
                if not current_block:
                    current_start = i
                current_block.append(line)

        if current_block:
            block_text = "\n".join(current_block)
            if self._count_tokens(block_text) > 10:
                chunk = await self._create_chunk(
                    file_id=file_id,
                    repo_id=repo_id,
                    index_id=index_id,
                    symbol_id=None,
                    chunk_type="documentation",
                    content=block_text,
                    start_line=current_start,
                    end_line=current_start + len(current_block) - 1,
                    language=language,
                    metadata={"chunk_strategy": "documentation"},
                )
                chunks.append(chunk)

        await self._db.flush()
        return chunks

    async def chunk_config(
        self,
        file_id: str,
        content: str,
        language: str,
        repo_id: str,
        index_id: str,
    ) -> list[CodeChunk]:
        """Chunk configuration files. Usually small: one chunk per file, or
        split by top-level sections for larger configs."""
        lines = content.split("\n")

        if self._count_tokens(content) <= DEFAULT_MAX_CHUNK_TOKENS:
            chunk = await self._create_chunk(
                file_id=file_id,
                repo_id=repo_id,
                index_id=index_id,
                symbol_id=None,
                chunk_type="config",
                content=content,
                start_line=1,
                end_line=len(lines),
                language=language,
                metadata={"chunk_strategy": "config_single"},
            )
            await self._db.flush()
            return [chunk]

        section_re = re.compile(r"^\[[^\]]+\]|^[A-Za-z_]\w*\s*[:{]|^---$")
        current_block: list[str] = []
        current_start = 1
        chunks: list[CodeChunk] = []

        for i, line in enumerate(lines, 1):
            is_section = bool(section_re.match(line))
            if is_section and current_block:
                block_text = "\n".join(current_block)
                if self._count_tokens(block_text) > 10:
                    chunk = await self._create_chunk(
                        file_id=file_id,
                        repo_id=repo_id,
                        index_id=index_id,
                        symbol_id=None,
                        chunk_type="config",
                        content=block_text,
                        start_line=current_start,
                        end_line=current_start + len(current_block) - 1,
                        language=language,
                        metadata={"chunk_strategy": "config_section"},
                    )
                    chunks.append(chunk)
                current_block = []
                current_start = i

            current_block.append(line)

        if current_block:
            block_text = "\n".join(current_block)
            if self._count_tokens(block_text) > 10:
                chunk = await self._create_chunk(
                    file_id=file_id,
                    repo_id=repo_id,
                    index_id=index_id,
                    symbol_id=None,
                    chunk_type="config",
                    content=block_text,
                    start_line=current_start,
                    end_line=current_start + len(current_block) - 1,
                    language=language,
                    metadata={"chunk_strategy": "config_section"},
                )
                chunks.append(chunk)

        await self._db.flush()
        return chunks

    async def embed_chunks(self, chunk_ids: list[str], repo_id: str) -> dict:
        """Generate embeddings for chunks and store them in the vector store.

        Returns ``{"embedded": N, "failed": N, "errors": [...]}``.
        """
        if not self._embedding or not self._vector_store:
            logger.warning("embed_chunks called without embedding_service or vector_store")
            return {"embedded": 0, "failed": len(chunk_ids), "errors": ["No embedding service configured"]}

        embedded = 0
        failed = 0
        errors: list[str] = []
        points: list[dict] = []

        for cid in chunk_ids:
            try:
                stmt = select(CodeChunk).where(CodeChunk.id == cid)
                result = await self._db.execute(stmt)
                chunk = result.scalar_one_or_none()
                if chunk is None:
                    failed += 1
                    continue

                embedding_text = self._build_embedding_text(chunk)
                vector = await self._embedding.embed(embedding_text)

                point_id = str(chunk.id)
                chunk.embedding_id = point_id
                chunk.embedding_model = getattr(self._embedding, "model_name", "unknown")
                chunk.embedding_version = "1.0"

                points.append({
                    "id": point_id,
                    "vector": vector,
                    "payload": {
                        "repository_id": str(repo_id),
                        "chunk_id": str(chunk.id),
                        "file_id": str(chunk.file_id),
                        "symbol_id": str(chunk.symbol_id) if chunk.symbol_id else None,
                        "chunk_type": chunk.chunk_type,
                        "language": chunk.language or "",
                        "file_path": "",
                        "start_line": chunk.start_line or 0,
                        "end_line": chunk.end_line or 0,
                        "token_count": chunk.token_count or 0,
                        "content_preview": (chunk.content[:200] if chunk.content else ""),
                    },
                })
                embedded += 1
            except Exception as exc:
                failed += 1
                errors.append(f"{cid}: {exc}")

        if points:
            try:
                await self._vector_store.upsert(collection=EMBEDDING_COLLECTION, points=points)
            except Exception as exc:
                logger.error("Vector store upsert failed: %s", exc)
                errors.append(f"Vector upsert: {exc}")
                failed += embedded
                embedded = 0

        await self._db.flush()

        return {"embedded": embedded, "failed": failed, "errors": errors}

    async def search_chunks(
        self,
        query: str,
        repo_id: str,
        chunk_type: str | None = None,
        language: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Hybrid search: combine vector similarity with lexical keyword matching."""
        results: list[dict] = []
        seen_ids: set[str] = set()

        vector_results = await self._vector_search(query, repo_id, chunk_type, language, limit)
        for vr in vector_results:
            cid = vr.get("chunk_id", "")
            if cid and cid not in seen_ids:
                vr["retrieval_source"] = "vector"
                results.append(vr)
                seen_ids.add(cid)

        lexical_results = await self._lexical_search(query, repo_id, chunk_type, language, limit)
        for lr in lexical_results:
            cid = lr.get("chunk_id", "")
            if cid and cid not in seen_ids:
                lr["retrieval_source"] = "lexical"
                results.append(lr)
                seen_ids.add(cid)
            elif cid in seen_ids:
                for existing in results:
                    if existing.get("chunk_id") == cid:
                        existing["retrieval_source"] = "hybrid"
                        existing["score"] = existing.get("score", 0) + lr.get("score", 0)
                        break

        results.sort(key=lambda r: r.get("score", 0), reverse=True)
        return results[:limit]

    async def get_chunks_for_symbol(self, symbol_id: str) -> list[CodeChunk]:
        """Get all chunks linked to a given symbol."""
        sym = await self._resolve_symbol(symbol_id)
        if sym is None:
            return []

        stmt = (
            select(CodeChunk)
            .where(CodeChunk.symbol_id == sym.id)
            .order_by(CodeChunk.start_line)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_chunks_for_file(self, file_id: str) -> list[CodeChunk]:
        """Get all chunks belonging to a file."""
        stmt = (
            select(CodeChunk)
            .where(CodeChunk.file_id == file_id)
            .order_by(CodeChunk.start_line)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_chunks_for_repository(self, repo_id: str, limit: int = 100) -> list[CodeChunk]:
        """Get the most recent chunks for a repository."""
        stmt = (
            select(CodeChunk)
            .where(CodeChunk.repository_id == repo_id)
            .order_by(CodeChunk.created_at.desc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    # ── Private helpers ───────────────────────────────────────────────

    async def _create_chunk(
        self,
        file_id: str,
        repo_id: str,
        index_id: str,
        symbol_id: str | None,
        chunk_type: str,
        content: str,
        start_line: int,
        end_line: int,
        language: str,
        metadata: dict | None = None,
    ) -> CodeChunk:
        token_count = self._count_tokens(content)

        chunk = CodeChunk(
            repository_id=repo_id,
            index_id=index_id,
            file_id=file_id,
            symbol_id=symbol_id,
            chunk_type=chunk_type,
            content=content,
            start_line=start_line,
            end_line=end_line,
            language=language or None,
            token_count=token_count,
            metadata_=metadata or {},
        )
        self._db.add(chunk)
        return chunk

    @staticmethod
    def _extract_content_segment(content: str, start_line: int, end_line: int) -> str:
        lines = content.split("\n")
        start = max(0, start_line - 1)
        end = min(len(lines), end_line)
        return "\n".join(lines[start:end])

    @staticmethod
    def _count_tokens(text: str) -> int:
        return len(text) // 4

    @staticmethod
    def _chunk_type_from_symbol(symbol_type: str) -> str:
        mapping = {
            SymbolType.CLASS.value: "class",
            SymbolType.INTERFACE.value: "class",
            SymbolType.STRUCT.value: "class",
            SymbolType.ENUM.value: "class",
            SymbolType.FUNCTION.value: "function",
            SymbolType.METHOD.value: "function",
            SymbolType.VARIABLE.value: "variable",
            SymbolType.CONSTANT.value: "variable",
            SymbolType.PROPERTY.value: "variable",
            SymbolType.TYPE.value: "type",
            SymbolType.IMPORT.value: "import",
            SymbolType.MODULE.value: "module",
            SymbolType.PACKAGE.value: "module",
            SymbolType.NAMESPACE.value: "module",
            SymbolType.FILE.value: "module",
        }
        return mapping.get(symbol_type, "code")

    @staticmethod
    def _should_chunk_file(file_path: str, language: str) -> bool:
        if language and language.lower() not in LANGUAGES_TO_CHUNK:
            basename = file_path.rsplit("/", 1)[-1] if "/" in file_path else file_path
            basename = basename.rsplit("\\", 1)[-1] if "\\" in basename else basename
            if not any(basename.endswith(ext) for ext in DOC_EXTENSIONS):
                return False

        basename = file_path.rsplit("/", 1)[-1] if "/" in file_path else file_path
        basename = basename.rsplit("\\", 1)[-1] if "\\" in basename else basename

        if basename in CONFIG_FILENAMES:
            return True

        if any(basename.endswith(ext) for ext in CONFIG_EXTENSIONS):
            return True

        if any(basename.endswith(ext) for ext in DOC_EXTENSIONS):
            return True

        if any(pat in basename for pat in TEST_FILENAMES):
            return True

        if language and language.lower() in LANGUAGES_TO_CHUNK:
            return True

        return False

    def _is_documentation_file(self, file_id: str, content: str, language: str) -> bool:
        if language == "markdown":
            return True
        basename = ""
        return False

    def _is_config_file(self, file_id: str, content: str, language: str) -> bool:
        if language in ("yaml", "json", "toml"):
            return True
        return False

    def _build_embedding_text(self, chunk: CodeChunk) -> str:
        parts: list[str] = []
        if chunk.chunk_type:
            parts.append(f"[{chunk.chunk_type}]")
        if chunk.language:
            parts.append(f"({chunk.language})")
        if chunk.metadata_ and chunk.metadata_.get("name"):
            parts.append(chunk.metadata_["name"])
        parts.append(chunk.content or "")
        return " ".join(parts)

    async def _vector_search(
        self,
        query: str,
        repo_id: str,
        chunk_type: str | None,
        language: str | None,
        limit: int,
    ) -> list[dict]:
        if not self._vector_store or not self._embedding:
            return []

        try:
            vector = await self._embedding.embed(query)
            must_filters: list[dict] = [{"key": "repository_id", "match": {"value": str(repo_id)}}]
            if chunk_type:
                must_filters.append({"key": "chunk_type", "match": {"value": chunk_type}})
            if language:
                must_filters.append({"key": "language", "match": {"value": language}})

            search_result = await self._vector_store.search(
                collection=EMBEDDING_COLLECTION,
                query_vector=vector,
                limit=limit,
                query_filter={"must": must_filters} if must_filters else None,
            )

            results: list[dict] = []
            for point in (search_result or []):
                payload = getattr(point, "payload", None) or {}
                results.append({
                    "chunk_id": payload.get("chunk_id", str(getattr(point, "id", ""))),
                    "score": getattr(point, "score", 0.0),
                    "file_id": payload.get("file_id", ""),
                    "chunk_type": payload.get("chunk_type", ""),
                    "language": payload.get("language", ""),
                    "file_path": payload.get("file_path", ""),
                    "start_line": payload.get("start_line", 0),
                    "end_line": payload.get("end_line", 0),
                    "content_preview": payload.get("content_preview", ""),
                })
            return results
        except Exception as exc:
            logger.warning("Vector search failed: %s", exc)
            return []

    async def _lexical_search(
        self,
        query: str,
        repo_id: str,
        chunk_type: str | None,
        language: str | None,
        limit: int,
    ) -> list[dict]:
        keywords = [w.strip() for w in query.split() if w.strip()]
        if not keywords:
            return []

        conditions = [CodeChunk.repository_id == repo_id]
        if chunk_type:
            conditions.append(CodeChunk.chunk_type == chunk_type)
        if language:
            conditions.append(CodeChunk.language == language)

        keyword_conditions = []
        for kw in keywords:
            keyword_conditions.append(CodeChunk.content.ilike(f"%{kw}%"))

        if keyword_conditions:
            conditions.append(or_(*keyword_conditions))

        stmt = (
            select(CodeChunk)
            .where(and_(*conditions))
            .order_by(CodeChunk.token_count.desc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        chunks = result.scalars().all()

        scored: list[dict] = []
        for chunk in chunks:
            content_lower = (chunk.content or "").lower()
            match_count = sum(1 for kw in keywords if kw.lower() in content_lower)
            score = match_count / len(keywords) if keywords else 0.0
            scored.append({
                "chunk_id": str(chunk.id),
                "score": score,
                "file_id": str(chunk.file_id),
                "chunk_type": chunk.chunk_type,
                "language": chunk.language or "",
                "start_line": chunk.start_line or 0,
                "end_line": chunk.end_line or 0,
                "content_preview": (chunk.content[:200] if chunk.content else ""),
            })

        scored.sort(key=lambda r: r["score"], reverse=True)
        return scored[:limit]

    async def _load_file_content(self, code_file: CodeFile) -> str | None:
        """Load file content. In production, reads from disk or object store.
        Returns None if content is unavailable."""
        return None

    async def _load_file_symbols(self, file_id: UUID) -> list[CodeSymbol]:
        stmt = (
            select(CodeSymbol)
            .where(CodeSymbol.file_id == file_id)
            .order_by(CodeSymbol.start_line)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def _resolve_symbol(self, symbol_id: str) -> CodeSymbol | None:
        stmt = select(CodeSymbol).where(CodeSymbol.symbol_id == symbol_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()


# ─── RAGContextBuilder ─────────────────────────────────────────────────


class RAGContextBuilder:
    """Build a complete RAG context bundle for a natural-language query.

    Combines semantic search, symbol resolution, dependency graph traversal,
    test mapping, documentation retrieval, and recent change history.
    """

    def __init__(
        self,
        db_session: AsyncSession,
        embedding_service: Any | None = None,
        vector_store: Any | None = None,
        graph_store: Any | None = None,
    ) -> None:
        self._db = db_session
        self._embedding = embedding_service
        self._vector_store = vector_store
        self._graph_store = graph_store
        self._chunker = SemanticChunker(db_session, embedding_service, vector_store)

    async def build_context(
        self,
        query: str,
        repo_id: str,
        max_tokens: int = 4096,
    ) -> RAGContextBundle:
        """Build the full RAG context for a query."""
        if isinstance(repo_id, str):
            repo_id = UUID(repo_id)
        symbols = await self.get_relevant_symbols(query, repo_id, limit=10)
        files = await self.get_relevant_files(query, repo_id, limit=10)

        dependencies: dict = {}
        graph_relationships: list[dict] = []

        if symbols:
            top_sym = symbols[0]
            sym_id = top_sym.get("symbol_id", "")
            if sym_id:
                dependencies = await self.get_dependency_context(sym_id, depth=2)
                graph_relationships = await self._get_graph_relationships(sym_id)

        tests: list[dict] = []
        for sym in symbols[:5]:
            sym_id = sym.get("symbol_id", "")
            if sym_id:
                test_ctx = await self.get_test_context(sym_id)
                if test_ctx.get("tests"):
                    tests.extend(test_ctx["tests"])

        documentation: list[dict] = []
        for f in files[:3]:
            file_id = f.get("file_id", "")
            if file_id:
                doc_ctx = await self.get_documentation_context(file_id)
                if doc_ctx.get("documentation"):
                    documentation.extend(doc_ctx["documentation"])

        recent_changes = await self.get_recent_changes(repo_id, days=30)

        snippets = await self._build_snippets(query, repo_id, symbols, files)

        bundle = RAGContextBundle(
            query=query,
            symbols=symbols,
            files=files,
            dependencies=dependencies,
            graph_relationships=graph_relationships,
            tests=tests,
            documentation=documentation,
            recent_changes=recent_changes,
            snippets=snippets,
        )

        bundle = self._fit_to_budget(bundle, max_tokens)
        bundle.citations = self._build_citations(bundle)

        return bundle

    async def get_relevant_symbols(self, query: str, repo_id: str, limit: int = 10) -> list[dict]:
        """Semantic search for symbols matching the query."""
        keywords = [w.strip() for w in query.split() if w.strip()]

        conditions = [CodeSymbol.repository_id == repo_id]
        keyword_conditions = []
        for kw in keywords:
            keyword_conditions.append(
                or_(
                    CodeSymbol.name.ilike(f"%{kw}%"),
                    CodeSymbol.qualified_name.ilike(f"%{kw}%"),
                    CodeSymbol.signature.ilike(f"%{kw}%"),
                    CodeSymbol.docstring.ilike(f"%{kw}%"),
                )
            )
        if keyword_conditions:
            conditions.append(or_(*keyword_conditions))

        stmt = (
            select(CodeSymbol)
            .where(and_(*conditions))
            .limit(limit * 3)
        )
        result = await self._db.execute(stmt)
        symbols = result.scalars().all()

        scored: list[dict] = []
        for sym in symbols:
            score = self._score_symbol_match(sym, query)
            scored.append({
                "symbol_id": sym.symbol_id,
                "name": sym.name,
                "qualified_name": sym.qualified_name,
                "symbol_type": sym.symbol_type,
                "language": sym.language or "",
                "file_id": str(sym.file_id),
                "start_line": sym.start_line,
                "end_line": sym.end_line,
                "signature": sym.signature or "",
                "docstring": (sym.docstring or "")[:300],
                "score": score,
            })

        scored.sort(key=lambda s: s["score"], reverse=True)
        return self._deduplicate(scored)[:limit]

    async def get_relevant_files(self, query: str, repo_id: str, limit: int = 10) -> list[dict]:
        """Semantic search for files matching the query."""
        keywords = [w.strip() for w in query.split() if w.strip()]

        conditions = [CodeFile.repository_id == repo_id]
        keyword_conditions = []
        for kw in keywords:
            keyword_conditions.append(
                or_(
                    CodeFile.file_path.ilike(f"%{kw}%"),
                    CodeFile.file_name.ilike(f"%{kw}%"),
                )
            )
        if keyword_conditions:
            conditions.append(or_(*keyword_conditions))

        stmt = (
            select(CodeFile)
            .where(and_(*conditions))
            .limit(limit * 3)
        )
        result = await self._db.execute(stmt)
        files = result.scalars().all()

        scored: list[dict] = []
        for f in files:
            score = self._score_file_match(f, query)
            scored.append({
                "file_id": str(f.id),
                "file_path": f.file_path,
                "file_name": f.file_name,
                "language": f.language or "",
                "line_count": f.line_count or 0,
                "symbol_count": f.symbol_count or 0,
                "score": score,
            })

        scored.sort(key=lambda f: f["score"], reverse=True)
        return self._deduplicate(scored)[:limit]

    async def get_dependency_context(self, symbol_id: str, depth: int = 2) -> dict:
        """Get dependencies and dependents of a symbol via the call/import graph."""
        sym = await self._resolve_symbol(symbol_id)
        if sym is None:
            return {"depends_on": [], "depended_by": [], "calls": [], "called_by": []}

        depends_on = await self._get_dependencies(sym.id, direction="outgoing", depth=depth)
        depended_by = await self._get_dependencies(sym.id, direction="incoming", depth=1)

        calls = await self._get_callees(sym.id, depth=depth)
        called_by = await self._get_callers(sym.id, depth=1)

        return {
            "depends_on": depends_on,
            "depended_by": depended_by,
            "calls": calls,
            "called_by": called_by,
        }

    async def get_test_context(self, symbol_id: str) -> dict:
        """Get tests that cover a given symbol."""
        sym = await self._resolve_symbol(symbol_id)
        if sym is None:
            return {"tests": [], "test_files": []}

        stmt = (
            select(CodeTest)
            .where(
                CodeTest.repository_id == sym.repository_id,
                CodeTest.source_symbol_name == sym.name,
            )
        )
        result = await self._db.execute(stmt)
        tests = result.scalars().all()

        test_dicts: list[dict] = []
        test_file_ids: set[str] = set()

        for t in tests:
            test_dicts.append({
                "test_id": str(t.id),
                "test_name": t.test_name,
                "test_type": t.test_type,
                "file_id": str(t.file_id),
                "source_symbol_name": t.source_symbol_name or "",
                "framework": t.framework or "",
            })
            test_file_ids.add(str(t.file_id))

        test_files: list[dict] = []
        if test_file_ids:
            file_stmt = select(CodeFile).where(CodeFile.id.in_([UUID(fid) for fid in test_file_ids]))
            file_result = await self._db.execute(file_stmt)
            for f in file_result.scalars().all():
                test_files.append({
                    "file_id": str(f.id),
                    "file_path": f.file_path,
                    "language": f.language or "",
                })

        return {"tests": test_dicts, "test_files": test_files}

    async def get_documentation_context(self, file_id: str) -> dict:
        """Get documentation chunks related to a file."""
        stmt = (
            select(CodeChunk)
            .where(
                CodeChunk.file_id == file_id,
                CodeChunk.chunk_type == "documentation",
            )
            .order_by(CodeChunk.start_line)
        )
        result = await self._db.execute(stmt)
        chunks = result.scalars().all()

        documentation: list[dict] = []
        for chunk in chunks:
            documentation.append({
                "chunk_id": str(chunk.id),
                "content": chunk.content[:500] if chunk.content else "",
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "token_count": chunk.token_count or 0,
            })

        return {"documentation": documentation}

    async def get_recent_changes(self, repo_id: str, days: int = 30) -> list[dict]:
        """Get recent git history for a repository."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        stmt = (
            select(CodeHistory)
            .where(
                CodeHistory.repository_id == repo_id,
                CodeHistory.commit_date >= cutoff,
            )
            .order_by(CodeHistory.commit_date.desc())
            .limit(50)
        )
        result = await self._db.execute(stmt)
        history = result.scalars().all()

        seen_commits: dict[str, dict] = {}
        changes: list[dict] = []

        for h in history:
            sha = h.commit_sha
            if sha not in seen_commits:
                seen_commits[sha] = {
                    "commit_sha": sha,
                    "author_name": h.author_name or "",
                    "author_email": h.author_email or "",
                    "message": (h.message or "")[:200],
                    "commit_date": h.commit_date.isoformat() if h.commit_date else "",
                    "files_changed": [],
                }
            seen_commits[sha]["files_changed"].append({
                "file_path": h.file_path,
                "change_type": h.change_type or "",
                "lines_added": h.lines_added,
                "lines_deleted": h.lines_deleted,
            })

        for sha, entry in seen_commits.items():
            changes.append(entry)

        return changes[:20]

    def _rank_results(self, results: list[dict], query: str) -> list[dict]:
        """Rerank results by multi-factor relevance."""
        query_lower = query.lower()
        query_tokens = set(query_lower.split())

        for r in results:
            base_score = r.get("score", 0.0)

            name = (r.get("name") or r.get("file_path") or "").lower()
            name_overlap = len(query_tokens & set(name.split())) / max(len(query_tokens), 1)

            doc = (r.get("docstring") or r.get("signature") or "").lower()
            doc_overlap = len(query_tokens & set(doc.split())) / max(len(query_tokens), 1)

            r["score"] = base_score * 0.5 + name_overlap * 0.3 + doc_overlap * 0.2

        results.sort(key=lambda r: r.get("score", 0), reverse=True)
        return results

    def _deduplicate(self, results: list[dict]) -> list[dict]:
        """Remove duplicate results by symbol_id or file_id."""
        seen: set[str] = set()
        deduped: list[dict] = []
        for r in results:
            key = r.get("symbol_id") or r.get("file_id") or r.get("chunk_id") or ""
            if key and key not in seen:
                seen.add(key)
                deduped.append(r)
            elif not key:
                deduped.append(r)
        return deduped

    def _fit_to_budget(self, bundle: RAGContextBundle, max_tokens: int) -> RAGContextBundle:
        """Trim results to fit within the token budget."""
        remaining = max_tokens
        estimated = 0

        symbol_budget = int(max_tokens * 0.30)
        trimmed_symbols: list[dict] = []
        for sym in bundle.symbols:
            sym_tokens = self._count_tokens_dict(sym)
            if estimated + sym_tokens > symbol_budget:
                break
            trimmed_symbols.append(sym)
            estimated += sym_tokens
        bundle.symbols = trimmed_symbols

        file_budget = int(max_tokens * 0.20)
        trimmed_files: list[dict] = []
        for f in bundle.files:
            f_tokens = self._count_tokens_dict(f)
            if estimated + f_tokens > file_budget:
                break
            trimmed_files.append(f)
            estimated += f_tokens
        bundle.files = trimmed_files

        snippet_budget = int(max_tokens * 0.30)
        trimmed_snippets: list[dict] = []
        for s in bundle.snippets:
            s_tokens = self._count_tokens_dict(s)
            if estimated + s_tokens > snippet_budget:
                break
            trimmed_snippets.append(s)
            estimated += s_tokens
        bundle.snippets = trimmed_snippets

        test_budget = int(max_tokens * 0.10)
        trimmed_tests: list[dict] = []
        for t in bundle.tests:
            t_tokens = self._count_tokens_dict(t)
            if estimated + t_tokens > test_budget:
                break
            trimmed_tests.append(t)
            estimated += t_tokens
        bundle.tests = trimmed_tests

        doc_budget = int(max_tokens * 0.10)
        trimmed_docs: list[dict] = []
        for d in bundle.documentation:
            d_tokens = self._count_tokens_dict(d)
            if estimated + d_tokens > doc_budget:
                break
            trimmed_docs.append(d)
            estimated += d_tokens
        bundle.documentation = trimmed_docs

        bundle.total_tokens = estimated
        return bundle

    def _build_citations(self, bundle: RAGContextBundle) -> list[dict]:
        """Build citation list from bundle contents."""
        citations: list[dict] = []
        seen: set[str] = set()

        for sym in bundle.symbols:
            sym_id = sym.get("symbol_id", "")
            if sym_id and sym_id not in seen:
                seen.add(sym_id)
                citations.append({
                    "type": "symbol",
                    "id": sym_id,
                    "name": sym.get("name", ""),
                    "file_path": sym.get("qualified_name", ""),
                    "line": sym.get("start_line"),
                })

        for f in bundle.files:
            fid = f.get("file_id", "")
            if fid and fid not in seen:
                seen.add(fid)
                citations.append({
                    "type": "file",
                    "id": fid,
                    "file_path": f.get("file_path", ""),
                })

        for s in bundle.snippets:
            chunk_id = s.get("chunk_id", "")
            if chunk_id and chunk_id not in seen:
                seen.add(chunk_id)
                citations.append({
                    "type": "chunk",
                    "id": chunk_id,
                    "file_path": s.get("file_path", ""),
                    "line": s.get("start_line"),
                })

        return citations

    # ── Private helpers ───────────────────────────────────────────────

    async def _build_snippets(
        self,
        query: str,
        repo_id: str,
        symbols: list[dict],
        files: list[dict],
    ) -> list[dict]:
        """Retrieve code snippets from chunks matching the query."""
        chunk_results = await self._chunker.search_chunks(
            query=query,
            repo_id=repo_id,
            limit=10,
        )

        snippets: list[dict] = []
        for cr in chunk_results:
            chunk_id = cr.get("chunk_id", "")
            stmt = select(CodeChunk).where(CodeChunk.id == chunk_id)
            result = await self._db.execute(stmt)
            chunk = result.scalar_one_or_none()
            if chunk is None:
                continue

            snippets.append({
                "chunk_id": chunk_id,
                "content": chunk.content[:1000] if chunk.content else "",
                "file_id": str(chunk.file_id),
                "symbol_id": str(chunk.symbol_id) if chunk.symbol_id else None,
                "chunk_type": chunk.chunk_type,
                "language": chunk.language or "",
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "score": cr.get("score", 0.0),
                "retrieval_source": cr.get("retrieval_source", ""),
            })

        return snippets

    async def _get_graph_relationships(self, symbol_id: str) -> list[dict]:
        """Query the Neo4j graph store for relationships around a symbol."""
        if not self._graph_store:
            return []

        try:
            query = """
            MATCH (s {id: $symbol_id})-[r]-(target)
            RETURN type(r) AS rel_type, labels(target) AS target_labels,
                   target.id AS target_id, target.name AS target_name
            LIMIT 30
            """
            result = await self._graph_store.run(query, symbol_id=symbol_id)
            relationships: list[dict] = []
            async for record in result:
                relationships.append({
                    "rel_type": record.get("rel_type", ""),
                    "target_labels": record.get("target_labels", []),
                    "target_id": record.get("target_id", ""),
                    "target_name": record.get("target_name", ""),
                })
            return relationships
        except Exception as exc:
            logger.debug("Graph store query failed: %s", exc)
            return []

    async def _get_dependencies(
        self, symbol_db_id: UUID, direction: str, depth: int
    ) -> list[dict]:
        """Walk the code_imports / code_calls tables for dependencies."""
        from app.code_intelligence.models import CodeCall, CodeImport

        deps: list[dict] = []
        visited: set[str] = set()
        queue: list[tuple[UUID, int]] = [(symbol_db_id, 0)]

        while queue:
            current_id, current_depth = queue.pop(0)
            if current_depth >= depth:
                continue
            key = str(current_id)
            if key in visited:
                continue
            visited.add(key)

            if direction in ("outgoing", "both"):
                call_stmt = (
                    select(CodeCall)
                    .where(CodeCall.caller_symbol_id == current_id)
                    .limit(20)
                )
                call_result = await self._db.execute(call_stmt)
                for call in call_result.scalars().all():
                    callee_id = call.callee_symbol_id
                    if callee_id:
                        sym_stmt = select(CodeSymbol).where(CodeSymbol.id == callee_id)
                        sym_result = await self._db.execute(sym_stmt)
                        callee_sym = sym_result.scalar_one_or_none()
                        if callee_sym:
                            deps.append({
                                "symbol_id": callee_sym.symbol_id,
                                "name": callee_sym.name,
                                "qualified_name": callee_sym.qualified_name,
                                "type": "call",
                                "depth": current_depth + 1,
                            })
                            if callee_id not in visited:
                                queue.append((callee_id, current_depth + 1))

                imp_stmt = (
                    select(CodeImport)
                    .where(CodeImport.source_file_id == current_id)
                    .limit(20)
                )
                imp_result = await self._db.execute(imp_stmt)
                for imp in imp_result.scalars().all():
                    if imp.imported_symbol_id:
                        sym_stmt = select(CodeSymbol).where(CodeSymbol.id == imp.imported_symbol_id)
                        sym_result = await self._db.execute(sym_stmt)
                        imp_sym = sym_result.scalar_one_or_none()
                        if imp_sym:
                            deps.append({
                                "symbol_id": imp_sym.symbol_id,
                                "name": imp_sym.name,
                                "qualified_name": imp_sym.qualified_name,
                                "type": "import",
                                "depth": current_depth + 1,
                            })

            if direction in ("incoming", "both"):
                call_stmt = (
                    select(CodeCall)
                    .where(CodeCall.callee_symbol_id == current_id)
                    .limit(20)
                )
                call_result = await self._db.execute(call_stmt)
                for call in call_result.scalars().all():
                    caller_id = call.caller_symbol_id
                    if caller_id:
                        sym_stmt = select(CodeSymbol).where(CodeSymbol.id == caller_id)
                        sym_result = await self._db.execute(sym_stmt)
                        caller_sym = sym_result.scalar_one_or_none()
                        if caller_sym:
                            deps.append({
                                "symbol_id": caller_sym.symbol_id,
                                "name": caller_sym.name,
                                "qualified_name": caller_sym.qualified_name,
                                "type": "called_by",
                                "depth": current_depth + 1,
                            })

        return deps

    async def _get_callees(self, symbol_db_id: UUID, depth: int) -> list[dict]:
        """Get symbols called by this symbol."""
        from app.code_intelligence.models import CodeCall

        callees: list[dict] = []
        visited: set[str] = set()
        queue: list[tuple[UUID, int]] = [(symbol_db_id, 0)]

        while queue:
            current_id, current_depth = queue.pop(0)
            if current_depth >= depth:
                continue
            key = str(current_id)
            if key in visited:
                continue
            visited.add(key)

            stmt = select(CodeCall).where(CodeCall.caller_symbol_id == current_id).limit(20)
            result = await self._db.execute(stmt)
            for call in result.scalars().all():
                callee_id = call.callee_symbol_id
                if callee_id:
                    sym_stmt = select(CodeSymbol).where(CodeSymbol.id == callee_id)
                    sym_result = await self._db.execute(sym_stmt)
                    callee_sym = sym_result.scalar_one_or_none()
                    if callee_sym:
                        callees.append({
                            "symbol_id": callee_sym.symbol_id,
                            "name": callee_sym.name,
                            "qualified_name": callee_sym.qualified_name,
                            "depth": current_depth + 1,
                        })
                        if callee_id not in visited:
                            queue.append((callee_id, current_depth + 1))

        return callees

    async def _get_callers(self, symbol_db_id: UUID, depth: int) -> list[dict]:
        """Get symbols that call this symbol."""
        from app.code_intelligence.models import CodeCall

        callers: list[dict] = []
        visited: set[str] = set()
        queue: list[tuple[UUID, int]] = [(symbol_db_id, 0)]

        while queue:
            current_id, current_depth = queue.pop(0)
            if current_depth >= depth:
                continue
            key = str(current_id)
            if key in visited:
                continue
            visited.add(key)

            stmt = select(CodeCall).where(CodeCall.callee_symbol_id == current_id).limit(20)
            result = await self._db.execute(stmt)
            for call in result.scalars().all():
                caller_id = call.caller_symbol_id
                if caller_id:
                    sym_stmt = select(CodeSymbol).where(CodeSymbol.id == caller_id)
                    sym_result = await self._db.execute(sym_stmt)
                    caller_sym = sym_result.scalar_one_or_none()
                    if caller_sym:
                        callers.append({
                            "symbol_id": caller_sym.symbol_id,
                            "name": caller_sym.name,
                            "qualified_name": caller_sym.qualified_name,
                            "depth": current_depth + 1,
                        })
                        if caller_id not in visited:
                            queue.append((caller_id, current_depth + 1))

        return callers

    async def _resolve_symbol(self, symbol_id: str) -> CodeSymbol | None:
        stmt = select(CodeSymbol).where(CodeSymbol.symbol_id == symbol_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    def _score_symbol_match(self, sym: CodeSymbol, query: str) -> float:
        """Multi-factor scoring for symbol relevance."""
        query_lower = query.lower()
        query_tokens = set(query_lower.split())

        name = (sym.name or "").lower()
        name_exact = 1.0 if query_lower == name else 0.0
        name_contains = 0.8 if query_lower in name else 0.0
        name_token_overlap = len(query_tokens & set(name.split())) / max(len(query_tokens), 1) * 0.6
        name_score = max(name_exact, name_contains, name_token_overlap)

        qname = (sym.qualified_name or "").lower()
        qname_score = 0.3 if query_lower in qname else 0.0

        sig = (sym.signature or "").lower()
        sig_score = 0.2 if any(t in sig for t in query_tokens) else 0.0

        doc = (sym.docstring or "").lower()
        doc_score = 0.15 if any(t in doc for t in query_tokens) else 0.0

        type_bonus = 0.1 if sym.symbol_type in (
            SymbolType.FUNCTION.value, SymbolType.CLASS.value, SymbolType.METHOD.value
        ) else 0.0

        return min(1.0, name_score + qname_score + sig_score + doc_score + type_bonus)

    def _score_file_match(self, f: CodeFile, query: str) -> float:
        """Multi-factor scoring for file relevance."""
        query_lower = query.lower()
        query_tokens = set(query_lower.split())

        path = (f.file_path or "").lower()
        path_score = 0.5 if query_lower in path else 0.0
        path_token_score = len(query_tokens & set(path.replace("/", " ").replace("\\", " ").replace(".", " ").replace("_", " ").replace("-", " ").split())) / max(len(query_tokens), 1) * 0.4

        name = (f.file_name or "").lower()
        name_score = 0.4 if query_lower in name else 0.0

        type_bonus = 0.1 if f.is_test_file else 0.0

        return min(1.0, max(path_score, path_token_score, name_score) + type_bonus)

    @staticmethod
    def _count_tokens_dict(d: dict) -> int:
        """Estimate token count from a dict (sum of string values)."""
        total = 0
        for v in d.values():
            if isinstance(v, str):
                total += len(v) // 4
            elif isinstance(v, (int, float)):
                total += 1
        return max(total, 1)
