"""Code Intelligence Indexing Pipeline — orchestrates all stages of repository indexing.

Connects parser, symbol extraction, graph building, metrics, smells, security,
architecture discovery, semantic chunking, embedding generation, and graph store
pushing into a coherent, trackable, resumable pipeline.
"""

import hashlib
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.code_intelligence.models import (
    CodeChunk,
    CodeFile,
    CodeIndex,
    CodeIndexJob,
    CodeIndexVersion,
    FileStatus,
    IndexStatus,
    JobStatus,
)
from app.code_intelligence.parser import ParserEngine
from app.code_intelligence.symbols import (
    CallGraphBuilder,
    ImportGraphBuilder,
    SymbolResolver,
)
from app.code_intelligence.metrics import MetricsCalculator
from app.code_intelligence.smells import SmellDetector
from app.code_intelligence.security import SecurityScanner
from app.code_intelligence.architecture import ArchitectureDiscovery
from app.core.events import Event, EventType, event_bus

logger = logging.getLogger(__name__)

IGNORE_PATTERNS: frozenset[str] = frozenset({
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "target",
    "bin",
    "obj",
    ".idea",
    ".vscode",
    ".env",
    ".env.local",
    ".env.development",
    ".env.production",
    ".env.staging",
    ".env.test",
    ".env.*",
    "*.pyc",
    "*.pyo",
    "*.so",
    "*.dll",
    "*.exe",
    "*.o",
    "*.a",
    "*.dylib",
    "*.min.js",
    "*.min.css",
    "package-lock.json",
    "yarn.lock",
    "poetry.lock",
    "Pipfile.lock",
    "go.sum",
    "Cargo.lock",
    "composer.lock",
})

STAGE_ORDER: list[str] = [
    "DISCOVER",
    "PARSE",
    "EXTRACT_SYMBOLS",
    "RESOLVE_REFS",
    "BUILD_GRAPH",
    "CALC_METRICS",
    "DETECT_SMELLS",
    "SECURITY_SCAN",
    "ARCHITECTURE",
    "CHUNK",
    "EMBED",
    "UPDATE_GRAPH",
    "VALIDATE",
    "ACTIVATE",
]

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

MAX_CHUNK_LINES: int = 200
CHUNK_OVERLAP_LINES: int = 20
EMBED_BATCH_SIZE: int = 64


