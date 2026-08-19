"""Index / Vector / Graph Consistency Validation module.

Validates referential integrity across every layer of the code intelligence
knowledge graph: symbols, references, graph edges, vectors, and file coverage.
Returns structured reports with per-issue diagnostics and repair suggestions.
"""

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional, Sequence, Type

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.code_intelligence.models import (
    CodeCall,
    CodeChunk,
    CodeFile,
    CodeHistory,
    CodeImport,
    CodeIndex,
    CodeIndexJob,
    CodeMetrics,
    CodeOwnership,
    CodeReference,
    CodeSmell,
    CodeSymbol,
    CodeTest,
    FileStatus,
    IndexStatus,
    JobStatus,
)

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────────


class IssueSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class IssueCategory(str, Enum):
    SYMBOL_REFERENCE = "SYMBOL_REFERENCE"
    GRAPH_EDGE = "GRAPH_EDGE"
    FILE_SYMBOL = "FILE_SYMBOL"
    DUPLICATE = "DUPLICATE"
    VECTOR = "VECTOR"
    INDEX_HEALTH = "INDEX_HEALTH"
    PARSER_ERROR = "PARSER_ERROR"


class RepairAction(str, Enum):
    DELETE_ORPHAN = "DELETE_ORPHAN"
    RE_RESOLVE = "RE_RESOLVE"
    RE_INDEX = "RE_INDEX"
    REGENERATE_EMBEDDING = "REGENERATE_EMBEDDING"
    REMOVE_DUPLICATE = "REMOVE_DUPLICATE"
    UPDATE_INDEX = "UPDATE_INDEX"
    REPARS_FILE = "REPARS_FILE"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    SKIP = "SKIP"


# ── Return dataclasses ──────────────────────────────────────────────────


@dataclass
class ConsistencyIssue:
    category: IssueCategory
    severity: IssueSeverity
    message: str
    entity_id: Optional[str] = None
    entity_type: Optional[str] = None
    details: dict = field(default_factory=dict)
    repair_action: Optional[RepairAction] = None
    repair_hint: Optional[str] = None