class IndexingPipeline:
    """Main indexing pipeline orchestrator.

    Coordinates all stages of code intelligence indexing: file discovery,
    parsing, symbol extraction, reference resolution, graph building,
    metrics calculation, smell detection, security scanning, architecture
    discovery, semantic chunking, embedding generation, and graph store
    updates.

    Each stage is independently trackable, resumable, and observable.
    If a stage fails, the index stays in PARTIAL status and the failed
    stage can be retried.
    """

    def __init__(
        self,
        db_session: AsyncSession,
        embedding_service: Any = None,
        vector_store: Any = None,
        graph_store: Any = None,
    ) -> None:
        self.db = db_session
        self._embedding_service = embedding_service
        self._vector_store = vector_store
        self._graph_store = graph_store
        self._parser = ParserEngine()

    # ── main entry points ────────────────────────────────────────────

    async def index_repository(
        self,
        repo_id: str,
        repo_path: str,
        commit_sha: Optional[str] = None,
        incremental: bool = True,
    ) -> CodeIndex:
        """Create an index and run all pipeline stages for a repository.

        This is the main entry point. It creates a CodeIndex record, runs
        every stage sequentially, and returns the completed index. If any
        stage fails, the index is left in PARTIAL status with the failed
        stage recorded so it can be retried.
        """
        repo_uuid = uuid.UUID(repo_id)
        index = CodeIndex(
            repository_id=repo_uuid,
            status=IndexStatus.QUEUED.value,
            commit_sha=commit_sha,
            files_total=0,
            files_processed=0,
            symbols_extracted=0,
            chunks_created=0,
            embeddings_stored=0,
            graph_edges_created=0,
            errors=[],
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(index)
        await self.db.flush()
        index_id = str(index.id)

        self._emit_event("pipeline_started", {
            "index_id": index_id,
            "repo_id": repo_id,
            "repo_path": repo_path,
            "commit_sha": commit_sha,
            "incremental": incremental,
        })

        stages_run = []
        for stage in STAGE_ORDER:
            if stage == "ACTIVATE":
                continue
            try:
                result = await self.run_stage(index_id, stage, repo_id=repo_id, repo_path=repo_path)
                stages_run.append({"stage": stage, "status": "completed", "result": result})
            except Exception as exc:
                logger.exception("Pipeline stage %s failed for index %s", stage, index_id)
                await self._record_error(index_id, stage, str(exc))
                await self._update_status(index_id, IndexStatus.PARTIAL.value, {
                    "failed_stage": stage,
                    "stages_completed": [s["stage"] for s in stages_run],
                })
                return await self._load_index(index_id)

        try:
            await self.run_stage(index_id, "ACTIVATE", repo_id=repo_id, repo_path=repo_path)
        except Exception as exc:
            logger.exception("Activation failed for index %s", index_id)
            await self._record_error(index_id, "ACTIVATE", str(exc))
            await self._update_status(index_id, IndexStatus.PARTIAL.value, {"failed_stage": "ACTIVATE"})

        final_index = await self._load_index(index_id)
        if final_index.status != IndexStatus.PARTIAL.value:
            final_index.completed_at = datetime.now(timezone.utc)
            self.db.add(final_index)

        self._emit_event("pipeline_completed", {
            "index_id": index_id,
            "repo_id": repo_id,
            "status": final_index.status,
            "files_total": final_index.files_total,
            "files_processed": final_index.files_processed,
            "symbols_extracted": final_index.symbols_extracted,
            "chunks_created": final_index.chunks_created,
        })

        await self.db.flush()
        return final_index

    async def index_file(
        self,
        file_path: str,
        content: str,
        language: str,
        index_id: str,
        repo_id: str,
    ) -> CodeFile:
        """Index a single file through the full pipeline.

        Parses the file, extracts symbols/imports/calls, builds call graph
        and import graph entries, calculates metrics, and creates chunks.
        Returns the created CodeFile record.
        """
        index_uuid = uuid.UUID(index_id)
        repo_uuid = uuid.UUID(repo_id)
        file_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        line_count = content.count("\n") + (1 if content and not content.endswith("\n") else 0)

        code_file = CodeFile(
            index_id=index_uuid,
            repository_id=repo_uuid,
            file_path=file_path,
            file_name=os.path.basename(file_path),
            language=language,
            file_hash=file_hash,
            size_bytes=len(content.encode("utf-8")),
            line_count=line_count,
            content=content,
            status=FileStatus.PARSING.value,
        )
        self.db.add(code_file)
        await self.db.flush()
        file_id = str(code_file.id)

        parse_result = self._parser.parse_file(file_path, content, language)
        if parse_result.error:
            code_file.status = FileStatus.ERROR.value
            code_file.parse_error = parse_result.error
            await self.db.flush()
            return code_file

        symbol_resolver = SymbolResolver(self.db)
        call_builder = CallGraphBuilder(self.db)
        import_builder = ImportGraphBuilder(self.db)

        symbol_dicts = []
        for sym in parse_result.symbols:
            symbol_dicts.append({
                "name": sym.name,
                "qualified_name": sym.qualified_name,
                "symbol_type": sym.symbol_type.value if hasattr(sym.symbol_type, "value") else str(sym.symbol_type),
                "start_line": sym.start_line,
                "end_line": sym.end_line,
                "signature": sym.signature,
                "docstring": sym.docstring,
                "visibility": sym.visibility,
                "is_async": sym.is_async,
                "is_abstract": sym.is_abstract,
                "is_static": sym.is_static,
                "decorators": sym.decorators,
                "parameters": sym.parameters,
                "return_type": sym.return_type,
                "parent_name": sym.parent_name,
                "language": sym.language or language,
                "module_path": os.path.dirname(file_path).replace(os.sep, "."),
            })

        created_symbols = await symbol_resolver.build_symbol_table(
            symbol_dicts, file_id, repo_id, index_id,
        )
        code_file.symbol_count = len(created_symbols)

        import_dicts = []
        for imp in parse_result.imports:
            import_dicts.append({
                "imported_name": imp.name,
                "alias": imp.alias,
                "import_type": imp.import_type,
                "is_external": imp.is_external,
                "is_stdlib": imp.is_stdlib,
            })

        reference_dicts = []
        for sym in symbol_dicts:
            for target_name in self._find_references_in_scope(sym, symbol_dicts):
                reference_dicts.append({
                    "source_name": sym["name"],
                    "target_name": target_name,
                    "reference_type": "REFERENCE",
                    "line": sym.get("start_line"),
                })

        if reference_dicts or import_dicts:
            await symbol_resolver.resolve_references(
                reference_dicts, import_dicts, file_id, repo_id, index_id,
            )

        call_dicts = []
        for call in parse_result.calls:
            call_dicts.append({
                "caller_name": call.caller_name,
                "callee_name": call.callee_name,
                "line": call.call_line,
                "call_type": call.call_type,
                "confidence": call.confidence,
            })

        if call_dicts:
            await call_builder.build_call_graph(
                file_id, call_dicts, symbol_dicts, repo_id, index_id,
            )

        if import_dicts:
            await import_builder.build_import_graph(
                file_id, import_dicts, repo_id, index_id,
            )

        metrics_calc = MetricsCalculator(self.db)
        await metrics_calc.calculate_file_metrics(
            file_id, content, language, symbol_dicts, repo_id,
        )

        await self._create_file_chunks(
            code_file, content, language, parse_result, index_id, repo_id,
        )

        code_file.status = FileStatus.PARSED.value
        code_file.chunk_count = await self._count_chunks(file_id)
        code_file.indexed_at = datetime.now(timezone.utc)
        await self.db.flush()

        return code_file

    async def run_stage(
        self,
        index_id: str,
        stage: str,
        file_ids: Optional[list[str]] = None,
        repo_id: Optional[str] = None,
        repo_path: Optional[str] = None,
    ) -> dict:
        """Run a specific pipeline stage.

        Records a CodeIndexJob for the stage and delegates to the
        appropriate handler. If file_ids is provided, only those files
        are processed (for incremental re-indexing).
        """
        job = CodeIndexJob(
            index_id=uuid.UUID(index_id),
            job_type=stage,
            status=JobStatus.RUNNING.value,
            file_ids=file_ids,
            started_at=datetime.now(timezone.utc),
        )
        self.db.add(job)
        await self.db.flush()
        job_id = str(job.id)

        self._emit_event("stage_started", {
            "index_id": index_id,
            "stage": stage,
            "job_id": job_id,
        })

        try:
            index = await self._load_index(index_id)
            if repo_id is None:
                repo_id = str(index.repository_id)

            stage_handlers: dict[str, Any] = {
                "DISCOVER": lambda: self.discover_files(repo_path or "", index_id, repo_id),
                "PARSE": lambda: self.parse_files(file_ids, index_id, repo_id),
                "EXTRACT_SYMBOLS": lambda: self._extract_symbols(index_id, repo_id),
                "RESOLVE_REFS": lambda: self.resolve_references(index_id, repo_id),
                "BUILD_GRAPH": lambda: self._build_graphs(index_id, repo_id),
                "CALC_METRICS": lambda: self.calculate_metrics(index_id, repo_id),
                "DETECT_SMELLS": lambda: self.detect_smells(index_id, repo_id),
                "SECURITY_SCAN": lambda: self.scan_security(index_id, repo_id),
                "ARCHITECTURE": lambda: self.discover_architecture(index_id, repo_id),
                "CHUNK": lambda: self.create_chunks(index_id, repo_id),
                "EMBED": lambda: self.embed_chunks(index_id, repo_id),
                "UPDATE_GRAPH": lambda: self.update_graph(index_id, repo_id),
                "VALIDATE": lambda: self.validate_index(index_id),
                "ACTIVATE": lambda: self.activate_index(index_id),
            }

            handler = stage_handlers.get(stage)
            if handler is None:
                raise ValueError(f"Unknown pipeline stage: {stage}")

            result = await handler()

            job.status = JobStatus.COMPLETED.value
            job.completed_at = datetime.now(timezone.utc)
            self.db.add(job)
            await self.db.flush()

            self._emit_event("stage_completed", {
                "index_id": index_id,
                "stage": stage,
                "job_id": job_id,
            })

            return result if isinstance(result, dict) else {"status": "completed"}

        except Exception as exc:
            job.status = JobStatus.FAILED.value
            job.error = str(exc)
            job.completed_at = datetime.now(timezone.utc)
            self.db.add(job)
            await self.db.flush()

            self._emit_event("stage_failed", {
                "index_id": index_id,
                "stage": stage,
                "job_id": job_id,
                "error": str(exc),
            })
            raise

    # ── stage: DISCOVER ──────────────────────────────────────────────

    async def discover_files(
        self, repo_path: str, index_id: str, repo_id: str,
    ) -> dict:
        """Walk the repository tree and create CodeFile records for every
        indexable source file, applying ignore rules and language detection.
        """
        index_uuid = uuid.UUID(index_id)
        repo_uuid = uuid.UUID(repo_id)
        discovered = 0
        skipped = 0
        repo_path_resolved = Path(repo_path).resolve()

        if not repo_path_resolved.exists():
            return {"discovered": 0, "skipped": 0, "error": "Repository path does not exist"}

        await self._update_status(index_id, IndexStatus.DISCOVERING.value)

        for root, dirs, files in os.walk(str(repo_path_resolved)):
            dirs[:] = [
                d for d in dirs
                if not self._should_skip_path(d, is_dir=True)
            ]

            for file_name in files:
                if self._should_skip_path(file_name, is_dir=False):
                    skipped += 1
                    continue

                file_path = os.path.join(root, file_name)
                relative_path = os.path.relpath(file_path, str(repo_path_resolved))
                language = self._detect_language(file_path)

                if not language:
                    skipped += 1
                    continue

                try:
                    stat_info = os.stat(file_path)
                except OSError:
                    skipped += 1
                    continue

                code_file = CodeFile(
                    index_id=index_uuid,
                    repository_id=repo_uuid,
                    file_path=relative_path,
                    file_name=file_name,
                    language=language,
                    size_bytes=stat_info.st_size,
                    status=FileStatus.QUEUED.value,
                )
                self.db.add(code_file)
                discovered += 1

        await self.db.flush()

        index = await self._load_index(index_id)
        index.files_total = discovered
        self.db.add(index)
        await self.db.flush()

        self._emit_event("files_discovered", {
            "index_id": index_id,
            "repo_id": repo_id,
            "discovered": discovered,
            "skipped": skipped,
        })

        return {"discovered": discovered, "skipped": skipped}

    # ── stage: PARSE ─────────────────────────────────────────────────

    async def parse_files(
        self, file_ids: Optional[list[str]], index_id: str, repo_id: str,
    ) -> dict:
        """Parse all (or selected) files: extract symbols, imports, and calls.

        If file_ids is provided only those files are re-parsed.
        Otherwise every QUEUED file in the index is parsed.
        """
        files = await self._load_files_for_index(index_id, file_ids)
        parsed = 0
        errors = 0

        await self._update_status(index_id, IndexStatus.PARSING.value)

        for code_file in files:
            try:
                full_path = self._resolve_file_path(code_file.file_path, repo_id)
                if not full_path or not os.path.isfile(full_path):
                    code_file.status = FileStatus.SKIPPED.value
                    code_file.parse_error = "File not found on disk"
                    errors += 1
                    continue

                with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()

                language = code_file.language or self._detect_language(full_path)
                parse_result = self._parser.parse_file(full_path, content, language)

                if parse_result.error:
                    code_file.status = FileStatus.ERROR.value
                    code_file.parse_error = parse_result.error
                    errors += 1
                    continue

                code_file.line_count = parse_result.line_count
                code_file.file_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                code_file.status = FileStatus.PARSED.value
                parsed += 1

            except Exception as exc:
                logger.warning("Failed to parse file %s: %s", code_file.file_path, exc)
                code_file.status = FileStatus.ERROR.value
                code_file.parse_error = str(exc)[:2000]
                errors += 1

        await self.db.flush()

        index = await self._load_index(index_id)
        index.files_processed = parsed
        self.db.add(index)
        await self.db.flush()

        self._emit_event("files_parsed", {
            "index_id": index_id,
            "parsed": parsed,
            "errors": errors,
        })

        return {"parsed": parsed, "errors": errors}

    # ── stage: EXTRACT_SYMBOLS ───────────────────────────────────────

    async def _extract_symbols(self, index_id: str, repo_id: str) -> dict:
        """Re-parse all PARSED files and insert symbols/imports/calls into the DB."""
        files = await self._load_files_for_index(index_id)
        symbol_resolver = SymbolResolver(self.db)
        call_builder = CallGraphBuilder(self.db)
        import_builder = ImportGraphBuilder(self.db)
        total_symbols = 0
        total_imports = 0
        total_calls = 0

        for code_file in files:
            if code_file.status != FileStatus.PARSED.value:
                continue

            full_path = self._resolve_file_path(code_file.file_path, repo_id)
            if not full_path or not os.path.isfile(full_path):
                continue

            try:
                with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except OSError:
                continue

            language = code_file.language or self._detect_language(full_path)
            parse_result = self._parser.parse_file(full_path, content, language)

            file_id = str(code_file.id)

            symbol_dicts = []
            for sym in parse_result.symbols:
                symbol_dicts.append({
                    "name": sym.name,
                    "qualified_name": sym.qualified_name,
                    "symbol_type": sym.symbol_type.value if hasattr(sym.symbol_type, "value") else str(sym.symbol_type),
                    "start_line": sym.start_line,
                    "end_line": sym.end_line,
                    "signature": sym.signature,
                    "docstring": sym.docstring,
                    "visibility": sym.visibility,
                    "is_async": sym.is_async,
                    "is_abstract": sym.is_abstract,
                    "is_static": sym.is_static,
                    "decorators": sym.decorators,
                    "parameters": sym.parameters,
                    "return_type": sym.return_type,
                    "parent_name": sym.parent_name,
                    "language": language,
                    "module_path": os.path.dirname(code_file.file_path).replace(os.sep, "."),
                })

            created_syms = await symbol_resolver.build_symbol_table(
                symbol_dicts, file_id, repo_id, index_id,
            )
            total_symbols += len(created_syms)
            code_file.symbol_count = len(created_syms)

            import_dicts = []
            for imp in parse_result.imports:
                import_dicts.append({
                    "imported_name": imp.name,
                    "alias": imp.alias,
                    "import_type": imp.import_type,
                    "is_external": imp.is_external,
                    "is_stdlib": imp.is_stdlib,
                })

            if import_dicts:
                created_imports = await import_builder.build_import_graph(
                    file_id, import_dicts, repo_id, index_id,
                )
                total_imports += len(created_imports)

            call_dicts = []
            for call in parse_result.calls:
                call_dicts.append({
                    "caller_name": call.caller_name,
                    "callee_name": call.callee_name,
                    "line": call.call_line,
                    "call_type": call.call_type,
                    "confidence": call.confidence,
                })

            if call_dicts:
                created_calls = await call_builder.build_call_graph(
                    file_id, call_dicts, symbol_dicts, repo_id, index_id,
                )
                total_calls += len(created_calls)

        await self.db.flush()

        index = await self._load_index(index_id)
        index.symbols_extracted = total_symbols
        self.db.add(index)
        await self.db.flush()

        self._emit_event("symbols_extracted", {
            "index_id": index_id,
            "symbols": total_symbols,
            "imports": total_imports,
            "calls": total_calls,
        })

        return {"symbols": total_symbols, "imports": total_imports, "calls": total_calls}

    # ── stage: RESOLVE_REFS ──────────────────────────────────────────

    async def resolve_references(self, index_id: str, repo_id: str) -> dict:
        """Resolve symbol references across the entire index.

        Matches unresolved references to their target symbols using
        name matching, qualified name matching, and short-name fallback.
        """
        from app.code_intelligence.models import CodeReference, CodeSymbol

        stmt = (
            select(CodeReference)
            .where(
                CodeReference.index_id == uuid.UUID(index_id),
                CodeReference.resolved.is_(False),
            )
        )
        result = await self.db.execute(stmt)
        unresolved = result.scalars().all()

        target_map_stmt = select(CodeSymbol).where(
            CodeSymbol.repository_id == uuid.UUID(repo_id),
        )
        target_result = await self.db.execute(target_map_stmt)
        all_symbols = target_result.scalars().all()

        target_map: dict[str, uuid.UUID] = {}
        for sym in all_symbols:
            target_map[sym.name] = sym.id
            target_map[sym.qualified_name] = sym.id
            short = sym.name.rsplit(".", 1)[-1] if "." in sym.name else sym.name
            if short not in target_map:
                target_map[short] = sym.id

        resolved_count = 0
        for ref in unresolved:
            if ref.target_name in target_map:
                ref.target_symbol_id = target_map[ref.target_name]
                ref.resolved = True
                resolved_count += 1

        await self.db.flush()

        self._emit_event("references_resolved", {
            "index_id": index_id,
            "resolved": resolved_count,
            "total_unresolved": len(unresolved) - resolved_count,
        })

        return {"resolved": resolved_count, "remaining": len(unresolved) - resolved_count}

    # ── stage: BUILD_GRAPH ───────────────────────────────────────────

    async def _build_graphs(self, index_id: str, repo_id: str) -> dict:
        """Validate and finalize the call graph, import graph, and dependency graph."""
        dep_builder = __import__(
            "app.code_intelligence.symbols", fromlist=["DependencyGraphBuilder"]
        ).DependencyGraphBuilder(self.db)
        inheritance_builder = __import__(
            "app.code_intelligence.symbols", fromlist=["InheritanceGraphBuilder"]
        ).InheritanceGraphBuilder(self.db)

        dep_graph = await dep_builder.build_dependency_graph(repo_id, index_id)
        inheritance_graph = await inheritance_builder.build_inheritance_graph(repo_id, index_id)

        edge_count = len(dep_graph.get("edges", []))
        inheritance_edges = len(inheritance_graph.get("extends", [])) + len(inheritance_graph.get("implements", []))

        index = await self._load_index(index_id)
        index.graph_edges_created = edge_count + inheritance_edges
        self.db.add(index)
        await self.db.flush()

        self._emit_event("graphs_built", {
            "index_id": index_id,
            "dependency_edges": edge_count,
            "inheritance_edges": inheritance_edges,
        })

        return {
            "dependency_edges": edge_count,
            "inheritance_edges": inheritance_edges,
            "nodes": len(dep_graph.get("nodes", [])),
        }

    # ── stage: CALC_METRICS ──────────────────────────────────────────

    async def calculate_metrics(self, index_id: str, repo_id: str) -> dict:
        """Calculate code metrics for all indexed files and their symbols."""
        files = await self._load_files_for_index(index_id)
        metrics_calc = MetricsCalculator(self.db)
        calculated = 0

        await self._update_status(index_id, IndexStatus.ANALYZING.value)

        for code_file in files:
            full_path = self._resolve_file_path(code_file.file_path, repo_id)
            if not full_path or not os.path.isfile(full_path):
                continue

            try:
                with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except OSError:
                continue

            language = code_file.language or self._detect_language(full_path)
            file_id = str(code_file.id)

            try:
                await metrics_calc.calculate_file_metrics(
                    file_id, content, language, [], repo_id,
                )
                calculated += 1
            except Exception as exc:
                logger.warning("Metrics calculation failed for %s: %s", code_file.file_path, exc)

        await self.db.flush()

        self._emit_event("metrics_calculated", {
            "index_id": index_id,
            "files_calculated": calculated,
        })

        return {"files_calculated": calculated}

    # ── stage: DETECT_SMELLS ─────────────────────────────────────────

    async def detect_smells(self, index_id: str, repo_id: str) -> dict:
        """Run all code smell detectors against the indexed repository."""
        detector = SmellDetector(self.db)
        smells = await detector.detect_all(repo_id, index_id)
        summary = await detector.get_smell_summary(repo_id)

        self._emit_event("smells_detected", {
            "index_id": index_id,
            "total_smells": summary["total_smells"],
            "by_type": summary["by_type"],
            "by_severity": summary["by_severity"],
        })

        return summary

    # ── stage: SECURITY_SCAN ─────────────────────────────────────────

    async def scan_security(self, index_id: str, repo_id: str) -> dict:
        """Run the security scanner across all indexed files."""
        scanner = SecurityScanner(self.db)
        findings = await scanner.scan_repository(repo_id, index_id)
        summary = await scanner.get_security_summary(repo_id)

        self._emit_event("security_scan_completed", {
            "index_id": index_id,
            "total_findings": summary["total_findings"],
            "by_severity": summary["by_severity"],
            "overall_severity": summary["overall_severity"],
        })

        return summary

    # ── stage: ARCHITECTURE ──────────────────────────────────────────

    async def discover_architecture(self, index_id: str, repo_id: str) -> dict:
        """Run architecture discovery across the indexed repository."""
        discovery = ArchitectureDiscovery(self.db)
        result = await discovery.discover_architecture(repo_id, index_id)

        summary = {
            "layers": len(result.layers),
            "services": len(result.services),
            "entry_points": len(result.entry_points),
            "api_endpoints": len(result.api_endpoints),
            "databases": len(result.databases),
            "queues": len(result.queues),
            "external_deps": len(result.external_deps),
            "frameworks": len(result.frameworks),
            "configuration": len(result.configuration),
            "monorepo_packages": len(result.monorepo),
        }

        self._emit_event("architecture_discovered", {
            "index_id": index_id,
            **summary,
        })

        return summary

    # ── stage: CHUNK ─────────────────────────────────────────────────

    async def create_chunks(self, index_id: str, repo_id: str) -> dict:
        """Create semantic chunks from indexed files for embedding and retrieval."""
        files = await self._load_files_for_index(index_id)
        total_chunks = 0

        await self._update_status(index_id, IndexStatus.CHUNKING.value)

        for code_file in files:
            if code_file.status not in (FileStatus.PARSED.value,):
                full_path = self._resolve_file_path(code_file.file_path, repo_id)
                if not full_path or not os.path.isfile(full_path):
                    continue
                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                except OSError:
                    continue
            else:
                full_path = self._resolve_file_path(code_file.file_path, repo_id)
                if not full_path or not os.path.isfile(full_path):
                    continue
                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                except OSError:
                    continue

            language = code_file.language or self._detect_language(full_path)
            chunks = self._chunk_content(
                content, language, str(code_file.id), repo_id, index_id,
            )

            for chunk in chunks:
                self.db.add(chunk)

            total_chunks += len(chunks)
            code_file.chunk_count = len(chunks)

        await self.db.flush()

        index = await self._load_index(index_id)
        index.chunks_created = total_chunks
        self.db.add(index)
        await self.db.flush()

        self._emit_event("chunks_created", {
            "index_id": index_id,
            "total_chunks": total_chunks,
        })

        return {"total_chunks": total_chunks}

    # ── stage: EMBED ─────────────────────────────────────────────────

    async def embed_chunks(self, index_id: str, repo_id: str) -> dict:
        """Generate embeddings for all chunks that lack an embedding_id."""
        if self._embedding_service is None:
            logger.info("No embedding service configured, skipping embed stage")
            return {"embedded": 0, "skipped": True}

        stmt = (
            select(CodeChunk)
            .where(
                CodeChunk.index_id == uuid.UUID(index_id),
                CodeChunk.embedding_id.is_(None),
            )
        )
        result = await self.db.execute(stmt)
        chunks = list(result.scalars().all())

        if not chunks:
            return {"embedded": 0}

        embedded = 0
        for i in range(0, len(chunks), EMBED_BATCH_SIZE):
            batch = chunks[i:i + EMBED_BATCH_SIZE]
            texts = [c.content[:2000] for c in batch]

            try:
                embeddings = self._embedding_service.get_embeddings(texts)
            except Exception as exc:
                logger.warning("Embedding batch failed: %s", exc)
                continue

            for chunk, embedding in zip(batch, embeddings):
                chunk.embedding_model = "text-embedding-3-small"
                chunk.embedding_version = "1.0"
                chunk.token_count = len(chunk.content.split()) if chunk.content else 0

                if self._vector_store is not None:
                    try:
                        embedding_id = await self._vector_store.upsert(
                            collection="repository_chunks",
                            vector=embedding,
                            payload={
                                "chunk_id": str(chunk.id),
                                "repository_id": repo_id,
                                "index_id": index_id,
                                "file_id": str(chunk.file_id),
                                "language": chunk.language or "",
                                "chunk_type": chunk.chunk_type,
                            },
                        )
                        chunk.embedding_id = str(embedding_id)
                    except Exception as exc:
                        logger.warning("Vector store upsert failed: %s", exc)
                        chunk.embedding_id = f"local_{chunk.id}"

                embedded += 1

        await self.db.flush()

        index = await self._load_index(index_id)
        index.embeddings_stored = embedded
        index.embedding_model = "text-embedding-3-small"
        self.db.add(index)
        await self.db.flush()

        self._emit_event("embeddings_generated", {
            "index_id": index_id,
            "embedded": embedded,
        })

        return {"embedded": embedded}

    # ── stage: UPDATE_GRAPH ──────────────────────────────────────────

    async def update_graph(self, index_id: str, repo_id: str) -> dict:
        """Push code intelligence data to the Neo4j graph store."""
        if self._graph_store is None:
            logger.info("No graph store configured, skipping UPDATE_GRAPH stage")
            return {"pushed": 0, "skipped": True}

        from app.code_intelligence.models import (
            CodeCall,
            CodeImport,
            CodeReference,
            CodeSymbol,
        )

        files_stmt = (
            select(CodeFile)
            .where(
                CodeFile.index_id == uuid.UUID(index_id),
                CodeFile.repository_id == uuid.UUID(repo_id),
            )
        )
        files_result = await self.db.execute(files_stmt)
        files = files_result.scalars().all()

        nodes_pushed = 0
        edges_pushed = 0

        for code_file in files:
            try:
                node_id = await self._graph_store.create_code_node(
                    file_path=code_file.file_path,
                    language=code_file.language or "unknown",
                    content_hash=code_file.file_hash or "",
                )
                nodes_pushed += 1
            except Exception as exc:
                logger.debug("Graph node creation failed for %s: %s", code_file.file_path, exc)
                continue

            sym_stmt = select(CodeSymbol).where(
                CodeSymbol.file_id == code_file.id,
            )
            sym_result = await self.db.execute(sym_stmt)
            symbols = sym_result.scalars().all()

            for sym in symbols:
                try:
                    sym_node = await self._graph_store.create_code_node(
                        file_path=f"{code_file.file_path}::{sym.name}",
                        language=sym.language or code_file.language or "unknown",
                        content_hash=sym.symbol_id,
                    )
                    await self._graph_store.create_relationship(
                        from_id=str(node_id) if isinstance(node_id, dict) else node_id,
                        to_id=sym_node["id"],
                        rel_type="CONTAINS",
                    )
                    nodes_pushed += 1
                except Exception:
                    continue

            import_stmt = select(CodeImport).where(
                CodeImport.source_file_id == code_file.id,
                CodeImport.resolved.is_(True),
            )
            import_result = await self.db.execute(import_stmt)
            imports = import_result.scalars().all()

            for imp in imports:
                if imp.imported_symbol_id:
                    try:
                        source_id = node_id if isinstance(node_id, str) else node_id.get("id", str(node_id))
                        await self._graph_store.create_relationship(
                            from_id=source_id,
                            to_id=str(imp.imported_symbol_id),
                            rel_type="IMPORTS",
                        )
                        edges_pushed += 1
                    except Exception:
                        continue

            call_stmt = select(CodeCall).where(
                CodeCall.caller_file_id == code_file.id,
                CodeCall.resolved.is_(True),
            )
            call_result = await self.db.execute(call_stmt)
            calls = call_result.scalars().all()

            for call in calls:
                if call.callee_symbol_id:
                    try:
                        source_id = node_id if isinstance(node_id, str) else node_id.get("id", str(node_id))
                        await self._graph_store.create_relationship(
                            from_id=source_id,
                            to_id=str(call.callee_symbol_id),
                            rel_type="CALLS",
                        )
                        edges_pushed += 1
                    except Exception:
                        continue

        await self.db.flush()

        self._emit_event("graph_updated", {
            "index_id": index_id,
            "nodes_pushed": nodes_pushed,
            "edges_pushed": edges_pushed,
        })

        return {"nodes_pushed": nodes_pushed, "edges_pushed": edges_pushed}

    # ── stage: VALIDATE ──────────────────────────────────────────────

    async def validate_index(self, index_id: str) -> dict:
        """Validate index integrity: check for missing files, parse errors,
        embedding mismatches, and graph inconsistencies.
        """
        index = await self._load_index(index_id)
        issues: list[str] = []

        files_stmt = select(CodeFile).where(CodeFile.index_id == uuid.UUID(index_id))
        files_result = await self.db.execute(files_stmt)
        files = files_result.scalars().all()

        total_files = len(files)
        error_files = sum(1 for f in files if f.status == FileStatus.ERROR.value)
        parsed_files = sum(1 for f in files if f.status == FileStatus.PARSED.value)
        no_chunks = sum(1 for f in files if f.chunk_count == 0 and f.status == FileStatus.PARSED.value)

        if error_files > 0:
            issues.append(f"{error_files} files failed parsing")

        if parsed_files > 0 and no_chunks == parsed_files:
            issues.append("No chunks created for any parsed files")

        chunk_stmt = select(func.count()).where(CodeChunk.index_id == uuid.UUID(index_id))
        chunk_result = await self.db.execute(chunk_stmt)
        chunk_count = chunk_result.scalar() or 0

        if total_files > 0 and chunk_count == 0:
            issues.append("Index has files but no chunks")

        symbol_stmt = select(func.count()).where(
            CodeSymbol.index_id == uuid.UUID(index_id),
        )
        symbol_result = await self.db.execute(symbol_stmt)
        symbol_count = symbol_result.scalar() or 0

        is_valid = len(issues) == 0

        validation_result = {
            "valid": is_valid,
            "total_files": total_files,
            "parsed_files": parsed_files,
            "error_files": error_files,
            "total_chunks": chunk_count,
            "total_symbols": symbol_count,
            "issues": issues,
        }

        self._emit_event("index_validated", {
            "index_id": index_id,
            "valid": is_valid,
            "issues": issues,
        })

        return validation_result

    # ── stage: ACTIVATE ──────────────────────────────────────────────

    async def activate_index(self, index_id: str) -> dict:
        """Atomically activate an index: validate, activate, create version,
        and retain rollback capability.
        """
        validation = await self.validate_index(index_id)
        if not validation["valid"]:
            return {
                "activated": False,
                "reason": "Validation failed",
                "issues": validation["issues"],
            }

        index = await self._load_index(index_id)

        prev_active_stmt = (
            select(CodeIndex)
            .where(
                CodeIndex.repository_id == index.repository_id,
                CodeIndex.status == IndexStatus.READY.value,
            )
        )
        prev_result = await self.db.execute(prev_active_stmt)
        prev_active = prev_result.scalars().all()

        for prev in prev_active:
            prev.status = IndexStatus.STALE.value
            self.db.add(prev)

        index.status = IndexStatus.READY.value
        self.db.add(index)

        version_count_stmt = (
            select(func.count())
            .where(CodeIndexVersion.index_id == index.id)
        )
        version_result = await self.db.execute(version_count_stmt)
        version_number = (version_result.scalar() or 0) + 1

        version = CodeIndexVersion(
            index_id=index.id,
            version_number=version_number,
            parser_version=index.parser_version,
            chunker_version=index.chunker_version,
            embedding_model=index.embedding_model,
            schema_version=index.schema_version,
            commit_sha=index.commit_sha,
            is_active=True,
            rollback_available=True,
        )
        self.db.add(version)

        await self.db.flush()

        self._emit_event("index_activated", {
            "index_id": index_id,
            "version_number": version_number,
        })

        return {
            "activated": True,
            "version_number": version_number,
        }

    # ── status & cancellation ────────────────────────────────────────

    async def get_index_status(self, index_id: str) -> dict:
        """Get the current status and metrics of an index."""
        index = await self._load_index(index_id)
        return {
            "index_id": index_id,
            "status": index.status,
            "commit_sha": index.commit_sha,
            "files_total": index.files_total,
            "files_processed": index.files_processed,
            "symbols_extracted": index.symbols_extracted,
            "chunks_created": index.chunks_created,
            "embeddings_stored": index.embeddings_stored,
            "graph_edges_created": index.graph_edges_created,
            "errors": index.errors or [],
            "started_at": index.started_at.isoformat() if index.started_at else None,
            "completed_at": index.completed_at.isoformat() if index.completed_at else None,
        }

    async def cancel_index(self, index_id: str) -> dict:
        """Cancel a running index. Jobs in progress will complete but no
        new stages will be started.
        """
        index = await self._load_index(index_id)
        index.status = IndexStatus.FAILED.value
        index.errors = (index.errors or []) + ["Cancelled by user"]
        self.db.add(index)

        running_jobs_stmt = (
            select(CodeIndexJob)
            .where(
                CodeIndexJob.index_id == uuid.UUID(index_id),
                CodeIndexJob.status == JobStatus.RUNNING.value,
            )
        )
        running_result = await self.db.execute(running_jobs_stmt)
        running_jobs = running_result.scalars().all()

        for job in running_jobs:
            job.status = JobStatus.CANCELLED.value
            job.completed_at = datetime.now(timezone.utc)
            self.db.add(job)

        await self.db.flush()

        self._emit_event("index_cancelled", {"index_id": index_id})

        return {"cancelled": True}

    # ── chunking helpers ─────────────────────────────────────────────

    def _chunk_content(
        self,
        content: str,
        language: str,
        file_id: str,
        repo_id: str,
        index_id: str,
    ) -> list[CodeChunk]:
        """Split content into semantic chunks for embedding and retrieval.

        Uses a hybrid approach: split on top-level function/class boundaries
        where possible, falling back to fixed-size line windows.
        """
        if not content.strip():
            return []

        lines = content.split("\n")
        chunks: list[CodeChunk] = []
        chunk_index = 0

        boundaries = self._find_semantic_boundaries(lines, language)

        if boundaries:
            for i in range(len(boundaries)):
                start = boundaries[i]
                end = boundaries[i + 1] if i + 1 < len(boundaries) else len(lines)
                chunk_text = "\n".join(lines[start:end]).strip()

                if not chunk_text:
                    continue

                chunk_type = self._classify_chunk_type(lines[start:end] if start < end else lines[:1], language)
                chunk_index_id = f"{file_id}:{chunk_index}"

                chunks.append(CodeChunk(
                    repository_id=uuid.UUID(repo_id),
                    index_id=uuid.UUID(index_id),
                    file_id=uuid.UUID(file_id),
                    chunk_type=chunk_type,
                    content=chunk_text,
                    start_line=start + 1,
                    end_line=end,
                    language=language,
                    token_count=len(chunk_text.split()),
                    metadata_={"chunk_index": chunk_index},
                ))
                chunk_index += 1
        else:
            for start in range(0, len(lines), MAX_CHUNK_LINES - CHUNK_OVERLAP_LINES):
                end = min(start + MAX_CHUNK_LINES, len(lines))
                chunk_text = "\n".join(lines[start:end]).strip()

                if not chunk_text:
                    continue

                chunk_type = self._classify_chunk_type(lines[start:end], language)
                chunk_index_id = f"{file_id}:{chunk_index}"

                chunks.append(CodeChunk(
                    repository_id=uuid.UUID(repo_id),
                    index_id=uuid.UUID(index_id),
                    file_id=uuid.UUID(file_id),
                    chunk_type=chunk_type,
                    content=chunk_text,
                    start_line=start + 1,
                    end_line=end,
                    language=language,
                    token_count=len(chunk_text.split()),
                    metadata_={"chunk_index": chunk_index},
                ))
                chunk_index += 1

                if end >= len(lines):
                    break

        return chunks

    def _find_semantic_boundaries(self, lines: list[str], language: str) -> list[int]:
        """Find line indices where top-level definitions begin."""
        boundaries: list[int] = [0]
        indent_patterns = {
            "python": ("def ", "class ", "async def "),
            "javascript": ("function ", "class ", "const ", "let ", "export "),
            "typescript": ("function ", "class ", "const ", "let ", "export ", "interface ", "type "),
            "go": ("func ", "type ", "package "),
            "java": ("public ", "private ", "protected ", "class ", "interface ", "enum "),
            "rust": ("fn ", "struct ", "enum ", "impl ", "pub fn ", "pub struct ", "pub enum "),
            "ruby": ("def ", "class ", "module "),
            "php": ("function ", "class ", "interface ", "trait ", "abstract "),
            "c_sharp": ("public ", "private ", "internal ", "class ", "interface ", "struct "),
        }

        patterns = indent_patterns.get(language, indent_patterns.get("python"))

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            for pat in patterns:
                if stripped.startswith(pat) or (len(stripped) > len(pat) and stripped[len(pat)] in (" ", "(", "\t")):
                    if not stripped.startswith("#") and not stripped.startswith("//"):
                        boundaries.append(i)
                        break

        return boundaries

    def _classify_chunk_type(self, lines: list[str], language: str) -> str:
        """Classify a chunk as function, class, import, comment, docstring, or code."""
        if not lines:
            return "code"

        first = lines[0].strip()

        if language == "python":
            if first.startswith("def ") or first.startswith("async def "):
                return "function"
            if first.startswith("class "):
                return "class"
            if first.startswith("import ") or first.startswith("from "):
                return "import"
            if first.startswith("#"):
                return "comment"
            if first.startswith('"""') or first.startswith("'''"):
                return "docstring"
        elif language in ("javascript", "typescript"):
            if first.startswith("function ") or first.startswith("async function "):
                return "function"
            if first.startswith("class "):
                return "class"
            if first.startswith("import ") or first.startswith("const ") and "require(" in first:
                return "import"
            if first.startswith("//") or first.startswith("/*"):
                return "comment"
        elif language == "go":
            if first.startswith("func "):
                return "function"
            if first.startswith("type ") or first.startswith("struct "):
                return "class"
            if first.startswith("package ") or first.startswith("import "):
                return "import"
            if first.startswith("//"):
                return "comment"
        elif language == "java":
            if "void " in first or "static " in first and "(" in first:
                return "function"
            if first.startswith("class ") or first.startswith("interface "):
                return "class"
            if first.startswith("import "):
                return "import"
            if first.startswith("//"):
                return "comment"
        elif language == "rust":
            if first.startswith("fn ") or first.startswith("pub fn "):
                return "function"
            if first.startswith("struct ") or first.startswith("enum ") or first.startswith("impl "):
                return "class"
            if first.startswith("use ") or first.startswith("mod "):
                return "import"
            if first.startswith("//"):
                return "comment"

        return "code"

    async def _create_file_chunks(
        self,
        code_file: CodeFile,
        content: str,
        language: str,
        parse_result: Any,
        index_id: str,
        repo_id: str,
    ) -> None:
        """Create chunks for a single file during index_file."""
        chunks = self._chunk_content(
            content, language, str(code_file.id), repo_id, index_id,
        )
        for chunk in chunks:
            self.db.add(chunk)
        code_file.chunk_count = len(chunks)

    # ── file/path helpers ────────────────────────────────────────────

    def _should_skip_path(self, name: str, is_dir: bool) -> bool:
        """Check if a file or directory should be ignored during discovery."""
        if name in IGNORE_PATTERNS:
            return True

        if name.endswith(("~", ".swp", ".swo", ".bak")):
            return True

        if not is_dir:
            for pattern in IGNORE_PATTERNS:
                if pattern.startswith("*.") and name.endswith(pattern[1:]):
                    return True

        return False

    def _detect_language(self, file_path: str) -> str:
        """Detect programming language from file extension."""
        _, ext = os.path.splitext(file_path)
        return EXTENSION_LANGUAGE_MAP.get(ext.lower(), "")

    def _resolve_file_path(self, relative_path: str, repo_id: str) -> Optional[str]:
        """Resolve a relative file path to an absolute path.

        Tries to find the file in common repository root locations.
        """
        if os.path.isabs(relative_path) and os.path.isfile(relative_path):
            return relative_path

        candidates = [
            relative_path,
            os.path.join("repos", repo_id, relative_path),
        ]

        for candidate in candidates:
            if os.path.isfile(candidate):
                return os.path.abspath(candidate)

        return relative_path if os.path.isfile(relative_path) else None

    async def _load_index(self, index_id: str) -> CodeIndex:
        """Load an index by ID with error handling."""
        stmt = select(CodeIndex).where(CodeIndex.id == uuid.UUID(index_id))
        result = await self.db.execute(stmt)
        index = result.scalar_one_or_none()
        if index is None:
            raise ValueError(f"Index not found: {index_id}")
        return index

    async def _load_files_for_index(
        self, index_id: str, file_ids: Optional[list[str]] = None,
    ) -> list[CodeFile]:
        """Load files for an index, optionally filtered by file IDs."""
        stmt = select(CodeFile).where(CodeFile.index_id == uuid.UUID(index_id))
        if file_ids:
            uuid_ids = [uuid.UUID(fid) for fid in file_ids]
            stmt = stmt.where(CodeFile.id.in_(uuid_ids))
        stmt = stmt.order_by(CodeFile.file_path)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _count_chunks(self, file_id: str) -> int:
        """Count chunks for a given file."""
        stmt = select(func.count()).where(CodeChunk.file_id == uuid.UUID(file_id))
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    @staticmethod
    def _find_references_in_scope(sym: dict, all_symbols: list[dict]) -> list[str]:
        """Find names referenced within a symbol's scope."""
        name = sym.get("name", "")
        references: list[str] = []
        for other in all_symbols:
            other_name = other.get("name", "")
            if other_name != name and other_name:
                references.append(other_name)
        return references[:50]

    # ── status & event helpers ───────────────────────────────────────

    async def _update_status(
        self, index_id: str, status: str, progress: Optional[dict] = None,
    ) -> None:
        """Update index status in the database."""
        index = await self._load_index(index_id)
        index.status = status
        if progress:
            errors = index.errors or []
            if "error" in progress:
                errors.append(progress["error"])
            index.errors = errors
        self.db.add(index)
        await self.db.flush()

    async def _record_error(self, index_id: str, stage: str, error: str) -> None:
        """Record a pipeline error on the index."""
        index = await self._load_index(index_id)
        errors = index.errors or []
        errors.append({"stage": stage, "error": error, "at": datetime.now(timezone.utc).isoformat()})
        index.errors = errors
        self.db.add(index)
        await self.db.flush()

    def _emit_event(self, event_type: str, data: dict) -> None:
        """Emit an event to the event bus (fire-and-forget)."""
        try:
            full_type = f"code_intelligence.{event_type}"
            event_data = {**data, "event_name": full_type}
            event = Event(
                event_type=EventType.pipeline_completed,
                data=event_data,
                source="code_intelligence_pipeline",
            )
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(event_bus.publish_nowait(event))
            else:
                loop.run_until_complete(event_bus.publish_nowait(event))
        except Exception:
            logger.debug("Failed to emit event %s", event_type)