@dataclass
class ValidationReport:
    repository_id: uuid.UUID
    index_id: Optional[uuid.UUID] = None
    validated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    issues: list[ConsistencyIssue] = field(default_factory=list)
    health_score: float = 100.0
    total_files: int = 0
    total_symbols: int = 0
    total_references: int = 0
    total_calls: int = 0
    total_imports: int = 0
    total_chunks: int = 0
    summary: dict = field(default_factory=dict)

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    @property
    def issues_by_severity(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for issue in self.issues:
            counts[issue.severity.value] += 1
        return dict(counts)

    @property
    def issues_by_category(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for issue in self.issues:
            counts[issue.category.value] += 1
        return dict(counts)


@dataclass
class SymbolReferenceResult:
    orphaned_references: list[ConsistencyIssue] = field(default_factory=list)
    dangling_references: list[ConsistencyIssue] = field(default_factory=list)
    total_checked: int = 0


@dataclass
class GraphEdgeResult:
    broken_call_edges: list[ConsistencyIssue] = field(default_factory=list)
    broken_import_edges: list[ConsistencyIssue] = field(default_factory=list)
    orphaned_edges: list[ConsistencyIssue] = field(default_factory=list)
    total_checked: int = 0


@dataclass
class FileSymbolResult:
    orphaned_files: list[ConsistencyIssue] = field(default_factory=list)
    orphaned_symbols: list[ConsistencyIssue] = field(default_factory=list)
    stale_file_records: list[ConsistencyIssue] = field(default_factory=list)


@dataclass
class DuplicateResult:
    duplicate_symbols: list[ConsistencyIssue] = field(default_factory=list)
    duplicate_ids: list[ConsistencyIssue] = field(default_factory=list)


@dataclass
class VectorResult:
    missing_embeddings: list[ConsistencyIssue] = field(default_factory=list)
    duplicate_vectors: list[ConsistencyIssue] = field(default_factory=list)
    dimension_mismatches: list[ConsistencyIssue] = field(default_factory=list)
    model_mismatches: list[ConsistencyIssue] = field(default_factory=list)
    orphaned_vectors: list[ConsistencyIssue] = field(default_factory=list)


@dataclass
class IndexHealthResult:
    stale_indexes: list[ConsistencyIssue] = field(default_factory=list)
    missing_files: list[ConsistencyIssue] = field(default_factory=list)
    parser_errors: list[ConsistencyIssue] = field(default_factory=list)
    failed_jobs: list[ConsistencyIssue] = field(default_factory=list)


# ── Main validator ──────────────────────────────────────────────────────


class ConsistencyValidator:
    """Validates referential integrity across symbols, graph edges, vectors,
    and file coverage for a given repository index.

    Usage::

        validator = ConsistencyValidator()
        report = await validator.validate_all(repo_id, index_id, db)
    """

    STALENESS_THRESHOLD_DAYS: int = 7
    _SEVERITY_DEDUCTIONS: dict[str, float] = {
        IssueSeverity.CRITICAL.value: 20.0,
        IssueSeverity.ERROR.value: 10.0,
        IssueSeverity.WARNING.value: 3.0,
        IssueSeverity.INFO.value: 0.5,
    }

    # ------------------------------------------------------------------ #
    # Public entry points                                                #
    # ------------------------------------------------------------------ #

    async def validate_all(
        self,
        repository_id: uuid.UUID,
        db: AsyncSession,
        index_id: Optional[uuid.UUID] = None,
    ) -> ValidationReport:
        """Run every validation pass and return a unified report."""
        report = ValidationReport(repository_id=repository_id, index_id=index_id)

        logger.info(
            "Starting full consistency validation for repository %s (index=%s)",
            repository_id, index_id,
        )

        # Populate aggregate counts
        report.total_files = await self._count(CodeFile, repository_id, index_id, db)
        report.total_symbols = await self._count(CodeSymbol, repository_id, index_id, db)
        report.total_references = await self._count(CodeReference, repository_id, index_id, db)
        report.total_calls = await self._count(CodeCall, repository_id, index_id, db)
        report.total_imports = await self._count(CodeImport, repository_id, index_id, db)
        report.total_chunks = await self._count(CodeChunk, repository_id, index_id, db)

        # Run each validation pass and collect issues
        ref_result = await self.validate_symbol_references(repository_id, db, index_id)
        report.issues.extend(ref_result.orphaned_references)
        report.issues.extend(ref_result.dangling_references)

        edge_result = await self.validate_graph_edges(repository_id, db, index_id)
        report.issues.extend(edge_result.broken_call_edges)
        report.issues.extend(edge_result.broken_import_edges)
        report.issues.extend(edge_result.orphaned_edges)

        file_result = await self.validate_file_symbols(repository_id, db, index_id)
        report.issues.extend(file_result.orphaned_files)
        report.issues.extend(file_result.orphaned_symbols)
        report.issues.extend(file_result.stale_file_records)

        dup_result = await self.validate_duplicates(repository_id, db, index_id)
        report.issues.extend(dup_result.duplicate_symbols)
        report.issues.extend(dup_result.duplicate_ids)

        vec_result = await self.validate_vectors(repository_id, db, index_id)
        report.issues.extend(vec_result.missing_embeddings)
        report.issues.extend(vec_result.duplicate_vectors)
        report.issues.extend(vec_result.dimension_mismatches)
        report.issues.extend(vec_result.model_mismatches)
        report.issues.extend(vec_result.orphaned_vectors)

        health_result = await self.validate_index_health(repository_id, db, index_id)
        report.issues.extend(health_result.stale_indexes)
        report.issues.extend(health_result.missing_files)
        report.issues.extend(health_result.parser_errors)
        report.issues.extend(health_result.failed_jobs)

        report.health_score = self._compute_health_score(report)
        report.summary = self._build_summary(report)

        logger.info(
            "Validation complete: score=%.1f, issues=%d",
            report.health_score, report.issue_count,
        )
        return report

    async def validate_symbol_references(
        self,
        repository_id: uuid.UUID,
        db: AsyncSession,
        index_id: Optional[uuid.UUID] = None,
    ) -> SymbolReferenceResult:
        """Check that every reference points to an existing symbol."""
        result = SymbolReferenceResult()
        refs = await self._query(CodeReference, repository_id, index_id, db)
        symbol_db_ids = await self._load_id_set(CodeSymbol, repository_id, index_id, db)
        result.total_checked = len(refs)

        for ref in refs:
            if ref.source_symbol_id and ref.source_symbol_id not in symbol_db_ids:
                result.dangling_references.append(ConsistencyIssue(
                    category=IssueCategory.SYMBOL_REFERENCE,
                    severity=IssueSeverity.WARNING,
                    message=(
                        f"Reference {ref.id} source_symbol_id "
                        f"{ref.source_symbol_id} no longer exists"
                    ),
                    entity_id=str(ref.id), entity_type="CodeReference",
                    details={
                        "source_symbol_id": str(ref.source_symbol_id),
                        "target_name": ref.target_name,
                        "reference_type": ref.reference_type,
                    },
                    repair_action=RepairAction.DELETE_ORPHAN,
                    repair_hint="Set source_symbol_id to NULL or delete the orphaned reference",
                ))

            if ref.target_symbol_id and ref.target_symbol_id not in symbol_db_ids:
                result.orphaned_references.append(ConsistencyIssue(
                    category=IssueCategory.SYMBOL_REFERENCE,
                    severity=IssueSeverity.WARNING,
                    message=(
                        f"Reference {ref.id} targets symbol "
                        f"{ref.target_symbol_id} that no longer exists"
                    ),
                    entity_id=str(ref.id), entity_type="CodeReference",
                    details={
                        "target_symbol_id": str(ref.target_symbol_id),
                        "target_name": ref.target_name,
                    },
                    repair_action=RepairAction.RE_RESOLVE,
                    repair_hint="Re-resolve target by name or mark the reference unresolved",
                ))

        logger.debug(
            "Symbol reference validation: checked=%d, orphaned=%d, dangling=%d",
            result.total_checked, len(result.orphaned_references), len(result.dangling_references),
        )
        return result

    async def validate_graph_edges(
        self,
        repository_id: uuid.UUID,
        db: AsyncSession,
        index_id: Optional[uuid.UUID] = None,
    ) -> GraphEdgeResult:
        """Validate call edges point to valid symbols, import edges to valid files."""
        result = GraphEdgeResult()
        symbol_db_ids = await self._load_id_set(CodeSymbol, repository_id, index_id, db)
        file_db_ids = await self._load_id_set(CodeFile, repository_id, index_id, db)

        calls = await self._query(CodeCall, repository_id, index_id, db)
        result.total_checked = len(calls)

        for call in calls:
            if call.caller_symbol_id not in symbol_db_ids:
                result.broken_call_edges.append(ConsistencyIssue(
                    category=IssueCategory.GRAPH_EDGE,
                    severity=IssueSeverity.ERROR,
                    message=(
                        f"Call edge {call.id} caller_symbol_id "
                        f"{call.caller_symbol_id} does not exist"
                    ),
                    entity_id=str(call.id), entity_type="CodeCall",
                    details={
                        "caller_symbol_id": str(call.caller_symbol_id),
                        "callee_name": call.callee_name,
                    },
                    repair_action=RepairAction.DELETE_ORPHAN,
                    repair_hint="Delete this call edge — caller symbol was removed",
                ))

            if call.callee_symbol_id and call.callee_symbol_id not in symbol_db_ids:
                result.broken_call_edges.append(ConsistencyIssue(
                    category=IssueCategory.GRAPH_EDGE,
                    severity=IssueSeverity.WARNING,
                    message=(
                        f"Call edge {call.id} callee_symbol_id "
                        f"{call.callee_symbol_id} does not exist"
                    ),
                    entity_id=str(call.id), entity_type="CodeCall",
                    details={
                        "caller_symbol_id": str(call.caller_symbol_id),
                        "callee_name": call.callee_name,
                        "resolved": call.resolved,
                    },
                    repair_action=RepairAction.RE_RESOLVE,
                    repair_hint="Re-resolve callee by name or clear callee_symbol_id",
                ))

            if call.caller_file_id not in file_db_ids:
                result.orphaned_edges.append(ConsistencyIssue(
                    category=IssueCategory.GRAPH_EDGE,
                    severity=IssueSeverity.ERROR,
                    message=(
                        f"Call edge {call.id} caller_file_id "
                        f"{call.caller_file_id} does not exist"
                    ),
                    entity_id=str(call.id), entity_type="CodeCall",
                    repair_action=RepairAction.DELETE_ORPHAN,
                    repair_hint="Delete this call edge — caller file was removed",
                ))

        imports = await self._query(CodeImport, repository_id, index_id, db)

        for imp in imports:
            if imp.source_file_id not in file_db_ids:
                result.broken_import_edges.append(ConsistencyIssue(
                    category=IssueCategory.GRAPH_EDGE,
                    severity=IssueSeverity.ERROR,
                    message=(
                        f"Import {imp.id} source_file_id "
                        f"{imp.source_file_id} does not exist"
                    ),
                    entity_id=str(imp.id), entity_type="CodeImport",
                    details={"imported_name": imp.imported_name, "import_type": imp.import_type},
                    repair_action=RepairAction.DELETE_ORPHAN,
                    repair_hint="Delete this import edge — source file was removed",
                ))

            if imp.imported_symbol_id and imp.imported_symbol_id not in symbol_db_ids:
                result.broken_import_edges.append(ConsistencyIssue(
                    category=IssueCategory.GRAPH_EDGE,
                    severity=IssueSeverity.WARNING,
                    message=(
                        f"Import {imp.id} imported_symbol_id "
                        f"{imp.imported_symbol_id} does not exist"
                    ),
                    entity_id=str(imp.id), entity_type="CodeImport",
                    details={"imported_name": imp.imported_name, "resolved": imp.resolved},
                    repair_action=RepairAction.RE_RESOLVE,
                    repair_hint="Re-resolve the import target or clear imported_symbol_id",
                ))

        logger.debug(
            "Graph edge validation: calls=%d, imports=%d, broken=%d",
            len(calls), len(imports),
            len(result.broken_call_edges) + len(result.broken_import_edges),
        )
        return result

    async def validate_file_symbols(
        self,
        repository_id: uuid.UUID,
        db: AsyncSession,
        index_id: Optional[uuid.UUID] = None,
    ) -> FileSymbolResult:
        """Detect stale file records and symbols orphaned from deleted files."""
        result = FileSymbolResult()
        files = await self._query(CodeFile, repository_id, index_id, db)
        file_db_ids = {f.id for f in files}

        for f in files:
            if f.status in (FileStatus.ERROR.value, FileStatus.SKIPPED.value):
                result.stale_file_records.append(ConsistencyIssue(
                    category=IssueCategory.FILE_SYMBOL,
                    severity=IssueSeverity.INFO,
                    message=(
                        f"File {f.file_path} has status {f.status}"
                        + (f" — {f.parse_error}" if f.parse_error else "")
                    ),
                    entity_id=str(f.id), entity_type="CodeFile",
                    details={"file_path": f.file_path, "status": f.status, "parse_error": f.parse_error},
                    repair_action=RepairAction.REPARS_FILE,
                    repair_hint="Re-queue this file for parsing",
                ))

        symbols = await self._query(CodeSymbol, repository_id, index_id, db)
        for sym in symbols:
            if sym.file_id not in file_db_ids:
                result.orphaned_symbols.append(ConsistencyIssue(
                    category=IssueCategory.FILE_SYMBOL,
                    severity=IssueSeverity.ERROR,
                    message=(
                        f"Symbol '{sym.name}' ({sym.symbol_id}) belongs to "
                        f"deleted file {sym.file_id}"
                    ),
                    entity_id=str(sym.id), entity_type="CodeSymbol",
                    details={
                        "symbol_id": sym.symbol_id, "name": sym.name,
                        "file_id": str(sym.file_id), "symbol_type": sym.symbol_type,
                    },
                    repair_action=RepairAction.DELETE_ORPHAN,
                    repair_hint="Delete this symbol and cascade its references, calls, chunks",
                ))

        logger.debug(
            "File-symbol validation: files=%d, symbols=%d, orphaned=%d, stale=%d",
            len(files), len(symbols), len(result.orphaned_symbols), len(result.stale_file_records),
        )
        return result

    async def validate_duplicates(
        self,
        repository_id: uuid.UUID,
        db: AsyncSession,
        index_id: Optional[uuid.UUID] = None,
    ) -> DuplicateResult:
        """Find duplicate symbol nodes sharing the same symbol_id or (name, file_id)."""
        result = DuplicateResult()
        symbols = await self._query(CodeSymbol, repository_id, index_id, db)

        by_symbol_id: dict[str, list[CodeSymbol]] = defaultdict(list)
        by_name_file: dict[tuple[str, uuid.UUID], list[CodeSymbol]] = defaultdict(list)

        for sym in symbols:
            by_symbol_id[sym.symbol_id].append(sym)
            by_name_file[(sym.name, sym.file_id)].append(sym)

        for sid, group in by_symbol_id.items():
            if len(group) > 1:
                ids = [str(s.id) for s in group]
                result.duplicate_ids.append(ConsistencyIssue(
                    category=IssueCategory.DUPLICATE,
                    severity=IssueSeverity.ERROR,
                    message=f"Duplicate symbol_id '{sid}' in {len(group)} rows",
                    entity_id=sid, entity_type="CodeSymbol",
                    details={"duplicate_db_ids": ids, "names": [s.name for s in group]},
                    repair_action=RepairAction.REMOVE_DUPLICATE,
                    repair_hint="Keep the most recently updated symbol and delete the rest",
                ))

        for (name, fid), group in by_name_file.items():
            if len(group) > 1:
                ids = [str(s.id) for s in group]
                result.duplicate_symbols.append(ConsistencyIssue(
                    category=IssueCategory.DUPLICATE,
                    severity=IssueSeverity.WARNING,
                    message=f"Symbol '{name}' appears {len(group)} times in file {fid}",
                    entity_id=ids[0], entity_type="CodeSymbol",
                    details={"duplicate_db_ids": ids, "file_id": str(fid)},
                    repair_action=RepairAction.REMOVE_DUPLICATE,
                    repair_hint="Merge or remove duplicate symbol records",
                ))

        logger.debug(
            "Duplicate validation: symbols=%d, dup_ids=%d, dup_name_file=%d",
            len(symbols), len(result.duplicate_ids), len(result.duplicate_symbols),
        )
        return result

    async def validate_vectors(
        self,
        repository_id: uuid.UUID,
        db: AsyncSession,
        index_id: Optional[uuid.UUID] = None,
    ) -> VectorResult:
        """Validate chunk embeddings: missing, duplicate, wrong model, orphaned."""
        result = VectorResult()
        index = await self._load_primary_index(repository_id, index_id, db)
        expected_model = index.embedding_model if index else None

        chunks = await self._query(CodeChunk, repository_id, index_id, db)
        file_db_ids = await self._load_id_set(CodeFile, repository_id, index_id, db)
        embedding_id_seen: dict[str, CodeChunk] = {}
        content_groups: dict[str, list[CodeChunk]] = defaultdict(list)

        for chunk in chunks:
            if not chunk.embedding_id:
                result.missing_embeddings.append(ConsistencyIssue(
                    category=IssueCategory.VECTOR,
                    severity=IssueSeverity.WARNING,
                    message=f"Chunk {chunk.id} (file={chunk.file_id}) has no embedding_id",
                    entity_id=str(chunk.id), entity_type="CodeChunk",
                    details={
                        "file_id": str(chunk.file_id), "chunk_type": chunk.chunk_type,
                        "content_preview": chunk.content[:120] if chunk.content else "",
                    },
                    repair_action=RepairAction.REGENERATE_EMBEDDING,
                    repair_hint="Re-queue this chunk for embedding generation",
                ))
                continue

            if chunk.embedding_id in embedding_id_seen:
                first = embedding_id_seen[chunk.embedding_id]
                result.duplicate_vectors.append(ConsistencyIssue(
                    category=IssueCategory.VECTOR,
                    severity=IssueSeverity.WARNING,
                    message=f"Chunk {chunk.id} shares embedding_id '{chunk.embedding_id}' with {first.id}",
                    entity_id=str(chunk.id), entity_type="CodeChunk",
                    details={"embedding_id": chunk.embedding_id, "conflicting_chunk_id": str(first.id)},
                    repair_action=RepairAction.REGENERATE_EMBEDDING,
                    repair_hint="Re-embed the duplicate chunk with a unique embedding_id",
                ))
            else:
                embedding_id_seen[chunk.embedding_id] = chunk

            if expected_model and chunk.embedding_model and chunk.embedding_model != expected_model:
                result.model_mismatches.append(ConsistencyIssue(
                    category=IssueCategory.VECTOR,
                    severity=IssueSeverity.WARNING,
                    message=(
                        f"Chunk {chunk.id} uses model '{chunk.embedding_model}' "
                        f"but index expects '{expected_model}'"
                    ),
                    entity_id=str(chunk.id), entity_type="CodeChunk",
                    details={"chunk_model": chunk.embedding_model, "expected_model": expected_model},
                    repair_action=RepairAction.REGENERATE_EMBEDDING,
                    repair_hint="Re-embed with the current embedding model",
                ))

            if chunk.file_id not in file_db_ids:
                result.orphaned_vectors.append(ConsistencyIssue(
                    category=IssueCategory.VECTOR,
                    severity=IssueSeverity.ERROR,
                    message=f"Chunk {chunk.id} references deleted file {chunk.file_id}",
                    entity_id=str(chunk.id), entity_type="CodeChunk",
                    details={"embedding_id": chunk.embedding_id, "file_id": str(chunk.file_id)},
                    repair_action=RepairAction.DELETE_ORPHAN,
                    repair_hint="Delete this chunk — its source file was removed",
                ))

            content_key = (chunk.content or "").strip()
            if content_key:
                content_groups[content_key].append(chunk)

        for content, dup_chunks in content_groups.items():
            if len(dup_chunks) > 1:
                ids = [str(c.id) for c in dup_chunks]
                result.duplicate_vectors.append(ConsistencyIssue(
                    category=IssueCategory.VECTOR,
                    severity=IssueSeverity.WARNING,
                    message=f"{len(dup_chunks)} chunks share identical content (first: {ids[0]})",
                    entity_id=ids[0], entity_type="CodeChunk",
                    details={"duplicate_chunk_ids": ids, "content_preview": content[:120]},
                    repair_action=RepairAction.REMOVE_DUPLICATE,
                    repair_hint="Remove duplicate chunks or investigate the chunking pipeline",
                ))

        logger.debug(
            "Vector validation: chunks=%d, missing=%d, orphans=%d, model_mismatch=%d",
            len(chunks), len(result.missing_embeddings),
            len(result.orphaned_vectors), len(result.model_mismatches),
        )
        return result

    async def validate_index_health(
        self,
        repository_id: uuid.UUID,
        db: AsyncSession,
        index_id: Optional[uuid.UUID] = None,
    ) -> IndexHealthResult:
        """Check for stale indexes, missing files, and parser errors."""
        result = IndexHealthResult()
        now = datetime.now(timezone.utc)
        threshold = now - timedelta(days=self.STALENESS_THRESHOLD_DAYS)

        indexes = await self._query(CodeIndex, repository_id, index_id, db)

        for idx in indexes:
            if idx.completed_at and idx.completed_at < threshold:
                days_stale = (now - idx.completed_at).days
                result.stale_indexes.append(ConsistencyIssue(
                    category=IssueCategory.INDEX_HEALTH,
                    severity=IssueSeverity.WARNING,
                    message=(
                        f"Index {idx.id} completed {days_stale}d ago "
                        f"(threshold: {self.STALENESS_THRESHOLD_DAYS}d)"
                    ),
                    entity_id=str(idx.id), entity_type="CodeIndex",
                    details={"completed_at": idx.completed_at.isoformat(), "days_stale": days_stale},
                    repair_action=RepairAction.UPDATE_INDEX,
                    repair_hint="Trigger a fresh index run for this repository",
                ))

            if idx.status == IndexStatus.FAILED.value:
                result.stale_indexes.append(ConsistencyIssue(
                    category=IssueCategory.INDEX_HEALTH,
                    severity=IssueSeverity.CRITICAL,
                    message=f"Index {idx.id} is in FAILED status",
                    entity_id=str(idx.id), entity_type="CodeIndex",
                    details={"status": idx.status, "errors": idx.errors},
                    repair_action=RepairAction.RE_INDEX,
                    repair_hint="Investigate error details and re-run the index pipeline",
                ))

            if idx.files_total > 0 and idx.files_processed < idx.files_total:
                missing = idx.files_total - idx.files_processed
                result.missing_files.append(ConsistencyIssue(
                    category=IssueCategory.INDEX_HEALTH,
                    severity=IssueSeverity.WARNING,
                    message=(
                        f"Index {idx.id} has {missing} unprocessed files "
                        f"({idx.files_processed}/{idx.files_total})"
                    ),
                    entity_id=str(idx.id), entity_type="CodeIndex",
                    details={"files_total": idx.files_total, "files_processed": idx.files_processed},
                    repair_action=RepairAction.RE_INDEX,
                    repair_hint="Resume or restart the indexing pipeline",
                ))

        files = await self._query(CodeFile, repository_id, index_id, db)
        for f in files:
            if f.status == FileStatus.ERROR.value:
                result.parser_errors.append(ConsistencyIssue(
                    category=IssueCategory.PARSER_ERROR,
                    severity=IssueSeverity.WARNING,
                    message=f"File '{f.file_path}' failed to parse"
                            + (f": {f.parse_error}" if f.parse_error else ""),
                    entity_id=str(f.id), entity_type="CodeFile",
                    details={"file_path": f.file_path, "parse_error": f.parse_error, "language": f.language},
                    repair_action=RepairAction.REPARS_FILE,
                    repair_hint="Check the parse error and re-queue for parsing",
                ))

        jobs = await self._load_failed_jobs(repository_id, index_id, db)
        for job in jobs:
            result.failed_jobs.append(ConsistencyIssue(
                category=IssueCategory.INDEX_HEALTH,
                severity=IssueSeverity.WARNING,
                message=(
                    f"Index job {job.id} (type={job.job_type}) FAILED "
                    f"after {job.attempts} attempts"
                ),
                entity_id=str(job.id), entity_type="CodeIndexJob",
                details={"job_type": job.job_type, "attempts": job.attempts, "error": job.error},
                repair_action=RepairAction.RE_INDEX,
                repair_hint="Re-queue the failed job",
            ))

        logger.debug(
            "Index health: indexes=%d, stale=%d, parser_errors=%d",
            len(indexes), len(result.stale_indexes), len(result.parser_errors),
        )
        return result

    async def get_health_score(
        self,
        repository_id: uuid.UUID,
        db: AsyncSession,
    ) -> float:
        """Compute a 0-100 index health score."""
        report = await self.validate_all(repository_id, db)
        return report.health_score

    async def get_repair_suggestions(
        self,
        repository_id: uuid.UUID,
        db: AsyncSession,
    ) -> list[dict]:
        """Return actionable repair suggestions grouped by action type."""
        report = await self.validate_all(repository_id, db)

        grouped: dict[str, list[dict]] = defaultdict(list)
        for issue in report.issues:
            action = issue.repair_action.value if issue.repair_action else "UNKNOWN"
            grouped[action].append({
                "category": issue.category.value,
                "severity": issue.severity.value,
                "entity_id": issue.entity_id,
                "entity_type": issue.entity_type,
                "message": issue.message,
                "hint": issue.repair_hint,
            })

        suggestions = [
            {
                "action": action,
                "count": len(items),
                "items": items,
                "priority": self._REPAIR_PRIORITIES.get(action, 10),
            }
            for action, items in grouped.items()
        ]
        suggestions.sort(key=lambda s: s["priority"], reverse=True)
        return suggestions

    async def validate_index(
        self,
        index_id: uuid.UUID,
        db: AsyncSession,
    ) -> ValidationReport:
        """Validate a single index and all its associated data."""
        stmt = select(CodeIndex).where(CodeIndex.id == index_id)
        result = await db.execute(stmt)
        idx = result.scalar_one_or_none()

        if idx is None:
            report = ValidationReport(repository_id=uuid.uuid4(), index_id=index_id)
            report.issues.append(ConsistencyIssue(
                category=IssueCategory.INDEX_HEALTH,
                severity=IssueSeverity.CRITICAL,
                message=f"Index {index_id} does not exist",
                entity_id=str(index_id), entity_type="CodeIndex",
                repair_action=RepairAction.MANUAL_REVIEW,
            ))
            report.health_score = 0.0
            return report

        return await self.validate_all(idx.repository_id, db, index_id)

    # ------------------------------------------------------------------ #
    # Health score & summary                                             #
    # ------------------------------------------------------------------ #

    def _compute_health_score(self, report: ValidationReport) -> float:
        score = 100.0
        for issue in report.issues:
            score -= self._SEVERITY_DEDUCTIONS.get(issue.severity.value, 0.0)
        return max(0.0, min(100.0, score))

    def _build_summary(self, report: ValidationReport) -> dict:
        return {
            "health_score": round(report.health_score, 2),
            "total_issues": report.issue_count,
            "by_severity": report.issues_by_severity,
            "by_category": report.issues_by_category,
            "totals": {
                "files": report.total_files,
                "symbols": report.total_symbols,
                "references": report.total_references,
                "calls": report.total_calls,
                "imports": report.total_imports,
                "chunks": report.total_chunks,
            },
        }

    _REPAIR_PRIORITIES: dict[str, int] = {
        RepairAction.DELETE_ORPHAN.value: 90,
        RepairAction.RE_INDEX.value: 80,
        RepairAction.REPARS_FILE.value: 70,
        RepairAction.RE_RESOLVE.value: 60,
        RepairAction.REGENERATE_EMBEDDING.value: 50,
        RepairAction.REMOVE_DUPLICATE.value: 40,
        RepairAction.UPDATE_INDEX.value: 30,
        RepairAction.MANUAL_REVIEW.value: 20,
        RepairAction.SKIP.value: 0,
    }

    # ------------------------------------------------------------------ #
    # Generic query helpers                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _repo_index_conditions(
        repository_id: uuid.UUID,
        index_id: Optional[uuid.UUID],
        model: Type[DeclarativeBase],
    ) -> list:
        """Build common [repository_id, index_id?] filter conditions."""
        conditions = [model.repository_id == repository_id]  # type: ignore[attr-defined]
        if index_id is not None:
            conditions.append(model.index_id == index_id)  # type: ignore[attr-defined]
        return conditions

    async def _query(
        self,
        model: Type[DeclarativeBase],
        repository_id: uuid.UUID,
        index_id: Optional[uuid.UUID],
        db: AsyncSession,
    ) -> Sequence:
        """Generic query: select all rows for a model filtered by repo/index."""
        conds = self._repo_index_conditions(repository_id, index_id, model)
        stmt = select(model).where(and_(*conds)) if conds else select(model)
        result = await db.execute(stmt)
        return result.scalars().all()

    async def _count(
        self,
        model: Type[DeclarativeBase],
        repository_id: uuid.UUID,
        index_id: Optional[uuid.UUID],
        db: AsyncSession,
    ) -> int:
        """Generic count for a model filtered by repo/index."""
        conds = self._repo_index_conditions(repository_id, index_id, model)
        stmt = select(func.count(model.id)).where(and_(*conds))  # type: ignore[attr-defined]
        result = await db.execute(stmt)
        return result.scalar() or 0

    async def _load_id_set(
        self,
        model: Type[DeclarativeBase],
        repository_id: uuid.UUID,
        index_id: Optional[uuid.UUID],
        db: AsyncSession,
    ) -> set[uuid.UUID]:
        """Load all primary-key IDs for a model as a set."""
        conds = self._repo_index_conditions(repository_id, index_id, model)
        stmt = select(model.id).where(and_(*conds))  # type: ignore[attr-defined]
        result = await db.execute(stmt)
        return {row[0] for row in result.all()}

    async def _load_primary_index(
        self,
        repository_id: uuid.UUID,
        index_id: Optional[uuid.UUID],
        db: AsyncSession,
    ) -> Optional[CodeIndex]:
        """Load the most recent index for a repository (optionally filtered)."""
        conds: list = [CodeIndex.repository_id == repository_id]
        if index_id is not None:
            conds.append(CodeIndex.id == index_id)
        stmt = (
            select(CodeIndex)
            .where(and_(*conds))
            .order_by(CodeIndex.created_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def _load_failed_jobs(
        self,
        repository_id: uuid.UUID,
        index_id: Optional[uuid.UUID],
        db: AsyncSession,
    ) -> list[CodeIndexJob]:
        """Load FAILED index jobs, optionally scoped to an index."""
        index_subq = (
            select(CodeIndex.id)
            .where(and_(*self._repo_index_conditions(repository_id, index_id, CodeIndex)))
            .subquery()
        )
        stmt = select(CodeIndexJob).where(
            and_(
                CodeIndexJob.index_id.in_(select(index_subq.c.id)),
                CodeIndexJob.status == JobStatus.FAILED.value,
            )
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())
